import contextlib
import io
import math
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from horizon import config, report
from horizon.__main__ import main
from horizon.whatif import Queue

NOW = datetime(2026, 10, 20, 15, 4, tzinfo=timezone.utc)


def widest(text):
    return max(len(line) for line in text.splitlines())


class ParseTest(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(report.parse_duration('5:00'), 300)
        self.assertEqual(report.parse_duration('300'), 300)
        self.assertEqual(report.parse_duration('5m'), 300)
        self.assertEqual(report.parse_duration('4.5m'), 270)
        self.assertEqual(report.parse_duration('90s'), 90)
        self.assertEqual(report.parse_duration('1h'), 3600)
        self.assertEqual(report.parse_duration('1:02:03'), 3723)
        self.assertIsNone(report.parse_duration(' '))

    def test_goals_percents_intervals(self):
        self.assertEqual(report.parse_goal('80/20'), (0.8, 20))
        self.assertEqual(report.parse_goal('90/15s'), (0.9, 15))
        self.assertEqual(report.parse_goal(''), (0.8, 20))
        self.assertEqual(report.parse_percent('35'), 0.35)
        self.assertEqual(report.parse_percent('35%'), 0.35)
        self.assertEqual(report.parse_percent('0.35'), 0.35)
        self.assertEqual(report.parse_interval('30'), 1800)
        self.assertEqual(report.parse_interval('15m'), 900)
        self.assertEqual(report.parse_interval('1h'), 3600)
        self.assertEqual(report.parse_queue('120@5:30'), (120, 330))
        self.assertEqual(report.parse_number('$1,250'), 1250)

    def test_formatting(self):
        self.assertEqual(report.secs(16.05), '0:16')
        self.assertEqual(report.secs(3723), '1:02:03')
        self.assertEqual(report.secs(math.inf), 'never')
        self.assertEqual(report.money(1234.4), '$1,234')
        self.assertEqual(report.money(-50), '-$50')
        self.assertEqual(report.pct(0.8263), '82.6%')
        self.assertEqual(report.goal_label(0.8, 20), '80/20')


class ReportTest(unittest.TestCase):
    def test_calc(self):
        text = report.calc_report(100, 300, patience=120, shrinkage=0.35, cost_per_hour=28)
        self.assertIn('Erlang C (nobody hangs up)', text)
        self.assertRegex(text, r'Erlang C .* 21 agents')
        self.assertRegex(text, r'Erlang A .* 19 agents')
        self.assertIn('Watch: 6.0% hang up', text)
        self.assertIn('29.2 FTE scheduled', text)
        self.assertLessEqual(widest(text), report.WIDTH)

    def test_calc_money(self):
        text = report.calc_report(60, 240, patience=90, cost_per_hour=28, cost_per_abandon=75)
        self.assertIn('15 agents, SL 99.2%, Aband 0.3%', text)
        self.assertIn('$225 per interval vs $476 at goal', text)
        self.assertLessEqual(widest(text), report.WIDTH)

    def test_what_ifs(self):
        text = report.containment_report(100, 300, contained=0.2, aht_change=0.1)
        self.assertRegex(text, r'Agents before +21')
        self.assertRegex(text, r'Agents after +19')
        pool = report.pooling_report([(120, 330), (80, 330), (40, 330)])
        self.assertIn('Pooling saves 7 agents (12%).', pool)
        move = report.move_report(Queue('Customer service', 100, 300, 22, patience=180),
                                  Queue('Fraud', 40, 420, 9, patience=120), 2)
        self.assertIn('Customer service', move)
        chat = report.concurrency_report(60, {1: 360, 2: 480, 3: 840})
        self.assertIn('Fewest agents at 2 chats at once.', chat)
        for t in (text, pool, move, chat):
            self.assertLessEqual(widest(t), report.WIDTH)

    def test_sites(self):
        cfg = config.load(os.path.join(config.CONFIG_DIR, 'operation.example.json'))
        text = report.sites_report(cfg, now=NOW)
        self.assertIn('Sun 25 Oct LON -> UTC+0', text)
        self.assertIn('Sun 1 Nov  New York -> UTC-5', text)
        lines = text.splitlines()
        ny = lines.index('8:00 New York, in site time')
        self.assertEqual(lines[ny + 1].split(), ['DEN', 'LON', 'BOG', 'MNL', 'NBO'])
        self.assertEqual(lines[ny + 2].split(), ['now', '06', '13', '07', '20', '15'])
        self.assertEqual(lines[ny + 3].split(), ['from', '25', 'Oct', '06', '12', '07', '20', '15'])
        self.assertEqual(lines[ny + 4].split(), ['from', '1', 'Nov', '06', '13', '08', '21', '16'])
        self.assertLessEqual(widest(text), report.WIDTH)


class CommandLineTest(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(list(argv)), 0)
        return out.getvalue()

    def test_commands(self):
        self.assertRegex(self.run_cli('calc', '100', '5:00'), r'Erlang C .* 21 agents')
        self.assertIn('Saved', self.run_cli('contain', '100', '5:00', '--contained', '20', '--aht-change', '10%'))
        self.assertIn('Pooled', self.run_cli('pool', '100@5:00', '100@5:00'))
        self.assertIn('Fraud', self.run_cli('move', '--from', 'CS', '100@5:00', '22', '--to', 'Fraud',
                                            '40@7:00', '9', '--agents', '2', '--patience', '3:00'))
        self.assertIn('Chats at once', self.run_cli('chat', '60', '--aht', '2=8:00', '3=14:00'))
        self.assertIn('Nairobi', self.run_cli('sites', '--at', '2026-11-04T13:00Z',
                                             '--config', os.path.join(config.CONFIG_DIR, 'operation.example.json')))


if __name__ == '__main__':
    unittest.main()
