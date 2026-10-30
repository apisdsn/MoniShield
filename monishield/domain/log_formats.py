"""Log format rules: how each service of a site logs (docs/11-log-formats.md, stage 52 step 1a).

A site lists rules in `log-formats.toml` (S4_LOG_FORMATS_FILE). Every service folder is matched against the rules from top
to bottom and the FIRST match wins; a rule names a preset (one of today's parsers, or a common format) or describes the
format (`json` / `logfmt` field mapping, `regex` with named groups). Without the file the rules of today are built from
the site profile (domain/services.py), so an existing site reads its logs exactly as before.

This module is pure (standard library only): it validates and matches rules; reading the file is in
monishield/infrastructure/config.py, and the parsers use the rules from step 1b on.
"""
import dataclasses, fnmatch, hashlib, json, re

# preset -> default kind. "legacy" presets are today's parsers in domain/parse.py.
PRESETS = {
    'ingress-nginx': 'http',     # legacy: ingress-nginx access + error log
    'nginx-frontend': 'http',    # legacy: nginx-style access log of the web frontend (first X-Forwarded-For entry)
    'coredns': 'app',            # legacy: CoreDNS
    'events-json': 'app',        # legacy: "[TAG-LEVEL] {...}" JSON events with requestId
    'spring-boot': 'app',        # legacy: Spring Boot / Logback default pattern
    'nginx-combined': 'http',
    'apache-combined': 'http',
    'json': 'app',
    'logfmt': 'app',
    'syslog': 'app',
    'regex': 'app',
    'auto': None,                # decided by detection (step 1d)
    'plain': 'app',
}
KINDS = ('http', 'app')
FEATURES = ('logins', 'pdf', 'tracing')
COLUMNS = ('time', 'level', 'ip', 'method', 'path', 'status', 'bytes', 'duration_ms', 'request_id', 'user', 'message',
           'logger', 'upstream', 'ua', 'referer')
LEVELS = ('ERROR', 'WARN', 'INFO', 'DEBUG')
TIME_FORMATS = ('iso', 'epoch', 'epoch_ms', 'clf')
KEYS = ('match', 'format', 'kind', 'fields', 'pattern', 'time_format', 'multiline', 'levels', 'tag', 'features', 'ip_header')
MATCH = re.compile(r'(?:[A-Za-z0-9*?._-]+/)?[A-Za-z0-9*?._-]+')
TAG = re.compile(r'[A-Za-z0-9_]{1,20}')
FIELD = re.compile(r'[A-Za-z0-9_@$-]+(?:\.[A-Za-z0-9_@$-]+)*')
MAX_PATTERN = 2000
NESTED = re.compile(r'\((?:[^()\\]|\\.)*[+*}]\)\s*[+*{]')   # (a+)+, (\d*)*, (x{2,}){3}: catastrophic backtracking


class FormatError(ValueError):
    """A rule that cannot be used; the message names the rule."""


@dataclasses.dataclass(frozen=True)
class Rule:
    match: str
    format: str
    kind: str | None = None
    fields: tuple = ()           # ((column, source key), …): hashable
    pattern: str = ''
    time_format: str = 'iso'
    multiline: str = ''
    levels: tuple = ()           # ((site word, LEVEL), …)
    tag: str = ''
    features: tuple = ()
    ip_header: str = ''

    @property
    def namespace(self): return self.match.split('/', 1)[0] if '/' in self.match else None

    @property
    def name(self): return self.match.split('/', 1)[-1]

    def matches(self, namespace, service):
        if self.namespace is not None and not fnmatch.fnmatchcase(namespace or '', self.namespace): return False
        return fnmatch.fnmatchcase(service or '', self.name)

    @property
    def key(self):
        """Short stable hash of the rule: a file is parsed again when the rule that read it changes (step 1d)."""
        return hashlib.sha256(json.dumps(dataclasses.asdict(self), sort_keys=True).encode()).hexdigest()[:12]

    def public(self):
        """For pages and the CLI: the rule as plain data."""
        d = dataclasses.asdict(self)
        d['fields'], d['levels'], d['features'] = dict(self.fields), dict(self.levels), list(self.features)
        return d


def _regex(text, where, what):
    if len(text) > MAX_PATTERN: raise FormatError(f'{where}: {what} is longer than {MAX_PATTERN} characters')
    if NESTED.search(text): raise FormatError(f'{where}: {what} has a nested repeat such as (a+)+, which can hang the parser')
    try: return re.compile(text)
    except re.error as e: raise FormatError(f'{where}: {what} is not a valid regular expression ({e})') from None


def check_regex(text, where, what):
    """A user's regular expression, compiled after the length and nested-repeat checks (also used by the raw log search)."""
    return _regex(text, where, what)


