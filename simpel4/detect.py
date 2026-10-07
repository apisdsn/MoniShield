"""Deteksi serangan dengan aturan OWASP Core Rule Set (CRS), kategori CAPEC (TRD §4.6, Tahap 21).

Cara "di skrip": aturan CRS (simpel4/crs_rules.json, diolah tools/ambil_crs.py dari rilis yang dikunci) dicocokkan ke
bagian request yang ADA di log nginx: URI, argumen query, nama berkas, User-Agent. Body POST, header lain, dan cookie
tidak tercatat, jadi tidak diperiksa; ini bukan pengganti WAF.

Seperti ModSecurity: nilai dicocokkan sebagai BYTE (UTF-8 dibaca latin-1, sehingga \\xHH di pola = satu byte), regex
memakai DOTALL, transformasi `t:` diterapkan berurutan, skor anomali = jumlah skor keparahan aturan yang kena
(CRITICAL 5, ERROR 4, WARNING 3, NOTICE 2), dan sebuah request dianggap serangan bila skornya mencapai ambang anomali
masuk bawaan CRS (5). Tingkat paranoia bawaan 1 (ASUMSI S1); aturan dengan tingkat lebih tinggi tidak dipakai.
Hasil per request: daftar ID aturan yang kena, CAPEC (yang jumlah skornya terbesar; seri -> ID aturan terkecil), keluarga
serangan CRS, keparahan tampilan 1–3, skor. Keterbatasan: aturan libinjection (942100 SQLi, 941100 XSS) tidak bisa dijalankan
di Python, jadi tautologi SQL klasik (' OR 1=1) baru tertangkap di tingkat paranoia 2.
"""
import base64, functools, html, json, os, posixpath, re
from urllib.parse import unquote_to_bytes

HERE = os.path.dirname(os.path.abspath(__file__))
SCORE = {'CRITICAL': 5, 'ERROR': 4, 'WARNING': 3, 'NOTICE': 2}
LEVEL = {'CRITICAL': 3, 'ERROR': 2, 'WARNING': 2, 'NOTICE': 1}   # tag tampilan 3 tingkat (TRD §4.6)
THRESHOLD = 5
PARANOIA = 1   # diatur dari konfigurasi (attack_paranoia) lewat use(cfg); ASUMSI S1: 1


def _load():
    with open(os.path.join(HERE, 'crs_rules.json'), encoding='utf-8') as fh: return json.load(fh)


DATA = _load()
CAPEC = json.load(open(os.path.join(HERE, 'capec.json'), encoding='utf-8'))
VERSION = f"crs-{DATA['version']}"


def use(cfg):
    """Pakai tingkat paranoia dari konfigurasi untuk proses ini."""
    global PARANOIA
    PARANOIA = max(1, min(4, int(cfg.attack_paranoia)))


def version_key(): return f'{VERSION}-pl{PARANOIA}'   # disimpan per folder; berubah -> agregat CRS diturunkan ulang


# ---------------------------------------------------------------- transformasi (semua bekerja pada "byte" latin-1)
def _b(s): return s.encode('utf-8', 'surrogateescape').decode('latin-1')
def _pct(m): return chr(int(m.group(1), 16))


def url_decode(s, uni=False):
    s = s.replace('+', ' ')
    if uni: s = re.sub(r'%u([0-9a-fA-F]{4})', lambda m: _b(chr(int(m.group(1), 16))), s)
    return re.sub(r'%([0-9a-fA-F]{2})', _pct, s)


