"""Own account email (owner request 2026-10-08). A signed-in user may change the email of their own account, but only
with three proofs, so that a stolen session alone cannot point the account at another address (and then use "forgot
password" to take it over):
  1. the current password,
  2. a code sent to the CURRENT email (skipped when the account has none yet),
  3. a code sent to the NEW email (the address works and belongs to the user).
Codes: 6 digits, valid 10 minutes, 5 wrong tries (monishield/domain/accounts.py). After the change the old address gets
a notice. Every step is audited (`email.change_start`, `email.change_fail`, `email.change`, `email.change_cancel`).
Admins can still set any user's email in Manage users.
"""
from monishield.domain import accounts, letters
from monishield.domain.errors import Fail


class EmailChanges:
    def __init__(self, ctx): self.ctx = ctx

    def view(self, user):
        return dict(email=user.get('email'), pending=self.ctx.auth.email_change_pending(user), mail_ready=self.ctx.mailer.ready())

    def start(self, user, password, new_email, ip=None, lang='id'):
        ctx = self.ctx
        if not ctx.mailer.ready():
            raise Fail('mail_not_configured', 'Email cannot be changed here yet: the mail server is not set up. Ask an admin.', 503)
        r = ctx.auth.email_change_start(user, password, new_email, ip)
        lang = lang if lang in ('id', 'en') else 'id'
        u = r['user']
        try:
            if r['old_code']:
                ctx.mailer.send(letters.email_change_code(lang, u['display_name'], u['username'], r['old_code'], accounts.CODE_MINUTES, True, r['new_email']), r['old_email'])
            ctx.mailer.send(letters.email_change_code(lang, u['display_name'], u['username'], r['new_code'], accounts.CODE_MINUTES, False, r['new_email']), r['new_email'])
        except Fail as e:
            ctx.auth.email_change_cancel(user, ip, f'email not sent: {e.message}'[:300])
            raise
        return dict(self.view(user), sent_old=accounts.mask_email(r['old_email']), sent_new=r['new_email'])

    def confirm(self, user, old_code, new_code, ip=None, lang='id'):
        ctx = self.ctx
        u, old = ctx.auth.email_change_confirm(user, old_code, new_code, ip)
        if old:   # notice to the previous address; a failure here does not undo the verified change
            try: ctx.mailer.send(letters.email_changed(lang if lang in ('id', 'en') else 'id', u['display_name'], u['username'],
                                                       accounts.mask_email(u['email']), ctx.cfg.dashboard_url), old)
            except Fail: pass
        return dict(email=u['email'], pending=None, mail_ready=ctx.mailer.ready())

    def cancel(self, user, ip=None):
        self.ctx.auth.email_change_cancel(user, ip, 'cancelled by the user')
        return self.view(user)