def rule_from(d, n):
    """One `[[service]]` table (dict) at position n (1-based) -> Rule. FormatError when it cannot be used."""
    where = f'rule {n}' + (f' ({d.get("match")})' if isinstance(d, dict) and d.get('match') else '')
    if not isinstance(d, dict): raise FormatError(f'{where}: must be a table')
    if unknown := sorted(set(d) - set(KEYS)): raise FormatError(f'{where}: unknown key {", ".join(unknown)}')
    m, fmt = d.get('match'), d.get('format')
    if not isinstance(m, str) or not MATCH.fullmatch(m): raise FormatError(f'{where}: match must be a service name or glob, optionally namespace/name')
    if fmt not in PRESETS: raise FormatError(f'{where}: format must be one of {", ".join(PRESETS)}')
    kind = d.get('kind', PRESETS[fmt])
    if kind is not None and kind not in KINDS: raise FormatError(f'{where}: kind must be http or app')
    fields = d.get('fields', {})
    if fields and fmt not in ('json', 'logfmt'): raise FormatError(f'{where}: fields only apply to the json and logfmt formats')
    if not isinstance(fields, dict): raise FormatError(f'{where}: fields must be a table of column = "source key"')
    for col, src in fields.items():
        if col not in COLUMNS: raise FormatError(f'{where}: unknown column {col!r} (columns: {", ".join(COLUMNS)})')
        if not isinstance(src, str) or not FIELD.fullmatch(src): raise FormatError(f'{where}: fields.{col} must be a key name, dotted for nested JSON')
    pattern = d.get('pattern', '')
    if fmt == 'regex':
        if not isinstance(pattern, str) or not pattern: raise FormatError(f'{where}: the regex format needs a pattern')
        groups = set(_regex(pattern, where, 'pattern').groupindex)
        if unknown := sorted(groups - set(COLUMNS)): raise FormatError(f'{where}: unknown group {", ".join(unknown)} (columns: {", ".join(COLUMNS)})')
        if missing := [g for g in ('time', 'message') if g not in groups]: raise FormatError(f'{where}: the pattern needs the named group(s) {", ".join(missing)}')
    elif pattern: raise FormatError(f'{where}: pattern only applies to the regex format')
    tf = d.get('time_format', 'iso')
    if not isinstance(tf, str) or not (tf in TIME_FORMATS or '%' in tf): raise FormatError(f'{where}: time_format must be iso, epoch, epoch_ms, clf or a strptime pattern')
    ml = d.get('multiline', '')
    if not isinstance(ml, str): raise FormatError(f'{where}: multiline must be a regular expression')
    if ml: _regex(ml, where, 'multiline')
    levels = d.get('levels', {})
    if not isinstance(levels, dict) or any(not isinstance(k, str) or v not in LEVELS for k, v in levels.items()):
        raise FormatError(f'{where}: levels maps a word to one of {", ".join(LEVELS)}')
    tag = d.get('tag', '')
    if tag and fmt != 'events-json': raise FormatError(f'{where}: tag only applies to the events-json format')
    if tag and not TAG.fullmatch(tag): raise FormatError(f'{where}: tag is 1-20 letters, digits or _')
    feats = d.get('features', [])
    if not isinstance(feats, list) or any(f not in FEATURES for f in feats): raise FormatError(f'{where}: features are {", ".join(FEATURES)}')
    ip_header = d.get('ip_header', '')
    if ip_header and kind != 'http': raise FormatError(f'{where}: ip_header only applies to http logs')
    if ip_header and (not isinstance(ip_header, str) or not FIELD.fullmatch(ip_header)): raise FormatError(f'{where}: ip_header must be a field name')
    return Rule(match=m, format=fmt, kind=kind, fields=tuple(sorted(fields.items())), pattern=pattern, time_format=tf,
                multiline=ml, levels=tuple(sorted(levels.items())), tag=tag, features=tuple(dict.fromkeys(feats)), ip_header=ip_header)


def rules_from(doc):
    """Parsed log-formats.toml (dict with a `service` array) -> (Rule, …). FormatError when any rule cannot be used."""
    if not isinstance(doc, dict) or set(doc) - {'service'}: raise FormatError('the file holds [[service]] tables only')
    items = doc.get('service', [])
    if not isinstance(items, list) or not items: raise FormatError('the file needs at least one [[service]] rule')
    return tuple(rule_from(d, n) for n, d in enumerate(items, 1))


def default_rules(profile, nginx='nginx-ingress-controller', dns='coredns'):
    """The rules of today, from the site profile (domain/services.py): the same parser for every service as before."""
    return (
        Rule(nginx, 'ingress-nginx', 'http'),
        Rule(dns, 'coredns', 'app'),
        Rule(profile.frontend, 'nginx-frontend', 'http'),
        Rule(profile.events, 'events-json', 'app', tag=profile.event_tag, features=('tracing',)),
        Rule(profile.auth, 'spring-boot', 'app', features=('logins',)),
        Rule(profile.report, 'spring-boot', 'app', features=('pdf',)),
        Rule('*', 'spring-boot', 'app'),   # any other service folder: Spring Boot, as before
    )


def match(rules, namespace, service):
    """The first rule that matches the service (and namespace), or None."""
    return next((r for r in rules if r.matches(namespace, service)), None)


def unreachable(rules):
    """Rules after a catch-all `*` never match: their positions (1-based), to warn the admin."""
    for i, r in enumerate(rules):
        if r.name == '*' and r.namespace is None: return list(range(i + 2, len(rules) + 1))
    return []


_current = None


def use(rules):
    global _current
    _current = None if rules is None else tuple(rules)


def current():
    """The rules of this process; None until the server or the CLI set them."""
    return _current
