"""Clean architecture dependency rule (docs/08-architecture.md): imports point inward only.

  domain          -> standard library + domain
  application     -> standard library + domain + application
  infrastructure  -> anything except interfaces
  interfaces      -> anything (composition root: interfaces/api/app.py, interfaces/cli.py)

Checked statically on every import statement (module level and inside functions)."""
import ast, pathlib, sys

import pytest

PKG = pathlib.Path(__file__).resolve().parent.parent / 'monishield'
LAYERS = ('domain', 'application', 'infrastructure', 'interfaces')
STDLIB = set(sys.stdlib_module_names)


def _imports(path):
    """-> [(line, absolute module name)] of a file; relative imports resolved against its package."""
    pkg = '.'.join(path.relative_to(PKG.parent).with_suffix('').parts[:-1])
    out = []
    for n in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(n, ast.Import): out += [(n.lineno, a.name) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ''
            if n.level:
                parts = pkg.split('.')[:len(pkg.split('.')) - (n.level - 1)]
                base = '.'.join(parts + ([n.module] if n.module else []))
            names = [f'{base}.{a.name}' for a in n.names] if base in ('monishield',) + tuple(f'monishield.{x}' for x in LAYERS) else [base]
            out += [(n.lineno, m) for m in names]
    return out


def _layer(module):
    parts = module.split('.')
    return parts[1] if len(parts) > 1 and parts[0] == 'monishield' and parts[1] in LAYERS else None


ALLOWED = {
    'domain': {'domain'},
    'application': {'domain', 'application'},
    'infrastructure': {'domain', 'application', 'infrastructure'},
    'interfaces': set(LAYERS),
}


def _violations(layer):
    bad = []
    for f in sorted((PKG / layer).rglob('*.py')):
        for line, mod in _imports(f):
            top = mod.split('.')[0]
            if top == 'monishield':
                target = _layer(mod)
                if target and target not in ALLOWED[layer]: bad.append(f'{f.relative_to(PKG.parent)}:{line} imports {mod}')
            elif layer in ('domain', 'application') and top not in STDLIB:
                bad.append(f'{f.relative_to(PKG.parent)}:{line} imports third-party {mod}')
    return bad


@pytest.mark.parametrize('layer', LAYERS)
def test_dependencies_point_inward(layer):
    assert _violations(layer) == []


def test_infrastructure_never_imports_interfaces():
    assert not any('interfaces' in v for v in _violations('infrastructure'))


def test_rule_catches_a_violation(tmp_path, monkeypatch):
    """The checker itself works: a domain module importing infrastructure is reported."""
    fake = tmp_path / 'monishield' / 'domain'
    fake.mkdir(parents=True)
    (fake / 'bad.py').write_text('from monishield.infrastructure import db\nimport duckdb\n')
    monkeypatch.setattr(sys.modules[__name__], 'PKG', tmp_path / 'monishield')
    assert len(_violations('domain')) == 2
