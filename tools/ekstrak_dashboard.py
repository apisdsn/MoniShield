#!/usr/bin/env python3
"""Extract the data object `D` from the old system's dashboard.html -> JSON, for the equivalence test.

  python3 tools/ekstrak_dashboard.py [output.json]

Default output: v2/data/dashboard-lama.json (not in git). dashboard.html is only read.
"""
import json, os, sys

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(os.path.dirname(V2), 'dashboard.html')


def extract(path=SRC):
    html = open(path, encoding='utf-8').read()
    return json.JSONDecoder().raw_decode(html, html.index('const D = ') + 10)[0]


def load(path=None, src=SRC):
    """Read the extraction result; create it when missing or older than dashboard.html."""
    path = path or os.path.join(V2, 'data', 'dashboard-lama.json')
    if not os.path.exists(path) or os.path.getmtime(path) < os.path.getmtime(src):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh: json.dump(extract(src), fh, ensure_ascii=False)
    return json.load(open(path, encoding='utf-8'))


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(V2, 'data', 'dashboard-lama.json')
    D = extract()
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh: json.dump(D, fh, ensure_ascii=False)
    print(f'-> {out}: {len(D["days"])} folders, {len(D["files"])} files, {len(D["ipinfo"])} ipinfo, {len(D["geo"])} geo', file=sys.stderr)
