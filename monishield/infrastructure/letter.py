"""Renders a letter (monishield/domain/letters.py) to an email: HTML with the MoniShield logo + a plain-text part.

Email clients ignore <style> blocks and external images often, so the HTML is a table layout with inline styles, and
the logo is a PNG attached inline (Content-ID) instead of an SVG or a link: Gmail and Outlook show it without asking.
Light colours only: most clients that offer a dark mode invert light emails well, the other way round less so.
"""
import html, os
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

LOGO = os.path.join(os.path.dirname(__file__), 'assets', 'logo.png')
BRAND, INK, MUTED, LINE, PAPER, BG = '#0d9488', '#0f1720', '#5b6876', '#e3e8ee', '#ffffff', '#eef2f5'
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "'SFMono-Regular', Menlo, Consolas, 'Liberation Mono', monospace"


def _e(s): return html.escape(str(s), quote=True)


def render_html(lt, logo_cid='monishield-logo'):
    p = ''.join(f'<p style="margin:0 0 14px;font:15px/1.6 {FONT};color:{INK}">{_e(x)}</p>' for x in lt['paragraphs'])
    code = ''
    if lt.get('code'):
        c = lt['code']
        code = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 18px"><tr><td align="center" '
                f'style="background:#f0fdfa;border:1px solid #99f6e4;border-radius:12px;padding:16px 12px">'
                f'<div style="font:600 12px/1.4 {FONT};color:{MUTED};text-transform:uppercase;letter-spacing:.08em">{_e(c["label"])}</div>'
                f'<div style="font:700 24px/1.4 {MONO};color:{INK};letter-spacing:.12em;margin-top:6px;word-break:break-all">{_e(c["value"])}</div>'
                + (f'<div style="font:13px/1.5 {FONT};color:{MUTED};margin-top:6px">{_e(c["note"])}</div>' if c.get('note') else '')
                + '</td></tr></table>')
    items = ''
    if lt['items']:
        items = (f'<ul style="margin:0 0 16px;padding-left:20px;font:15px/1.6 {FONT};color:{INK}">'
                 + ''.join(f'<li style="margin:0 0 4px">{_e(x)}</li>' for x in lt['items']) + '</ul>')
    btn = ''
    if lt.get('button'):
        b = lt['button']
        btn = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:4px 0 18px"><tr><td style="background:{BRAND};border-radius:10px">'
               f'<a href="{_e(b["url"])}" style="display:inline-block;padding:12px 22px;font:600 15px/1 {FONT};color:#ffffff;text-decoration:none">{_e(b["label"])}</a>'
               '</td></tr></table>')
    notes = ''.join(f'<p style="margin:0 0 10px;font:13px/1.6 {FONT};color:{MUTED}">{_e(x)}</p>' for x in lt['notes'])
    return f"""<!doctype html>
<html lang="{_e(lt['lang'])}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{_e(lt['subject'])}</title></head>
<body style="margin:0;padding:0;background:{BG}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{_e(lt['preheader'])}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG}"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:{PAPER};border:1px solid {LINE};border-radius:16px">
<tr><td style="padding:22px 28px;border-bottom:3px solid {BRAND}">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="padding-right:12px"><img src="cid:{logo_cid}" width="40" height="40" alt="MoniShield" style="display:block;border:0"></td>
<td style="font:700 20px/1 {FONT};color:{INK};letter-spacing:.01em">MoniShield</td></tr></table></td></tr>
<tr><td style="padding:26px 28px 10px">
<h1 style="margin:0 0 16px;font:700 21px/1.3 {FONT};color:{INK}">{_e(lt['title'])}</h1>
{p}{code}{items}{btn}{notes}</td></tr>
<tr><td style="padding:14px 28px 22px;border-top:1px solid {LINE};font:12px/1.6 {FONT};color:{MUTED}">{_e(lt['footer'])}</td></tr>
</table></td></tr></table></body></html>"""


def render_text(lt):
    out = [lt['title'], '=' * len(lt['title']), '']
    out += [x + '\n' for x in lt['paragraphs']]
    if lt.get('code'):
        c = lt['code']
        out += [f"{c['label']}: {c['value']}"] + ([c['note']] if c.get('note') else []) + ['']
    out += [f'- {x}' for x in lt['items']] + ([''] if lt['items'] else [])
    if lt.get('button'): out += [f"{lt['button']['label']}: {lt['button']['url']}", '']
    out += [x + '\n' for x in lt['notes']]
    out += ['--', lt['footer']]
    return '\n'.join(out) + '\n'


def message(lt, sender, to):
    """-> EmailMessage: multipart/alternative (text + HTML), the HTML part related to the inline logo."""
    m = EmailMessage()
    m['Subject'], m['From'], m['To'], m['Date'] = lt['subject'], sender, to if isinstance(to, str) else ', '.join(to), formatdate(localtime=False)
    m['Message-ID'] = make_msgid('monishield')
    m['Auto-Submitted'] = 'auto-generated'   # RFC 3834: out-of-office replies are not sent back
    m.set_content(render_text(lt))
    cid = make_msgid('logo')[1:-1]
    m.add_alternative(render_html(lt, cid), subtype='html')
    with open(LOGO, 'rb') as fh:
        m.get_payload()[1].add_related(fh.read(), maintype='image', subtype='png', cid=f'<{cid}>', filename='monishield.png')
    return m
