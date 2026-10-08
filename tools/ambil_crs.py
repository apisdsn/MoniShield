"""Fetch the OWASP Core Rule Set (CRS) rules of a PINNED version and save them as monishield/domain/crs_rules.json (TRD §4.6, Stage 21).

    py tools/ambil_crs.py            # download (git clone tag), process, write monishield/domain/crs_rules.json + CRS-LICENSE.txt
    py tools/ambil_crs.py --check    # re-process and compare: exit 1 when the file in the repo differs
    py tools/ambil_crs.py --src DIR  # use an existing CRS copy (no network)

What is taken: files REQUEST-913, 930, 931, 932, 933, 934, 941, 942, 944; only rules whose targets are request parts
that EXIST in the nginx log (URI, query arguments, file name, User-Agent). Rules that cannot be used as they are
(libinjection operators, unsupported transformations, patterns the Python regex engine rejects, rule chains,
targets not in the log) are RECORDED in the `skipped` section with their reason, not silently altered.
(The skip reasons stay in Indonesian: they are data in the committed crs_rules.json, which --check compares byte for byte.)
No download happens while the dashboard runs: the JSON file is part of the repo.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

VERSION = 'v4.30.0'
COMMIT = 'e03a4f6dabc7a30ebd8c52c97d28a154f590a48f'   # `git rev-parse` of the tag above; checked on every download
REPO = 'https://github.com/coreruleset/coreruleset.git'
FILES = ('913', '930', '931', '932', '933', '934', '941', '942', '944')
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(V2, 'monishield', 'domain', 'crs_rules.json')
LICENSE_OUT = os.path.join(V2, 'monishield', 'domain', 'CRS-LICENSE.txt')

# ModSecurity variables -> request parts present in the nginx log (the rest is not logged)
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
    if head != COMMIT: raise SystemExit(f'commit {VERSION} = {head}, not the pinned {COMMIT}: check before updating')


def statements(text):
    """Whole SecRule/SecAction statements (continuation lines '\\' joined), comments dropped."""
    out, cur = [], ''
    for line in text.splitlines():
        s = line.rstrip()
        if not cur and (not s.strip() or s.lstrip().startswith('#')): continue
        if s.endswith('\\'): cur += s[:-1].strip() + ' '; continue
        cur += s.strip(); out.append(cur); cur = ''
    return out


def split_args(st):
    """'SecRule A "B" "C"' -> ['SecRule', 'A', 'B', 'C'] (double quotes with \\" inside)."""
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
    """'id:1,t:none,msg:'a,b',tag:'x'' -> [(key, value)]."""
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
    """-> (op, content) or raises ValueError(reason)."""
    op = rule_op
    if op in ('pmFromFile', 'pmf'): return 'pm', sorted({w.lower() for f in arg.split() for w in load_data(src, f)})
    if op == 'pm': return 'pm', sorted({w.lower() for w in arg.split()})
    if op == 'rx':
        # ModSecurity matches BYTES: escape \x{HH} (<= 0xff) = one byte. The detector matches UTF-8 bytes read as latin-1,
        # so \x{HH} -> \xHH means the same. Multi-byte escapes, POSIX classes and \Q..\E have no safe equivalent.
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
            if chained:                      # chained follow-up rule: skipped together with its parent
                chained = 'chain' in d; continue
            if rid is None: continue
            if all(v.lstrip('!&').startswith('TX:') for v in variables.split('|')): continue   # control rules (paranoia level, score)
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
            attack = next((t[7:] for t in tags if t.startswith('attack-')), None)   # CRS attack family tag (xss, sqli, rce, ...)
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
        print(f"CRS {VERSION} ({COMMIT[:12]}): {c['kept']} rules taken (per paranoia level {c['by_pl']}), {c['skipped']} skipped")
        reasons = {}
        for s in data['skipped']: reasons[s['reason'].split(':')[0]] = reasons.get(s['reason'].split(':')[0], 0) + 1
        for r, n in sorted(reasons.items(), key=lambda x: -x[1]): print(f'  skipped {n:3} × {r}')
        if a.check:
            same = os.path.exists(OUT) and open(OUT, encoding='utf-8').read() == text
            print('crs_rules.json matches the re-processed result' if same else 'crs_rules.json DIFFERS from the re-processed result')
            return 0 if same else 1
        with open(OUT, 'w', encoding='utf-8') as fh: fh.write(text)
        shutil.copyfile(os.path.join(src, 'LICENSE'), LICENSE_OUT)
        print(f'written: {os.path.relpath(OUT, V2)}, {os.path.relpath(LICENSE_OUT, V2)}')
        return 0
    finally:
        if tmp: shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
