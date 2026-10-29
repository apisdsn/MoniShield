"""Local time zone of the monitored site (S4_TIMEZONE_OFFSET / S4_TIMEZONE_LABEL; default +07:00 "WIB").

Log timestamps are stored in UTC; pages, hours, folder dates and daily jobs use this fixed offset. A folder D holds the
logs of (D-1 00:00, D 00:00] local time, like the S3 export. A fixed offset only: no daylight saving time.
`current()` is set once when the server or the CLI starts (`use(from_config(cfg))`). Pure: standard library only.
"""
import dataclasses, datetime, re

DEFAULT_OFFSET, DEFAULT_LABEL = '+07:00', 'WIB'
OFFSET = re.compile(r'(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?')
LABEL = re.compile(r'[A-Za-z][A-Za-z0-9+-]{0,9}')


def parse_offset(text):
    """'+07:00', '+7', 'UTC+5:30', '-03:00', '+0545' -> minutes east of UTC. ValueError when it is not an offset."""
    m = OFFSET.fullmatch((text or '').strip().upper())
    if not m: raise ValueError('not an offset like +07:00')
    h, mm = int(m[2]), int(m[3] or 0)
    if h > 14 or mm > 59 or (h == 14 and mm): raise ValueError('offset must be between -14:00 and +14:00')
    return (h * 60 + mm) * (1 if m[1] == '+' else -1)


def validate(offset, label):
    """-> error message or None."""
    try: parse_offset(offset)
    except ValueError as e: return str(e)
    if not LABEL.fullmatch(label or ''): return 'the label is 1-10 letters, digits, + or - (e.g. WIB, CET, UTC+7)'
    return None


@dataclasses.dataclass(frozen=True)
class Zone:
    minutes: int = 7 * 60
    label: str = DEFAULT_LABEL

    @property
    def delta(self): return datetime.timedelta(minutes=self.minutes)

    @property
    def text(self):
        """'+07:00'"""
        s, m = ('-' if self.minutes < 0 else '+'), abs(self.minutes)
        return f'{s}{m // 60:02d}:{m % 60:02d}'

    def local(self, utc):
        """UTC datetime (naive or aware) -> naive local datetime."""
        if utc.tzinfo: utc = utc.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return utc + self.delta

    def today(self, now_utc): return self.local(now_utc).date()


def from_config(cfg): return Zone(parse_offset(cfg.timezone_offset), cfg.timezone_label)


_current = Zone()


def use(zone):
    global _current
    _current = zone


def current(): return _current
