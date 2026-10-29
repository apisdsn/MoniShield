"""Local time zone of the site (domain/timezone.py, S4_TIMEZONE_OFFSET / S4_TIMEZONE_LABEL)."""
import dataclasses, datetime

import pytest

import logs_mini
from monishield.domain import kafka_message, retention, timezone
from monishield.infrastructure import config, db, ingest
from monishield.infrastructure.queries import sql

UTC = datetime.timezone.utc


@pytest.fixture
def zone():
    """Use a zone for one test, then go back to the default (+07:00 WIB)."""
    def use(offset, label='TST'): timezone.use(timezone.Zone(timezone.parse_offset(offset), label))
    yield use
    timezone.use(timezone.Zone())


def test_offsets_and_labels():
    assert [timezone.parse_offset(x) for x in ('+07:00', '+7', 'UTC+5:30', '-03:00', '+0545', 'GMT+8')] == [420, 420, 330, -180, 345, 480]
    for bad in ('7', '+15:00', '+07:60', 'Asia/Jakarta', ''):
        with pytest.raises(ValueError): timezone.parse_offset(bad)
    assert timezone.Zone(330, 'IST').text == '+05:30' and timezone.Zone(-180, 'BRT').text == '-03:00'
    assert timezone.validate('+07:00', 'WIB') is None and 'label' in timezone.validate('+07:00', 'not a label!')


def test_config_validates_the_zone():
    c = config.load(env={'S4_TIMEZONE_OFFSET': '+00:00', 'S4_TIMEZONE_LABEL': 'UTC'}, dotenv=False)
    assert timezone.from_config(c) == timezone.Zone(0, 'UTC')
    assert timezone.from_config(config.load(env={}, dotenv=False)) == timezone.Zone(420, 'WIB')   # default = the old fixed WIB
    with pytest.raises(SystemExit, match='S4_TIMEZONE_OFFSET'): config.load(env={'S4_TIMEZONE_OFFSET': 'WIB'}, dotenv=False)


def test_local_times_folders_and_daily_jobs(zone):
    t = datetime.datetime(2026, 1, 1, 20, 30)
    assert sql.local_time(t) == '2026-01-02 03:30'                       # default +7
    zone('-03:00')
    assert sql.local_time(t) == '2026-01-01 17:30'
    assert kafka_message.folder_of(datetime.datetime(2026, 1, 2, 2, 0, tzinfo=UTC)) == '2026-01-02'   # 23:00 local on Jan 1
    assert retention.today_local(datetime.datetime(2026, 1, 2, 2, 0, tzinfo=UTC)) == datetime.date(2026, 1, 1)
    nxt = retention.next_daily(datetime.datetime(2026, 1, 1, 12, 0, tzinfo=UTC), 2)                  # 02:00 local = 05:00 UTC
    assert nxt == datetime.datetime(2026, 1, 2, 5, 0, tzinfo=UTC)


def test_folders_are_derived_again_when_the_zone_changes(tmp_path, zone):
    cfg = dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'),
                              inbox_dir=str(tmp_path / 'inbox'), offline=True)
    con = db.open(cfg.db_path)
    ingest.run(cfg, con, workers=0)
    hours = lambda: [r[0] for r in con.execute("SELECT strftime(hour_wib, '%H') FROM agg_hour WHERE service = 'nginx-ingress-controller' ORDER BY 1").fetchall()]
    before = hours()
    con.execute('UPDATE folder_state SET tz_minutes = NULL')             # folders from before the setting count as +7 h
    assert ingest.run(cfg, con, workers=0)['folders_rezoned'] == []
    zone('+00:00')
    r = ingest.run(cfg, con, workers=0)
    assert r['folders_rezoned'] and hours() != before
    assert {h for (h,) in con.execute('SELECT DISTINCT tz_minutes FROM folder_state').fetchall()} == {0}
    assert ingest.run(cfg, con, workers=0)['folders_rezoned'] == []      # once only
