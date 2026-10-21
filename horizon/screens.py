"""What each app screen computes, kept apart from the Pythonista `ui` code so it can be
tested anywhere. Every screen takes the text people typed (a dict of strings) and
returns what to show."""

from . import config as configmod
from . import report
from .erlang import staffing_table
from .whatif import Queue

# (key, label, default, hint)
CALC_FIELDS = [
    ('calls', 'Calls per interval', '100', ''),
    ('aht', 'Handle time (AHT)', '5:00', 'm:ss'),
    ('interval', 'Interval, minutes', '30', ''),
    ('goal', 'Goal (SL/seconds)', '80/20', ''),
    ('patience', 'Caller patience', '2:00', 'blank = Erlang C'),
    ('max_abandon', 'Max abandon %', '5', 'optional'),
    ('max_occupancy', 'Max occupancy %', '90', 'optional'),
    ('shrinkage', 'Shrinkage %', '35', 'optional'),
    ('cost', 'Cost per agent hour', '', 'optional'),
    ('abandon_cost', 'Cost per hang-up', '', 'optional'),
]

WHATIF_MODES = ['AI', 'Pool', 'Move', 'Chat']

WHATIF_FIELDS = {
    'AI': [
        ('calls', 'Calls per interval', '100', ''),
        ('aht', 'Handle time (AHT)', '5:00', 'm:ss'),
        ('goal', 'Goal (SL/seconds)', '80/20', ''),
        ('patience', 'Caller patience', '', 'blank = Erlang C'),
        ('contained', 'Bot contains %', '20', ''),
        ('recontact', 'Of those, come back %', '0', ''),
        ('aht_change', 'Handle time change %', '10', 'harder calls left'),
        ('assist', 'Agent assist, seconds', '0', 'off every call'),
        ('cost', 'Cost per agent hour', '', 'optional'),
    ],
    'Pool': [
        ('queues', 'Queues (calls@AHT)', '120@5:30, 80@5:30, 40@5:30', ''),
        ('goal', 'Goal (SL/seconds)', '80/20', ''),
        ('patience', 'Caller patience', '', 'blank = Erlang C'),
    ],
    'Move': [
        ('from_name', 'From queue', 'Customer service', ''),
        ('from_queue', 'Its calls@AHT', '100@5:00', ''),
        ('from_agents', 'Its agents', '22', ''),
        ('to_name', 'To queue', 'Fraud', ''),
        ('to_queue', 'Its calls@AHT', '40@7:00', ''),
        ('to_agents', 'Its agents', '9', ''),
        ('move', 'Agents to move', '2', ''),
        ('borrowed_aht', 'Their AHT there', '', 'blank = same'),
        ('patience', 'Caller patience', '3:00', 'blank = Erlang C'),
        ('goal', 'Goal (SL/seconds)', '80/20', ''),
    ],
    'Chat': [
        ('chats', 'Chats per interval', '60', ''),
        ('aht_by_concurrency', 'AHT at N chats', '1=6:00, 2=8:00, 3=14:00', 'N=m:ss, ...'),
        ('goal', 'Goal (SL/seconds)', '80/60', ''),
        ('patience', 'Customer patience', '', 'blank = Erlang C'),
    ],
}


def defaults(fields, cfg=None):
    values = {key: default for key, _, default, _ in fields}
    goals = (cfg or {}).get('goals', {})
    if 'max_abandon' in values and goals.get('max_abandon') is not None:
        values['max_abandon'] = report.num(round(100 * goals['max_abandon'], 1))
    if 'max_occupancy' in values and goals.get('max_occupancy') is not None:
        values['max_occupancy'] = report.num(round(100 * goals['max_occupancy'], 1))
    return values


def _text(values, key):
    return str(values.get(key, '') or '').strip()


