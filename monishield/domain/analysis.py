"""Analysis settings (stage 62): which log of a source is its access log, which are its application logs, which field carries the
request ID, and the business metrics a site counts itself.

The file `analysis.toml` (S4_ANALYSIS_FILE) has one table per source (`s3`, `kafka`, `collector`); a missing file or key means
Auto, which is what the pages did before this file existed:

    [collector]
    access_log = "monishield-https-1"      # "auto" (the default) or a service name
    app_logs = ["monishield-app-1"]        # "auto" or a list of service names
    request_id = "trace_id"                # "auto" or the name of a field in the log line

    [[collector.business]]
    name = "Sign-ins"
    service = "monishield-https-1"
    match = "request"                      # "request" (an access-log request) or "log_line" (an application log line)
    method = "POST"
    path = "/api/v1/auth/login"            # a path key (ids in the path read ":n" or ":id"); a trailing * matches a prefix
    status = "2xx"                         # "2xx".."5xx" or an exact code

    [[collector.business]]
    name = "Payments Received"
    service = "shop-app"
    match = "log_line"
    text = "Payment received"              # case-insensitive text of the line

This module is pure (standard library only): it validates the settings, writes the TOML text and decides whether one request or
one log line counts for a rule. Reading and writing the file is in monishield/infrastructure/analysis_file.py, counting the
rules over a folder in monishield/infrastructure/queries/business.py.
"""
import dataclasses, json, re

from monishield.domain import formats, log_formats

SOURCES = ('s3', 'kafka', 'collector')
AUTO = 'auto'
MATCHES = ('request', 'log_line')
CLASSES = ('2xx', '3xx', '4xx', '5xx')
METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')
MAX_METRICS = 30
MAX_SERVICES = 50
SERVICE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._@:-]{0,99}')
NAME = re.compile(r'\S(?:.{0,58}\S)?')
PATH = re.compile(r'/[^\s*]*\*?')
KEYS = ('access_log', 'app_logs', 'request_id', 'business')
METRIC_KEYS = ('name', 'service', 'match', 'method', 'path', 'status', 'text')
ID_FIELDS = formats.ID_NAMES   # the names read when request_id is Auto


class AnalysisError(ValueError):
    """Settings that cannot be used; the message names the source and the item."""


@dataclasses.dataclass(frozen=True)
class Metric:
    name: str
    service: str
    match: str
    method: str = ''
    path: str = ''
    status: str = ''
    text: str = ''

    def public(self): return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Settings:
    access_log: str = AUTO
    app_logs: object = AUTO       # AUTO, or a tuple of service names
    request_id: str = AUTO
    business: tuple = ()          # (Metric, …)

    def public(self):
        return dict(access_log=self.access_log, app_logs=self.app_logs if self.app_logs == AUTO else list(self.app_logs),
                    request_id=self.request_id, business=[m.public() for m in self.business])

    @property
    def default(self): return self == Settings()


def _service(value, where):
    if not isinstance(value, str) or not SERVICE.fullmatch(value): raise AnalysisError(f'{where}: a service name is letters, digits and . _ @ : -')
    return value


def metric_from(d, where):
    """One business rule (a dict as the page sends it, or one `[[source.business]]` table) -> Metric."""
    if not isinstance(d, dict): raise AnalysisError(f'{where}: a rule is a table')
    if unknown := sorted(set(d) - set(METRIC_KEYS)): raise AnalysisError(f'{where}: unknown key {", ".join(unknown)}')
    name = d.get('name')
    if not isinstance(name, str) or not NAME.fullmatch(name.strip() if isinstance(name, str) else ''): raise AnalysisError(f'{where}: the name is 1-60 characters')
    name = name.strip()
    where = f'{where} ({name})'
    service = _service(d.get('service'), where)
    match = d.get('match')
    if match not in MATCHES: raise AnalysisError(f'{where}: match must be request or log_line')
    method, path, status, text = (d.get(k) or '' for k in ('method', 'path', 'status', 'text'))
    status = str(status) if isinstance(status, int) and not isinstance(status, bool) else status
    for k, v in (('method', method), ('path', path), ('status', status), ('text', text)):
        if not isinstance(v, str): raise AnalysisError(f'{where}: {k} must be text')
    if match == 'log_line':
        if method or path or status: raise AnalysisError(f'{where}: a log line rule has text only')
        if not text.strip() or len(text) > 200: raise AnalysisError(f'{where}: the text is 1-200 characters')
        text = text.strip()
    else:
        if text: raise AnalysisError(f'{where}: a request rule has method, path and status, not text')
        method = method.upper()
        if method and method not in METHODS: raise AnalysisError(f'{where}: method is one of {", ".join(METHODS)}')
        if path and (len(path) > 300 or not PATH.fullmatch(path)): raise AnalysisError(f'{where}: the path starts with / and may end with *')
        if status and not (status in CLASSES or (re.fullmatch(r'[1-5]\d\d', status))): raise AnalysisError(f'{where}: status is 2xx, 3xx, 4xx, 5xx or a code such as 201')
        if not (method or path or status): raise AnalysisError(f'{where}: give a method, a path or a status')
    return Metric(name, service, match, method, path, status, text)


