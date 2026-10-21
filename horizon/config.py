"""Load the operation config: sites, their hours, costs and goals.

The app reads config/operation.json if it exists, otherwise the example next to
it. operation.json is ignored by git, so your real hours and costs stay on your
devices.

Hours are local to each site, 24-hour clock. Keys are day names ('mon'..'sun'),
ranges ('mon-fri', 'sat-sun') or 'daily'; later keys override earlier ones.
Values are 'HH:MM-HH:MM', a list of those, 'closed' or '24h'. A range that ends
at or before it starts runs past midnight ('22:00-06:00').
"""

import json
import os
from datetime import timedelta

from .clock import zone

DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, 'config')


def config_path():
    mine = os.path.join(CONFIG_DIR, 'operation.json')
    return mine if os.path.exists(mine) else os.path.join(CONFIG_DIR, 'operation.example.json')


def load(path=None):
    path = path or config_path()
    with open(path, encoding='utf-8') as f:
        cfg = json.load(f)
    cfg['_path'] = path
    for site in cfg.get('sites', []):
        for key in ('id', 'name', 'zone'):
            if not site.get(key):
                raise ValueError('every site needs %r (check %s)' % (key, path))
        zone(site['zone'])
        site['_hours'] = parse_hours(site.get('hours', {}))
    return cfg


def _minutes(text):
    h, m = text.strip().split(':')
    value = int(h) * 60 + int(m)
    if not 0 <= value <= 24 * 60:
        raise ValueError('bad time %r' % text)
    return value


def _ranges(value):
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_ranges(v))
        return out
    text = value.strip().lower()
    if text == 'closed':
        return []
    if text == '24h':
        return [(0, 24 * 60)]
    start, end = (_minutes(p) for p in text.split('-'))
    if end <= start:
        end += 24 * 60
    return [(start, end)]


def _days(key):
    key = key.strip().lower()
    if key == 'daily':
        return list(range(7))
    if '-' in key:
        a, b = key.split('-')
        i, j = DAYS.index(a), DAYS.index(b)
        return list(range(i, j + 1)) if i <= j else list(range(i, 7)) + list(range(0, j + 1))
    return [DAYS.index(key)]


def parse_hours(spec):
    """{'mon-fri': '08:00-20:00', 'sat': '09:00-17:00'} -> {0: [(480, 1200)], ...}"""
    week = {d: [] for d in range(7)}
    for key, value in spec.items():
        if key.startswith('_'):
            continue
        for d in _days(key):
            week[d] = _ranges(value)
    return week


def is_open(site, when):
    """Is the site open at the aware instant `when`?"""
    local = zone(site['zone']).local(when)
    minute = local.hour * 60 + local.minute
    week = site['_hours']
    if any(s <= minute < e for s, e in week[local.weekday()]):
        return True
    yesterday = week[(local.weekday() - 1) % 7]
    return any(s <= minute + 24 * 60 < e for s, e in yesterday)


def next_open_change(site, when, horizon_days=8):
    """Next instant the site opens or closes, scanning in 15-minute steps."""
    state = is_open(site, when)
    t = when.replace(second=0, microsecond=0)
    t -= timedelta(minutes=t.minute % 15)
    end = when + timedelta(days=horizon_days)
    while t < end:
        t += timedelta(minutes=15)
        if is_open(site, t) != state:
            return t, not state
    return None, state
