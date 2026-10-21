"""Smoke test for the Pythonista app, using the strict `ui` stand-in in pythonista_stubs/."""

import base64
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUBS = os.path.join(ROOT, 'tests', 'pythonista_stubs')
sys.path.insert(0, ROOT)
sys.path.insert(0, STUBS)

import clipboard  # noqa: E402
import ui  # noqa: E402  (the stand-in, except inside Pythonista)
from horizon import config  # noqa: E402

# Inside Pythonista the real ui module wins, and this test would open the app for real.
STAND_IN = os.path.abspath(getattr(ui, '__file__', '') or '').startswith(STUBS)
if STAND_IN:
    import horizon_app  # noqa: E402


@unittest.skipUnless(STAND_IN, 'runs against the ui stand-in, not inside Pythonista')
class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        horizon_app.STATE_PATH = os.path.join(self.tmp, 'state.json')
        self.operation = config.OPERATION
        config.OPERATION = os.path.join(self.tmp, 'config', 'operation.json')
        del ui.calls[:]
        self.app = horizon_app.main()
        ui.run_delayed()

    def tearDown(self):
        config.OPERATION = self.operation
        clipboard.text = ''
        shutil.rmtree(self.tmp)

    def field(self, rows, key):
        return next(r.field for r in rows if r.key == key)

    def test_calc_tab(self):
        app = self.app
        self.assertEqual(app.headline.text, '20 agents')      # 2:00 patience, abandon capped at 5%
        self.assertIn('Erlang A', app.detail.text)
        self.assertIn('Erlang C (nobody hangs up)', app.calc_report.text)
        self.assertEqual(len(app.cliff.bars), 9)
        app.cliff.draw()
        self.assertTrue(any(c[0] == 'draw_string' and c[1] == '20' for c in ui.calls))

        self.field(app.calc_rows, 'calls').type('200')
        ui.run_delayed()
        self.assertNotEqual(app.headline.text, '20 agents')
        self.assertTrue(app.headline.text.endswith(' agents'))

        self.field(app.calc_rows, 'aht').type('abc')
        ui.run_delayed()
        self.assertEqual(app.headline.text, '-')
        self.assertIn('Check the inputs', app.detail.text)
        app.cliff.draw()

    def test_layout_fits_the_screen(self):
        app = self.app
        tab = app.calc_tab
        self.assertEqual(tab.width, app.width)
        for view, _ in tab.items:
            self.assertGreaterEqual(view.x, 0)
            self.assertLessEqual(view.x + view.width, tab.width)
        last = max(v.y + v.height for v, _ in tab.items if not v.hidden)
        self.assertGreaterEqual(tab.scroll.content_size[1], last)

    def test_whatif_modes(self):
        app = self.app
        app.tabs_control.pick(1)
        for i, mode in enumerate(['AI', 'Pool', 'Move', 'Chat']):
            app.mode_control.pick(i)
            self.assertNotIn('Check the inputs', app.whatif_report.text, mode)
            visible = [r for r in app.mode_rows[mode] if not r.hidden]
            self.assertEqual(len(visible), len(app.mode_rows[mode]))
            others = [r for m, rows in app.mode_rows.items() if m != mode for r in rows]
            self.assertTrue(all(r.hidden for r in others))
        app.mode_control.pick(0)
        self.assertIn('Agents before', app.whatif_report.text)
        self.field(app.mode_rows['AI'], 'contained').type('35')
        ui.run_delayed()
        self.assertIn('Bot contains 35%', app.whatif_report.text)

    def test_sites_tab(self):
        app = self.app
        app.tabs_control.pick(2)
        self.assertIn('Nairobi', app.sites_report.text)
        self.assertIn('These are example sites', app.sites_report.text)
        app.refresh_button.tap()
        self.assertIn('in site time', app.sites_report.text)

    def test_paste_setup_link(self):
        app = self.app
        app.tabs_control.pick(2)
        cfg = {'sites': [{'id': 'SJO', 'name': 'San José', 'zone': 'America/Costa_Rica',
                          'hours': {'mon-fri': '08:00-20:00'}}]}
        code = base64.urlsafe_b64encode(json.dumps(cfg).encode()).decode().rstrip('=')
        clipboard.text = 'https://example.github.io/event-horizon-wfm/#setup=' + code
        app.paste_button.tap()
        self.assertTrue(app.sites_report.text.startswith('Loaded 1 site from your setup link.'))
        self.assertIn('San José', app.sites_report.text)
        self.assertNotIn('example sites', app.sites_report.text)
        with open(config.OPERATION, encoding='utf-8') as f:
            self.assertEqual(json.load(f), cfg)
        again = horizon_app.main()           # the next start reads the saved sites
        self.assertIn('San José', again.sites_report.text)

    def test_paste_something_else(self):
        app = self.app
        app.tabs_control.pick(2)
        clipboard.text = 'Lunch at noon?'
        app.paste_button.tap()
        self.assertTrue(app.sites_report.text.startswith('That setup link could not be used:'))
        self.assertIn('These are example sites', app.sites_report.text)
        self.assertFalse(os.path.exists(config.OPERATION))

    def test_state_is_remembered(self):
        self.field(self.app.calc_rows, 'calls').type('150')
        ui.run_delayed()
        self.app.tabs_control.pick(2)
        with open(horizon_app.STATE_PATH) as f:
            state = json.load(f)
        self.assertEqual(state['calc']['calls'], '150')
        again = horizon_app.main()
        self.assertEqual(again.tabs_control.selected_index, 2)
        self.assertEqual(self.field(again.calc_rows, 'calls').text, '150')

    def test_dark_mode_loads(self):
        ui.style = 'dark'
        try:
            module = importlib.reload(horizon_app)
            module.STATE_PATH = os.path.join(self.tmp, 'dark.json')
            self.assertTrue(module.DARK)
            module.main()
        finally:
            ui.style = 'light'
            importlib.reload(horizon_app)


if __name__ == '__main__':
    unittest.main()
