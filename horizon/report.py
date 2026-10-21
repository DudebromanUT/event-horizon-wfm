"""Phone-width text for each screen, shared by the Pythonista app and the command line.

Lines stay within 44 characters so they fit a phone in portrait in a monospace font.
"""

import math
from datetime import datetime, timedelta

from . import config as configmod
from .channels import compare_concurrency
from .clock import UTC, format_offset, zone
from .economics import cheapest_staffing, cost_at, fte, round_up_fte, staff_cost
from .erlang import required_agents, staffing_table
from .whatif import containment, move_agents, pooling

WIDTH = 44


# --- Parsing what people type -------------------------------------------

def parse_number(text):
    text = str(text).strip().replace(',', '').replace('$', '')
    return float(text) if text else None


def parse_duration(text):
    """'5:00', '300', '5m', '90s', '1h', '1:02:03' -> seconds. Blank -> None."""
    text = str(text).strip().lower()
    if not text:
        return None
    if ':' in text:
        total = 0.0
        for part in text.split(':'):
            total = total * 60 + float(part or 0)
        return total
    for suffix, scale in (('h', 3600.0), ('m', 60.0), ('s', 1.0)):
        if text.endswith(suffix):
            return float(text[:-1]) * scale
    return float(text)


def parse_interval(text):
    """'30', '30m', '15', '1h' -> seconds. A bare number is minutes."""
    text = str(text).strip().lower()
    if not text:
        return 1800.0
    if text[-1].isdigit():
        return float(text) * 60.0
    return parse_duration(text)


def parse_percent(text):
    """'35', '35%', '0.35' -> 0.35. Blank -> None."""
    text = str(text).strip()
    if not text:
        return None
    if text.endswith('%'):
        return float(text[:-1]) / 100.0
    value = float(text)
    return value / 100.0 if value > 1 else value


def parse_goal(text):
    """'80/20' -> (0.8, 20.0). Blank -> (0.8, 20.0)."""
    text = str(text).strip().lower().replace('s', '')
    if not text:
        return 0.8, 20.0
    level, target = text.split('/')
    return parse_percent(level), parse_duration(target)


def parse_queue(text):
    """'120@5:30' -> (120.0, 330.0)."""
    calls, aht = str(text).split('@')
    return parse_number(calls), parse_duration(aht)


# --- Formatting -----------------------------------------------------------

def pct(x, digits=1):
    return '%.*f%%' % (digits, 100.0 * x)


def secs(s):
    if s is None:
        return '-'
    if s == math.inf:
        return 'never'
    s = int(round(s))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return '%d:%02d:%02d' % (h, m, sec) if h else '%d:%02d' % (m, sec)


def money(x):
    return '-$%s' % format(-x, ',.0f') if x < 0 else '$%s' % format(x, ',.0f')


def num(x):
    return ('%d' % x) if float(x).is_integer() else ('%.1f' % x)


def minutes_label(interval):
    m = interval / 60.0
    return '%s min' % num(m) if m < 60 else '%s hr' % num(m / 60.0)


def goal_label(sl, target):
    return '%s/%s' % (num(round(100 * sl, 1)), num(target))


def _row(left, right, width=WIDTH):
    return left + ' ' * max(1, width - len(left) - len(right)) + right


# --- Staffing for one interval -------------------------------------------

TABLE = '%7s %7s %6s %7s %5s'


def headline(calls, aht, interval=1800.0, sl=0.8, target=20.0, patience=None, max_abandon=None,
             max_occupancy=None):
    """The staffing level for the big number at the top of the screen."""
    return required_agents(calls, aht, sl, target, interval, patience, max_occupancy=max_occupancy,
                           max_abandon=max_abandon if patience is not None else None)


