"""Renders a letter (monishield/domain/letters.py) to an email: HTML + a plain-text part.

Email clients ignore <style> blocks, so the HTML is a table layout with inline styles. The logo is the PNG linked from
the dashboard (`logo_url`, https://<S4_DASHBOARD_URL>/mail-logo.png). It is never attached: relays that rewrite
messages for open tracking (SumoPod, kirim.email) break attached Content-ID images, which is why the daily reports
showed a broken box while the codes (already linked) did not (owner report 2026-10-28). Without a public https
dashboard address the brand mark is drawn in HTML instead. Light colours only: most clients that offer a dark mode
invert light emails well, the other way round less so.
"""
import html, os, re
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

LOGO = os.path.join(os.path.dirname(__file__), 'assets', 'logo.png')   # served at /mail-logo.png
BRAND, INK, MUTED, LINE, PAPER, BG, SOFT = '#0f766e', '#0f1720', '#5b6876', '#e3e8ee', '#ffffff', '#eef2f5', '#f6f8fa'
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "'SFMono-Regular', Menlo, Consolas, 'Liberation Mono', monospace"
STATUS = dict(ok=('#f0fdf4', '#bbf7d0', '#166534', '#16a34a'), check=('#fffbeb', '#fde68a', '#92400e', '#d97706'),
              crit=('#fef2f2', '#fecaca', '#991b1b', '#dc2626'))   # background, border, text, dot
_NUM = re.compile(r'(\d+)\. (.+)')
_DELTA = re.compile(r'^(.*?)\s*\(([▲▼≈][^)]*)\)$')


def _e(s): return html.escape(str(s), quote=True)


def _mark(logo=''):
    """Logo + name. logo = public PNG address; empty = a teal square with "M" drawn in HTML."""
    icon = (f'<td width="34" height="34" valign="middle" style="width:34px;height:34px"><img src="{_e(logo)}" width="34" height="34" alt="" '
            f'style="display:block;width:34px;height:34px;border:0"></td>' if logo else
            f'<td width="34" height="34" align="center" valign="middle" style="width:34px;height:34px;background:{BRAND};border-radius:9px;'
            f'font:800 18px/34px {FONT};color:#ffffff">M</td>')
    return (f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>{icon}'
            f'<td style="padding-left:10px;font:700 18px/1 {FONT};color:{INK};letter-spacing:.01em">MoniShield</td></tr></table>')


def _status(st):
    bg, border, ink, dot = STATUS.get(st.get('level'), STATUS['check'])
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 22px"><tr>'
            f'<td style="background:{bg};border:1px solid {border};border-radius:12px;padding:12px 16px;font:600 15px/1.4 {FONT};color:{ink}">'
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:5px;background:{dot};margin-right:8px;vertical-align:middle"></span>'
            f'<span style="vertical-align:middle">{_e(st["text"])}</span></td></tr></table>')


def _value(v):
    """'251,280 (▲ 56%)' -> value with the change as a small grey note."""
    m = _DELTA.match(v)
    if not m: return f'<span style="font-weight:600;color:{INK}">{_e(v)}</span>'
    return (f'<span style="font-weight:600;color:{INK}">{_e(m.group(1))}</span>'
            f'<span style="display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;background:{SOFT};border:1px solid {LINE};'
            f'font:600 12px/1.5 {FONT};color:{MUTED};white-space:nowrap">{_e(m.group(2))}</span>')


def _rows(items):
    """'Label: value' items as a two-column table; lines without a label span both columns."""
    out = []
    for i, x in enumerate(items):
        top = '' if i == 0 else f'border-top:1px solid {LINE};'
        label, sep, value = x.partition(': ')
        if sep:
            keep = 'white-space:nowrap;' if len(label) <= 16 else ''   # "S3 2026-10-27" stays on one line on a phone
            out.append(f'<tr><td style="{top}{keep}padding:9px 12px 9px 0;font:14px/1.45 {FONT};color:{MUTED};vertical-align:top">{_e(label)}</td>'
                       f'<td align="right" style="{top}padding:9px 0;font:14px/1.45 {FONT};color:{INK};text-align:right;vertical-align:top">{_value(value)}</td></tr>')
        else:
            out.append(f'<tr><td colspan="2" style="{top}padding:9px 0;font:14px/1.45 {FONT};color:{INK}">{_e(x)}</td></tr>')
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(out)}</table>'


def _numbered(items, level):
    ink = STATUS.get(level, STATUS['check'])[3]
    rows = []
    for x in items:
        n, text = _NUM.fullmatch(x).groups()
        rows.append(f'<tr><td width="34" valign="top" style="padding:0 0 10px">'
                    f'<div style="width:24px;height:24px;border-radius:12px;background:{ink};color:#ffffff;font:700 12px/24px {FONT};text-align:center">{_e(n)}</div></td>'
                    f'<td valign="top" style="padding:2px 0 10px;font:14px/1.5 {FONT};color:{INK}">{_e(text)}</td></tr>')
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(rows)}</table>'


