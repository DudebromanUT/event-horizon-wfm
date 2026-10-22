"""Staffing questions asked out loud: what Siri heard, turned into numbers, and an answer short
enough to be read back. staffing_shortcut.py uses it from Shortcuts (Run Pythonista Script).

Answers come as typed or dictated text, so numbers may be digits or words ('600', 'six hundred'),
handle time may be '6:30', '6 minutes 30 seconds', 'six and a half minutes' or '390', and a goal
may be '80/20', '80 in 20', 'eighty twenty' or '8020' (dictation sometimes runs the two together).
"""

import re

from .erlang import required_agents
from .report import num

UNITS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7,
         'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
         'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19}
TENS = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80,
        'ninety': 90}
TIME_UNITS = {'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
              'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
              's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1}
FILLER = {'and', 'a'}


def numbers(text):
    """Every number in `text` with the time unit said after it, if any:
    'six minutes 30 seconds' -> [(6, 'minutes'), (30, 'seconds')], 'eighty in twenty' -> [(80, None), (20, None)]."""
    found = []
    total = chunk = None    # a number said in words: 'one thousand' + 'two hundred'
    last = None             # the kind of word before: 'unit', 'teen', 'tens', 'hundred' or 'thousand'
    after_number = False    # 'half' only counts straight after a number ('six and a half')

    def finish():
        nonlocal total, chunk, last
        if total is not None or chunk is not None:
            found.append([(total or 0) + (chunk or 0), None])
        total = chunk = last = None

    for word in re.findall(r'\d+(?:[.,]\d+)*|[a-z]+', text.lower()):
        if word[0].isdigit():
            finish()
            found.append([float(word.replace(',', '')), None])
            after_number = True
        elif word in UNITS or word in TENS:
            n = UNITS.get(word, TENS.get(word))
            kind = 'tens' if word in TENS else ('unit' if n < 10 else 'teen')
            joins = last in ('hundred', 'thousand') or (kind == 'unit' and last == 'tens')
            if not joins:
                finish()
            chunk, last = (chunk or 0) + n, kind
            after_number = True
        elif word == 'hundred':
            chunk, last = (chunk or 1) * 100, 'hundred'
            after_number = True
        elif word == 'thousand':
            total, chunk, last = (total or 0) + (chunk or 1) * 1000, None, 'thousand'
            after_number = True
        elif word in FILLER:
            continue
        elif word == 'half' and after_number:
            if chunk is not None or total is not None:
                chunk = (chunk or 0) + 0.5
            else:
                found[-1][0] += 0.5
        else:
            finish()
            if word in TIME_UNITS and after_number and found[-1][1] is None:
                found[-1][1] = word
            after_number = False
    finish()
    return [(float(n), unit) for n, unit in found]


def parse_calls(text):
    found = numbers(text)
    if not found or not 0 < found[0][0] <= 100000:
        raise ValueError('calls')
    return found[0][0]


def parse_handle_time(text):
    """Seconds. A bare number up to 60 is minutes ('6'); above 60 it's seconds ('360')."""
    clock = re.search(r'(\d+):(\d{1,2})', text)
    if clock:
        seconds = int(clock.group(1)) * 60 + int(clock.group(2))
    else:
        found = numbers(text)
        if not found:
            raise ValueError('handle time')
        if any(unit for _, unit in found):
            # A number without a unit takes the next unit down: '6 minutes 30' is 6:30, '6 and 30 seconds' too.
            seconds, previous = 0.0, None
            for n, unit in found:
                scale = TIME_UNITS[unit] if unit else {None: 60, 3600: 60, 60: 1}.get(previous)
                if scale is None:
                    raise ValueError('handle time')
                seconds += n * scale
                previous = scale
        elif len(found) == 1:
            n = found[0][0]
            seconds = n * 60 if n <= 60 else n
        elif len(found) == 2 and found[1][0] < 60:
            seconds = found[0][0] * 60 + found[1][0]    # 'five thirty' is 5:30
        else:
            raise ValueError('handle time')
    if not 10 <= seconds <= 7200:
        raise ValueError('handle time')
    return float(seconds)


def parse_goal(text):
    """(percent, seconds): '80/20' -> (80, 20)."""
    found = [n for n, _ in numbers(text)]
    if len(found) == 1 and found[0].is_integer() and found[0] >= 100:
        digits = '%d' % found[0]
        found = [float(digits[:2]), float(digits[2:])]   # '8020' is 80/20
    if len(found) < 2:
        raise ValueError('goal')
    percent, seconds = found[0], found[1]
    if not (1 <= percent <= 99 and 1 <= seconds <= 600):
        raise ValueError('goal')
    return percent, seconds


def plural(n, word):
    return '%s %s%s' % (num(n), word, '' if n == 1 else 's')


def spoken_duration(seconds):
    """390 -> '6 minutes 30 seconds'. Words, because '6:30' is read aloud as a time of day."""
    m, s = divmod(int(round(seconds)), 60)
    parts = ([plural(m, 'minute')] if m else []) + ([plural(s, 'second')] if s or not m else [])
    return ' '.join(parts)


def interval_label(interval):
    return {900: 'per 15 minutes', 1800: 'per half hour', 3600: 'per hour'}.get(
        interval, 'per %s' % plural(interval / 60.0, 'minute'))


def answer(calls, aht, percent, target, interval=1800, max_occupancy=None):
    """Erlang C for the goal, plus the staffing that keeps occupancy under the limit if that's more."""
    m = required_agents(calls, aht, sl=percent / 100.0, target=target, interval=interval)
    wait = 'under a second' if m.asa < 0.5 else plural(round(m.asa), 'second')
    lines = [
        '%s %s, handle time %s, goal %s%% in %s.' % (plural(calls, 'call'), interval_label(interval),
                                                     spoken_duration(aht), num(percent), plural(target, 'second')),
        'You need %s. That answers %.1f%% within %s, with an average wait of %s and agents %d%% busy.' % (
            plural(m.agents, 'agent'), 100 * m.sl, plural(target, 'second'), wait, round(100 * m.occupancy)),
    ]
    if max_occupancy and m.occupancy > max_occupancy:
        capped = required_agents(calls, aht, sl=percent / 100.0, target=target, interval=interval,
                                 max_occupancy=max_occupancy)
        lines.append('To keep agents at or under %d%% busy, staff %d.' % (round(100 * max_occupancy), capped.agents))
    return '\n'.join(lines)


HINTS = {
    'calls': 'how many calls. Try a number like 600.',
    'handle time': 'the handle time. Try 6 minutes, 6:30 or 390 seconds.',
    'goal': 'the goal. Try 80/20, meaning 80% answered in 20 seconds.',
}


def reply(calls_text, aht_text, goal_text, interval=1800, max_occupancy=None):
    """The answer, or which answer couldn't be understood and what was heard."""
    for field, text, parse in (('calls', calls_text, parse_calls), ('handle time', aht_text, parse_handle_time),
                               ('goal', goal_text, parse_goal)):
        try:
            parse(text)
        except ValueError:
            return 'I didn\'t catch %s I heard "%s".' % (HINTS[field], text.strip())
    percent, target = parse_goal(goal_text)
    return answer(parse_calls(calls_text), parse_handle_time(aht_text), percent, target, interval, max_occupancy)


def split_sentence(text):
    """One answer with everything in it, in the order asked: '600, 6 minutes, 80 20' ->
    ('600', '360 seconds', '80/20'). Without a goal ('600, 6:30') the goal is 80/20."""
    text = re.sub(r'(\d+):(\d{2})', lambda m: ' %d seconds ' % (int(m.group(1)) * 60 + int(m.group(2))), text)
    found = numbers(text)
    if len(found) < 2:
        raise ValueError('sentence')
    if found[-1][1]:
        goal = (80.0, 20.0)
        middle = found[1:]
    elif found[-1][0].is_integer() and found[-1][0] >= 100 and len(found) >= 3:
        goal = parse_goal(num(found[-1][0]))
        middle = found[1:-1]
    elif len(found) >= 4:
        goal = (found[-2][0], found[-1][0])
        middle = found[1:-2]
    else:
        raise ValueError('sentence')
    words = ' '.join('%s %s' % (num(n), unit or '') for n, unit in middle)
    return num(found[0][0]), '%s seconds' % num(parse_handle_time(words)), '%s/%s' % (num(goal[0]), num(goal[1]))


def reply_sentence(text, interval=1800, max_occupancy=None):
    try:
        parts = split_sentence(text)
    except ValueError:
        return ('I didn\'t catch that. Say calls, handle time and goal, like: 600, 6 minutes, 80 20. '
                'I heard "%s".' % text.strip())
    return reply(*parts, interval=interval, max_occupancy=max_occupancy)