def settings_from(d, source):
    """The table of one source (dict) -> Settings. AnalysisError when any part cannot be used."""
    where = source
    if not isinstance(d, dict): raise AnalysisError(f'{where}: must be a table')
    if unknown := sorted(set(d) - set(KEYS)): raise AnalysisError(f'{where}: unknown key {", ".join(unknown)}')
    access = d.get('access_log', AUTO)
    if access != AUTO: access = _service(access, f'{where}.access_log')
    apps = d.get('app_logs', AUTO)
    if apps != AUTO:
        if not isinstance(apps, list) or not apps or len(apps) > MAX_SERVICES: raise AnalysisError(f'{where}.app_logs: "auto" or a list of 1-{MAX_SERVICES} services')
        apps = tuple(dict.fromkeys(_service(s, f'{where}.app_logs') for s in apps))
    rid = d.get('request_id', AUTO)
    if rid != AUTO and (not isinstance(rid, str) or not log_formats.FIELD.fullmatch(rid) or len(rid) > 100):
        raise AnalysisError(f'{where}.request_id: "auto" or a field name, dotted for nested JSON')
    items = d.get('business', [])
    if not isinstance(items, list) or len(items) > MAX_METRICS: raise AnalysisError(f'{where}.business: a list of at most {MAX_METRICS} rules')
    metrics = tuple(metric_from(m, f'{where}.business {n}') for n, m in enumerate(items, 1))
    seen = set()
    for m in metrics:
        if m.name.lower() in seen: raise AnalysisError(f'{where}.business: the name "{m.name}" is used twice')
        seen.add(m.name.lower())
    return Settings(access, apps, rid, metrics)


def parse(doc):
    """Parsed analysis.toml (dict, source -> table) -> {source: Settings} for all three sources (a missing one is Auto)."""
    if not isinstance(doc, dict): raise AnalysisError('the file holds one table per source')
    if unknown := sorted(set(doc) - set(SOURCES)): raise AnalysisError(f'unknown source {", ".join(unknown)} (sources: {", ".join(SOURCES)})')
    return {s: settings_from(doc.get(s, {}), s) for s in SOURCES}


def defaults(): return {s: Settings() for s in SOURCES}


# TOML writer (the Analysis Settings page saves the file; no third-party package)
def _s(text): return json.dumps(text, ensure_ascii=False).replace('\x7f', '\\u007f')


HEADER = ('# What the analysis pages read (docs/10-user-guide.md, Analysis Settings). Written by the Analysis Settings page of MoniShield.\n'
          '# A missing source or key is Auto. The page rewrites this file when it saves, so comments written by hand are not kept.\n')


def dumps(by_source):
    """{source: Settings} -> text of analysis.toml. `parse(tomllib.loads(dumps(x))) == x` (a source with nothing set is not written)."""
    out = [HEADER]
    for source in SOURCES:
        st = by_source.get(source) or Settings()
        if st.default: continue
        lines = [f'[{source}]']
        if st.access_log != AUTO: lines.append(f'access_log = {_s(st.access_log)}')
        if st.app_logs != AUTO: lines.append('app_logs = [' + ', '.join(_s(x) for x in st.app_logs) + ']')
        if st.request_id != AUTO: lines.append(f'request_id = {_s(st.request_id)}')
        block = ['\n'.join(lines)]
        for m in st.business:
            rows = [f'[[{source}.business]]', f'name = {_s(m.name)}', f'service = {_s(m.service)}', f'match = {_s(m.match)}']
            for k in ('method', 'path', 'status', 'text'):
                if getattr(m, k): rows.append(f'{k} = {_s(getattr(m, k))}')
            block.append('\n'.join(rows))
        out.append('\n\n'.join(block) + '\n')
    return '\n'.join(out)


# Matching
def like_pattern(path):
    """A rule path -> SQL LIKE pattern (escape character `\\`): exact, or a prefix when it ends with *."""
    esc = path.rstrip('*').replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return esc + '%' if path.endswith('*') else esc


def status_bounds(status):
    """'2xx' -> (200, 299), '201' -> (201, 201), '' -> None."""
    if not status: return None
    if status in CLASSES: return int(status[0]) * 100, int(status[0]) * 100 + 99
    return int(status), int(status)


def request_matches(m, service, method, path_key, status):
    """Does one request (an access-log row) count for the rule? Same answer as the SQL of queries/business.py."""
    if m.match != 'request' or service != m.service: return False
    if m.method and (method or '').upper() != m.method: return False
    if m.path:
        if m.path.endswith('*'):
            if not (path_key or '').startswith(m.path[:-1]): return False
        elif path_key != m.path: return False
    if m.status:
        lo, hi = status_bounds(m.status)
        if status is None or not lo <= status <= hi: return False
    return True


def line_matches(m, service, message):
    """Does one application log line count for the rule?"""
    return m.match == 'log_line' and service == m.service and m.text.lower() in (message or '').lower()


def suggest_name(method, path):
    """A readable name for a suggested rule: the last two words of the path without versions and ids ("/api/v1/auth/login" -> "Auth Login")."""
    words = [w for seg in path.split('/') for w in re.split(r'[-_.]+', seg) if w and not re.fullmatch(r'v\d+|api|:n|:id|\{.*\}|\d+', w, re.I)]
    text = ' '.join(w[:1].upper() + w[1:] for w in words[-2:])
    return text or (method or 'Requests')


# The request ID field read for NEW lines (domain/formats.py): Auto = the common names, else the configured name first
def id_fields(settings_by_source):
    """Field names configured as the request ID in any source, to be read besides the common names while parsing."""
    return tuple(dict.fromkeys(s.request_id for s in settings_by_source.values() if s.request_id != AUTO))


_current = defaults()


def use(by_source):
    global _current
    _current = defaults() if by_source is None else dict(by_source)


def current(source='s3'):
    """The settings of a source in this process (Auto until the server or the CLI sets them)."""
    return _current.get(source) or Settings()


def all_current(): return dict(_current)


def of(cfg):
    """The settings of the source a configuration view belongs to (SourceConfig has `source`; the main Config is S3)."""
    return current(getattr(cfg, 'source', 's3'))
