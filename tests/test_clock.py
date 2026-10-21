import base64
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from horizon import config
from horizon.clock import BUILT_IN, UTC, Zone, format_offset, hours, zone

try:
    import zoneinfo
    zoneinfo.ZoneInfo('Europe/London')
    HAVE_ZONEINFO = True
except Exception:
    HAVE_ZONEINFO = False


def utc(*args):
    return datetime(*args, tzinfo=UTC)


class BuiltInRulesTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_ZONEINFO, 'needs a zoneinfo database to compare against')
    def test_built_in_rules_match_zoneinfo(self):
        start, end = utc(2008, 1, 1), utc(2036, 1, 1)
        for name in BUILT_IN:
            built_in, system = Zone(name, use_zoneinfo=False), Zone(name)
            self.assertEqual(built_in.changes(start, end), system.changes(start, end), name)
            t = utc(2026, 1, 1, 12)
            while t < utc(2028, 1, 1):
                self.assertEqual(built_in.offset(t), system.offset(t), (name, t))
                t += timedelta(hours=13)

    def test_this_years_changes(self):
        for use_zoneinfo in ([False, True] if HAVE_ZONEINFO else [False]):
            london = Zone('Europe/London', use_zoneinfo)
            denver = Zone('America/Denver', use_zoneinfo)
            lagos = Zone('Africa/Lagos', use_zoneinfo)
            after = utc(2026, 10, 19)
            self.assertEqual(london.next_change(after), (utc(2026, 10, 25, 1), timedelta(0)))
            self.assertEqual(denver.next_change(after), (utc(2026, 11, 1, 8), timedelta(hours=-7)))
            self.assertIsNone(lagos.next_change(after))
            self.assertEqual(london.next_change(utc(2026, 11, 2))[0], utc(2027, 3, 28, 1))
            self.assertEqual(denver.next_change(utc(2026, 11, 2))[0], utc(2027, 3, 14, 9))

    def test_winter_shift_against_new_york(self):
        ny, pr = zone('America/New_York'), zone('America/Puerto_Rico')
        summer = ny.to_utc(datetime(2027, 7, 7, 8, 0))
        winter = ny.to_utc(datetime(2026, 11, 4, 8, 0))
        self.assertEqual(pr.local(summer).hour, 8)
        self.assertEqual(pr.local(winter).hour, 9)
        self.assertEqual(zone('Africa/Nairobi').local(winter).hour, 16)
        self.assertEqual(zone('America/Guatemala').local(winter).hour, 7)

    def test_gap_and_repeated_hour(self):
        for use_zoneinfo in ([False, True] if HAVE_ZONEINFO else [False]):
            ny = Zone('America/New_York', use_zoneinfo)
            self.assertEqual(ny.to_utc(datetime(2026, 11, 1, 1, 30)), utc(2026, 11, 1, 5, 30))
            self.assertEqual(ny.to_utc(datetime(2027, 3, 14, 2, 30)), utc(2027, 3, 14, 7, 30))
            self.assertEqual(ny.to_utc(datetime(2027, 1, 5, 9, 0)), utc(2027, 1, 5, 14, 0))

    def test_formatting(self):
        self.assertEqual(format_offset(timedelta(hours=-6)), 'UTC-6')
        self.assertEqual(format_offset(timedelta(hours=5, minutes=30)), 'UTC+5:30')
        self.assertEqual(format_offset(timedelta(0)), 'UTC+0')
        self.assertEqual(hours(timedelta(hours=-4)), -4.0)
        with self.assertRaises(ValueError):
            Zone('Mars/Olympus_Mons', use_zoneinfo=False)


class ConfigTest(unittest.TestCase):
    def test_example_loads(self):
        cfg = config.load(os.path.join(config.CONFIG_DIR, 'operation.example.json'))
        names = [s['name'] for s in cfg['sites']]
        self.assertEqual(len(names), 5)
        self.assertIn('Nairobi', names)

    def test_setup_link(self):
        cfg = {'note': 'Two sites', 'sites': [
            {'id': 'SJO', 'name': 'San José', 'zone': 'America/Costa_Rica', 'hours': {'mon-fri': '08:00-20:00'}},
            {'id': 'KGL', 'name': 'Kigali', 'zone': 'Africa/Kigali', 'hours': {'daily': '24h'}}]}
        # The web app's encoding: compact JSON as UTF-8, then base64url without padding.
        compact = json.dumps(cfg, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        code = base64.urlsafe_b64encode(compact).decode().rstrip('=')
        for text in ('https://example.github.io/event-horizon-wfm/#setup=' + code,
                     ' #setup=%s\n%s ' % (code[:40], code[40:]), json.dumps(cfg)):
            got = config.read_setup(text)
            self.assertEqual(got['sites'][0]['name'], 'San José')
            self.assertEqual(got['sites'][1]['_hours'][0], [(0, 1440)])
        for bad in ('Lunch at noon?', '#setup=!!!', '[1, 2]', '{"sites": []}',
                    '{"sites": [{"id": "X", "name": "X", "zone": "Mars/Olympus_Mons"}]}'):
            with self.assertRaises(ValueError):
                config.read_setup(bad)

    def test_save(self):
        tmp = tempfile.mkdtemp()
        try:
            cfg = config.read_setup('{"sites": [{"id": "SJO", "name": "San José", "zone": "America/Costa_Rica"}]}')
            path = config.save(cfg, os.path.join(tmp, 'config', 'operation.json'))
            with open(path, encoding='utf-8') as f:
                text = f.read()
            self.assertIn('San José', text)
            self.assertNotIn('_hours', text)
            self.assertEqual(config.load(path)['sites'][0]['_hours'][0], [])
            self.assertEqual(os.listdir(os.path.dirname(path)), ['operation.json'])
        finally:
            shutil.rmtree(tmp)

    def test_hours(self):
        week = config.parse_hours({'daily': '08:00-20:00', 'sun': 'closed', 'fri': ['08:00-12:00', '13:00-22:00']})
        self.assertEqual(week[0], [(480, 1200)])
        self.assertEqual(week[6], [])
        self.assertEqual(week[4], [(480, 720), (780, 1320)])
        self.assertEqual(config.parse_hours({'sat-mon': '24h'})[0], [(0, 1440)])
        self.assertEqual(config.parse_hours({'mon': '22:00-06:00'})[0], [(1320, 1800)])

    def test_open_and_overnight(self):
        site = {'zone': 'America/Puerto_Rico', '_hours': config.parse_hours({'mon-fri': '22:00-06:00'})}
        # Tuesday 2027-01-05 03:00 in Puerto Rico is 07:00 UTC: still Monday night's shift.
        self.assertTrue(config.is_open(site, utc(2027, 1, 5, 7)))
        self.assertFalse(config.is_open(site, utc(2027, 1, 5, 12)))
        # Saturday 03:00 local belongs to Friday night's shift.
        self.assertTrue(config.is_open(site, utc(2027, 1, 9, 7)))
        self.assertFalse(config.is_open(site, utc(2027, 1, 10, 7)))
        when, opening = config.next_open_change(site, utc(2027, 1, 5, 12))
        self.assertTrue(opening)
        self.assertEqual(when, utc(2027, 1, 6, 2))     # 22:00 Tuesday local


if __name__ == '__main__':
    unittest.main()