def js_decode(s):
    s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: _b(chr(int(m.group(1), 16))), s)
    s = re.sub(r'\\x([0-9a-fA-F]{2})', _pct, s)
    s = re.sub(r'\\([0-7]{1,3})', lambda m: chr(int(m.group(1), 8) & 0xff), s)
    return re.sub(r'\\([abfnrtv\\\'"?])', lambda m: {'a': '\a', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t', 'v': '\v'}.get(m.group(1), m.group(1)), s)


def css_decode(s): return re.sub(r'\\([0-9a-fA-F]{1,6})\s?', lambda m: chr(int(m.group(1), 16) & 0xff), re.sub(r'\\(?=[^0-9a-fA-F\n])', '', s))


def cmd_line(s):
    s = re.sub(r'[\\"\'^]', '', s)
    s = re.sub(r'[,;]', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r' (?=[/(])', '', s)
    return s.lower()


def normalize_path(s, win=False):
    if win: s = s.replace('\\', '/')
    if not s: return s
    lead, trail = s.startswith('/'), s.endswith('/')
    n = posixpath.normpath(s)
    if n == '.': n = ''
    if not lead and n.startswith('/'): n = n[1:]
    return n + ('/' if trail and not n.endswith('/') else '')


def _b64(s):
    try: return base64.b64decode(s + '=' * (-len(s) % 4), validate=False).decode('latin-1')
    except Exception: return s   # noqa: BLE001  bukan base64: nilai apa adanya, seperti ModSecurity


T = {
    'none': lambda s: s, 'lowercase': str.lower, 'urlDecode': url_decode, 'urlDecodeUni': lambda s: url_decode(s, True),
    'htmlEntityDecode': lambda s: _b(html.unescape(s.encode('latin-1').decode('utf-8', 'surrogateescape'))),
    'jsDecode': js_decode, 'cssDecode': css_decode, 'escapeSeqDecode': js_decode,
    'removeNulls': lambda s: s.replace('\x00', ''), 'replaceNulls': lambda s: s.replace('\x00', ' '),
    'replaceComments': lambda s: re.sub(r'/\*.*?(\*/|$)', ' ', s, flags=re.S),
    'removeComments': lambda s: re.sub(r'/\*.*?(\*/|$)|--.*$|#.*$', '', s, flags=re.S | re.M),
    'removeCommentsChar': lambda s: re.sub(r'/\*|\*/|--|#', '', s),
    'compressWhitespace': lambda s: re.sub(r'\s+', ' ', s), 'removeWhitespace': lambda s: re.sub(r'\s+', '', s),
    'normalizePath': normalize_path, 'normalisePath': normalize_path,
    'normalizePathWin': lambda s: normalize_path(s, True), 'normalisePathWin': lambda s: normalize_path(s, True),
    'cmdLine': cmd_line, 'utf8toUnicode': lambda s: s, 'base64Decode': _b64, 'base64DecodeExt': _b64,
    'hexDecode': lambda s: bytes.fromhex(s).decode('latin-1') if re.fullmatch(r'(?:[0-9a-fA-F]{2})*', s) else s,
    'sqlHexDecode': lambda s: re.sub(r'0x((?:[0-9a-fA-F]{2})+)', lambda m: bytes.fromhex(m.group(1)).decode('latin-1'), s),
    'trim': str.strip, 'trimLeft': str.lstrip, 'trimRight': str.rstrip,
}


@functools.lru_cache(maxsize=400_000)
def transform(value, tfs):
    for t in tfs: value = T[t](value)
    return value


# ---------------------------------------------------------------- aturan
def _trie_regex(words):
    """Kata-kata -> satu regex berbentuk trie (awalan bersama digabung): jauh lebih cepat daripada alternasi datar."""
    trie = {}
    for w in words:
        node = trie
        for ch in w: node = node.setdefault(ch, {})
        node[''] = True
    def emit(node):
        alts, end = [], '' in node
        for ch in sorted(k for k in node if k):
            alts.append(re.escape(ch) + emit(node[ch]))
        if not alts: return ''
        body = alts[0] if len(alts) == 1 and not end else '(?:' + '|'.join(alts) + ')'
        return body + ('?' if end and alts else '')
    return emit(trie)


def _matcher(r):
    op, arg = r['op'], r['arg']
    if op == 'rx': return re.compile(arg, re.S).search
    if op == 'pm':   # @pm: tanpa beda huruf besar/kecil; kata sudah huruf kecil di crs_rules.json
        rx = re.compile(_trie_regex(arg), re.S).search
        return lambda v: rx(v.lower())
    a = arg.lower() if isinstance(arg, str) else arg
    return {'contains': lambda v: arg in v, 'beginsWith': lambda v: v.startswith(arg), 'endsWith': lambda v: v.endswith(arg),
            'streq': lambda v: v == arg, 'within': lambda v: v in arg, 'containsWord': lambda v: re.search(rf'\b{re.escape(arg)}\b', v)}.get(op, lambda v: a in v)


@functools.lru_cache(maxsize=8)
def rules(pl=1):
    """Aturan aktif untuk tingkat paranoia pl: [(id, keparahan, capec, keluarga, sasaran, transformasi, pencocok)]."""
    out = []
    for r in DATA['rules']:
        if r['pl'] is None or r['pl'] > pl: continue
        tfs = tuple(t for t in r['transforms'] if t != 'none') if 'none' in r['transforms'] else tuple(r['transforms'])
        out.append((r['id'], r['severity'], r['capec'], r['attack'], tuple(r['targets']), tfs, _matcher(r)))
    return out


# ---------------------------------------------------------------- bagian request yang ada di log
def _args(query):
    names, values = [], []
    for part in query.split('&'):
        if not part: continue
        k, _, v = part.partition('=')
        names.append(url_decode(k, True)); values.append(url_decode(v, True))
    return names, values


def parts(method, path, ua):
    p = _b(path)
    uri_path, _, query = p.partition('?')
    names, values = _args(query)
    return {'uri': [p], 'filename': [uri_path], 'basename': [uri_path.rsplit('/', 1)[-1]], 'query': [query] if query else [],
            'args': values, 'arg_names': names, 'ua': [_b(ua)] if ua and ua != '-' else [], 'line': [f'{method} {p} HTTP/1.1']}


def _hits(values, active):
    hit = []
    for rid, sev, capec, attack, targets, tfs, match in active:
        if any(match(transform(v, tfs)) for t in targets for v in values.get(t, ())): hit.append((rid, sev, capec, attack))
    return hit


@functools.lru_cache(maxsize=200_000)
def _path_hits(method, path, pl):
    v = parts(method, path, '')
    return tuple(_hits(v, [r for r in rules(pl) if set(r[4]) - {'ua'}]))


@functools.lru_cache(maxsize=50_000)
def _ua_hits(ua, pl):
    return tuple(_hits({'ua': [_b(ua)] if ua and ua != '-' else []}, [r for r in rules(pl) if 'ua' in r[4]]))


def classify(method, path, ua, pl=1):
    """-> dict(rules, capec, attack, severity, score) bila skor >= ambang, selain itu None. Hasil per bagian di-cache."""
    hits = {h[0]: h for h in _path_hits(method, path, pl) + _ua_hits(ua, pl)}
    if not hits: return None
    score = sum(SCORE.get(h[1], 0) for h in hits.values())
    if score < THRESHOLD: return None
    # kategori = CAPEC dengan jumlah skor terbesar di antara aturan yang kena (seri -> ID aturan terkecil); keluarga ikut aturan itu
    per = {}
    for rid, sev, capec, attack in hits.values():
        t = per.setdefault(capec, [0, rid, attack]); t[0] += SCORE.get(sev, 0)
        if rid < t[1]: t[1], t[2] = rid, attack
    capec, (_, _, attack) = min(per.items(), key=lambda kv: (-kv[1][0], kv[1][1]))
    return dict(rules=sorted(hits), capec=capec, attack=attack, severity=max(LEVEL.get(h[1], 1) for h in hits.values()), score=score)


MSG = {r['id']: r['msg'] for r in DATA['rules']}


def rule_msgs(ids):
    """{id: pesan aturan CRS (bahasa Inggris, apa adanya dari rilis)} untuk ID yang diberikan."""
    return {str(i): MSG[i] for i in sorted(set(ids)) if i in MSG}


def capec_name(cid, lang='id'):
    return CAPEC['capec'].get(str(cid), {}).get(lang, f'CAPEC-{cid}')
