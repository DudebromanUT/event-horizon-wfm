"""The Scriptable version of the Siri script (scriptable/Staffing.js) gives horizon/voice.py's answers."""

import json
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from horizon import voice  # noqa: E402

CASES = ['600, 6 minutes, 80 20', 'six hundred calls, six and a half minutes, eighty twenty', '600 6:30 8020',
         '600 360 80 20', '600, 6 minutes', '600 6 minutes 30 seconds 90 30', '25, 6 minutes, 80 20',
         '1,200 calls, 4 minutes 45 seconds, 90 in 30', 'twelve hundred, five thirty, 80/20', '45, 90 seconds, 95 15',
         'hello', '600']


@unittest.skipUnless(shutil.which('node'), 'needs node')
class ScriptableTest(unittest.TestCase):
    def test_same_answers_as_python(self):
        script = ("const s = require(%s); const out = JSON.parse(process.argv[1]).map(t => s.replySentence(t, 1800, 0.9));"
                  "console.log(JSON.stringify(out));") % json.dumps(os.path.join(ROOT, 'scriptable', 'Staffing.js'))
        out = subprocess.run(['node', '-e', script, json.dumps(CASES)], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        for text, js in zip(CASES, json.loads(out.stdout)):
            self.assertEqual(js, voice.reply_sentence(text, max_occupancy=0.9), text)


if __name__ == '__main__':
    unittest.main()
