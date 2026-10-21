"""Staffing by voice: dictated answers, the spoken reply, and the Shortcuts script."""

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from horizon import voice  # noqa: E402


class NumbersTest(unittest.TestCase):
    def values(self, text):
        return [n for n, _ in voice.numbers(text)]

    def test_digits_and_words(self):
        for text, expected in [('600', [600]), ('1,200', [1200]), ('6.5', [6.5]), ('six hundred', [600]),
                               ('twelve hundred', [1200]), ('one thousand two hundred', [1200]),
                               ('one hundred and twenty', [120]), ('a hundred', [100]),
                               ('twenty-five', [25]), ('about 600 calls per half hour', [600]),
                               ('eighty in twenty', [80, 20]), ('eighty twenty', [80, 20]),
                               ('five and a half', [5.5]), ('6 and a half', [6.5]), ('blue', [])]:
            self.assertEqual(self.values(text), expected, text)

    def test_units_stick_to_the_number_before(self):
        self.assertEqual(voice.numbers('six minutes 30 seconds'), [(6, 'minutes'), (30, 'seconds')])
        self.assertEqual(voice.numbers('600 calls per half hour'), [(600, None)])


class ParseTest(unittest.TestCase):
    def test_calls(self):
        for text in ('600', '600.0', 'six hundred', 'About 600 calls.'):
            self.assertEqual(voice.parse_calls(text), 600, text)
        for bad in ('lots', '0', ''):
            with self.assertRaises(ValueError):
                voice.parse_calls(bad)

    def test_handle_time(self):
        for text, expected in [('6:00', 360), ('6:30', 390), ('6 minutes', 360), ('Six minutes.', 360),
                               ('6 minutes 30 seconds', 390), ('6 minutes and 30 seconds', 390), ('6 min 30', 390),
                               ('6 and 30 seconds', 390), ('6.5 minutes', 390), ('five and a half minutes', 330),
                               ('6 and a half minutes', 390), ('five thirty', 330), ('360', 360),
                               ('360 seconds', 360), ('6', 360), ('90s', 90), ('45 seconds', 45),
                               ('1 hour', 3600)]:
            self.assertEqual(voice.parse_handle_time(text), expected, text)
        for bad in ('blue', '5 seconds', '3 hours', '30 seconds 5', ''):
            with self.assertRaises(ValueError):
                voice.parse_handle_time(bad)

    def test_goal(self):
        for text, expected in [('80/20', (80, 20)), ('80 20', (80, 20)), ('80-20', (80, 20)), ('8020', (80, 20)),
                               ('80% in 20 seconds', (80, 20)), ('eighty twenty', (80, 20)),
                               ('Eighty in twenty.', (80, 20)), ('90/30', (90, 30)), ('80/120', (80, 120)),
                               ('80120', (80, 120))]:
            self.assertEqual(voice.parse_goal(text), expected, text)
        for bad in ('80', 'fast', '100/20', '80/0', '0/20', '100', ''):
            with self.assertRaises(ValueError):
                voice.parse_goal(bad)


class ReplyTest(unittest.TestCase):
    def test_answer_reads_back_what_it_heard(self):
        text = voice.reply('600', 'six minutes', 'eighty twenty')
        lines = text.split('\n')
        self.assertEqual(lines[0], '600 calls per half hour, handle time 6 minutes, goal 80% in 20 seconds.')
        self.assertEqual(lines[1], 'You need 129 agents. That answers 80.8% within 20 seconds, '
                                   'with an average wait of 13 seconds and agents 93% busy.')
        self.assertEqual(len(lines), 2)
        self.assertNotIn(':', text)     # '6:00' would be read aloud as a time of day

    def test_occupancy_limit(self):
        text = voice.reply('600', '6:00', '80/20', max_occupancy=0.9)
        self.assertTrue(text.endswith('To keep agents at or under 90% busy, staff 134.'))
        quiet = voice.reply('100', '5:00', '80/20', max_occupancy=0.9)   # 20 agents, 83% busy
        self.assertNotIn('staff', quiet)

    def test_spoken_words(self):
        self.assertEqual(voice.spoken_duration(390), '6 minutes 30 seconds')
        self.assertEqual(voice.spoken_duration(60), '1 minute')
        self.assertEqual(voice.spoken_duration(45), '45 seconds')
        self.assertEqual(voice.interval_label(900), 'per 15 minutes')
        self.assertIn('1 call per hour', voice.reply('1', '3 minutes', '80/20', interval=3600))

    def test_what_it_did_not_catch(self):
        self.assertEqual(voice.reply('600', 'blue', '80/20'),
                         'I didn\'t catch the handle time. Try 6 minutes, 6:30 or 390 seconds. I heard "blue".')
        self.assertTrue(voice.reply('lots', '6:00', '80/20').startswith('I didn\'t catch how many calls.'))
        self.assertTrue(voice.reply('600', '6:00', '80').startswith('I didn\'t catch the goal.'))


class ScriptTest(unittest.TestCase):
    def run_script(self, *args, stdin=None):
        out = subprocess.run([sys.executable, os.path.join(ROOT, 'staffing_shortcut.py')] + list(args),
                             input=stdin, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def test_three_arguments(self):
        out = self.run_script('600', '6 minutes', '80/20')
        self.assertIn('You need 129 agents.', out)
        self.assertIn('staff 134', out)          # the example sites' 90% occupancy limit

    def test_one_argument_split_by_bars_or_lines(self):
        self.assertIn('You need 129 agents.', self.run_script('600 | 6 minutes | 80/20'))
        self.assertIn('You need 129 agents.', self.run_script('600\n6:00\n8020'))

    def test_typed_in_pythonista(self):
        self.assertIn('You need 129 agents.', self.run_script(stdin='600\n6 minutes\n80/20\n'))

    def test_wrong_number_of_answers(self):
        self.assertIn('It passed 2.', self.run_script('600', '6 minutes'))


if __name__ == '__main__':
    unittest.main()
