"""The Pythonista installer, with stand-ins for console, keychain and the GitHub download."""

import importlib.util
import io
import os
import shutil
import sys
import tempfile
import types
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER = os.path.join(ROOT, 'pythonista', 'install_event_horizon.py')


def zipball(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('DudebromanUT-event-horizon-wfm-abc123/', '')
        for name, body in files.items():
            z.writestr('DudebromanUT-event-horizon-wfm-abc123/' + name, body)
    return buf.getvalue()


class Response(object):
    def __init__(self, status, content=b''):
        self.status_code, self.content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.keys, self.alerts, self.requests_made = {}, [], []
        self.private = False
        self.response = Response(200, zipball({'horizon_app.py': 'print(1)\n', 'horizon/erlang.py': '# engine\n',
                                               '../escape.py': 'nope'}))
        console = types.SimpleNamespace(
            input_alert=lambda title, message='', text='', ok='OK', hide_cancel_button=False: ' tok123 ',
            alert=lambda *a, **k: self.alerts.append(a),
            hud_alert=lambda message, *a, **k: self.alerts.append(message))
        keychain = types.SimpleNamespace(
            get_password=lambda s, a: self.keys.get((s, a)),
            set_password=lambda s, a, p: self.keys.__setitem__((s, a), p),
            delete_password=lambda s, a: self.keys.pop((s, a), None))
        requests = types.SimpleNamespace(get=self.fake_get)
        self.saved = {name: sys.modules.get(name) for name in ('console', 'keychain', 'requests')}
        sys.modules.update(console=console, keychain=keychain, requests=requests)
        spec = importlib.util.spec_from_file_location('install_event_horizon', INSTALLER)
        self.installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.installer)
        self.installer.DEST = os.path.join(self.tmp, 'event-horizon')

    def tearDown(self):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        shutil.rmtree(self.tmp)

    def fake_get(self, url, headers=None, timeout=None):
        self.requests_made.append((url, headers))
        if self.private and 'Authorization' not in headers:
            return Response(404)
        return self.response

    def test_public_repo_needs_no_token(self):
        dest = self.installer.DEST
        os.makedirs(os.path.join(dest, 'config'))
        with open(os.path.join(dest, 'config', 'operation.json'), 'w') as f:
            f.write('{"mine": true}')
        self.installer.main()
        url, headers = self.requests_made[0]
        self.assertEqual(url, 'https://api.github.com/repos/DudebromanUT/event-horizon-wfm/zipball/main')
        self.assertNotIn('Authorization', headers)
        self.assertEqual(len(self.requests_made), 1)
        self.assertEqual(self.keys, {})
        with open(os.path.join(dest, 'horizon', 'erlang.py')) as f:
            self.assertEqual(f.read(), '# engine\n')
        with open(os.path.join(dest, 'config', 'operation.json')) as f:
            self.assertEqual(f.read(), '{"mine": true}')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'escape.py')))
        self.assertIn('Event Horizon updated (2 files)', self.alerts)

    def test_private_repo_asks_for_a_token_once(self):
        self.private = True
        self.installer.main()
        self.assertEqual(self.requests_made[1][1]['Authorization'], 'Bearer tok123')
        self.assertEqual(self.keys[('event-horizon', 'github-token')], 'tok123')
        self.assertIn('Event Horizon updated (2 files)', self.alerts)

    def test_bad_token_is_forgotten(self):
        self.private = True
        self.keys[('event-horizon', 'github-token')] = 'old'
        self.response = Response(401)
        self.installer.main()
        self.assertNotIn(('event-horizon', 'github-token'), self.keys)
        self.assertTrue(any('401' in a[0] for a in self.alerts if isinstance(a, tuple)))


if __name__ == '__main__':
    unittest.main()
