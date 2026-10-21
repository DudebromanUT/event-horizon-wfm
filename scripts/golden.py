#!/usr/bin/env python3
"""Write tests/web/golden.json: the Python engine's answers for a fixed set of cases.

The web app's JavaScript engine must give the same answers (tests/web/engine.test.mjs runs
them), so the phone app and the Python engine can never disagree. Run this after changing
either engine, then commit the new golden.json.

  python3 scripts/golden.py           write the file
  python3 scripts/golden.py --check   fail if the file is out of date (CI)
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from horizon import config, report  # noqa: E402
from horizon.channels import compare_concurrency  # noqa: E402
from horizon.clock import BUILT_IN, Zone  # noqa: E402
from horizon.economics import cheapest_staffing, cost_at, fte, staff_cost  # noqa: E402
from horizon.erlang import erlang_a, erlang_c, required_agents, staffing_table  # noqa: E402
from horizon.whatif import Queue, containment, move_agents, pooling  # noqa: E402

PATH = os.path.join(ROOT, 'tests', 'web', 'golden.json')
UTC = timezone.utc


def clean(value):
    """JSON has no infinity; the JavaScript test reads 'inf' back as Infinity."""
    if isinstance(value, float) and math.isinf(value):
        return 'inf'
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def metrics(m):
    d = m.as_dict()
    return {k: d[k] for k in ('model', 'agents', 'load', 'p_wait', 'sl', 'asa', 'abandon', 'occupancy')}


def utc(text):
    return datetime.strptime(text, '%Y-%m-%dT%H:%M').replace(tzinfo=UTC)


def iso(dt):
    return dt.astimezone(UTC).strftime('%Y-%m-%dT%H:%MZ')


def minutes(offset):
    return int(offset.total_seconds() // 60)


def staffing_cases():
    out = {'erlang_c': [], 'erlang_a': [], 'required': [], 'tables': [], 'cheapest': [], 'money': [],
           'pooling': [], 'containment': [], 'move': [], 'chat': []}
    for args in [(100, 300, 21, 20, 1800), (100, 300, 18, 20, 1800), (80, 330, 19, 20, 1800),
                 (900, 280, 150, 30, 1800), (4, 600, 2, 20, 900), (100, 300, 16, 20, 1800),
                 (0, 300, 5, 20, 1800), (600, 300, 120, 15, 3600), (2500, 240, 360, 20, 1800)]:
        out['erlang_c'].append({'in': args, 'out': metrics(erlang_c(*args))})
    for args in [(100, 300, 19, 120, 20, 1800), (60, 240, 9, 90, 20, 1800), (100, 300, 15, 120, 30, 1800),
                 (30, 500, 6, 300, 60, 1800), (200, 300, 30, 45, 10, 1800), (50, 300, 0, 120, 20, 1800),
                 (100, 300, 20, 120, 0, 1800), (100, 300, 10, 120, 20, 1800), (6000, 300, 936, 180, 20, 1800),
                 (400, 420, 90, 180, 20, 1800), (12.5, 380, 4, 240, 30, 900)]:
        out['erlang_a'].append({'in': args, 'out': metrics(erlang_a(*args))})
    for kw in [dict(calls=100, aht=300), dict(calls=80, aht=330), dict(calls=100, aht=300, patience=120),
               dict(calls=100, aht=300, patience=120, max_abandon=0.03),
               dict(calls=600, aht=300, sl=0.5, max_occupancy=0.85), dict(calls=6000, aht=300, patience=180),
               dict(calls=6000, aht=300, patience=180, max_abandon=0.02), dict(calls=100, aht=300, max_asa=10),
               dict(calls=0, aht=300), dict(calls=60, aht=240, sl=0.9, target=15, patience=90),
               dict(calls=37.5, aht=412, interval=900, sl=0.85, target=30, patience=200, max_occupancy=0.88)]:
        out['required'].append({'in': kw, 'out': metrics(required_agents(**kw))})
    for kw in [dict(calls=100, aht=300, around=19, spread=4, patience=120),
               dict(calls=100, aht=300, around=21, spread=3), dict(calls=10, aht=300, around=2, spread=4)]:
        rows = staffing_table(kw['calls'], kw['aht'], kw['around'], kw['spread'], patience=kw.get('patience'))
        out['tables'].append({'in': kw, 'out': [metrics(r) for r in rows]})
    for args in [(60, 240, 90, 28, 75, 20, 1800, 0.0), (100, 300, 180, 28, 4, 20, 1800, 0.0),
                 (100, 360, 150, 28, 30, 20, 1800, 0.0), (60, 240, 90, 28, 75, 20, 1800, 0.3)]:
        best = cheapest_staffing(*args)
        at10 = cost_at(10, *args)
        out['cheapest'].append({'in': args, 'out': {
            'agents': best.agents, 'staff': best.staff, 'abandons': best.abandons, 'total': best.total,
            'sl': best.metrics.sl, 'abandon': best.metrics.abandon, 'at_10': at10.total}})
    out['money'] = [{'fte': [19, 0.35], 'out': fte(19, 0.35)},
                    {'staff_cost': [10, 28, 1800, 0.3], 'out': staff_cost(10, 28, 1800, 0.3)}]
    for queues, goals in [([(100, 300)] * 3, {}), ([(120, 330), (80, 330), (40, 330)], {}),
                          ([(30, 330), (20, 330), (10, 330)], {}), ([(100, 240), (100, 360)], {'patience': 150}),
                          ([(80, 300), (0, 300), (20, 200)], {'sl': 0.9, 'target': 30})]:
        p = pooling(queues, **goals)
        out['pooling'].append({'in': {'queues': queues, 'goals': goals}, 'out': {
            'separate': [m.agents for m in p.separate], 'pooled': p.pooled.agents, 'pooled_aht': p.pooled.aht,
            'saved': p.saved}})
    for kw in [dict(calls=100, aht=300, contained=0.2), dict(calls=100, aht=300, contained=0.2, aht_change=0.1),
               dict(calls=100, aht=300, assist_seconds=30), dict(calls=100, aht=300, contained=0.2, recontact=0.5),
               dict(calls=600, aht=300, contained=0.2, aht_change=0.1, patience=180, max_abandon=0.05)]:
        r = containment(**kw)
        out['containment'].append({'in': kw, 'out': {
            'before': r.before.agents, 'after': r.after.agents, 'effective': r.effective_containment,
            'calls_after': r.calls_after, 'aht_after': r.aht_after, 'saved': r.saved, 'saved_share': r.saved_share}})
    cs = dict(name='CS', calls=100, aht=300, agents=22, patience=180)
    fraud = dict(name='Fraud', calls=40, aht=420, agents=9, patience=120)
    for n, borrowed in [(2, None), (2, 540), (0, None), (5, 480)]:
        mv = move_agents(Queue(**cs), Queue(**fraud), n, borrowed)
        out['move'].append({'in': {'source': cs, 'dest': fraud, 'n': n, 'borrowed_aht': borrowed}, 'out': {
            k: metrics(getattr(mv, k)) for k in ('source_before', 'source_after', 'dest_before', 'dest_after')}})
    for chats, ahts, sl, target in [(60, {1: 360, 2: 480, 3: 840}, 0.8, 60), (150, {1: 300, 2: 420, 3: 560, 4: 760}, 0.8, 30)]:
        rows = compare_concurrency(chats, ahts, sl, target)
        out['chat'].append({'in': {'chats': chats, 'aht_by_concurrency': {str(k): v for k, v in ahts.items()},
                                   'sl': sl, 'target': target},
                            'out': [{'concurrency': r.concurrency, 'agents': r.agents, 'seats': r.seats.agents}
                                    for r in rows]})
    return out


ZONES = sorted(BUILT_IN) + ['Europe/Paris', 'Australia/Sydney', 'Asia/Kathmandu', 'America/St_Johns',
                            'Pacific/Auckland', 'America/Sao_Paulo']
INSTANTS = ['2026-10-19T06:00', '2026-10-25T00:59', '2026-10-25T01:00', '2026-11-01T05:59', '2026-11-01T06:00',
            '2026-11-01T07:59', '2026-11-01T08:00', '2027-01-15T12:00', '2027-03-14T06:59', '2027-03-14T07:00',
            '2027-03-14T08:59', '2027-03-14T09:00', '2027-03-28T00:59', '2027-03-28T01:00', '2027-04-04T12:00',
            '2027-07-07T12:00']

SEVEN = {
    'anchors': [{'label': '8:00 New York', 'zone': 'America/New_York', 'time': '08:00'},
                {'label': '8:30 London', 'zone': 'Europe/London', 'time': '08:30'}],
    'sites': [
        {'id': 'S1', 'name': 'Site one', 'zone': 'America/Denver', 'hours': {'mon-fri': '07:00-19:00', 'sat': '08:00-16:00'}},
        {'id': 'S2', 'name': 'Site two', 'zone': 'Europe/London', 'hours': {'mon-fri': '08:00-20:00'}},
        {'id': 'S3', 'name': 'Site three', 'zone': 'Africa/Lagos', 'hours': {'mon-sat': '08:00-22:00'}},
        {'id': 'S4', 'name': 'Site four', 'zone': 'Asia/Manila', 'hours': {'daily': '06:00-23:00', 'sun': 'closed'}},
        {'id': 'S5', 'name': 'Site five', 'zone': 'America/Puerto_Rico', 'hours': {'mon-fri': '22:00-06:00'}},
        {'id': 'S6', 'name': 'Site six', 'zone': 'America/Guatemala', 'hours': {'mon-fri': ['06:00-12:00', '13:00-20:00']}},
        {'id': 'S7', 'name': 'Site seven', 'zone': 'Asia/Kolkata', 'hours': {'daily': '24h'}},
    ],
}


def clock_cases():
    out = {'offsets': [], 'changes': [], 'to_utc': [], 'hours': [], 'open': [], 'boards': []}
    for name in ZONES:
        z = Zone(name)
        out['offsets'].append({'zone': name, 'out': [minutes(z.offset(utc(t))) for t in INSTANTS]})
        out['changes'].append({'zone': name, 'out': [[iso(at), minutes(off)] for at, off in
                                                     z.changes(utc('2026-10-19T00:00'), utc('2027-12-31T00:00'))]})
    for name, local in [('America/New_York', '2026-11-01T01:30'), ('America/New_York', '2027-03-14T02:30'),
                        ('America/New_York', '2027-01-05T09:00'), ('Europe/London', '2026-10-25T01:30'),
                        ('Europe/London', '2027-03-28T01:30'), ('America/Denver', '2026-11-01T01:15'),
                        ('Asia/Kolkata', '2027-02-01T08:00'), ('Africa/Lagos', '2026-12-24T23:45')]:
        out['to_utc'].append({'zone': name, 'local': local,
                              'out': iso(Zone(name).to_utc(datetime.strptime(local, '%Y-%m-%dT%H:%M')))})
    for spec in [{'mon-fri': '08:00-20:00', 'sat': '09:00-17:00'}, {'daily': '08:00-20:00', 'sun': 'closed'},
                 {'fri': ['08:00-12:00', '13:00-22:00']}, {'sat-mon': '24h'}, {'mon': '22:00-06:00'}, {}]:
        week = config.parse_hours(spec)
        out['hours'].append({'in': spec, 'out': [week[d] for d in range(7)]})
    for site in SEVEN['sites']:
        s = dict(site, _hours=config.parse_hours(site['hours']))
        for t in ['2027-01-05T07:00', '2027-01-05T12:00', '2027-01-09T07:00', '2027-01-10T07:00', '2027-01-10T16:30',
                  '2027-01-11T05:00', '2027-01-11T11:30', '2027-01-11T18:20']:
            when, opening = config.next_open_change(s, utc(t))
            out['open'].append({'site': site['id'], 'at': t, 'open': config.is_open(s, utc(t)),
                                'next': [iso(when), opening] if when else None})
    example = config.load(os.path.join(config.CONFIG_DIR, 'operation.example.json'))
    seven = dict(SEVEN, sites=[dict(s, _hours=config.parse_hours(s['hours'])) for s in SEVEN['sites']])
    for name, cfg in [('example', example), ('seven', seven)]:
        for t in ['2026-10-20T15:04', '2026-10-28T12:00', '2026-11-04T13:00', '2027-03-20T12:00',
                  '2027-07-07T12:00', '2027-01-09T03:00']:
            board = report.sites_board(cfg, utc(t))
            out['boards'].append({'config': name, 'at': t, 'out': board})
    out['seven'] = SEVEN
    return out


def format_cases():
    return {
        'secs': [[v, report.secs(v)] for v in [0, 16.05, 59.5, 60, 299.6, 3723, 7200]],
        'pct': [[v, d, report.pct(v, d)] for v, d in [(0.8263, 1), (0.0604, 1), (0.795, 0), (1.0, 1), (0.12345, 2)]],
        'money': [[v, report.money(v)] for v in [0, 28, 1234.4, 1234.5, 99999.9, -50]],
    }


def build():
    data = {'_about': 'Generated by scripts/golden.py from the Python engine. Do not edit by hand.',
            'staffing': staffing_cases(), 'clock': clock_cases(), 'format': format_cases()}
    return clean(data)


def close(a, b, path='$'):
    """Same structure; numbers equal to 1e-12 relative (libm can differ in the last digit)."""
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return '%s: keys differ' % path
        for k in a:
            err = close(a[k], b[k], '%s.%s' % (path, k))
            if err:
                return err
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return '%s: lengths differ' % path
        for i, (x, y) in enumerate(zip(a, b)):
            err = close(x, y, '%s[%d]' % (path, i))
            if err:
                return err
        return None
    if isinstance(a, float) or isinstance(b, float):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and \
                abs(a - b) <= 1e-12 * max(1.0, abs(a), abs(b)):
            return None
        return '%s: %r != %r' % (path, a, b)
    return None if a == b else '%s: %r != %r' % (path, a, b)


def main():
    data = build()
    if '--check' in sys.argv[1:]:
        with open(PATH, encoding='utf-8') as f:
            saved = json.load(f)
        err = close(json.loads(json.dumps(data)), saved)
        if err:
            print('tests/web/golden.json is out of date (%s). Run: python3 scripts/golden.py' % err)
            return 1
        print('golden.json is up to date')
        return 0
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write('\n')
    print('wrote', os.path.relpath(PATH, ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
