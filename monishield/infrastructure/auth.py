"""Accounts, sessions, roles, and audit (TRD §2.6, §8.2–§8.3).

Owner decision 2026-10-06: account database = **PostgreSQL** via an **ORM** (SQLAlchemy), session token = **JWT**.
DuckDB stays for log analytics only and must be rebuildable without losing accounts (TRD K11).

- ORM: models below; database URL from `S4_AUTH_DATABASE_URL`. Empty = a SQLite file via the same ORM
  (only for tests and local runs without a database server).
- JWT (HS256, `S4_JWT_SECRET`) carries `sub` (user id) and `sid` (session id). Signature and expiry are
  checked first, **then the session row is checked in the database**: so logout, password reset, deactivation,
  and role changes take effect immediately, which pure JWT without server-side state cannot do.
- Passwords: per-account salted scrypt (standard library). Passwords and tokens are never stored or logged.

Two roles: 'admin' and 'user'. Per-module restrictions are deferred (TRD §8.3).
"""
import contextlib, datetime, hmac, re, secrets, threading, time

import jwt
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, create_engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from monishield.domain import accounts
from monishield.domain.accounts import PASSWORD_MAX, ROLES, AuthError, check_password, check_username, hash_password, job_token_ok   # noqa: F401

MAX_FAILED, LOCK_MINUTES = 5, 15
JOB_STATUS = {'berjalan': 'running', 'selesai': 'done', 'gagal': 'failed', 'coba': 'dry_run'}   # old -> current
IP_MAX_FAILED, IP_WINDOW_S = 20, 15 * 60   # per-IP limiter, in memory
JWT_ALG, JWT_ISS, JWT_SECRET_MIN = 'HS256', 'monishield', 32


# ------------------------------------------------------------------ model ORM
class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'app_user'   # 'user' is a keyword in PostgreSQL
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    password_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    password_salt: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    hash_params: Mapped[str] = mapped_column(String(16), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(32))
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)


class Session(Base):
    __tablename__ = 'app_session'
    sid: Mapped[str] = mapped_column(String(32), primary_key=True)   # the `sid` claim in the JWT
    user_id: Mapped[int] = mapped_column(ForeignKey('app_user.user_id', ondelete='CASCADE'), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(200))


class AuditLog(Base):
    __tablename__ = 'audit_log'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))


class ImportJob(Base):
    __tablename__ = 'import_job'   # filled by Stage 19 (S3 import)
    job_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requested_by: Mapped[str | None] = mapped_column(String(40))
    bucket: Mapped[str | None] = mapped_column(String(80))
    prefix: Mapped[str | None] = mapped_column(String(300))
    folder: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    files: Mapped[int | None] = mapped_column(Integer)
    skipped: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)


class AppSetting(Base):
    """Settings an admin changes from the UI (e.g. automatic S3 sync). JSON values; not secrets."""
    __tablename__ = 'app_setting'
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(40))


class AlertLog(Base):
    """Notifications sent / failed (monishield/alerts.py). `key` prevents duplicate sends for the same event."""
    __tablename__ = 'alert_log'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


def now(): return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)   # all times UTC
def iso(dt): return dt.isoformat(sep=' ') if dt else None


def redact_url(url):
    """Database URL without the password, for printing."""
    return re.sub(r'(://[^:/@]+):[^@]*@', r'\1:***@', url or '')


