/* Formatting the numbers people read. Matches horizon/report.py, including Python's habit of
 * rounding exact halves to even, so the phone app and the Python engine print the same values. */

export function roundHalfEven(x, digits = 0) {
  const f = 10 ** digits;
  const v = x * f;
  const r = Math.round(v);
  // Math.round sends exact halves up; Python sends them to the even neighbour.
  return (Math.abs(v % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r) / f;
}

export function pct(x, digits = 1) {
  return (100 * x).toFixed(digits) + '%';
}

export function secs(s) {
  if (s == null || Number.isNaN(s)) return '-';
  if (s === Infinity) return 'never';
  const t = roundHalfEven(s);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
  const two = n => String(n).padStart(2, '0');
  return h ? h + ':' + two(m) + ':' + two(sec) : m + ':' + two(sec);
}

export function money(x) {
  const v = roundHalfEven(Math.abs(x));
  const text = '$' + v.toLocaleString('en-US', { maximumFractionDigits: 0 });
  return x < 0 ? '-' + text : text;
}

export function num(x, digits = 1) {
  return Number.isInteger(x) ? String(x) : x.toFixed(digits);
}

export function goalLabel(sl, target) {
  return num(Math.round(sl * 1000) / 10) + '/' + num(target);
}

/* A number from a text field; blank gives null. Accepts "1,250" and "$28". */
export function readNumber(text) {
  const t = String(text ?? '').trim().replace(/[,$\s]/g, '');
  if (!t) return null;
  const v = Number(t);
  if (!Number.isFinite(v)) throw new RangeError('"' + text + '" is not a number.');
  return v;
}

/* Percent from a text field: "35" -> 0.35. Blank gives null. */
export function readPercent(text) {
  const v = readNumber(String(text ?? '').replace('%', ''));
  return v == null ? null : v / 100;
}