def _bullets(items):
    return (f'<ul style="margin:0;padding-left:20px;font:15px/1.6 {FONT};color:{INK}">'
            + ''.join(f'<li style="margin:0 0 4px">{_e(x)}</li>' for x in items) + '</ul>')


def _section(sec, level):
    items = sec['items']
    if items and all(_NUM.fullmatch(x) for x in items): body = _numbered(items, level)
    elif items and sum(': ' in x for x in items) * 2 >= len(items): body = _rows(items)
    else: body = _bullets(items)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px"><tr><td>'
            f'<div style="font:700 12px/1.4 {FONT};color:{MUTED};text-transform:uppercase;letter-spacing:.08em;margin:0 0 6px">{_e(sec["title"])}</div>'
            f'<div style="background:{PAPER};border:1px solid {LINE};border-radius:12px;padding:6px 16px">{body}</div>'
            '</td></tr></table>')


def render_html(lt, logo=''):
    st = lt.get('status')
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
    items = f'<div style="margin:0 0 16px">{_bullets(lt["items"])}</div>' if lt['items'] else ''
    secs = ''.join(_section(sec, (st or {}).get('level')) for sec in lt.get('sections') or [])
    btn = ''
    if lt.get('button'):
        b = lt['button']
        btn = (f'<table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin:8px auto 22px"><tr>'
               f'<td align="center" style="background:{BRAND};border-radius:10px">'
               f'<a href="{_e(b["url"])}" style="display:inline-block;padding:13px 28px;font:600 15px/1 {FONT};color:#ffffff;text-decoration:none">{_e(b["label"])}</a>'
               '</td></tr></table>')
    notes = ''.join(f'<p style="margin:0 0 10px;font:13px/1.6 {FONT};color:{MUTED}">{_e(x)}</p>' for x in lt['notes'])
    return f"""<!doctype html>
<html lang="{_e(lt['lang'])}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{_e(lt['subject'])}</title></head>
<body style="margin:0;padding:0;background:{BG}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{_e(lt['preheader'])}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG}"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px">
<tr><td style="padding:0 4px 14px">{_mark(logo)}</td></tr>
<tr><td style="background:{PAPER};border:1px solid {LINE};border-top:4px solid {BRAND};border-radius:14px;padding:28px 28px 8px">
<h1 style="margin:0 0 18px;font:700 22px/1.3 {FONT};color:{INK}">{_e(lt['title'])}</h1>
{_status(st) if st else ''}{p}{code}{items}{secs}{btn}{notes}</td></tr>
<tr><td align="center" style="padding:16px 12px 0;font:12px/1.6 {FONT};color:{MUTED}">{_e(lt['footer'])}</td></tr>
</table></td></tr></table></body></html>"""


def render_text(lt):
    out = [lt['title'], '=' * len(lt['title']), '']
    if lt.get('status'): out += [lt['status']['text'], '']
    out += [x + '\n' for x in lt['paragraphs']]
    if lt.get('code'):
        c = lt['code']
        out += [f"{c['label']}: {c['value']}"] + ([c['note']] if c.get('note') else []) + ['']
    out += [f'- {x}' for x in lt['items']] + ([''] if lt['items'] else [])
    for sec in lt.get('sections') or []: out += [sec['title']] + [f'- {x}' for x in sec['items']] + ['']
    if lt.get('button'): out += [f"{lt['button']['label']}: {lt['button']['url']}", '']
    out += [x + '\n' for x in lt['notes']]
    out += ['--', lt['footer']]
    return '\n'.join(out) + '\n'


def logo_url(dashboard_url):
    """Public logo address for letters, or '' when the dashboard has no https address (the mark is then drawn in HTML)."""
    u = (dashboard_url or '').strip().rstrip('/')
    return f'{u}/mail-logo.png' if u.startswith('https://') else ''


def message(lt, sender, to, logo=''):
    """-> EmailMessage: multipart/alternative (text + HTML). logo = public logo address (logo_url), or '' for the HTML mark."""
    m = EmailMessage()
    m['Subject'], m['From'], m['To'], m['Date'] = lt['subject'], sender, to if isinstance(to, str) else ', '.join(to), formatdate(localtime=False)
    m['Message-ID'] = make_msgid('monishield')
    m['Auto-Submitted'] = 'auto-generated'   # RFC 3834: out-of-office replies are not sent back
    m.set_content(render_text(lt))
    m.add_alternative(render_html(lt, logo), subtype='html')
    return m
