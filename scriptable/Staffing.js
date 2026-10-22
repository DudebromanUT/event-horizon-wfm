// Event Horizon: staffing by voice, for the Scriptable app ("Hey Siri, Staffing").
//
// The Staffing shortcut asks "Calls, handle time and goal?" and runs this script with the
// answer, such as "600, six minutes, eighty twenty". It says how many agents meet the goal
// (Erlang C), plus the staffing that keeps occupancy under MAX_OCCUPANCY when that's higher.
// It reads back what it heard, so a misheard number is easy to spot. Works offline.
//
// This is a port of horizon/voice.py; tests/web/staffing.test.cjs checks it gives the same
// answers. Copy the whole file into a new Scriptable script named Staffing.

const INTERVAL_MINUTES = 30;   // the question is per half hour
const MAX_OCCUPANCY = 0.9;     // set to 0 for no occupancy line

const UNITS = { zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9,
  ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17,
  eighteen: 18, nineteen: 19 };
const TENS = { twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90 };
const TIME_UNITS = { h: 3600, hr: 3600, hrs: 3600, hour: 3600, hours: 3600, m: 60, min: 60, mins: 60,
  minute: 60, minutes: 60, s: 1, sec: 1, secs: 1, second: 1, seconds: 1 };
const FILLER = new Set(['and', 'a']);

// Every number in the text, digits or words, with the time unit said straight after it.
function numbers(text) {
  const found = [];
  let total = null, chunk = null, last = null, afterNumber = false;
  const finish = () => {
    if (total !== null || chunk !== null) found.push([(total || 0) + (chunk || 0), null]);
    total = chunk = last = null;
  };
  for (const word of text.toLowerCase().match(/\d+(?:[.,]\d+)*|[a-z]+/g) || []) {
    if (/^\d/.test(word)) {
      finish();
      found.push([parseFloat(word.replace(/,/g, '')), null]);
      afterNumber = true;
    } else if (word in UNITS || word in TENS) {
      const n = word in UNITS ? UNITS[word] : TENS[word];
      const kind = word in TENS ? 'tens' : (n < 10 ? 'unit' : 'teen');
      const joins = last === 'hundred' || last === 'thousand' || (kind === 'unit' && last === 'tens');
      if (!joins) finish();
      chunk = (chunk || 0) + n; last = kind;
      afterNumber = true;
    } else if (word === 'hundred') {
      chunk = (chunk || 1) * 100; last = 'hundred'; afterNumber = true;
    } else if (word === 'thousand') {
      total = (total || 0) + (chunk || 1) * 1000; chunk = null; last = 'thousand'; afterNumber = true;
    } else if (FILLER.has(word)) {
      continue;
    } else if (word === 'half' && afterNumber) {
      if (chunk !== null || total !== null) chunk = (chunk || 0) + 0.5;
      else found[found.length - 1][0] += 0.5;
    } else {
      finish();
      if (word in TIME_UNITS && afterNumber && found[found.length - 1][1] === null) found[found.length - 1][1] = word;
      afterNumber = false;
    }
  }
  finish();
  return found;
}