def calc_report(calls, aht, interval=1800.0, sl=0.8, target=20.0, patience=None,
                max_abandon=None, max_occupancy=None, shrinkage=None, cost_per_hour=None,
                cost_per_abandon=None, spread=3):
    lines = ['%s calls / %s  AHT %s  goal %s' % (num(calls), minutes_label(interval), secs(aht),
                                               goal_label(sl, target))]
    caps = []
    if max_abandon is not None and patience is not None:
        caps.append('abandon <= %s' % pct(max_abandon, 0))
    if max_occupancy is not None:
        caps.append('occupancy <= %s' % pct(max_occupancy, 0))
    if caps:
        lines.append('and ' + ', '.join(caps))
    c = required_agents(calls, aht, sl, target, interval, None, max_occupancy=max_occupancy)
    lines.append('Workload %.1f Erlangs' % c.load)
    lines.append('')
    lines.append(_row('Erlang C (nobody hangs up)', '%d agents' % c.agents))
    lines.append('  SL %s  ASA %s  Occ %s' % (pct(c.sl), secs(c.asa), pct(c.occupancy, 0)))
    head = c
    if patience is not None:
        a = headline(calls, aht, interval, sl, target, patience, max_abandon, max_occupancy)
        lines.append(_row('Erlang A (patience %s)' % secs(patience), '%d agents' % a.agents))
        lines.append('  SL %s  ASA %s  Aband %s  Occ %s' % (pct(a.sl), secs(a.asa), pct(a.abandon),
                                                         pct(a.occupancy, 0)))
        head = a
        if max_abandon is None and a.abandon > 0.05:
            lines.append('  Watch: %s hang up to hit the goal.' % pct(a.abandon))
            lines.append('  Set a max abandon to stop that.')
    lines.append('')
    lines.append(TABLE % ('Agents', 'SL', 'ASA', 'Aband', 'Occ'))
    for m in staffing_table(calls, aht, head.agents, spread, target, interval, patience):
        mark = '>' if m.agents == head.agents else ' '
        lines.append(TABLE % ('%s %d' % (mark, m.agents), pct(m.sl), secs(m.asa),
                              pct(m.abandon) if patience is not None else '-', pct(m.occupancy, 0)))
    if shrinkage:
        need = fte(head.agents, shrinkage)
        lines.append('')
        lines.append('At %s shrinkage: %.1f FTE scheduled' % (pct(shrinkage, 0), need))
        lines.append('  (%s to hire)' % num(round_up_fte(need)))
    if cost_per_hour:
        lines.append('Agent cost %s per interval' % money(staff_cost(head.agents, cost_per_hour, interval,
                                                                       shrinkage or 0.0)))
    if cost_per_hour and cost_per_abandon and patience is not None:
        best = cheapest_staffing(calls, aht, patience, cost_per_hour, cost_per_abandon, target, interval,
                                 shrinkage or 0.0)
        at_goal = cost_at(head.agents, calls, aht, patience, cost_per_hour, cost_per_abandon, target,
                          interval, shrinkage or 0.0)
        lines.append('')
        lines.append('Cheapest at %s per hang-up:' % money(cost_per_abandon))
        lines.append('  %d agents, SL %s, Aband %s' % (best.agents, pct(best.metrics.sl),
                                                     pct(best.metrics.abandon)))
        lines.append('  %s per interval vs %s at goal' % (money(best.total), money(at_goal.total)))
        lines.append('  (agent cost plus hang-up cost)')
    return '\n'.join(lines)


# --- What-ifs ---------------------------------------------------------------

def containment_report(calls, aht, contained=0.0, aht_change=0.0, assist_seconds=0.0, recontact=0.0,
                       interval=1800.0, sl=0.8, target=20.0, patience=None, cost_per_hour=None,
                       shrinkage=None, **goals):
    r = containment(calls, aht, contained, aht_change, assist_seconds, recontact, sl, target, interval,
                    patience, **goals)
    lines = ['AI what-if: %s calls / %s, AHT %s' % (num(calls), minutes_label(interval), secs(aht)),
             'Goal %s, %s' % (goal_label(sl, target), 'Erlang A' if patience else 'Erlang C'), '']
    if contained:
        lines.append('Bot contains %s; %s of those come back,' % (pct(contained, 0), pct(recontact, 0)))
        lines.append('so %s of calls never reach an agent.' % pct(r.effective_containment, 0))
    if aht_change:
        lines.append('Handle time on what is left: %+.0f%%' % (100 * aht_change))
    if assist_seconds:
        lines.append('Agent assist: %ss off every call' % num(assist_seconds))
    lines.append('Left: %s calls at AHT %s' % (num(round(r.calls_after, 1)), secs(r.aht_after)))
    lines.append('')
    lines.append(_row('Agents before', '%d' % r.before.agents))
    lines.append(_row('Agents after', '%d' % r.after.agents))
    lines.append(_row('Saved', '%d (%s of staff)' % (r.saved, pct(r.saved_share, 0))))
    if cost_per_hour:
        lines.append(_row('Saved per interval', money(staff_cost(r.saved, cost_per_hour, interval,
                                                                 shrinkage or 0.0))))
    return '\n'.join(lines)


