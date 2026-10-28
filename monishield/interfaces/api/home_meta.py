"""Link preview of the public home page (owner request 2026-10-28): the title, description and image that WhatsApp,
LinkedIn, Telegram or X show when the address is shared. Their crawlers do not run JavaScript, so the server writes the
tags into index.html for "/". The language follows `?lang=en|id` (a shared link can pick it), else the first language
the client asks for, else Indonesian. The texts are UI copy, so they are kept in both languages here."""
import html

TEXT = {
    'id': dict(title='MoniShield · Monitoring log & keamanan', locale='id_ID',
               description='Pantau log dan keamanan layanan dari satu dashboard: deteksi serangan, akar masalah error, '
                           'peta asal request, dan laporan harian.',
               alt='MoniShield: pantau log dan keamanan layanan dari satu dashboard'),
    'en': dict(title='MoniShield · Log & security monitoring', locale='en_US',
               description="Watch your services' logs and security from one dashboard: attack detection, the cause of errors, "
                           'a request origin map, and a daily report.',
               alt='MoniShield: watch your service logs and security from one dashboard'),
}


def pick_lang(query_lang, accept_language):
    """`?lang=` wins; else the first language of Accept-Language that is id or en; else id."""
    if query_lang in TEXT: return query_lang
    for part in (accept_language or '').split(','):
        tag = part.split(';')[0].strip().lower()[:2]
        if tag in TEXT: return tag
    return 'id'


def render(index_html, lang, base, source_url=''):
    """index.html of the web app -> the same page with the preview tags for `lang`. base = public address without a
    trailing slash (https://monishield.example.com). source_url: the "Source code" link of the page (S4_SOURCE_URL), read by
    Landing.svelte from the monishield:source tag; empty = no link."""
    t, e = TEXT[lang], lambda s: html.escape(s, quote=True)
    url = f'{base}/' + ('?lang=en' if lang == 'en' else '')
    other = 'en' if lang == 'id' else 'id'
    tags = '\n'.join([
        f'<meta name="description" content="{e(t["description"])}" />',
        f'<link rel="canonical" href="{e(url)}" />',
        f'<link rel="alternate" hreflang="id" href="{e(base)}/" />',
        f'<link rel="alternate" hreflang="en" href="{e(base)}/?lang=en" />',
        '<meta property="og:type" content="website" />',
        '<meta property="og:site_name" content="MoniShield" />',
        f'<meta property="og:title" content="{e(t["title"])}" />',
        f'<meta property="og:description" content="{e(t["description"])}" />',
        f'<meta property="og:url" content="{e(url)}" />',
        f'<meta property="og:image" content="{e(base)}/og-{lang}.png" />',
        '<meta property="og:image:width" content="1200" />',
        '<meta property="og:image:height" content="630" />',
        f'<meta property="og:image:alt" content="{e(t["alt"])}" />',
        f'<meta property="og:locale" content="{t["locale"]}" />',
        f'<meta property="og:locale:alternate" content="{TEXT[other]["locale"]}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
    ] + ([f'<meta name="monishield:source" content="{e(source_url)}" />'] if source_url else []))
    out = index_html.replace('<html lang="id"', f'<html lang="{lang}"', 1)
    out = out.replace('<title>MoniShield</title>', f'<title>{e(t["title"])}</title>', 1)
    return out.replace('</head>', tags + '\n</head>', 1)
