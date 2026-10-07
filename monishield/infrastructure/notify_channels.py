"""Saluran notifikasi (adapter): Telegram Bot API, webhook Discord, email SMTP. Hanya mengirim judul + teks yang sudah
disusun dan dibersihkan dari alamat IP oleh lapisan di atasnya (monishield/domain/alerts.py `scrub`).
Galat dikembalikan sebagai AlertFail tanpa kredensial."""
import json, smtplib, ssl, urllib.error, urllib.request
from email.message import EmailMessage

from monishield.domain.alerts import TELEGRAM_API, AlertFail

TIMEOUT = 15


def _post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'User-Agent': 'MoniShield'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r: return r.status
    except urllib.error.HTTPError as x:
        raise AlertFail(f'ditolak HTTP {x.code}') from None
    except (urllib.error.URLError, OSError) as x:
        raise AlertFail(f'tidak terjangkau ({type(getattr(x, "reason", x)).__name__})') from None


def send_telegram(ch, title, text):
    _post_json(f"{ch.get('api') or TELEGRAM_API}/bot{ch['bot_token']}/sendMessage",
               dict(chat_id=ch['chat_id'], text=f'{title}\n\n{text}'[:4000], disable_web_page_preview=True))


def send_discord(ch, title, text):
    _post_json(ch['webhook_url'], dict(content=f'**{title}**\n{text}'[:1990], allowed_mentions=dict(parse=[])))


def send_email(ch, title, text):
    m = EmailMessage()
    m['Subject'], m['From'], m['To'] = title, ch['sender'], ', '.join(x.strip() for x in ch['to'].split(',') if x.strip())
    m.set_content(text)
    try:
        ctx = ssl.create_default_context()
        cls = smtplib.SMTP_SSL if ch['security'] == 'ssl' else smtplib.SMTP
        kw = dict(context=ctx) if ch['security'] == 'ssl' else {}
        with cls(ch['host'], ch['port'], timeout=TIMEOUT, **kw) as s:
            if ch['security'] == 'starttls': s.starttls(context=ctx)
            if ch['username']: s.login(ch['username'], ch['password'])
            s.send_message(m)
    except smtplib.SMTPAuthenticationError:
        raise AlertFail('SMTP menolak nama pengguna / sandi') from None
    except (smtplib.SMTPException, OSError) as x:
        raise AlertFail(f'SMTP gagal ({type(x).__name__})') from None


SENDERS = dict(telegram=send_telegram, discord=send_discord, email=send_email)




class Channels:
    """Port NotificationChannels: send(nama saluran, setelan saluran, judul, teks). Fungsi modul dicari saat dipanggil
    (bisa diganti di uji)."""
    names = tuple(SENDERS)

    def send(self, name, ch, title, text): return globals()['SENDERS'][name](ch, title, text)