def calc(values):
    """-> dict(headline, detail, bars, goal, report). `bars` feeds the cliff chart:
    (agents, service level, is the recommended level)."""
    calls = report.parse_number(_text(values, 'calls'))
    aht = report.parse_duration(_text(values, 'aht'))
    if calls is None or not aht:
        raise ValueError('Enter calls and handle time.')
    interval = report.parse_interval(_text(values, 'interval'))
    sl, target = report.parse_goal(_text(values, 'goal'))
    patience = report.parse_duration(_text(values, 'patience'))
    max_abandon = report.parse_percent(_text(values, 'max_abandon'))
    max_occupancy = report.parse_percent(_text(values, 'max_occupancy'))
    m = report.headline(calls, aht, interval, sl, target, patience, max_abandon, max_occupancy)
    parts = ['Erlang A' if patience else 'Erlang C', 'SL ' + report.pct(m.sl), 'ASA ' + report.secs(m.asa)]
    if patience:
        parts.append('Aband ' + report.pct(m.abandon))
    parts.append('Occ ' + report.pct(m.occupancy, 0))
    rows = staffing_table(calls, aht, m.agents, 4, target, interval, patience)
    text = report.calc_report(calls, aht, interval, sl, target, patience, max_abandon, max_occupancy,
                              report.parse_percent(_text(values, 'shrinkage')),
                              report.parse_number(_text(values, 'cost')),
                              report.parse_number(_text(values, 'abandon_cost')))
    return {'headline': '%d agents' % m.agents, 'detail': '  '.join(parts),
            'bars': [(r.agents, r.sl, r.agents == m.agents) for r in rows], 'goal': sl, 'report': text}


def _queue(text):
    return report.parse_queue(text.replace(' ', ''))


def whatif(mode, values):
    sl, target = report.parse_goal(_text(values, 'goal'))
    patience = report.parse_duration(_text(values, 'patience'))
    if mode == 'AI':
        return report.containment_report(
            report.parse_number(_text(values, 'calls')), report.parse_duration(_text(values, 'aht')),
            contained=report.parse_percent(_text(values, 'contained')) or 0.0,
            aht_change=(report.parse_number(_text(values, 'aht_change').rstrip('%')) or 0.0) / 100.0,
            assist_seconds=report.parse_duration(_text(values, 'assist')) or 0.0,
            recontact=report.parse_percent(_text(values, 'recontact')) or 0.0,
            sl=sl, target=target, patience=patience, cost_per_hour=report.parse_number(_text(values, 'cost')))
    if mode == 'Pool':
        queues = [_queue(q) for q in _text(values, 'queues').split(',') if q.strip()]
        return report.pooling_report(queues, sl=sl, target=target, patience=patience)
    if mode == 'Move':
        source = Queue(_text(values, 'from_name') or 'From', *_queue(_text(values, 'from_queue')),
                       agents=int(report.parse_number(_text(values, 'from_agents'))), target=target,
                       patience=patience)
        dest = Queue(_text(values, 'to_name') or 'To', *_queue(_text(values, 'to_queue')),
                     agents=int(report.parse_number(_text(values, 'to_agents'))), target=target,
                     patience=patience)
        return report.move_report(source, dest, int(report.parse_number(_text(values, 'move'))),
                                  report.parse_duration(_text(values, 'borrowed_aht')))
    if mode == 'Chat':
        pairs = {}
        for item in _text(values, 'aht_by_concurrency').split(','):
            if item.strip():
                c, h = item.split('=')
                pairs[int(c)] = report.parse_duration(h)
        return report.concurrency_report(report.parse_number(_text(values, 'chats')), pairs, sl=sl,
                                         target=target, patience=patience)
    raise ValueError('unknown what-if %r' % mode)


def sites(cfg=None, now=None):
    cfg = cfg or configmod.load()
    text = report.sites_report(cfg, now)
    name = cfg['_path'].replace('\\', '/').split('/')[-1]
    if name == 'operation.example.json':
        text += '\n\nUsing the example sites. Copy\nconfig/operation.example.json to\nconfig/operation.json and edit it.'
    return text
