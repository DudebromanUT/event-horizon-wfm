/* Site clocks: local time, UTC offsets, daylight-saving changes, opening hours, and the Sites board.
 * Uses the browser's built-in time zone database (Intl), so every IANA zone works offline.
 * Mirrors horizon/clock.py, horizon/config.py and report.sites_board; tests/web/engine.test.mjs
 * checks the board against the Python one. */

export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAY = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
const MINUTE = 60000, HOUR = 3600000, DAY = 86400000;
const pad = n => String(n).padStart(2, '0');

const formatters = new Map();
function formatter(zone) {
  let f = formatters.get(zone);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', {
      timeZone: zone, hourCycle: 'h23', weekday: 'short',
      year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric',
    });
    formatters.set(zone, f);
  }
  return f;
}

export function isZone(zone) {
  try { formatter(zone); return true; } catch (e) { return false; }
}

export function zoneNames() {
  try { return Intl.supportedValuesOf('timeZone'); } catch (e) { return []; }
}

/* Wall-clock fields at `zone` for the instant `date`. weekday: 0 = Monday. */
export function local(zone, date) {
  const p = {};
  for (const part of formatter(zone).formatToParts(date)) p[part.type] = part.value;
  return { year: +p.year, month: +p.month, day: +p.day, hour: +p.hour % 24, minute: +p.minute, second: +p.second,
    weekday: WEEKDAY[p.weekday] };
}

/* UTC offset in minutes at the instant `date`. */
export function offset(zone, date) {
  const w = local(zone, date);
  const asUtc = Date.UTC(w.year, w.month - 1, w.day, w.hour, w.minute, w.second);
  return Math.round((asUtc - Math.floor(date.getTime() / 1000) * 1000) / MINUTE);
}

/* The instant for a wall-clock time at `zone`. In the spring-forward gap the earlier offset is
 * used; in the repeated autumn hour, the first occurrence. Same rule as horizon/clock.py. */
export function toUtc(zone, year, month, day, hour, minute) {
  const guess = Date.UTC(year, month - 1, day, hour, minute);
  for (const probe of [guess - 12 * HOUR, guess + 12 * HOUR]) {
    const off = offset(zone, new Date(probe));
    const candidate = guess - off * MINUTE;
    if (offset(zone, new Date(candidate)) === off) return new Date(candidate);
  }
  return new Date(guess - offset(zone, new Date(guess)) * MINUTE);
}

/* Instants between start and end when the offset changes: [{at, offset}]. */
export function changes(zone, start, end) {
  const out = [];
  let t = start.getTime();
  const stop = end.getTime();
  let prev = offset(zone, new Date(t));
  while (t < stop) {
    const next = Math.min(t + DAY, stop);
    const off = offset(zone, new Date(next));
    if (off !== prev) {
      let h = Math.floor(t / HOUR) * HOUR;
      while (offset(zone, new Date(h)) !== off) h += HOUR;
      out.push({ at: new Date(h), offset: off });
      prev = off;
    }
    t = next;
  }
  return out;
}

export function formatOffset(minutes) {
  const sign = minutes >= 0 ? '+' : '-';
  const h = Math.floor(Math.abs(minutes) / 60), m = Math.abs(minutes) % 60;
  return 'UTC' + sign + h + (m ? ':' + pad(m) : '');
}

// --- Opening hours -------------------------------------------------------------

function toMinutes(text) {
  const [h, m] = text.trim().split(':');
  const value = Number(h) * 60 + Number(m);
  if (!(value >= 0 && value <= 1440)) throw new RangeError('Bad time "' + text + '".');
  return value;
}

function ranges(value) {
  if (Array.isArray(value)) return value.flatMap(ranges);
  const text = String(value).trim().toLowerCase();
  if (text === 'closed') return [];
  if (text === '24h') return [[0, 1440]];
  const [start, end] = text.split('-').map(toMinutes);
  return [[start, end <= start ? end + 1440 : end]];
}

function days(key) {
  key = key.trim().toLowerCase();
  if (key === 'daily') return [0, 1, 2, 3, 4, 5, 6];
  const names = DAYS.map(d => d.toLowerCase());
  if (key.includes('-')) {
    const [i, j] = key.split('-').map(k => names.indexOf(k));
    if (i < 0 || j < 0) throw new RangeError('Bad days "' + key + '".');
    const out = [];
    for (let d = i; ; d = (d + 1) % 7) { out.push(d); if (d === j) break; }
    return out;
  }
  const d = names.indexOf(key);
  if (d < 0) throw new RangeError('Bad day "' + key + '".');
  return [d];
}

/* {'mon-fri': '08:00-20:00', sat: '09:00-17:00'} -> [[ [480, 1200] ], ...] for Monday..Sunday.
 * Later keys override earlier ones; a range that ends at or before it starts runs past midnight. */
export function parseHours(spec) {
  const week = [[], [], [], [], [], [], []];
  for (const [key, value] of Object.entries(spec || {})) {
    if (key.startsWith('_')) continue;
    for (const d of days(key)) week[d] = ranges(value);
  }
  return week;
}

export function isOpen(site, date) {
  const w = local(site.zone, date);
  const minute = w.hour * 60 + w.minute;
  const week = site._hours || parseHours(site.hours);
  if (week[w.weekday].some(([s, e]) => s <= minute && minute < e)) return true;
  return week[(w.weekday + 6) % 7].some(([s, e]) => s <= minute + 1440 && minute + 1440 < e);
}

