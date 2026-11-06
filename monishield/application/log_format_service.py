"""Log Formats page (docs/11-log-formats.md, step 1e): which format reads each service, a suggestion from the newest lines, a test of
a format on them, and saving the rules. Rules are saved to log-formats.toml (ctx.logformats) and put to use in this process at once
(log_formats.use), so the next ingest and the live map read with them without a restart."""
import datetime

from monishield.application import sources
from monishield.domain import format_check, log_formats, retention, services as profile, timezone
from monishield.domain.errors import Fail

DAYS = 7           # services seen in the last days are listed
READ_BAD_PCT = 95  # below this the page marks a service as read badly
SELECTABLE = format_check.SUGGEST_ORDER   # formats the Format select offers (no settings needed)


def _today(): return retention.today_local(datetime.datetime.now(datetime.timezone.utc))


def _src(ctx, name):
    if not sources.valid(name): raise Fail('invalid_parameter', 'source must be s3, kafka or collector.', 400)
    return ctx.sources[name]


def rules_now():
    """The rules in use: the file's, or the built-in ones of the site profile."""
    return log_formats.current() or log_formats.default_rules(profile.current())


def _rule(d):
    try: return log_formats.rule_from(d, 1)
    except log_formats.FormatError as e: raise Fail('invalid_rule', _sentence(str(e).split(': ', 1)[-1]), 400) from None


def _sentence(text): return text[:1].upper() + text[1:] + ('' if text.endswith('.') else '.')


def services(ctx):
    """Every service seen in the last DAYS days of each source -> rows with the lines today, the share of lines read and the rule in use."""
    today, rules = _today(), rules_now()
    since = (today - datetime.timedelta(days=DAYS - 1)).isoformat()
    out = []
    for name, sctx in ctx.sources.items():
        seen = {}
        for ns, svc, folder, lines, unread in sctx.warehouse.format_usage(since):
            s = seen.setdefault((ns, svc), dict(today=0, newest='', lines=0, unread=0))
            if folder == today.isoformat(): s['today'] = lines
            if folder > s['newest']: s.update(newest=folder, lines=lines, unread=unread)
        for (ns, svc), s in sorted(seen.items(), key=lambda kv: (kv[0][1].lower(), kv[0][0])):
            idx = next((i for i, r in enumerate(rules) if r.matches(ns, svc)), None)
            rule = rules[idx] if idx is not None else None
            counted = rule is not None and rule.format not in format_check.LEGACY_READERS   # today's parsers count no unread lines
            out.append(dict(source=name, namespace=ns, service=svc, lines_today=s['today'], folder=s['newest'],
                            read_pct=round(100 * (1 - min(s['unread'], s['lines']) / s['lines']), 1) if counted and s['lines'] else None,
                            rule_index=idx, format=rule.format if rule else None, kind=rule.kind if rule else None,
                            own_rule=bool(rule and rule.match == log_formats.override_key(ns, svc))))
    return out


def view(ctx):
    rules = rules_now()
    return dict(rules=[r.public() for r in rules], file=dict(exists=ctx.logformats.exists(), path=ctx.logformats.path), unreachable=log_formats.unreachable(rules),
                services=services(ctx), formats=list(SELECTABLE), read_bad_pct=READ_BAD_PCT, days=DAYS)


def _recent_folders(sctx):
    """Date folders on disk from the last DAYS days, newest first."""
    today = _today()
    since = (today - datetime.timedelta(days=DAYS - 1)).isoformat()
    log, inbox = sctx.logfolders.dates()
    return sorted((f for f in log | inbox if since <= f <= (today + datetime.timedelta(days=1)).isoformat()), reverse=True)


def _lines(ctx, source, namespace, service, n=format_check.SAMPLE):
    sctx = _src(ctx, source)
    if not isinstance(service, str) or not service: raise Fail('invalid_parameter', 'service is required.', 400)
    return ctx.loglines.tail(sctx.cfg, _recent_folders(sctx), namespace or None, service, n)


def suggest(ctx, source, namespace, service):
    """The format that reads the most of the service's last 200 lines (available=False without lines)."""
    folder, lines = _lines(ctx, source, namespace, service)
    if not lines: return dict(available=False)
    current = log_formats.match(rules_now(), namespace, service) or log_formats.Rule('*', 'plain', 'app')
    return dict(available=True, folder=folder, **format_check.suggest(lines, current))


def _local(t):
    if not t: return None
    return (datetime.datetime.fromisoformat(t) + timezone.current().delta).strftime('%H:%M:%S')


def test(ctx, source, namespace, service, rule):
    """The last 5 entries of the service read with `rule` (a rule table as the page sends it). Nothing is saved."""
    r = _rule(rule)
    folder, lines = _lines(ctx, source, namespace, service)
    if not lines: return dict(available=False)
    t = format_check.test(r, lines)
    return dict(available=True, folder=folder, format=r.format, read=t['read'], total=t['total'], rows=[dict(x, time=_local(x.get('time'))) for x in t['rows']])


def save(ctx, rules, admin, ip):
    """Validate, write log-formats.toml, use the rules at once. FormatError text becomes a 400."""
    try:
        parsed = log_formats.check_saveable(log_formats.rules_from(dict(service=rules if isinstance(rules, list) else [])))
    except log_formats.FormatError as e: raise Fail('invalid_rule', _sentence(str(e)), 400) from None
    ctx.logformats.write(log_formats.dumps(parsed))
    log_formats.use(parsed)
    ctx.auth.audit('log_formats.save', admin, f"{len(parsed)} rules by {admin['username']}", ip)
    return view(ctx)


def read_today(ctx, source, admin, ip):
    """Read today's folder of the source again with the rules in use (the Ingest page's lock and thread). Busy when an ingest runs."""
    sctx = _src(ctx, source)
    today = _today().isoformat()
    log, inbox = sctx.logfolders.dates()
    if today not in log | inbox and today not in sctx.warehouse.known_folders(): raise Fail('not_found', 'This source has no folder for today.', 404)
    sctx.ingest.start(today, True, admin['username'])
    ctx.auth.audit('log_formats.read_today', admin, f"source={source} folder={today} by {admin['username']}", ip)
    return dict(started=True, folder=today)