const isInt = (x) => Number.isInteger(x);
// Python's '%d' if whole, else '%.1f'
const num = (x) => isInt(x) ? String(x) : x.toFixed(1);
const plural = (n, word) => `${num(n)} ${word}${n === 1 ? '' : 's'}`;
// Python's round(): halves go to the even neighbour
function roundHalfEven(x) {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

function parseHandleTime(text) {
  const clock = text.match(/(\d+):(\d{1,2})/);
  let seconds;
  if (clock) {
    seconds = parseInt(clock[1], 10) * 60 + parseInt(clock[2], 10);
  } else {
    const found = numbers(text);
    if (!found.length) throw new Error('handle time');
    if (found.some(([, unit]) => unit)) {
      seconds = 0;
      let previous = null;
      for (const [n, unit] of found) {
        const scale = unit ? TIME_UNITS[unit] : ({ null: 60, 3600: 60, 60: 1 })[previous];
        if (scale === undefined) throw new Error('handle time');
        seconds += n * scale;
        previous = scale;
      }
    } else if (found.length === 1) {
      const n = found[0][0];
      seconds = n <= 60 ? n * 60 : n;
    } else if (found.length === 2 && found[1][0] < 60) {
      seconds = found[0][0] * 60 + found[1][0];
    } else {
      throw new Error('handle time');
    }
  }
  if (!(seconds >= 10 && seconds <= 7200)) throw new Error('handle time');
  return seconds;
}

function parseGoal(text) {
  let found = numbers(text).map(([n]) => n);
  if (found.length === 1 && isInt(found[0]) && found[0] >= 100) {
    const digits = String(found[0]);
    found = [parseFloat(digits.slice(0, 2)), parseFloat(digits.slice(2))];
  }
  if (found.length < 2) throw new Error('goal');
  const [percent, seconds] = found;
  if (!(percent >= 1 && percent <= 99 && seconds >= 1 && seconds <= 600)) throw new Error('goal');
  return [percent, seconds];
}

// One answer in the order asked: calls, handle time, goal (80/20 if left off).
function splitSentence(text) {
  text = text.replace(/(\d+):(\d{2})/g, (_, m, s) => ` ${parseInt(m, 10) * 60 + parseInt(s, 10)} seconds `);
  const found = numbers(text);
  if (found.length < 2) throw new Error('sentence');
  let goal, middle;
  const last = found[found.length - 1];
  if (last[1]) {
    goal = [80, 20]; middle = found.slice(1);
  } else if (isInt(last[0]) && last[0] >= 100 && found.length >= 3) {
    goal = parseGoal(num(last[0])); middle = found.slice(1, -1);
  } else if (found.length >= 4) {
    goal = parseGoal(`${num(found[found.length - 2][0])}/${num(last[0])}`); middle = found.slice(1, -2);
  } else {
    throw new Error('sentence');
  }
  const calls = found[0][0];
  if (!(calls > 0 && calls <= 100000)) throw new Error('sentence');
  const aht = parseHandleTime(middle.map(([n, unit]) => `${num(n)} ${unit || ''}`).join(' '));
  return [calls, aht, goal[0], goal[1]];
}

// Erlang C, as in docs/app/engine.js
function erlangC(calls, aht, agents, target, interval) {
  const a = calls * aht / interval;
  if (agents <= a) return { agents, sl: 0, asa: Infinity, occupancy: 1 };
  let invB = 1;
  for (let k = 1; k <= agents; k++) invB = 1 + invB * k / a;
  const pWait = agents / (invB * (agents - a) + a);
  return { agents, sl: 1 - pWait * Math.exp(-(agents - a) * target / aht), asa: pWait * aht / (agents - a),
    occupancy: a / agents };
}

function requiredAgents(calls, aht, sl, target, interval, maxOccupancy) {
  let n = Math.max(1, Math.floor(calls * aht / interval) + 1);
  for (;; n++) {
    const m = erlangC(calls, aht, n, target, interval);
    if (m.sl >= sl - 1e-12 && (!maxOccupancy || m.occupancy <= maxOccupancy + 1e-12)) return m;
  }
}

function spokenDuration(seconds) {
  const s0 = roundHalfEven(seconds), m = Math.floor(s0 / 60), s = s0 % 60;
  return [...(m ? [plural(m, 'minute')] : []), ...(s || !m ? [plural(s, 'second')] : [])].join(' ');
}

function intervalLabel(interval) {
  return { 900: 'per 15 minutes', 1800: 'per half hour', 3600: 'per hour' }[interval]
    || `per ${plural(interval / 60, 'minute')}`;
}

function answer(calls, aht, percent, target, interval = 1800, maxOccupancy = 0) {
  const m = requiredAgents(calls, aht, percent / 100, target, interval, 0);
  const wait = m.asa < 0.5 ? 'under a second' : plural(roundHalfEven(m.asa), 'second');
  const lines = [
    `${plural(calls, 'call')} ${intervalLabel(interval)}, handle time ${spokenDuration(aht)}, goal ${num(percent)}% in ${plural(target, 'second')}.`,
    `You need ${plural(m.agents, 'agent')}. That answers ${(100 * m.sl).toFixed(1)}% within ${plural(target, 'second')}, with an average wait of ${wait} and agents ${roundHalfEven(100 * m.occupancy)}% busy.`,
  ];
  if (maxOccupancy && m.occupancy > maxOccupancy) {
    const capped = requiredAgents(calls, aht, percent / 100, target, interval, maxOccupancy);
    lines.push(`To keep agents at or under ${roundHalfEven(100 * maxOccupancy)}% busy, staff ${capped.agents}.`);
  }
  return lines.join('\n');
}

function replySentence(text, interval = 1800, maxOccupancy = 0) {
  let parts;
  try {
    parts = splitSentence(text);
  } catch (e) {
    return `I didn't catch that. Say calls, handle time and goal, like: 600, 6 minutes, 80 20. I heard "${text.trim()}".`;
  }
  return answer(parts[0], parts[1], parts[2], parts[3], interval, maxOccupancy);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { numbers, parseHandleTime, parseGoal, splitSentence, answer, replySentence };
} else {
  // Scriptable: the answer from the shortcut, or typed in when run in the app.
  const run = async () => {
    let text = args.shortcutParameter || (args.plainTexts && args.plainTexts[0]) || '';
    if (Array.isArray(text)) text = text.join(' ');
    if (!String(text).trim() && config.runsInApp) {
      const ask = new Alert();
      ask.title = 'Calls, handle time and goal?';
      ask.addTextField('600, 6 minutes, 80 20');
      ask.addAction('Answer');
      await ask.present();
      text = ask.textFieldValue(0);
    }
    const reply = replySentence(String(text), INTERVAL_MINUTES * 60, MAX_OCCUPANCY);
    Script.setShortcutOutput(reply);
    if (config.runsWithSiri) Speech.speak(reply);
    if (!config.runsInApp) {
      // Shown as a notification, so the shortcut needs no step after this one.
      const note = new Notification();
      note.title = 'Staffing';
      note.body = reply;
      await note.schedule();
    } else {
      const show = new Alert();
      show.title = 'Staffing';
      show.message = reply;
      show.addAction('OK');
      await show.present();
    }
    Script.complete();
  };
  run();
}