/* Next instant the site opens or closes, in 15-minute steps: [Date, opening] or [null, openNow]. */
export function nextOpenChange(site, date, horizonDays = 8) {
  const state = isOpen(site, date);
  let t = Math.floor(date.getTime() / MINUTE) * MINUTE;
  t -= (new Date(t).getUTCMinutes() % 15) * MINUTE;
  const end = date.getTime() + horizonDays * DAY;
  while (t < end) {
    t += 15 * MINUTE;
    if (isOpen(site, new Date(t)) !== state) return [new Date(t), !state];
  }
  return [null, state];
}

// --- Config and the Sites board -------------------------------------------------

/* Check a config's sites and attach parsed hours. Throws with a message people can act on. */
export function prepare(cfg) {
  const sites = (cfg.sites || []).map((s, i) => {
    for (const key of ['id', 'name', 'zone']) {
      if (!s[key]) throw new RangeError('Site ' + (i + 1) + ' needs a ' + key + '.');
    }
    if (!isZone(s.zone)) throw new RangeError(s.name + ': "' + s.zone + '" is not a time zone this device knows.');
    return { ...s, _hours: parseHours(s.hours) };
  });
  for (const a of cfg.anchors || []) {
    if (!isZone(a.zone)) throw new RangeError(a.label + ': "' + a.zone + '" is not a time zone this device knows.');
  }
  return { ...cfg, sites, anchors: cfg.anchors || [] };
}

function sameDay(a, b) {
  return a.year === b.year && a.month === b.month && a.day === b.day;
}

const clockText = w => DAYS[w.weekday] + ' ' + pad(w.hour) + ':' + pad(w.minute);
const dateText = w => DAYS[w.weekday] + ' ' + w.day + ' ' + MONTHS[w.month - 1];

export function siteStatus(site, now) {
  const [when, opening] = nextOpenChange(site, now);
  if (!when) return opening ? 'Open all week' : 'Closed all week';
  const at = local(site.zone, when);
  const stamp = sameDay(at, local(site.zone, now)) ? pad(at.hour) + ':' + pad(at.minute) : clockText(at);
  return (opening ? 'Closed, opens ' : 'Open until ') + stamp;
}

function isoMinute(date) {
  return date.toISOString().slice(0, 16) + 'Z';
}

/* Everything the Sites screen shows, as data (the same shape as report.sites_board). */
export function sitesBoard(cfg, now = new Date(), weeks = 6) {
  const sites = cfg.sites || [];
  const rows = sites.map(s => ({
    id: s.id, name: s.name, zone: s.zone, local: clockText(local(s.zone, now)),
    offset: formatOffset(offset(s.zone, now)), open: isOpen(s, now), status: siteStatus(s, now),
  }));

  // Every zone that matters: the sites', then the anchors' (customer clocks).
  const watched = [];
  for (const s of sites) if (!watched.some(w => w.zone === s.zone)) watched.push({ zone: s.zone, label: s.id });
  for (const a of cfg.anchors || []) {
    if (!watched.some(w => w.zone === a.zone)) watched.push({ zone: a.zone, label: a.label.split(' ').slice(1).join(' ') || a.label });
  }
  const end = new Date(now.getTime() + weeks * 7 * DAY);
  const found = [];
  for (const w of watched) for (const c of changes(w.zone, now, end)) found.push({ ...c, label: w.label, zone: w.zone });
  found.sort((x, y) => x.at - y.at || (x.label < y.label ? -1 : x.label > y.label ? 1 : 0)
    || (x.zone < y.zone ? -1 : x.zone > y.zone ? 1 : 0) || x.offset - y.offset);
  const changeRows = found.map(c => ({ at: isoMinute(c.at), date: dateText(local(c.zone, c.at)), label: c.label,
    offset: formatOffset(c.offset) }));

  const anchors = (cfg.anchors || []).map(a => {
    const [hh, mm] = a.time.split(':').map(Number);
    const candidates = [], seen = new Set();
    [now, ...found.map(c => new Date(c.at.getTime() + 12 * HOUR))].forEach((d, i) => {
      const day = local(a.zone, d);
      const key = day.year + '-' + day.month + '-' + day.day;
      if (seen.has(key)) return;
      seen.add(key);
      const instant = toUtc(a.zone, day.year, day.month, day.day, hh, mm);
      candidates.push({ label: i === 0 ? 'now' : 'from ' + day.day + ' ' + MONTHS[day.month - 1],
        cells: sites.map(s => local(s.zone, instant)) });
    });
    // Keep only rows where some site's clock differs from the row before.
    const same = (p, r) => p.cells.every((c, k) => c.hour === r.cells[k].hour && c.minute === r.cells[k].minute);
    const shown = candidates.filter((r, k) => k === 0 || !same(candidates[k - 1], r));
    const whole = shown.every(r => r.cells.every(c => c.minute === 0));
    const fmt = c => whole ? pad(c.hour) : pad(c.hour) + ':' + pad(c.minute);
    return { label: a.label, ids: sites.map(s => s.id), rows: shown.map(r => ({ label: r.label, times: r.cells.map(fmt) })) };
  });

  const n = local('UTC', now);
  return { heading: dateText(n) + ' ' + pad(n.hour) + ':' + pad(n.minute), sites: rows, weeks, changes: changeRows, anchors };
}
