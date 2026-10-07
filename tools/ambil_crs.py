"""Ambil aturan OWASP Core Rule Set (CRS) versi TERKUNCI dan simpan sebagai monishield/domain/crs_rules.json (TRD §4.6, Tahap 21).

    py tools/ambil_crs.py            # unduh (git clone tag), olah, tulis monishield/domain/crs_rules.json + CRS-LICENSE.txt
    py tools/ambil_crs.py --check    # olah ulang dan bandingkan: keluar 1 bila berkas di repo berbeda
    py tools/ambil_crs.py --src DIR  # pakai salinan CRS yang sudah ada (tanpa jaringan)

Yang diambil: berkas REQUEST-913, 930, 931, 932, 933, 934, 941, 942, 944; hanya aturan yang sasarannya bagian request
yang ADA di log nginx (URI, argumen query, nama berkas, User-Agent). Aturan yang tidak bisa dipakai apa adanya
(operator libinjection, transformasi yang tidak didukung, pola yang tidak diterima mesin regex Python, rantai aturan,
sasaran yang tidak ada di log) DICATAT di bagian `skipped` beserta alasannya, tidak diubah diam-diam.
Saat dashboard berjalan tidak ada unduhan: berkas JSON ikut repo.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

VERSION = 'v4.30.0'
COMMIT = 'e03a4f6dabc7a30ebd8c52c97d28a154f590a48f'   # hasil `git rev-parse` tag di atas; diperiksa tiap unduhan
REPO = 'https://github.com/coreruleset/coreruleset.git'
FILES = ('913', '930', '931', '932', '933', '934', '941', '942', '944')
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(V2, 'monishield', 'domain', 'crs_rules.json')
LICENSE_OUT = os.path.join(V2, 'monishield', 'domain', 'CRS-LICENSE.txt')

# variabel ModSecurity -> bagian request yang ada di log nginx (selebihnya tidak tercatat)
TARGETS = {'REQUEST_URI': 'uri', 'REQUEST_URI_RAW': 'uri', 'REQUEST_FILENAME': 'filename', 'REQUEST_BASENAME': 'basename',
           'QUERY_STRING': 'query', 'ARGS': 'args', 'ARGS_GET': 'args', 'ARGS_NAMES': 'arg_names', 'ARGS_GET_NAMES': 'arg_names',
           'REQUEST_HEADERS:User-Agent': 'ua', 'REQUEST_HEADERS': 'ua', 'REQUEST_LINE': 'line'}
TRANSFORMS = {'none', 'urlDecode', 'urlDecodeUni', 'lowercase', 'htmlEntityDecode', 'jsDecode', 'cssDecode', 'removeNulls', 'replaceNulls',
              'replaceComments', 'removeComments', 'compressWhitespace', 'removeWhitespace', 'normalizePath', 'normalisePath', 'normalizePathWin',
              'normalisePathWin', 'cmdLine', 'utf8toUnicode', 'base64Decode', 'base64DecodeExt', 'hexDecode', 'sqlHexDecode', 'escapeSeqDecode',
              'trim', 'trimLeft', 'trimRight', 'removeCommentsChar'}
OPERATORS = {'rx', 'pm', 'pmFromFile', 'pmf', 'contains', 'beginsWith', 'endsWith', 'streq', 'within', 'containsWord'}


def fetch(dest):
    subprocess.run(['git', '-c', 'advice.detachedHead=false', 'clone', '-q', '--depth', '1', '--branch', VERSION, REPO, dest], check=True)
    head = subprocess.run(['git', '-C', dest, 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if head != COMMIT: raise SystemExit(f'commit {VERSION} = {head}, bukan {COMMIT} yang dikunci: periksa sebelum memperbarui')


def statements(text):
    """Pernyataan SecRule/SecAction utuh (baris lanjutan '\\' digabung), komentar dibuang."""
    out, cur = [], ''
    for line in text.splitlines():
        s = line.rstrip()
        if not cur and (not s.strip() or s.lstrip().startswith('#')): continue
        if s.endswith('\\'): cur += s[:-1].strip() + ' '; continue
        cur += s.strip(); out.append(cur); cur = ''
    return out


def split_args(st):
    """'SecRule A "B" "C"' -> ['SecRule', 'A', 'B', 'C'] (kutip ganda dengan \\" di dalamnya)."""
    toks, i = [], 0
    while i < len(st):
        if st[i].isspace(): i += 1; continue
        if st[i] == '"':
            j, buf = i + 1, []
            while j < len(st) and st[j] != '"':
                if st[j] == '\\' and j + 1 < len(st) and st[j + 1] == '"': buf.append('"'); j += 2; continue
                buf.append(st[j]); j += 1
            toks.append(''.join(buf)); i = j + 1
        else:
            j = i
            while j < len(st) and not st[j].isspace(): j += 1
            toks.append(st[i:j]); i = j
    return toks


def actions(s):
    """'id:1,t:none,msg:'a,b',tag:'x'' -> [(kunci, nilai)]."""
    out = []
    for m in re.finditer(r"\s*([A-Za-z_]+)(?::('(?:[^'\\]|\\.)*'|[^,]*))?\s*(?:,|$)", s):
        if not m.group(1): continue
        v = m.group(2)
        out.append((m.group(1), v[1:-1] if v and v.startswith("'") else v))
    return out


def load_data(src, name):
    with open(os.path.join(src, 'rules', name), encoding='utf-8') as fh:
        return [l.strip() for l in fh if l.strip() and not l.lstrip().startswith('#')]


def convert(rule_op, arg, src):
    """-> (op, isi) atau melempar ValueError(alasan)."""
    op = rule_op
    if op in ('pmFromFile', 'pmf'): return 'pm', sorted({w.lower() for f in arg.split() for w in load_data(src, f)})
    if op == 'pm': return 'pm', sorted({w.lower() for w in arg.split()})
    if op == 'rx':
        # ModSecurity mencocokkan BYTE: escape \x{HH} (<= 0xff) = satu byte. Detektor mencocokkan byte UTF-8 yang dibaca latin-1,
        # jadi \x{HH} -> \xHH bermakna sama. Yang lebih dari satu byte, kelas POSIX, dan \Q..\E tidak punya padanan aman.
        if re.search(r'\\x\{[0-9a-fA-F]{3,}\}', arg): raise ValueError('escape \\x{...} lebih dari satu byte')
        arg = re.sub(r'\\x\{([0-9a-fA-F]{1,2})\}', lambda m: '\\x' + m.group(1).zfill(2), arg)
        if re.search(r'\[\[:\w+:\]\]|\\Q|\\E', arg): raise ValueError('sintaks PCRE yang tidak didukung re Python')
        try: re.compile(arg)
        except re.error as e: raise ValueError(f'pola ditolak re Python: {e}') from None
        return 'rx', arg
    return op, arg


def rules_of(src):
    keep, skipped = [], []
    for code in FILES:
        path = next(os.path.join(src, 'rules', f) for f in sorted(os.listdir(os.path.join(src, 'rules'))) if f.startswith(f'REQUEST-{code}-') and f.endswith('.conf'))
        chained = False
        for st in statements(open(path, encoding='utf-8').read()):
            toks = split_args(st)
            if toks[0] != 'SecRule' or len(toks) < 4:
                continue
            variables, operator, acts = toks[1], toks[2], actions(toks[3])
            d = {}
            for k, v in acts: d.setdefault(k, []).append(v)
            rid = d.get('id', [None])[0]
            if chained:                      # aturan lanjutan rantai: ikut dilewati bersama induknya
                chained = 'chain' in d; continue
            if rid is None: continue
            if all(v.lstrip('!&').startswith('TX:') for v in variables.split('|')): continue   # aturan kendali (tingkat paranoia, skor)
            tags = d.get('tag', [])
            pl = next((int(t.split('/')[1]) for t in tags if t.startswith('paranoia-level/')), None)
            base = dict(id=int(rid), file=os.path.basename(path), pl=pl)
            if 'chain' in d:
                chained = True; skipped.append(dict(base, reason='rantai aturan (chain)')); continue
            m = re.match(r'^(!?)@(\w+)\s*(.*)$', operator, re.S)
            if not m: skipped.append(dict(base, reason=f'operator tidak dikenal: {operator[:40]}')); continue
            neg, op, arg = m.groups()
            if neg: skipped.append(dict(base, reason=f'operator negasi !@{op}')); continue
            if op not in OPERATORS: skipped.append(dict(base, reason=f'operator @{op} tidak didukung (mis. libinjection)')); continue
            targets = sorted({TARGETS[v] for v in variables.split('|') if not v.startswith('!') and v.split(':/', 1)[0] in TARGETS})
            if not targets: skipped.append(dict(base, reason='sasaran tidak ada di log nginx: ' + variables[:80])); continue
            tf = [t for t in d.get('t', []) if t]
            bad = [t for t in tf if t not in TRANSFORMS]
            if bad: skipped.append(dict(base, reason='transformasi tidak didukung: ' + ', '.join(bad))); continue
            try: op, arg = convert(op, arg, src)
            except ValueError as e: skipped.append(dict(base, reason=str(e))); continue
            capec = [t.split('/')[-1] for t in tags if t.startswith('capec/')]
            attack = next((t[7:] for t in tags if t.startswith('attack-')), None)   # tag keluarga serangan CRS (xss, sqli, rce, ...)
            keep.append(dict(base, severity=d.get('severity', ['NOTICE'])[0], capec=capec[0] if capec else None, capec_path=next((t for t in tags if t.startswith('capec/')), None),
                             attack=attack,
                             msg=d.get('msg', [''])[0], targets=targets, transforms=tf, op=op, arg=arg))
    keep.sort(key=lambda r: r['id']); skipped.sort(key=lambda r: r['id'])
    return keep, skipped


def build(src):
    keep, skipped = rules_of(src)
    return dict(source='OWASP Core Rule Set', version=VERSION, commit=COMMIT, license='Apache-2.0', files=[f'REQUEST-{c}' for c in FILES],
                counts=dict(kept=len(keep), skipped=len(skipped), by_pl={str(p): sum(1 for r in keep if r['pl'] == p) for p in sorted({r['pl'] for r in keep})}),
                rules=keep, skipped=skipped)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--check', action='store_true'); ap.add_argument('--src')
    a = ap.parse_args()
    tmp = None
    try:
        src = a.src
        if not src:
            tmp = tempfile.mkdtemp(prefix='crs-'); src = os.path.join(tmp, 'crs'); fetch(src)
        data = build(src)
        text = json.dumps(data, ensure_ascii=False, indent=1) + '\n'
        c = data['counts']
        print(f"CRS {VERSION} ({COMMIT[:12]}): {c['kept']} aturan diambil (per tingkat paranoia {c['by_pl']}), {c['skipped']} dilewati")
        reasons = {}
        for s in data['skipped']: reasons[s['reason'].split(':')[0]] = reasons.get(s['reason'].split(':')[0], 0) + 1
        for r, n in sorted(reasons.items(), key=lambda x: -x[1]): print(f'  dilewati {n:3} × {r}')
        if a.check:
            same = os.path.exists(OUT) and open(OUT, encoding='utf-8').read() == text
            print('crs_rules.json sama dengan hasil olah ulang' if same else 'crs_rules.json BERBEDA dari hasil olah ulang')
            return 0 if same else 1
        with open(OUT, 'w', encoding='utf-8') as fh: fh.write(text)
        shutil.copyfile(os.path.join(src, 'LICENSE'), LICENSE_OUT)
        print(f'ditulis: {os.path.relpath(OUT, V2)}, {os.path.relpath(LICENSE_OUT, V2)}')
        return 0
    finally:
        if tmp: shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
