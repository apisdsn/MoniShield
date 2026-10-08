"""Notification channels (adapter): Telegram Bot API, Discord webhook, SMTP email. Only sends a title + text already
composed and scrubbed of IP addresses by the layer above (monishield/domain/alerts.py `scrub`).
Errors are returned as AlertFail without credentials."""
import json, smtplib, urllib.error, urllib.request   # noqa: F401  (smtplib: tests replace smtplib.SMTP)

from monishield.domain import letters
from monishield.domain.alerts import TELEGRAM_API, AlertFail
from monishield.infrastructure import letter, mailer

TIMEOUT = 15


def _post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'User-Agent': 'MoniShield'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r: return r.status
    except urllib.error.HTTPError as x:
        raise AlertFail(f'rejected HTTP {x.code}') from None
    except (urllib.error.URLError, OSError) as x:
        raise AlertFail(f'unreachable ({type(getattr(x, "reason", x)).__name__})') from None


def send_telegram(ch, title, text):
    _post_json(f"{ch.get('api') or TELEGRAM_API}/bot{ch['bot_token']}/sendMessage",
               dict(chat_id=ch['chat_id'], text=f'{title}\n\n{text}'[:4000], disable_web_page_preview=True))


def send_discord(ch, title, text):
    _post_json(ch['webhook_url'], dict(content=f'**{title}**\n{text}'[:1990], allowed_mentions=dict(parse=[])))


def send_email(ch, title, text):
    """The notification in the MoniShield letter layout (monishield/domain/letters.py), through the mail server settings."""
    lt = letters.notification(ch.get('lang') or 'id', title, text)
    to = ', '.join(x.strip() for x in ch['to'].split(',') if x.strip())
    try: mailer.deliver(ch, letter.message(lt, ch['sender'], to))
    except mailer.MailFail as e: raise AlertFail(e.message) from None


SENDERS = dict(telegram=send_telegram, discord=send_discord, email=send_email)




class Channels:
    """NotificationChannels port: send(channel name, channel settings, title, text). Module functions are looked up at call time
    (tests can replace them)."""
    names = tuple(SENDERS)

    def send(self, name, ch, title, text): return globals()['SENDERS'][name](ch, title, text)