POOL = '%-6s %8s %8s %8s'


def pooling_report(queues, interval=1800.0, sl=0.8, target=20.0, patience=None, **goals):
    p = pooling(queues, sl, target, interval, patience, **goals)
    lines = ['Pooling: goal %s, %s' % (goal_label(sl, target), 'Erlang A' if patience else 'Erlang C'), '',
             POOL % ('Queue', 'Calls', 'AHT', 'Agents')]
    kept = [(c, h) for c, h in queues if c > 0]
    for i, ((calls, aht), m) in enumerate(zip(kept, p.separate), 1):
        lines.append(POOL % (i, num(calls), secs(aht), m.agents))
    lines.append(POOL % ('Apart', '', '', p.agents_separate))
    lines.append(POOL % ('Pooled', num(sum(c for c, _ in kept)), secs(p.pooled.aht), p.pooled.agents))
    lines.append('')
    share = p.saved / p.agents_separate if p.agents_separate else 0.0
    lines.append('Pooling saves %d agents (%s).' % (p.saved, pct(share, 0)))
    lines.append('Assumes cross-trained agents keep the')
    lines.append('same handle time.')
    return '\n'.join(lines)


MOVE = '%-16s %6s %7s %7s'


def move_report(source, dest, n, borrowed_aht=None):
    mv = move_agents(source, dest, n, borrowed_aht)
    lines = ['Move %d agents: %s -> %s' % (n, source.name, dest.name), '', MOVE % ('', 'Agents', 'SL', 'Aband')]
    for label, before, after in ((source.name, mv.source_before, mv.source_after),
                                 (dest.name, mv.dest_before, mv.dest_after)):
        for name, m in ((label[:16], before), ('  after', after)):
            lines.append(MOVE % (name, m.agents, pct(m.sl), pct(m.abandon) if m.patience else '-'))
    return '\n'.join(lines)


def concurrency_report(chats, aht_by_concurrency, interval=1800.0, sl=0.8, target=60.0, patience=None):
    rows = compare_concurrency(chats, aht_by_concurrency, sl, target, interval, patience)
    lines = ['Chat: %s chats / %s, goal %s' % (num(chats), minutes_label(interval), goal_label(sl, target)),
             '', '%13s %6s %8s' % ('Chats at once', 'AHT', 'Agents')]
    for r in rows:
        lines.append('%13d %6s %8d' % (r.concurrency, secs(r.aht), r.agents))
    best = min(rows, key=lambda r: (r.agents, r.concurrency))
    lines.append('')
    lines.append('Fewest agents at %d chats at once.' % best.concurrency)
    return '\n'.join(lines)


# --- Sites ------------------------------------------------------------------

DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _clock(local):
    """'Tue 09:04'"""
    return '%s %02d:%02d' % (DAYS[local.weekday()], local.hour, local.minute)


def _date(d):
    """'Sun 25 Oct'"""
    return '%s %d %s' % (DAYS[d.weekday()], d.day, MONTHS[d.month - 1])


def site_status(site, now):
    """'Open until 19:00', 'Closed, opens Mon 08:00', 'Open all week'."""
    z = zone(site['zone'])
    when, opening = configmod.next_open_change(site, now)
    if when is None:
        return 'Open all week' if opening else 'Closed all week'
    at = z.local(when)
    stamp = '%02d:%02d' % (at.hour, at.minute) if at.date() == z.local(now).date() else _clock(at)
    return ('Closed, opens ' if opening else 'Open until ') + stamp


