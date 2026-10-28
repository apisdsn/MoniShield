"""Writes values to the .env file (Configuration page; owner request 2026-10-07: "semua configuration … ke dalam .env"
(all configuration … into .env)).

Only the lines of changed keys are touched; comments, order, and other lines stay. A key that is not active yet is first
looked up as a commented example line (`# KEY=…`, as in .env.example) and activated in place; if there is none, it is
appended at the end. Removing (value None) = the line is deactivated to `# KEY=` without the old value (so secrets
are not left behind in a comment), so the default applies again.

The file is written IN PLACE (not renamed), because in Docker .env is mounted as a single file (bind mount): a rename
would break the mount. The result is read back with the same reader the server uses (config.read_dotenv); if it does
not match, the old content is restored.
"""
import os, re, threading

from monishield.domain.settings import SettingsFail
from monishield.infrastructure import config

_LOCK = threading.Lock()
MARK = '# --- diisi dari layar Konfigurasi MoniShield ---'


class EnvFileFail(Exception):
    pass


def writable(path):
    if os.path.exists(path): return os.access(path, os.W_OK)
    return os.access(os.path.dirname(path) or '.', os.W_OK)


def fmt(value):
    """Python value -> .env text (unquoted when safe)."""
    if isinstance(value, bool): return 'true' if value else 'false'
    if isinstance(value, (list, dict)):
        import json
        value = json.dumps(value, ensure_ascii=False)
    return str(value)


def _quote(v):
    if re.search(r'[\x00-\x1f\x7f]', v): raise EnvFileFail('The value must not contain newlines or control characters.')
    if v == '' or (not re.search(r'[\s#]', v) and v[:1] not in ('"', "'")): return v
    if '"' not in v: return f'"{v}"'
    if "'" not in v: return f"'{v}'"
    raise EnvFileFail('The value must not contain both single and double quotes.')


def _key_re(name, active):
    return re.compile(rf'^\s*(export\s+)?{re.escape(name)}\s*=' if active else rf'^\s*#\s*(export\s+)?{re.escape(name)}\s*=')


def update(path, changes):
    """changes: {VARIABLE_NAME: text | None}. -> list of changed names."""
    lines_new = {k: (None if v is None else f'{k}={_quote(v)}') for k, v in changes.items()}
    with _LOCK:
        old = open(path, encoding='utf-8').read() if os.path.exists(path) else ''
        lines = old.split('\n')
        if lines and lines[-1] == '': lines.pop()
        for name, line in lines_new.items():
            act = [i for i, l in enumerate(lines) if _key_re(name, True).match(l)]
            if line is None:
                for i in act: lines[i] = f'# {name}='
                continue
            if act:
                lines[act[0]] = line
                for i in act[1:]: lines[i] = f'# {name}='   # duplicate: the first one is used
                continue
            com = [i for i, l in enumerate(lines) if _key_re(name, False).match(l)]
            if com: lines[com[0]] = line
            else:
                if MARK not in lines: lines += ['', MARK]
                lines.append(line)
        text = '\n'.join(lines) + '\n'
        if text == old: return []
        new_file = not os.path.exists(path)
        with open(path, 'r+' if not new_file else 'w', encoding='utf-8') as fh:
            fh.seek(0); fh.write(text); fh.truncate()
        if new_file: os.chmod(path, 0o600)
        try:
            back = config.read_dotenv(path)
            ok = all((back.get(k) is None and v is None) or (v is not None and back.get(k) == v) for k, v in changes.items())
        except SystemExit: ok = False
        if not ok:
            with open(path, 'r+', encoding='utf-8') as fh: fh.seek(0); fh.write(old); fh.truncate()
            raise EnvFileFail('The written .env does not read back the same; change reverted.')
        return sorted(changes)


class EnvStore:
    """EnvStore port for the Configuration page: reads/writes one .env file + sees the process environment variables.
    Values are written by their variable names (S4_…, AWS_…); the caller does not know the file format."""

    def __init__(self, path): self.path = path

    def values(self):
        try: return config.read_dotenv(self.path)
        except SystemExit: return {}

    def environ(self): return os.environ

    def exists(self): return os.path.exists(self.path)

    def writable(self): return writable(self.path)   # looked up at call time (tests can replace it)

    def write(self, changes):
        """{NAME: Python value | None (line deactivated)} -> list of changed names. Failure -> SettingsFail."""
        try: return update(self.path, {k: None if v is None else fmt(v) for k, v in changes.items()})
        except EnvFileFail as e: raise SettingsFail(str(e)) from None