class Auth:
    def __init__(self, url, jwt_secret=None, idle_minutes=60, max_hours=12):
        """url = SQLAlchemy URL (postgresql+psycopg://… or sqlite:///…). jwt_secret is required for login/session verification."""
        if jwt_secret is not None and len(jwt_secret) < JWT_SECRET_MIN:
            raise ValueError(f'S4_JWT_SECRET must be at least {JWT_SECRET_MIN} characters')
        self.url, self.secret, self.idle, self.max_hours = url, jwt_secret, idle_minutes, max_hours
        sqlite = url.startswith('sqlite')
        self.engine = create_engine(url, pool_pre_ping=True, **(dict(connect_args={'check_same_thread': False}) if sqlite else dict(pool_size=5, max_overflow=5)))
        self._Session = sessionmaker(self.engine, expire_on_commit=False)
        self._ip_fail, self._lock = {}, threading.Lock()
        # dummy salt: verification is still computed for nonexistent users, so response time does not leak whether a user exists
        self._dummy_salt = secrets.token_bytes(16)
        Base.metadata.create_all(self.engine)   # ponytail: no migration tool; add Alembic when the account schema first changes
        with self.engine.begin() as c:   # import job status was Indonesian before 2026-10-08
            for a, b in JOB_STATUS.items(): c.execute(update(ImportJob).where(ImportJob.status == a).values(status=b))

    @contextlib.contextmanager
    def _tx(self):
        """One ORM transaction. AuthError = deliberate rejection: failure counters and audit are STILL saved."""
        s = self._Session()
        try:
            yield s
            s.commit()
        except AuthError:
            s.commit(); raise
        except BaseException:
            s.rollback(); raise
        finally:
            s.close()

    def close(self): self.engine.dispose()

    # ---------------------------------------------------------------- audit
    def _audit(self, s, action, user=None, detail=None, ip=None):
        """Trail of actions that change access or data. Never contains passwords or tokens."""
        uid = user.get('user_id') if isinstance(user, dict) else getattr(user, 'user_id', None)
        name = user.get('username') if isinstance(user, dict) else getattr(user, 'username', None)
        s.add(AuditLog(at=now(), user_id=uid, username=name, action=action, detail=detail, ip=ip))

    def audit(self, action, user=None, detail=None, ip=None):
        with self._tx() as s: self._audit(s, action, user, detail, ip)

    def audit_list(self, limit=50, offset=0):
        with self._tx() as s:
            total = s.scalar(select(func.count()).select_from(AuditLog))
            rows = [dict(id=r.id, at=iso(r.at), username=r.username, action=r.action, detail=r.detail, ip=r.ip)
                    for r in s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset))]
        return total, rows

    # ---------------------------------------------------------------- import_job (Stage 19)
    @staticmethod
    def _job(j):
        return dict(job_id=j.job_id, requested_by=j.requested_by, bucket=j.bucket, prefix=j.prefix, folder=j.folder, status=j.status,
                    bytes=j.bytes, files=j.files, skipped=j.skipped, message=j.message, started_at=iso(j.started_at), finished_at=iso(j.finished_at))

    def job_create(self, by, bucket, prefix, folder, status='running'):
        with self._tx() as s:
            j = ImportJob(requested_by=(by or '')[:40] or None, bucket=bucket, prefix=prefix, folder=folder, status=status, started_at=now())
            s.add(j); s.flush()
            return j.job_id

    def job_finish(self, job_id, status, bytes=None, files=None, skipped=None, message=None):
        with self._tx() as s:
            j = s.get(ImportJob, job_id)
            if j: j.status, j.bytes, j.files, j.skipped, j.message, j.finished_at = status, bytes, files, skipped, (message or '')[:2000] or None, now()

    def job_get(self, job_id):
        with self._tx() as s:
            j = s.get(ImportJob, job_id)
            return self._job(j) if j else None

    def job_list(self, limit=20):
        with self._tx() as s: return [self._job(j) for j in s.scalars(select(ImportJob).order_by(ImportJob.job_id.desc()).limit(limit))]

    # ---------------------------------------------------------------- settings from the UI
    def setting_get(self, key):
        """-> value (json.loads result) or None if never saved."""
        import json
        with self._tx() as s:
            r = s.get(AppSetting, key)
            return dict(value=json.loads(r.value), updated_at=iso(r.updated_at), updated_by=r.updated_by) if r else None

    def setting_set(self, key, value, by=None):
        import json
        with self._tx() as s:
            r = s.get(AppSetting, key)
            if r is None: r = AppSetting(key=key); s.add(r)
            r.value, r.updated_at, r.updated_by = json.dumps(value, ensure_ascii=False), now(), (by or '')[:40] or None

    def setting_delete(self, key):
        """Delete an old setting (moved to .env; settings.migrate)."""
        with self._tx() as s:
            r = s.get(AppSetting, key)
            if r is not None: s.delete(r)

    # ---------------------------------------------------------------- notification history
    def alert_seen(self, key):
        """Is there already a SUCCESSFUL send for this key (to any channel)?"""
        with self._tx() as s:
            return s.scalar(select(func.count()).select_from(AlertLog).where(AlertLog.key == key, AlertLog.ok.is_(True))) > 0

    def alert_add(self, key, event, channel, ok, summary=None, error=None):
        with self._tx() as s:
            s.add(AlertLog(at=now(), key=key[:120], event=event[:40], channel=channel[:20], ok=bool(ok), summary=(summary or '')[:500] or None,
                           error=(error or '')[:500] or None))

    def alert_list(self, limit=30):
        with self._tx() as s:
            return [dict(at=iso(a.at), event=a.event, channel=a.channel, ok=a.ok, summary=a.summary, error=a.error)
                    for a in s.scalars(select(AlertLog).order_by(AlertLog.id.desc()).limit(limit))]

    # ---------------------------------------------------------------- user
    @staticmethod
    def _public(u):
        return dict(user_id=u.user_id, username=u.username, display_name=u.display_name, role=u.role, active=bool(u.active),
                    must_change_password=bool(u.must_change_password), created_at=iso(u.created_at), last_login_at=iso(u.last_login_at),
                    locked=bool(u.locked_until and u.locked_until > now()))

    def _get(self, s, user_id, lock=False):
        q = select(User).where(User.user_id == user_id)
        u = s.scalar(q.with_for_update() if lock else q)
        if not u: raise AuthError('not_found', 'User not found.', 404)
        return u

    def count_users(self):
        with self._tx() as s: return s.scalar(select(func.count()).select_from(User))

    def list_users(self):
        with self._tx() as s: return [self._public(u) for u in s.scalars(select(User).order_by(User.username))]

    def get_user(self, user_id):
        with self._tx() as s: return self._public(self._get(s, user_id))

    def create_user(self, username, display_name, role, password, by=None, ip=None, must_change=True):
        username = check_username(username.strip().lower() if isinstance(username, str) else username)
        if role not in ROLES: raise AuthError('invalid_role', "Role must be 'admin' or 'user'.")
        display_name = (display_name or username).strip()[:80] or username
        h, salt = hash_password(check_password(password, username))
        with self._tx() as s:
            u = User(username=username, display_name=display_name, role=role, password_hash=h, password_salt=salt, hash_params=':'.join(map(str, accounts.SCRYPT)),
                     must_change_password=must_change, active=True, failed_logins=0, created_at=now(), created_by=by['username'] if by else None)
            s.add(u)
            try: s.flush()
            except IntegrityError:
                s.rollback(); raise AuthError('username_taken', 'Username already taken.', 409) from None
            self._audit(s, 'user.create', by, f'{username} ({role})', ip)
            return self._public(u)

    @staticmethod
    def _admins_left(s, excluding):
        return s.scalar(select(func.count()).select_from(User).where(User.role == 'admin', User.active.is_(True), User.user_id != excluding))

    def update_user(self, user_id, by, ip=None, display_name=None, role=None, active=None):
        with self._tx() as s:
            u = self._get(s, user_id, lock=True)
            if role is not None and role not in ROLES: raise AuthError('invalid_role', "Role must be 'admin' or 'user'.")
            loses_admin = u.role == 'admin' and u.active and ((role is not None and role != 'admin') or active is False)
            if loses_admin and not self._admins_left(s, user_id):
                raise AuthError('last_admin', 'The last admin cannot be demoted or deactivated.', 409)
            changes = []
            if display_name is not None:
                u.display_name = display_name.strip()[:80] or u.username; changes.append('name')
            if role is not None and role != u.role:
                changes.append(f'role {u.role} -> {role}'); u.role = role
            if active is not None and bool(active) != bool(u.active):
                u.active, u.failed_logins, u.locked_until = bool(active), 0, None
                changes.append('activated' if active else 'deactivated')
                if not active: s.execute(delete(Session).where(Session.user_id == user_id))
            if changes: self._audit(s, 'user.update', by, f"{u.username}: {', '.join(changes)}", ip)
            s.flush()
            return self._public(u)

    def delete_user(self, user_id, by, ip=None):
        with self._tx() as s:
            u = self._get(s, user_id, lock=True)
            if by and by['user_id'] == user_id: raise AuthError('self_delete', 'You cannot delete your own account.', 409)
            if u.role == 'admin' and u.active and not self._admins_left(s, user_id):
                raise AuthError('last_admin', 'The last admin cannot be deleted.', 409)
            s.execute(delete(Session).where(Session.user_id == user_id))   # explicit: SQLite does not always run ON DELETE CASCADE
            self._audit(s, 'user.delete', by, u.username, ip)
            s.delete(u)

    @staticmethod
    def _set_password(u, password, must_change):
        u.password_hash, u.password_salt = hash_password(password)
        u.hash_params, u.must_change_password, u.failed_logins, u.locked_until = ':'.join(map(str, accounts.SCRYPT)), must_change, 0, None

    def reset_password(self, user_id, by, ip=None):
        """New temporary password (returned ONCE); all the user's sessions are revoked; must be changed at login."""
        temp = secrets.token_urlsafe(12)
        with self._tx() as s:
            u = self._get(s, user_id, lock=True)
            self._set_password(u, temp, True)
            s.execute(delete(Session).where(Session.user_id == user_id))
            self._audit(s, 'user.reset_password', by, u.username, ip)
        return temp

    def change_password(self, user, old, new, keep_token=None, ip=None):
        keep = (self._claims(keep_token, verify_exp=False) or {}).get('sid') if keep_token else None
        with self._tx() as s:
            u = s.scalar(select(User).where(User.user_id == user['user_id']).with_for_update())
            if not u or not isinstance(old, str) or not self._verify(u, old): raise AuthError('wrong_password', 'Current password is wrong.', 403)
            check_password(new, u.username)
            if hmac.compare_digest(old, new): raise AuthError('invalid_password', 'The new password must differ from the current password.')
            self._set_password(u, new, False)
            s.execute(delete(Session).where(Session.user_id == u.user_id, Session.sid != (keep or '')))   # other sessions revoked
            self._audit(s, 'user.change_password', user, None, ip)

    # ---------------------------------------------------------------- JWT
    def _encode(self, user_id, sid, issued, expires):
        if not self.secret: raise RuntimeError('S4_JWT_SECRET not set')
        aware = lambda d: d.replace(tzinfo=datetime.timezone.utc)
        return jwt.encode(dict(iss=JWT_ISS, sub=str(user_id), sid=sid, iat=aware(issued), exp=aware(expires)), self.secret, algorithm=JWT_ALG)

    def _claims(self, token, verify_exp=True):
        """Valid JWT claims, or None. Only HS256 with the server secret is accepted (alg 'none' and others are rejected)."""
        if not token or not self.secret or not isinstance(token, str): return None
        try:
            return jwt.decode(token, self.secret, algorithms=[JWT_ALG], issuer=JWT_ISS,
                              options=dict(require=['exp', 'iat', 'sub', 'sid', 'iss'], verify_exp=verify_exp))
        except jwt.InvalidTokenError:
            return None

    # ---------------------------------------------------------------- login & session
    @staticmethod
    def _verify(u, password):
        n, r, p = map(int, u.hash_params.split(':'))
        return hmac.compare_digest(hash_password(password, u.password_salt, (n, r, p))[0], u.password_hash)

    def _ip_blocked(self, ip):
        with self._lock:
            t = [x for x in self._ip_fail.get(ip, []) if x > time.time() - IP_WINDOW_S]
            self._ip_fail[ip] = t
            return len(t) >= IP_MAX_FAILED

    def _ip_failed(self, ip):
        with self._lock: self._ip_fail.setdefault(ip, []).append(time.time())

    def login(self, username, password, ip=None, user_agent=None):
        """Returns (JWT, user). Same error message for 'no such user' and 'wrong password'."""
        salah = AuthError('invalid_credentials', 'Wrong username or password.', 401)
        if self._ip_blocked(ip): raise AuthError('too_many_attempts', 'Too many attempts. Try again in a few minutes.', 429)
        username = username.strip().lower() if isinstance(username, str) else ''
        if not isinstance(password, str) or len(password) > PASSWORD_MAX: password = ''
        with self._tx() as s:
            u = s.scalar(select(User).where(User.username == username).with_for_update())
            if not u:
                hash_password(password, self._dummy_salt)          # same cost as for a real user
                self._ip_failed(ip); self._audit(s, 'login.fail', None, username[:40], ip)
                raise salah
            if u.locked_until and u.locked_until > now():
                self._audit(s, 'login.locked', u, None, ip)
                raise AuthError('too_many_attempts', f'Too many attempts. Try again in {LOCK_MINUTES} minutes.', 429)
            if not self._verify(u, password) or not u.active:
                gagal = u.failed_logins + 1
                kunci = gagal >= MAX_FAILED
                u.failed_logins, u.locked_until = (0, now() + datetime.timedelta(minutes=LOCK_MINUTES)) if kunci else (gagal, None)
                self._ip_failed(ip); self._audit(s, 'login.fail', u, 'account locked' if kunci else None, ip)
                raise salah
            t = now(); habis = t + datetime.timedelta(hours=self.max_hours)
            sid = secrets.token_urlsafe(16)
            s.add(Session(sid=sid, user_id=u.user_id, created_at=t, last_seen_at=t, expires_at=habis, ip=ip, user_agent=(user_agent or '')[:200]))
            u.failed_logins, u.locked_until, u.last_login_at = 0, None, t
            s.execute(delete(Session).where(Session.expires_at < t))   # drop expired sessions
            self._audit(s, 'login.ok', u, None, ip)
            s.flush()
            return self._encode(u.user_id, sid, t, habis), self._public(u)

    def session_user(self, token):
        """The session's user, or None. JWT signature + expiry, THEN the session row in the database (no cache)."""
        c = self._claims(token)
        if not c: return None
        t = now()
        with self._tx() as s:
            row = s.execute(select(Session, User).join(User, User.user_id == Session.user_id).where(Session.sid == c['sid'])).first()
            if not row or str(row[1].user_id) != c['sub']: return None
            ses, u = row
            if ses.expires_at <= t or ses.last_seen_at + datetime.timedelta(minutes=self.idle) <= t or not u.active:
                s.delete(ses); return None
            if (t - ses.last_seen_at).total_seconds() >= 60: ses.last_seen_at = t   # record activity at most once a minute
            return self._public(u)

    def logout(self, token, user=None, ip=None):
        c = self._claims(token, verify_exp=False)
        with self._tx() as s:
            if c: s.execute(delete(Session).where(Session.sid == c['sid']))
            if user: self._audit(s, 'logout', user, None, ip)

    def bootstrap_admin(self, username, password):
        """Create the first admin ONLY when there are no users yet. The password must be changed at first login."""
        if not username or not password or self.count_users(): return None
        return self.create_user(username, 'Administrator', 'admin', password)
