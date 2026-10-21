"""Command line: python3 -m horizon <command> ...

  calc 100 5:00 --patience 2:00 --goal 80/20 --shrinkage 35 --cost 28
  calc 60 4:00 --patience 1:30 --cost 28 --abandon-cost 75
  contain 100 5:00 --contained 20 --aht-change 10 --assist 0
  pool 120@5:30 80@5:30 40@5:30
  move --from "Customer service" 100@5:00 22 --to Fraud 40@7:00 9 --agents 2 --patience 3:00
  chat 60 --aht 1=6:00 2=8:00 3=14:00 --goal 80/60
  sites [--at 2026-11-04T13:00]
"""

import argparse
import sys
from datetime import datetime

from . import config, report
from .clock import UTC
from .whatif import Queue


def _common(p, goal='80/20'):
    p.add_argument('--interval', default='30', help='interval length, minutes (default 30)')
    p.add_argument('--goal', default=goal, help='service level goal, e.g. 80/20 (default %s)' % goal)
    p.add_argument('--patience', default='', help='average caller patience, e.g. 2:00 (turns on Erlang A)')
    p.add_argument('--max-abandon', default='', help='abandon cap, percent')
    p.add_argument('--max-occupancy', default='', help='occupancy cap, percent')


def _goals(args):
    sl, target = report.parse_goal(args.goal)
    return dict(interval=report.parse_interval(args.interval), sl=sl, target=target,
                patience=report.parse_duration(args.patience))


def _caps(args):
    caps = {}
    if args.max_abandon:
        caps['max_abandon'] = report.parse_percent(args.max_abandon)
    if args.max_occupancy:
        caps['max_occupancy'] = report.parse_percent(args.max_occupancy)
    return caps


def main(argv=None):
    parser = argparse.ArgumentParser(prog='horizon', description='Event Horizon staffing math.')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('calc', help='staffing for one interval')
    p.add_argument('calls')
    p.add_argument('aht', help='average handle time, e.g. 5:00 or 300')
    _common(p)
    p.add_argument('--shrinkage', default='', help='percent')
    p.add_argument('--cost', default='', help='loaded cost per paid agent hour')
    p.add_argument('--abandon-cost', default='', help='cost of one hang-up')

    p = sub.add_parser('contain', help='AI containment and agent assist what-if')
    p.add_argument('calls')
    p.add_argument('aht')
    _common(p)
    p.add_argument('--contained', default='0', help='percent the bot resolves')
    p.add_argument('--recontact', default='0', help='percent of contained that come back')
    p.add_argument('--aht-change', default='0', help='percent change in handle time of what is left')
    p.add_argument('--assist', default='0', help='seconds agent assist takes off each call')
    p.add_argument('--cost', default='', help='loaded cost per paid agent hour')

    p = sub.add_parser('pool', help='separate queues versus one pooled queue')
    p.add_argument('queues', nargs='+', help='CALLS@AHT for each queue, e.g. 120@5:30')
    _common(p)

    p = sub.add_parser('move', help='move agents between two queues')
    p.add_argument('--from', dest='source', nargs=3, metavar=('NAME', 'CALLS@AHT', 'AGENTS'), required=True)
    p.add_argument('--to', dest='dest', nargs=3, metavar=('NAME', 'CALLS@AHT', 'AGENTS'), required=True)
    p.add_argument('--agents', type=int, required=True, help='how many to move')
    p.add_argument('--borrowed-aht', default='', help='handle time of borrowed agents on the new queue')
    _common(p)

    p = sub.add_parser('chat', help='compare chat concurrency levels')
    p.add_argument('chats')
    p.add_argument('--aht', nargs='+', required=True, help='CONCURRENCY=AHT pairs, e.g. 2=8:00')
    _common(p, goal='80/60')

    p = sub.add_parser('sites', help='site clocks, hours and daylight-saving shifts')
    p.add_argument('--at', default='', help='UTC time to show, e.g. 2026-11-04T13:00')
    p.add_argument('--config', default='', help='path to operation.json')

    args = parser.parse_args(argv)
    if args.command == 'calc':
        out = report.calc_report(report.parse_number(args.calls), report.parse_duration(args.aht),
                                 shrinkage=report.parse_percent(args.shrinkage),
                                 cost_per_hour=report.parse_number(args.cost),
                                 cost_per_abandon=report.parse_number(args.abandon_cost),
                                 **_goals(args), **_caps(args))
    elif args.command == 'contain':
        out = report.containment_report(report.parse_number(args.calls), report.parse_duration(args.aht),
                                        contained=report.parse_percent(args.contained) or 0.0,
                                        recontact=report.parse_percent(args.recontact) or 0.0,
                                        aht_change=(report.parse_number(args.aht_change.rstrip('%')) or 0.0) / 100.0,
                                        assist_seconds=report.parse_duration(args.assist) or 0.0,
                                        cost_per_hour=report.parse_number(args.cost),
                                        **_goals(args), **_caps(args))
    elif args.command == 'pool':
        out = report.pooling_report([report.parse_queue(q) for q in args.queues], **_goals(args), **_caps(args))
    elif args.command == 'move':
        g = _goals(args)
        queues = []
        for name, spec, agents in (args.source, args.dest):
            calls, aht = report.parse_queue(spec)
            queues.append(Queue(name, calls, aht, int(agents), g['target'], g['interval'], g['patience']))
        out = report.move_report(queues[0], queues[1], args.agents,
                                 report.parse_duration(args.borrowed_aht))
    elif args.command == 'chat':
        pairs = {}
        for item in args.aht:
            c, h = item.split('=')
            pairs[int(c)] = report.parse_duration(h)
        g = _goals(args)
        out = report.concurrency_report(report.parse_number(args.chats), pairs, g['interval'], g['sl'],
                                        g['target'], g['patience'])
    else:
        at = None
        if args.at:
            at = datetime.fromisoformat(args.at.rstrip('Z')).replace(tzinfo=UTC)
        out = report.sites_report(config.load(args.config or None), now=at)
    print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
