"""Log profile: which service writes which log format, and the few site-specific values the parsers need (owner request
2026-10-28: no client names, domains or addresses in the code). The code only knows ROLES; the real service names of a
site are configuration (S4_SERVICE_NAMES, S4_EVENT_TAG, S4_UPSTREAM_PREFIX, S4_BUSINESS_ENDPOINTS in .env).

Roles and their log formats:
  nginx     ingress-nginx access + error log (fixed name: the Kubernetes default)
  dns       CoreDNS errors (fixed name: the Kubernetes default)
  frontend  nginx-style access log of the web frontend
  events    JSON application events "[<TAG>-<LEVEL>] {...}" with requestId (joined with nginx for request tracing)
  auth      Spring Boot log with the login lines (failed logins, lockouts)
  report    Spring Boot log with JasperReports PDF lines
  reference Spring Boot log (plain)
Any other service folder is read as a Spring Boot log (old A10).

`current()` is the profile of this process: set once from the configuration when the server or the CLI starts
(`use(from_config(cfg))`). Parser worker processes get it passed explicitly with each file.
"""
import dataclasses, re

NGINX, DNS = 'nginx-ingress-controller', 'coredns'
ROLES = ('frontend', 'events', 'auth', 'report', 'reference')
DEFAULT_NAMES = dict(frontend='web-frontend', events='event-api', auth='auth-service', report='report-service', reference='reference-service')
DEFAULT_TAG = 'APP'
# endpoint of the events service (method + path key) -> business metric, counted on 2xx responses. The metric names are
# fixed keys of the Business page (web/src/i18n biz.*); the endpoints are site configuration.
METRICS = ('reports_created', 'report_registrations', 'otp_requested', 'otp_verified', 'files_uploaded', 'attachments_added')
DEFAULT_BUSINESS = {
    'POST /reports': 'reports_created', 'POST /reports/register': 'report_registrations',
    'POST /reports/request-otp': 'otp_requested', 'POST /reports/verify-otp': 'otp_verified',
    'POST /uploads': 'files_uploaded', 'POST /files': 'files_uploaded', 'POST /attachments': 'attachments_added',
}
NAME = re.compile(r'[a-z0-9][a-z0-9-]{0,62}')
TAG = re.compile(r'[A-Za-z0-9_]{1,20}')
ENDPOINT = re.compile(r'(GET|POST|PUT|PATCH|DELETE) /\S*')


@dataclasses.dataclass(frozen=True)
class Profile:
    frontend: str = DEFAULT_NAMES['frontend']
    events: str = DEFAULT_NAMES['events']
    auth: str = DEFAULT_NAMES['auth']
    report: str = DEFAULT_NAMES['report']
    reference: str = DEFAULT_NAMES['reference']
    event_tag: str = DEFAULT_TAG
    upstream_prefix: str = ''
    business: tuple = tuple(DEFAULT_BUSINESS.items())   # ((endpoint, metric), …): hashable, so the profile can be cached

    @property
    def spring(self): return (self.auth, self.reference, self.report)

    @property
    def business_map(self): return dict(self.business)

    def endpoint_of(self, metric):
        """First endpoint counted as `metric` (e.g. the OTP check, whose failures are counted too), or None."""
        return next((ep for ep, m in self.business if m == metric), None)

    def names(self): return {r: getattr(self, r) for r in ROLES}


def validate(names=None, tag=DEFAULT_TAG, business=None):
    """-> error message or None. names: {role: service}; business: {endpoint: metric}."""
    for role, svc in (names or {}).items():
        if role not in ROLES: return f'unknown role {role!r} (roles: {", ".join(ROLES)})'
        if not isinstance(svc, str) or not NAME.fullmatch(svc): return f'{role}: service names are lower case letters, digits and -'
    if not TAG.fullmatch(tag or ''): return 'the event tag is 1-20 letters, digits or _'
    for ep, metric in (business or {}).items():
        if not ENDPOINT.fullmatch(ep): return f'{ep!r} is not "METHOD /path"'
        if metric not in METRICS: return f'{metric!r} is not a business metric ({", ".join(METRICS)})'
    return None


def from_config(cfg):
    names = {**DEFAULT_NAMES, **(cfg.service_names or {})}
    return Profile(**names, event_tag=cfg.event_tag or DEFAULT_TAG, upstream_prefix=cfg.upstream_prefix or '',
                   business=tuple((cfg.business_endpoints or DEFAULT_BUSINESS).items()))


_current = Profile()


def use(profile):
    global _current
    _current = profile


def current(): return _current
