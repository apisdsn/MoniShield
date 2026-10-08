"""Mail server (Mailer port adapter): sends letters (monishield/domain/letters.py, rendered by letter.py) through the
SMTP server of the Configuration page → Mail server (SMTP) (S4_SMTP_HOST, S4_SMTP_PORT, S4_SMTP_SECURITY, S4_SMTP_USERNAME,
SMTP_PASSWORD, S4_SMTP_FROM). Used by the password reset, the email notification channel and the test email.
Errors never contain the password."""
import smtplib, ssl

from monishield.domain.errors import Fail
from monishield.infrastructure import letter as render

TIMEOUT = 15


class MailFail(Fail):
    def __init__(self, message, code='mail_failed', status=502): super().__init__(code, message, status)

    def __str__(self): return self.message


def settings(cfg):
    return dict(host=cfg.smtp_host, port=cfg.smtp_port, security=cfg.smtp_security, username=cfg.smtp_username,
                password=cfg.smtp_password, sender=cfg.smtp_from)


def ready(s): return bool(s.get('host') and s.get('port') and s.get('sender'))


def deliver(s, msg):
    """Send one EmailMessage with the SMTP settings `s` (dict from settings())."""
    try:
        ctx = ssl.create_default_context()
        cls = smtplib.SMTP_SSL if s['security'] == 'ssl' else smtplib.SMTP
        kw = dict(context=ctx) if s['security'] == 'ssl' else {}
        with cls(s['host'], int(s['port']), timeout=TIMEOUT, **kw) as c:
            if s['security'] == 'starttls': c.starttls(context=ctx)
            if s.get('username'): c.login(s['username'], s['password'])
            c.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise MailFail('The mail server rejected the username or password.') from None
    except smtplib.SMTPRecipientsRefused:
        raise MailFail('The mail server refused the recipient address.') from None
    except (smtplib.SMTPException, OSError) as x:
        port, sec = int(s['port']), s['security']
        if (sec == 'ssl' and port == 587) or (sec == 'starttls' and port == 465):
            raise MailFail(f'Port {port} does not match the security setting: use 465 with SSL/TLS or 587 with STARTTLS ({type(x).__name__}).') from None
        raise MailFail(f'The mail server could not be reached or refused the message ({type(x).__name__}).') from None


class Mailer:
    """Mailer port: ready() and send(letter, to). Settings are read at call time (the Configuration page changes them live)."""

    def __init__(self, cfg): self.cfg = cfg

    def ready(self): return ready(settings(self.cfg))

    def send(self, lt, to):
        s = settings(self.cfg)
        if not ready(s): raise MailFail('The mail server (SMTP) is not set up: fill in Configuration → Mail server.', 'mail_not_configured', 503)
        deliver(s, render.message(lt, s['sender'], to, render.logo_url(self.cfg.dashboard_url)))
