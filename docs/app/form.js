/* Bind a form: restore what was typed last time, recalculate as people type, remember the values. */

import { load, save } from './store.js';
import { readNumber, readPercent } from './format.js';

export function values(form) {
  const out = {};
  for (const input of form.querySelectorAll('input, select, textarea')) {
    if (input.type === 'radio') {
      if (input.checked) out[input.name] = input.value;
    } else if (input.id) {
      out[input.id] = input.value;
    }
  }
  return out;
}

function restore(form, saved) {
  if (!saved) return;
  for (const input of form.querySelectorAll('input, select, textarea')) {
    if (input.type === 'radio') {
      if (saved[input.name] != null) input.checked = saved[input.name] === input.value;
    } else if (input.id && saved[input.id] != null) {
      input.value = saved[input.id];
    }
  }
}

/* Calls update(values) now and after each edit (debounced), saving the values under `key`. */
export function bind(form, key, update) {
  restore(form, load(key));
  let timer = 0;
  const run = () => {
    const v = values(form);
    save(key, v);
    update(v);
  };
  form.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(run, 120); });
  form.addEventListener('change', run);
  form.addEventListener('submit', e => e.preventDefault());
  run();
  return run;
}

/* Field readers that say which field is wrong. */
export function number(v, id, label, { required = true, min = null, integer = false } = {}) {
  let n;
  try { n = readNumber(v[id]); } catch (e) { throw fieldError(id, label + ' needs a number.'); }
  if (n == null) {
    if (required) throw fieldError(id, label + ' is empty.');
    return null;
  }
  if (min != null && n < min) throw fieldError(id, label + ' must be at least ' + min + '.');
  if (integer && !Number.isInteger(n)) throw fieldError(id, label + ' must be a whole number.');
  return n;
}

export function percent(v, id, label, { required = true, max = 100 } = {}) {
  let p;
  try { p = readPercent(v[id]); } catch (e) { throw fieldError(id, label + ' needs a number.'); }
  if (p == null) {
    if (required) throw fieldError(id, label + ' is empty.');
    return null;
  }
  if (p < 0 || p * 100 > max) throw fieldError(id, label + ' must be between 0% and ' + max + '%.');
  return p;
}

/* A percent that may be negative ("-10" for 10% shorter). Blank gives 0. */
export function signedPercent(v, id, label) {
  const raw = String(v[id] ?? '').replace('%', '');
  let n;
  try { n = readNumber(raw); } catch (e) { throw fieldError(id, label + ' needs a number.'); }
  if (n == null) return 0;
  if (n <= -100) throw fieldError(id, label + ' must be above -100%.');
  return n / 100;
}

function fieldError(id, message) {
  const e = new RangeError(message);
  e.field = id;
  return e;
}

/* Mark the field an error points at, and clear the rest. */
export function flag(form, error) {
  for (const input of form.querySelectorAll('[aria-invalid]')) input.removeAttribute('aria-invalid');
  if (error && error.field) {
    const input = form.querySelector('#' + error.field);
    if (input) input.setAttribute('aria-invalid', 'true');
  }
}
