"""Forgot password (owner request 2026-10-08): the sign-in page asks for a username or email; the account's email receives a
unique temporary password (letters, digits and special characters; monishield/domain/accounts.py `temp_password`) in
the MoniShield letter (monishield/domain/letters.py). Signing in with it forces a new password right away.

Safety:
- The answer is the same whether or not the account exists or has an email (no account discovery).
- The old password keeps working until the temporary one is used, and any successful sign-in cancels it: asking for
  resets cannot lock anyone out. One temporary password per account per minute, and per address at most
  IP_MAX requests per IP_WINDOW_S.
- Sending happens in a background thread, so the response time does not reveal whether an email was sent.
- Every request is in the audit log (`password.forgot`, `password.reset_used`), never the password itself.
"""
import threading, time

from monishield.domain import letters
from monishield.domain.errors import Fail

IP_MAX, IP_WINDOW_S = 5, 15 * 60


class PasswordResets:
    def __init__(self, ctx):
        self.ctx, self._lock, self._ip, self._threads = ctx, threading.Lock(), {}, []

    def available(self):
        cfg = self.ctx.cfg
        return bool(cfg.password_reset and self.ctx.mailer.ready())

    def _limited(self, ip):
        with self._lock:
            t = [x for x in self._ip.get(ip, []) if x > time.time() - IP_WINDOW_S]
            if len(t) >= IP_MAX: self._ip[ip] = t; return True
            self._ip[ip] = t + [time.time()]
            return False

    def forgot(self, login, ip=None, lang='id'):
        cfg = self.ctx.cfg
        if not cfg.password_reset: raise Fail('reset_disabled', 'Password reset by email is turned off. Contact an admin.', 403)
        if not self.ctx.mailer.ready():
            raise Fail('mail_not_configured', 'Password reset by email is not available: the mail server is not set up. Contact an admin.', 503)
        if not isinstance(login, str) or not login.strip(): raise Fail('invalid_parameter', 'Enter your username or email address.', 400)
        if self._limited(ip): raise Fail('too_many_attempts', 'Too many requests. Try again in a few minutes.', 429)
        r = self.ctx.auth.request_reset(login, cfg.password_reset_minutes, ip)
        if r:
            th = threading.Thread(target=self._send, args=(r[0], r[1], ip, lang), name='password-reset', daemon=True)
            th.start(); self._threads.append(th)
        return dict(sent=True, minutes=cfg.password_reset_minutes)

    def _send(self, user, temp, ip, lang):
        cfg = self.ctx.cfg
        lt = letters.password_reset(lang if lang in ('id', 'en') else 'id', user['display_name'], user['username'], temp, cfg.password_reset_minutes, cfg.dashboard_url)
        try: self.ctx.mailer.send(lt, user['email'])
        except Exception as e:   # noqa: BLE001  the temporary password is withdrawn and the reason audited
            self.ctx.auth.cancel_reset(user['user_id'], getattr(e, 'message', type(e).__name__), ip)

    def wait(self, timeout=30):
        """Tests: wait for the emails in flight."""
        for th in self._threads: th.join(timeout)
        self._threads = [t for t in self._threads if t.is_alive()]
