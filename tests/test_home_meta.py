"""Link preview tags of the public home page (owner request 2026-10-28: the preview card in WhatsApp/LinkedIn, ID and EN)."""
from monishield.interfaces.api import home_meta

PAGE = '<!doctype html>\n<html lang="id" data-theme="dark">\n<head>\n<title>MoniShield</title>\n</head><body></body></html>'


def test_language_follows_the_link_then_the_client():
    assert home_meta.pick_lang('en', 'id-ID,id;q=0.9') == 'en'           # ?lang= wins
    assert home_meta.pick_lang(None, 'en-US,en;q=0.9,id;q=0.8') == 'en'
    assert home_meta.pick_lang(None, 'id-ID,en;q=0.8') == 'id'
    assert home_meta.pick_lang(None, 'fr-FR,de;q=0.8') == 'id'           # neither: Indonesian
    assert home_meta.pick_lang('xx', None) == 'id' and home_meta.pick_lang(None, '') == 'id'


def test_tags_per_language():
    en = home_meta.render(PAGE, 'en', 'https://monishield.example.com')
    assert '<html lang="en"' in en and '<title>MoniShield · Log &amp; security monitoring</title>' in en
    assert '<meta property="og:image" content="https://monishield.example.com/og-en.png" />' in en
    assert '<meta property="og:url" content="https://monishield.example.com/?lang=en" />' in en
    assert 'og:locale" content="en_US"' in en and 'og:locale:alternate" content="id_ID"' in en and 'summary_large_image' in en
    idn = home_meta.render(PAGE, 'id', 'https://monishield.example.com')
    assert '<html lang="id"' in idn and 'og-id.png' in idn and 'Pantau log dan keamanan layanan' in idn and 'hreflang="en"' in idn
    assert idn.count('</head>') == 1


def test_host_is_escaped():
    out = home_meta.render(PAGE, 'id', 'https://x"><script>alert(1)</script>')
    assert '<script>alert(1)</script>' not in out and '&quot;&gt;&lt;script&gt;' in out
