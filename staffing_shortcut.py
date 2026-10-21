"""Staffing by voice: the script behind the Staffing shortcut ("Hey Siri, Staffing").

The shortcut asks three questions (calls per half hour, handle time, goal) and passes the
answers here with Pythonista's Run Pythonista Script action, with "Run in Pythonista" off.
What this prints is what Siri says back. Run it in Pythonista itself to type the answers.

The occupancy limit comes from your sites (config/operation.json, or the example sites).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from horizon import config, voice  # noqa: E402

INTERVAL_MINUTES = 30   # if you change this, change the shortcut's first question to match

QUESTIONS = ('Calls per half hour? ', 'Handle time? ', 'Goal, like 80/20? ')
USAGE = 'The Staffing shortcut should pass three answers: calls, handle time and goal.'


def answers(argv):
    """The three answers, as separate arguments or as one text split by | or new lines."""
    parts = [a for a in argv if a.strip()]
    if len(parts) == 1:
        parts = [p for p in parts[0].replace('|', '\n').split('\n') if p.strip()]
    return parts


def in_shortcuts():
    try:
        import shortcuts    # Pythonista
        return shortcuts.is_running_shortcut()
    except Exception:
        return False


def occupancy_limit():
    try:
        return config.load().get('goals', {}).get('max_occupancy')
    except Exception:
        return None


def main(argv):
    parts = answers(argv)
    if not parts and not in_shortcuts():
        try:
            parts = [input(q) for q in QUESTIONS]
        except EOFError:
            return USAGE
    if len(parts) != 3:
        return '%s It passed %d.' % (USAGE, len(parts))
    return voice.reply(*parts, interval=INTERVAL_MINUTES * 60, max_occupancy=occupancy_limit())


if __name__ == '__main__':
    print(main(sys.argv[1:]))