def sites_board(cfg, now=None, weeks=6):
    """Everything the Sites screen shows, as data. The web app builds the same thing in
    JavaScript, and tests/web/golden.json holds this function's output to check it."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    sites = cfg.get('sites', [])
    rows = []
    for s in sites:
        z = zone(s['zone'])
        rows.append({'id': s['id'], 'name': s['name'], 'zone': s['zone'], 'local': _clock(z.local(now)),
                     'offset': format_offset(z.offset(now)), 'open': configmod.is_open(s, now),
                     'status': site_status(s, now)})

    # Every zone that matters: the sites', then the anchors' (customer clocks).
    watched = []
    for s in sites:
        if s['zone'] not in [z for z, _ in watched]:
            watched.append((s['zone'], s['id']))
    for a in cfg.get('anchors', []):
        if a['zone'] not in [z for z, _ in watched]:
            watched.append((a['zone'], a['label'].split(' ', 1)[-1]))
    end = now + timedelta(weeks=weeks)
    found = sorted((instant, label, name, offset)
                   for name, label in watched for instant, offset in zone(name).changes(now, end))
    changes = [{'at': instant.strftime('%Y-%m-%dT%H:%MZ'), 'date': _date(zone(name).local(instant)),
                'label': label, 'offset': format_offset(offset)} for instant, label, name, offset in found]

    anchors = []
    for a in cfg.get('anchors', []):
        az = zone(a['zone'])
        hh, mm = (int(x) for x in a['time'].split(':'))
        candidates, seen = [], set()
        for i, d in enumerate([now] + [c[0] + timedelta(hours=12) for c in found]):
            day = az.local(d).date()
            if day in seen:
                continue
            seen.add(day)
            instant = az.to_utc(datetime(day.year, day.month, day.day, hh, mm))
            cells = [zone(s['zone']).local(instant) for s in sites]
            label = 'now' if i == 0 else 'from %d %s' % (day.day, MONTHS[day.month - 1])
            candidates.append((label, cells))
        # Keep only rows where some site's clock differs from the row before.
        shown = candidates[:1] + [r for p, r in zip(candidates, candidates[1:])
                                  if [(c.hour, c.minute) for c in r[1]] != [(c.hour, c.minute) for c in p[1]]]
        whole = all(c.minute == 0 for _, cells in shown for c in cells)
        fmt = (lambda c: '%02d' % c.hour) if whole else (lambda c: '%02d:%02d' % (c.hour, c.minute))
        anchors.append({'label': a['label'], 'ids': [s['id'] for s in sites],
                        'rows': [{'label': label, 'times': [fmt(c) for c in cells]} for label, cells in shown]})
    return {'heading': '%s %02d:%02d' % (_date(now), now.hour, now.minute), 'sites': rows,
            'weeks': weeks, 'changes': changes, 'anchors': anchors}


def sites_report(cfg, now=None, weeks=6):
    b = sites_board(cfg, now, weeks)
    lines = ['Sites at %s UTC' % b['heading'], '']
    for s in b['sites']:
        lines.append('%-15s %-9s %s' % (s['name'][:15], s['local'], s['offset']))
        lines.append('  ' + s['status'])
    lines.append('')
    if b['changes']:
        lines.append('Clock changes in the next %d weeks' % weeks)
        for c in b['changes']:
            lines.append('  %-10s %s -> %s' % (c['date'], c['label'], c['offset']))
    else:
        lines.append('No clock changes in the next %d weeks.' % weeks)
    for a in b['anchors']:
        width = 1 + max([len(t) for r in a['rows'] for t in r['times']] + [3])
        lines.append('')
        lines.append('%s, in site time' % a['label'])
        lines.append(' ' * 11 + ''.join(('%' + str(width) + 's') % i[:width - 1] for i in a['ids']))
        for r in a['rows']:
            lines.append('%-11s' % r['label'] + ''.join(('%' + str(width) + 's') % t for t in r['times']))
    return '\n'.join(lines)
