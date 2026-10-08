"""Email letters (pure; owner request 2026-10-08): ONE layout for every email MoniShield sends, so a password reset, an
OTP code, a notification or a test message all look the same (MoniShield logo, title, text, optional code box,
optional list, optional button, footer). This module only decides the CONTENT, in two languages; the HTML/text
rendering with the logo is monishield/infrastructure/letter.py and sending is monishield/infrastructure/mailer.py.

A letter is a plain dict:
  subject, preheader (the grey preview line in mail clients), title, lang,
  paragraphs [text], code {label, value, note} | None, items [text], button {label, url} | None, notes [text]
"""

T = dict(
    id=dict(
        hello='Halo {name},', footer='Email otomatis dari MoniShield. Jangan membalas email ini.',
        ignore='Jika Anda tidak meminta ini, abaikan email ini. Sandi lama Anda tetap berlaku.',
        reset_subject='Sandi sementara MoniShield', reset_title='Sandi sementara',
        reset_intro='Ada permintaan atur ulang sandi untuk akun {username}. Masuk dengan sandi sementara di bawah ini, lalu buat sandi baru.',
        reset_label='Sandi sementara', reset_note='Berlaku {minutes} menit dan hanya bisa dipakai sekali.',
        reset_steps=['Buka halaman masuk MoniShield.', 'Masuk dengan nama pengguna {username} dan sandi sementara ini.', 'Buat sandi baru Anda sendiri.'],
        open='Buka MoniShield',
        otp_subject='Kode verifikasi MoniShield', otp_title='Kode verifikasi',
        otp_intro='Gunakan kode di bawah ini untuk {purpose}.', otp_label='Kode', otp_note='Berlaku {minutes} menit. Jangan berikan kode ini kepada siapa pun.',
        otp_ignore='Jika Anda tidak sedang melakukan ini, abaikan email ini.',
        test_subject='Email uji MoniShield', test_title='Server email tersambung',
        test_intro='Pengaturan server email (SMTP) MoniShield sudah benar. Email berikutnya, seperti sandi sementara dan notifikasi, akan dikirim dengan cara ini.',
        notif_preheader='Notifikasi MoniShield'),
    en=dict(
        hello='Hello {name},', footer='Automatic email from MoniShield. Please do not reply.',
        ignore='If you did not ask for this, ignore this email. Your old password still works.',
        reset_subject='Your MoniShield temporary password', reset_title='Temporary password',
        reset_intro='Someone asked to reset the password of the account {username}. Sign in with the temporary password below, then choose a new password.',
        reset_label='Temporary password', reset_note='Valid for {minutes} minutes and can be used once.',
        reset_steps=['Open the MoniShield sign-in page.', 'Sign in with the username {username} and this temporary password.', 'Choose your own new password.'],
        open='Open MoniShield',
        otp_subject='Your MoniShield verification code', otp_title='Verification code',
        otp_intro='Use the code below to {purpose}.', otp_label='Code', otp_note='Valid for {minutes} minutes. Never share this code.',
        otp_ignore='If you are not doing this right now, ignore this email.',
        test_subject='MoniShield test email', test_title='Mail server connected',
        test_intro='The MoniShield mail server (SMTP) settings work. Future emails, such as temporary passwords and notifications, are sent this way.',
        notif_preheader='MoniShield notification'),
)


def _t(lang): return T[lang if lang in T else 'id']


def letter(lang, subject, title, preheader='', paragraphs=(), code=None, items=(), button=None, notes=()):
    return dict(lang=lang if lang in T else 'id', subject=subject, title=title, preheader=preheader or title, paragraphs=list(paragraphs),
                code=code, items=list(items), button=button, notes=list(notes), footer=_t(lang)['footer'])


def _button(t, url): return dict(label=t['open'], url=url) if url else None


def password_reset(lang, name, username, temp, minutes, url=''):
    t = _t(lang)
    return letter(lang, t['reset_subject'], t['reset_title'], t['reset_note'].format(minutes=minutes),
                  paragraphs=[t['hello'].format(name=name or username), t['reset_intro'].format(username=username)],
                  code=dict(label=t['reset_label'], value=temp, note=t['reset_note'].format(minutes=minutes)),
                  items=[s.format(username=username) for s in t['reset_steps']], button=_button(t, url), notes=[t['ignore']])


def otp(lang, name, code, minutes, purpose, url=''):
    """One-time code letter (ready for e-mail OTP; `purpose` completes the sentence "Use the code below to …")."""
    t = _t(lang)
    return letter(lang, t['otp_subject'], t['otp_title'], t['otp_note'].format(minutes=minutes),
                  paragraphs=[t['hello'].format(name=name), t['otp_intro'].format(purpose=purpose)],
                  code=dict(label=t['otp_label'], value=code, note=t['otp_note'].format(minutes=minutes)), button=_button(t, url), notes=[t['otp_ignore']])


def notification(lang, title, text, url=''):
    """A notification (monishield/domain/alerts.py texts): lines starting with "• " become a list, the rest paragraphs;
    an "Open: <url>" / "Buka: <url>" line becomes the button."""
    t, paras, items = _t(lang), [], []
    for line in str(text).split('\n'):
        line = line.strip()
        if not line: continue
        head, sep, rest = line.partition(': ')
        if sep and head in (T['id']['open'].split()[0], T['en']['open'].split()[0]) and rest.startswith(('http://', 'https://')):
            url = url or rest; continue
        if line.startswith('• '): items.append(line[2:])
        else: paras.append(line)
    return letter(lang, title, title, t['notif_preheader'], paragraphs=paras, items=items, button=_button(t, url))


def smtp_test(lang, url=''):
    t = _t(lang)
    return letter(lang, t['test_subject'], t['test_title'], paragraphs=[t['test_intro']], button=_button(t, url))
