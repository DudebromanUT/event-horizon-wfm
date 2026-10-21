"""Site clocks: local time, UTC offsets and daylight-saving changes.

Uses the system time zone database (zoneinfo) when there is one. Pythonista on
iOS may not expose it, so the zones Event Horizon uses are also built in: fixed
offsets for places without daylight saving, and the current US and EU rules for
the rest. Tests check the built-in rules against zoneinfo hour by hour.
"""

from datetime import datetime, timedelta, timezone

UTC = timezone.utc

# zone: (standard offset in hours, daylight-saving rule or None). Common contact-center zones whose
# rules haven't changed since 2008; any other zone works wherever the system has a zoneinfo database.
BUILT_IN = {
    'UTC': (0, None),
    # Europe: the EU rule
    'Europe/London': (0, 'EU'), 'Europe/Dublin': (0, 'EU'), 'Europe/Lisbon': (0, 'EU'),
    'Europe/Madrid': (1, 'EU'), 'Europe/Paris': (1, 'EU'), 'Europe/Berlin': (1, 'EU'), 'Europe/Rome': (1, 'EU'),
    'Europe/Warsaw': (1, 'EU'), 'Europe/Athens': (2, 'EU'), 'Europe/Bucharest': (2, 'EU'), 'Europe/Sofia': (2, 'EU'),
    # Africa and the Middle East: no daylight saving
    'Africa/Accra': (0, None), 'Africa/Lagos': (1, None), 'Africa/Johannesburg': (2, None), 'Africa/Kigali': (2, None),
    'Africa/Nairobi': (3, None), 'Asia/Dubai': (4, None),
    # Asia and Australia: no daylight saving
    'Asia/Kolkata': (5.5, None), 'Asia/Kathmandu': (5.75, None), 'Asia/Jakarta': (7, None),
    'Asia/Ho_Chi_Minh': (7, None), 'Asia/Manila': (8, None), 'Asia/Singapore': (8, None),
    'Asia/Kuala_Lumpur': (8, None), 'Asia/Shanghai': (8, None), 'Asia/Tokyo': (9, None),
    'Australia/Brisbane': (10, None),
    # North America: the US rule (Canada follows it)
    'America/Halifax': (-4, 'US'), 'America/New_York': (-5, 'US'), 'America/Toronto': (-5, 'US'),
    'America/Chicago': (-6, 'US'), 'America/Denver': (-7, 'US'), 'America/Los_Angeles': (-8, 'US'),
    'America/Anchorage': (-9, 'US'), 'America/Phoenix': (-7, None), 'Pacific/Honolulu': (-10, None),
    # Caribbean, Central and South America: no daylight saving
    'America/Puerto_Rico': (-4, None), 'America/Santo_Domingo': (-4, None), 'America/Jamaica': (-5, None),
    'America/Panama': (-5, None), 'America/Bogota': (-5, None), 'America/Lima': (-5, None),
    'America/Guatemala': (-6, None), 'America/El_Salvador': (-6, None), 'America/Tegucigalpa': (-6, None),
    'America/Managua': (-6, None), 'America/Costa_Rica': (-6, None), 'America/Belize': (-6, None),
}


def _nth_sunday(year, month, n):
    first = datetime(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def _last_sunday(year, month):
    nxt = datetime(year + month // 12, month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() + 1) % 7)


def _dst_window_utc(rule, std_hours, year):
    """Daylight saving start and end for `year`, as naive UTC datetimes."""
    if rule == 'US':    # 2:00 local on the 2nd Sunday of March to 2:00 local on the 1st Sunday of November
        start = _nth_sunday(year, 3, 2) + timedelta(hours=2 - std_hours)
        end = _nth_sunday(year, 11, 1) + timedelta(hours=2 - (std_hours + 1))
    elif rule == 'EU':  # 1:00 UTC on the last Sunday of March to 1:00 UTC on the last Sunday of October
        start = _last_sunday(year, 3) + timedelta(hours=1)
        end = _last_sunday(year, 10) + timedelta(hours=1)
    else:
        raise ValueError('unknown rule %r' % rule)
    return start, end


class Zone:
    """A time zone that answers 'what is the UTC offset at this instant?'."""

    def __init__(self, name, use_zoneinfo=True):
        self.name = name
        self._info = None
        self._rule = None
        if use_zoneinfo:
            try:
                from zoneinfo import ZoneInfo
                self._info = ZoneInfo(name)
            except Exception:
                pass
        if self._info is None:
            if name not in BUILT_IN:
                raise ValueError('unknown time zone %r (no zoneinfo database and not built in)' % name)
            self._rule = BUILT_IN[name]

    @property
    def source(self):
        return 'zoneinfo' if self._info is not None else 'built-in'

    def offset(self, when):
        """UTC offset (timedelta) in effect at the aware datetime `when`."""
        when = when.astimezone(UTC)
        if self._info is not None:
            return when.astimezone(self._info).utcoffset()
        std, rule = self._rule
        if rule is None:
            return timedelta(hours=std)
        start, end = _dst_window_utc(rule, std, when.year)
        naive = when.replace(tzinfo=None)
        return timedelta(hours=std + 1) if start <= naive < end else timedelta(hours=std)

    def local(self, when):
        """The aware local time at this zone for the instant `when`."""
        return when.astimezone(timezone(self.offset(when)))

    def to_utc(self, local_naive):
        """UTC instant for a wall-clock time here. In the spring-forward gap the earlier
        offset is used; in the repeated autumn hour, the first occurrence."""
        guess = local_naive.replace(tzinfo=UTC)
        for probe in (guess - timedelta(hours=12), guess + timedelta(hours=12)):
            off = self.offset(probe)
            candidate = (local_naive - off).replace(tzinfo=UTC)
            if self.offset(candidate) == off:
                return candidate
        return (local_naive - self.offset(guess)).replace(tzinfo=UTC)

    def changes(self, start, end):
        """Instants between `start` and `end` (aware) when the UTC offset changes, as
        (instant, new offset). Scans a day at a time, then finds the hour of the change."""
        out = []
        t = start.astimezone(UTC)
        end = end.astimezone(UTC)
        prev = self.offset(t)
        while t < end:
            nxt = min(t + timedelta(days=1), end)
            off = self.offset(nxt)
            if off != prev:
                h = t.replace(minute=0, second=0, microsecond=0)
                while self.offset(h) != off:
                    h += timedelta(hours=1)
                out.append((h, off))
                prev = off
            t = nxt
        return out

    def next_change(self, after, within_days=400):
        found = self.changes(after, after + timedelta(days=within_days))
        return found[0] if found else None


_cache = {}


def zone(name):
    if name not in _cache:
        _cache[name] = Zone(name)
    return _cache[name]


def hours(offset):
    """timedelta offset as hours, e.g. -6.0."""
    return offset.total_seconds() / 3600.0


def format_offset(offset):
    total = int(offset.total_seconds() // 60)
    sign = '+' if total >= 0 else '-'
    h, m = divmod(abs(total), 60)
    return 'UTC%s%d' % (sign, h) + (':%02d' % m if m else '')
