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
        hello='Halo {name},', footer='Email ini dikirim otomatis oleh MoniShield. Mohon tidak membalas email ini.',
        ignore='Jika Anda tidak merasa meminta pengaturan ulang kata sandi, abaikan email ini. Kata sandi Anda saat ini tetap berlaku.',
        reset_subject='Kata sandi sementara akun MoniShield Anda', reset_title='Kata sandi sementara',
        reset_intro='Kami menerima permintaan untuk mengatur ulang kata sandi akun MoniShield Anda ({username}). Gunakan kata sandi sementara berikut untuk masuk.',
        reset_label='Kata sandi sementara', reset_note='Berlaku selama {minutes} menit dan hanya dapat digunakan satu kali.',
        reset_steps=['Buka halaman masuk MoniShield.', 'Masuk menggunakan nama pengguna {username} dan kata sandi sementara di atas.',
                     'Buat kata sandi baru saat diminta.'],
        open='Buka MoniShield',
        otp_subject='Kode verifikasi MoniShield Anda', otp_title='Kode verifikasi',
        otp_intro='Gunakan kode berikut untuk {purpose}.', otp_label='Kode verifikasi',
        otp_note='Berlaku selama {minutes} menit. Jangan bagikan kode ini kepada siapa pun, termasuk pihak yang mengaku dari MoniShield.',
        otp_ignore='Jika Anda tidak sedang melakukan permintaan ini, abaikan email ini.',
        test_subject='Uji pengiriman email MoniShield', test_title='Server email berhasil terhubung',
        test_intro='Pengaturan server email (SMTP) MoniShield sudah benar. Email berikutnya, seperti kata sandi sementara dan notifikasi, akan dikirim melalui server ini.',
        notif_preheader='Notifikasi dari MoniShield',
        change_old='mengonfirmasi bahwa Anda ingin mengganti email akun MoniShield Anda ({username}) menjadi {new}',
        change_new='memverifikasi alamat email baru akun MoniShield Anda ({username})',
        changed_subject='Email akun MoniShield Anda telah diganti', changed_title='Email akun diganti',
        changed_intro='Email akun MoniShield Anda ({username}) baru saja diganti menjadi {new}. Email berikutnya, termasuk kata sandi sementara, dikirim ke alamat baru tersebut.',
        changed_note='Jika Anda tidak melakukan perubahan ini, segera hubungi admin MoniShield.'),
    en=dict(
        hello='Hello {name},', footer='This email was sent automatically by MoniShield. Please do not reply.',
        ignore='If you did not request a password reset, you can ignore this email. Your current password still works.',
        reset_subject='Your MoniShield temporary password', reset_title='Temporary password',
        reset_intro='We received a request to reset the password of your MoniShield account ({username}). Use the temporary password below to sign in.',
        reset_label='Temporary password', reset_note='Valid for {minutes} minutes and can be used only once.',
        reset_steps=['Open the MoniShield sign-in page.', 'Sign in with the username {username} and the temporary password above.',
                     'Choose a new password when asked.'],
        open='Open MoniShield',
        otp_subject='Your MoniShield verification code', otp_title='Verification code',
        otp_intro='Use the code below to {purpose}.', otp_label='Verification code',
        otp_note='Valid for {minutes} minutes. Never share this code with anyone, including people who claim to be from MoniShield.',
        otp_ignore='If you are not making this request right now, you can ignore this email.',
        test_subject='MoniShield email test', test_title='Mail server connected',
        test_intro='The MoniShield mail server (SMTP) settings work. Future emails, such as temporary passwords and notifications, will be sent through this server.',
        notif_preheader='Notification from MoniShield',
        change_old='confirm that you want to change the email of your MoniShield account ({username}) to {new}',
        change_new='verify the new email address of your MoniShield account ({username})',
        changed_subject='The email of your MoniShield account was changed', changed_title='Account email changed',
        changed_intro='The email of your MoniShield account ({username}) was just changed to {new}. Future emails, including temporary passwords, go to that address.',
        changed_note='If you did not make this change, contact your MoniShield admin right away.'),
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


def email_change_code(lang, name, username, value, minutes, to_old, new_email):
    """The code for an own email change: one letter to the OLD address (proves the owner agrees), one to the NEW one
    (proves the address works). Built on the OTP letter."""
    t = _t(lang)
    purpose = (t['change_old'] if to_old else t['change_new']).format(username=username, new=new_email)
    return otp(lang, name or username, value, minutes, purpose)


def email_changed(lang, name, username, new_masked, url=''):
    """Security notice to the OLD address after the change."""
    t = _t(lang)
    return letter(lang, t['changed_subject'], t['changed_title'], t['changed_note'],
                  paragraphs=[t['hello'].format(name=name or username), t['changed_intro'].format(username=username, new=new_masked)],
                  button=_button(t, url), notes=[t['changed_note']])
