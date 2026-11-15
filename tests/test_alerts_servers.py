"""Notifications for unusual server values, almost-full disks and offline collectors (stage 63). No network, no database."""
import dataclasses, datetime, json

from monishield.application import alert_service
from monishield.domain import alerts
from monishield.infrastructure import config

HOOK = 'https://discord.com/api/webhooks/1234567890/rahasiaWebhookDiscordUji0000'
HOST, CTR, MOUNT, COLLECTOR = 'db-prod-7', 'payments-api', '/var/lib/secret-data', 'office-gateway'
NAMES = (HOST, CTR, MOUNT, COLLECTOR)


def cfg_of(lang='en', events='metric_unusual,disk_full,collector_offline', url='https://logs.example.com'):
    return alerts.load(dataclasses.replace(config.Config(), alert_events=events, alert_lang=lang, dashboard_url=url))


def ids(*parts): return alerts.watch_id(*parts)


def run(cfg, state, **found): return alerts.server_events(cfg, state, found)


def test_defaults_and_event_list():
    assert alerts.EVENTS.index('metric_unusual') < alerts.EVENTS.index('summary')
    on = alerts.load(config.Config())['events']
    assert on['disk_full'] and on['collector_offline'] and not on['metric_unusual']


def test_disk_full_alerts_once_clears_and_resends_for_a_new_item():
    cfg, a, b = cfg_of(), ids('disk', 1, HOST, MOUNT), ids('disk', 1, HOST, '/')
    msgs, state = run(cfg, {}, disk_full={a: ''})
    assert [m[0] for m in msgs] == ['disk_full'] and msgs[0][2].startswith('Servers: 1 disk almost full (90% or more used)')
    state = {'disk_full': sorted(msgs[0][3])}
    assert run(cfg, state, disk_full={a: ''})[0] == []                       # still open: silent
    msgs, state = run(cfg, state, disk_full={a: '', b: ''})                  # a new item while the first is open
    assert 'Servers: 2 disks almost full' in msgs[0][2]
    state = {'disk_full': sorted(msgs[0][3])}
    msgs, state = run(cfg, state, disk_full={b: ''})                         # one clears: no message, state shrinks
    assert msgs == [] and state['disk_full'] == [b]
    msgs, state = run(cfg, state, disk_full={})
    assert msgs == [] and state['disk_full'] == []
    assert run(cfg, state, disk_full={a: ''})[0]                             # it comes back: alerts again


def test_unusual_counts_by_kind_and_failed_check_keeps_state():
    cfg = cfg_of()
    found = {ids('u', 1, HOST, '', 'mem_used'): 'mem_used', ids('u', 1, HOST, CTR, 'cpu'): 'cpu', ids('u', 1, HOST, '', 'cpu'): 'cpu'}
    msgs, _ = run(cfg, {}, metric_unusual=found)
    assert msgs[0][2].startswith('Servers: 3 unusual values (memory 1, CPU 2)') and msgs[0][2].endswith('/servers')
    keep = {'metric_unusual': ['x']}
    assert run(cfg, keep, metric_unusual=None) == ([], keep)                 # the metrics file was not readable: nothing changes


def test_offline_collector_alerts_once_and_recovers():
    cfg, a = cfg_of(), ids('collector', 5)
    msgs, _ = run(cfg, {}, collector_offline={a: ''}, collector_online=set(), collector_late=set())
    assert msgs[0][1] == 'Collector offline' and msgs[0][2].startswith('Collectors: 1 offline') and msgs[0][2].endswith('/collectors')
    state = {'collector_offline': [a]}
    assert run(cfg, state, collector_offline={a: ''}, collector_online=set(), collector_late=set())[0] == []
    msgs, new = run(cfg, state, collector_offline={}, collector_online=set(), collector_late={a})   # Late: still open, no message
    assert msgs == [] and new['collector_offline'] == [a]
    msgs, new = run(cfg, state, collector_offline={}, collector_online={a}, collector_late=set())
    assert [m[2].split('\n')[0] for m in msgs] == ['Collectors: 1 back online'] and msgs[0][4] == {a}
    msgs, new = run(cfg, state, collector_offline={}, collector_online=set(), collector_late=set())   # deleted or revoked: dropped silently
    assert msgs == [] and new['collector_offline'] == []


def test_off_events_do_nothing_and_forget():
    cfg = cfg_of(events='disk_full')
    msgs, new = run(cfg, {'collector_offline': ['x']}, collector_offline={ids('collector', 1): ''})
    assert msgs == [] and 'collector_offline' not in new


