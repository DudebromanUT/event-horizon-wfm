"""Run the test suite: `python3 run_tests.py` on a computer, or tap Run in Pythonista."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(os.path.join(HERE, 'tests'), top_level_dir=HERE)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
