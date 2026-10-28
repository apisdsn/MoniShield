"""Mail server replies (monishield/infrastructure/mailer.py) against a small local SMTP server, and how the notifications
count a message the server received without confirming it (owner report 2026-10-28: the provider logged the daily report,
MoniShield showed "Failed (SMTPServerDisconnected)" and sent it again an hour later)."""
import socket, threading
from email.message import EmailMessage

import pytest

from monishield.application import alert_service
from monishield.domain.alerts import AlertUnconfirmed
from monishield.infrastructure import mailer


def server(after_data):
    """SMTP server on 127.0.0.1 for one connection. after_data: 'ok' (250), 'reject' (550), 'close' (hang up without a
    reply), 'silent' (never greets). -> port."""
    lst = socket.socket()
    lst.bind(('127.0.0.1', 0)); lst.listen(1)

    def run():
        con, _ = lst.accept()
        f = con.makefile('rb')
        say = lambda s: con.sendall(s.encode() + b'\r\n')
        try:
            if after_data == 'silent':
                f.readline(); return   # waits until the client gives up
            say('220 test ESMTP')
            while line := f.readline():
                cmd = line.decode().strip().upper()
                if cmd.startswith(('EHLO', 'HELO')): say('250 test')
                elif cmd.startswith(('MAIL', 'RCPT', 'RSET', 'NOOP')): say('250 OK')
                elif cmd == 'DATA':
                    say('354 go on')
                    while f.readline() not in (b'.\r\n', b''): pass
                    if after_data == 'close': return
                    say('250 queued' if after_data == 'ok' else '550 rejected')
                elif cmd == 'QUIT': say('221 bye'); return
        finally:
            con.close(); lst.close()

    threading.Thread(target=run, daemon=True).start()
    return lst.getsockname()[1]


def settings(port): return dict(host='127.0.0.1', port=port, security='none', username='', password='', sender='a@example.com')


def letter():
    m = EmailMessage()
    m['From'], m['To'], m['Subject'] = 'a@example.com', 'b@example.com', 'Uji'
    m.set_content('isi')
    return m


def test_message_accepted():
    mailer.deliver(settings(server('ok')), letter())


def test_connection_closed_after_the_message_is_unconfirmed_not_failed():
    with pytest.raises(mailer.MailUnconfirmed) as e: mailer.deliver(settings(server('close')), letter())
    assert e.value.code == 'mail_unconfirmed' and "check the mail provider's log" in e.value.message


def test_rejected_after_the_message_is_a_failure():
    with pytest.raises(mailer.MailFail) as e: mailer.deliver(settings(server('reject')), letter())
    assert not isinstance(e.value, mailer.MailUnconfirmed)
    assert e.value.message == 'The mail server could not be reached or refused the message (SMTPDataError).'


def test_no_answer_names_the_wait(monkeypatch):
    monkeypatch.setattr(mailer, 'TIMEOUT', 1)
    with pytest.raises(mailer.MailFail) as e: mailer.deliver(settings(server('silent')), letter())
    assert not isinstance(e.value, mailer.MailUnconfirmed)
    assert e.value.message.startswith('The mail server did not answer within 1 seconds (')


def test_mailer_send_returns_the_note_instead_of_failing(monkeypatch):
    """Codes (password reset, email change) are not cancelled when the server only failed to confirm."""
    class Cfg:
        smtp_host, smtp_security, smtp_username, smtp_password, smtp_from, dashboard_url = '127.0.0.1', 'none', '', '', 'a@example.com', ''
    Cfg.smtp_port = server('close')
    lt = dict(subject='Uji', preheader='', heading='Uji', paragraphs=['isi'], lang='id')
    monkeypatch.setattr(mailer.render, 'message', lambda lt, sender, to, logo='': letter())
    assert "check the mail provider's log" in mailer.Mailer(Cfg).send(lt, 'b@example.com')
    Cfg.smtp_port = server('ok')
    assert mailer.Mailer(Cfg).send(lt, 'b@example.com') is None


def test_unconfirmed_notification_counts_as_sent_and_is_not_sent_again():
    class Auth:
        def __init__(self): self.rows = []
        def alert_seen(self, key): return any(r[0] == key and r[2] for r in self.rows)
        def alert_add(self, key, event, channel, ok, summary=None, error=None): self.rows.append((key, channel, ok, error))

    class Channels:
        calls = 0
        def send(self, name, ch, title, text):
            Channels.calls += 1
            raise AlertUnconfirmed('The mail server received the message but closed the connection before confirming it; '
                                   "check the mail provider's log.")

    class Ctx: auth, channels = Auth(), Channels()

    cfg = dict(lang='id', channels=dict(email=dict(enabled=True)))
    notes = {}
    out = alert_service.deliver(Ctx, cfg, 'summary:2026-10-27', 'summary', 'Ringkasan', 'isi', notes=notes)
    assert out == dict(email=None) and 'closed the connection' in notes['email']
    key, channel, ok, error = Ctx.auth.rows[0]
    assert ok is True and 'closed the connection' in error   # history: sent, with the note
    assert alert_service.deliver(Ctx, cfg, 'summary:2026-10-27', 'summary', 'Ringkasan', 'isi') == {}   # not sent again
    assert Channels.calls == 1


def test_every_email_links_the_logo(monkeypatch):
    """Notifications link the logo like the codes do (an attached logo showed as a broken box after relays rewrote it)."""
    from monishield.infrastructure import notify_channels
    box = []
    monkeypatch.setattr(mailer, 'deliver', lambda s, m: box.append(m))
    ch = dict(host='smtp.example.com', port=465, security='ssl', username='', password='', sender='a@example.com', to='b@example.com', lang='id')
    notify_channels.send_email(dict(ch, dashboard_url='https://monishield.example.com/'), 'Ringkasan', '🟢 Status: **AMAN**')
    notify_channels.send_email(dict(ch, dashboard_url='http://10.0.0.5:8000'), 'Ringkasan', '🟢 Status: **AMAN**')
    linked, drawn = (m.get_body(('html',)).get_content() for m in box)
    assert 'src="https://monishield.example.com/mail-logo.png"' in linked
    assert '<img' not in drawn and '>M</td>' in drawn   # no https address: the mark is drawn in HTML
    assert all([p.get_content_type() for p in m.walk()] == ['multipart/alternative', 'text/plain', 'text/html'] for m in box)   # never attached