def test_no_name_in_any_text_and_indonesian():
    for lang in ('en', 'id'):
        cfg = cfg_of(lang)
        out, _ = run(cfg, {}, metric_unusual={ids('u', 1, HOST, CTR, 'cpu'): 'cpu'}, disk_full={ids('disk', 1, HOST, MOUNT): ''},
                     collector_offline={ids('collector', 1): ''}, collector_online=set(), collector_late=set())
        out += run(cfg, {'collector_offline': [ids('collector', 1)]}, collector_offline={}, collector_online={ids('collector', 1)}, collector_late=set())[0]
        assert len(out) == 4
        for ev, title, text, *_ in out:
            assert not any(n in title + text for n in NAMES) and '[IP]' not in alerts.scrub(text)
            assert alerts.scrub(text) == text
    assert run(cfg_of('id'), {}, metric_unusual={'a': 'cpu'})[0][0][2] != run(cfg_of('en'), {}, metric_unusual={'a': 'cpu'})[0][0][2]


# Notifier (application): a fake context
class Auth:
    def __init__(self): self.setting, self.log = {}, []
    def setting_get(self, k): return dict(value=self.setting[k]) if k in self.setting else None
    def setting_set(self, k, v, by=None): self.setting[k] = json.loads(json.dumps(v))
    def alert_seen(self, key): return any(k == key and ok for k, ok in self.log)
    def alert_add(self, key, event, channel, ok, summary=None, error=None): self.log.append((key, ok))


class Ctx:
    def __init__(self, tmp_events='metric_unusual,disk_full,collector_offline'):
        self.cfg = dataclasses.replace(config.Config(), alert_events=tmp_events, alert_lang='en', alert_discord=True, discord_webhook_url=HOOK,
                                       dashboard_url='https://logs.example.com')
        self.auth, self.sent = Auth(), []
        self.channels = type('C', (), dict(send=lambda s, name, ch, title, text: self.sent.append((title, text)), names=('discord',)))()
        self.col = [dict(id=1, name=COLLECTOR, status='offline')]
        self.watched = dict(unusual=[], disk_full=[])
        self.collectors = type('K', (), dict(list=lambda s: list(self.col)))()
        self.metrics = type('M', (), dict(watch=lambda s, cols, now: self.watched))()


def test_notifier_sends_once_survives_restart_and_recovers():
    ctx = Ctx()
    n = alert_service.Notifier(ctx)
    now = datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc)
    ctx.watched = dict(unusual=[(1, HOST, CTR, 'cpu')], disk_full=[(1, HOST, MOUNT)])
    first = n.check_servers(now)
    assert sorted(e for e, _ in first) == ['collector_offline', 'disk_full', 'metric_unusual'] and len(ctx.sent) == 3
    assert n.check_servers(now) == [] and alert_service.Notifier(ctx).check_servers(now) == []   # a restart does not repeat
    ctx.col.append(dict(id=2, name='second', status='offline'))
    assert [e for e, _ in n.check_servers(now)] == ['collector_offline'] and 'Collectors: 2 offline' in ctx.sent[-1][1]
    ctx.col[:] = [dict(id=1, name=COLLECTOR, status='online'), dict(id=2, name='second', status='late')]
    assert n.check_servers(now) == [('collector_offline', 'Collectors: 1 back online\nOpen: https://logs.example.com/collectors')]
    ctx.watched = dict(unusual=[], disk_full=[])
    n.check_servers(now)
    ctx.watched = dict(unusual=[], disk_full=[(1, HOST, MOUNT)])
    assert [e for e, _ in n.check_servers(now)] == ['disk_full']                   # cleared, then back: a new alert
    for title, text in ctx.sent: assert not any(x in title + text for x in NAMES + ('second',))


def test_notifier_failed_send_is_retried_and_metrics_error_is_ignored():
    ctx = Ctx()
    n = alert_service.Notifier(ctx)
    calls = []
    def send(s, name, ch, title, text):
        calls.append(1)
        if len(calls) == 1: raise RuntimeError('down')
        ctx.sent.append(text)
    ctx.channels = type('C', (), dict(send=send, names=('discord',)))()
    ctx.metrics = type('M', (), dict(watch=lambda s, cols, now: 1 / 0))()
    assert n.check_servers() == [] and ctx.auth.setting.get(n.STATE, {}).get('collector_offline', []) == []
    assert [e for e, _ in n.check_servers()] == ['collector_offline']
