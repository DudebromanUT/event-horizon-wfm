/* Sites: every site's clock and hours, the coming clock changes, and where customer times land in
 * each site's day. Your sites live on this device; the setup code or link moves them between devices. */

import { $, el, setText, showError, toast } from './dom.js';
import { isZone, parseHours, prepare, sitesBoard, zoneNames } from './clock.js';
import { load, remove, save } from './store.js';
import { EXAMPLE } from './defaults.js';

let cfg = null;          // prepared config in use
let custom = false;      // true once you've saved your own sites
let timer = 0;
let resetArmed = false;

function current() {
  const saved = load('config');
  if (saved) {
    try { return { cfg: prepare(saved), custom: true }; } catch (e) { /* fall back to the examples */ }
  }
  return { cfg: prepare(EXAMPLE), custom: false };
}

function plain(c) {
  return {
    note: c.note,
    anchors: c.anchors,
    goals: c.goals,
    sites: c.sites.map(({ _hours, ...s }) => s),
  };
}

function use(config, message) {
  const prepared = prepare(config);
  save('config', plain(prepared));
  cfg = prepared;
  custom = true;
  render();
  if (message) toast(message);
}

// --- Setup link: #setup=<base64url JSON> ---------------------------------------------

function encode(obj) {
  const bytes = new TextEncoder().encode(JSON.stringify(obj));
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function decode(text) {
  const b64 = text.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(b64 + '='.repeat((4 - b64.length % 4) % 4));
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(bin, ch => ch.charCodeAt(0))));
}

function takeSetupLink() {
  const hash = location.hash;
  if (!hash.startsWith('#setup=')) return;
  try {
    const incoming = decode(hash.slice(7));
    use(incoming, `Loaded ${incoming.sites.length} sites from your setup link.`);
  } catch (e) {
    toast('That setup link could not be read: ' + (e.message || e));
  }
  history.replaceState(null, '', location.pathname + location.search + '#sites');
}

// --- The board -------------------------------------------------------------------------

function render() {
  if (!cfg) return;
  const board = sitesBoard(cfg, new Date());
  const names = Object.fromEntries(cfg.sites.map(s => [s.id, s.name]));
  setText('s-heading', `At ${board.heading} UTC. Times update every 30 seconds.`);
  // A note travels with a setup (such as "the hours are placeholders"); the examples say they're examples.
  const note = $('#s-example');
  note.hidden = custom && !cfg.note;
  note.textContent = custom ? (cfg.note || '') : 'These are example sites. Tap Edit sites to put in your own, or open your setup link.';

  $('#s-grid').replaceChildren(...board.sites.map(s => {
    const [day, time] = s.local.split(' ');
    return el('li', { class: 'clock' },
      el('div', { class: 'who' }, el('span', { class: 'name', text: s.name }),
        el('span', { class: 'pill' + (s.open ? ' good' : '') }, el('span', { class: 'dot' }), s.status)),
      el('div', { class: 'when' }, el('span', { class: 'time', text: time }), el('span', { class: 'meta', text: `${day} · ${s.offset}` })));
  }));

  setText('s-changes-title', `Clock changes in the next ${board.weeks} weeks`);
  $('#s-changes').replaceChildren(...(board.changes.length ? board.changes.map(c =>
    el('li', {}, el('span', { class: 'when', text: c.date }),
      el('span', { class: 'what', text: `${names[c.label] || c.label} changes to ${c.offset}` + (names[c.label] ? '' : ' (customer clock)') })))
    : [el('li', {}, el('span', { class: 'what', text: 'None. Every clock keeps its offset.' }))]));

  $('#s-anchors').replaceChildren(...board.anchors.map(a => {
    const head = el('tr', {}, el('th', { scope: 'col', text: '' }),
      ...a.ids.map(id => el('th', { scope: 'col', title: names[id] || id }, el('abbr', { title: names[id] || id, text: id }))));
    const rows = a.rows.map((r, i) => el('tr', {}, el('th', { scope: 'row', text: r.label }),
      ...r.times.map((t, k) => el('td', { class: i && t !== a.rows[i - 1].times[k] ? 'moved' : null, text: t }))));
    return el('div', { class: 'card anchor' },
      el('h2', { text: `${a.label}, in site time` }),
      el('div', { class: 'table-wrap' }, el('table', {}, el('thead', {}, head), el('tbody', {}, ...rows))),
      a.rows.length > 1 ? el('p', { class: 'lede', text: 'Highlighted times move when a clock changes.' }) : null);
  }));
}

export function onShow() {
  render();
  clearInterval(timer);
  timer = setInterval(() => { if (document.visibilityState === 'visible') render(); }, 30000);
}

export function onHide() {
  clearInterval(timer);
}

// --- The editor -------------------------------------------------------------------------

const HM = /^\d{2}:\d{2}$/;

/* Hours that fit the simple form: one range for Mon-Fri, one for Sat, one for Sun. */
function simpleHours(hours) {
  let week;
  try { week = parseHours(hours); } catch (e) { return null; }
  const one = d => (week[d].length <= 1 ? week[d][0] || null : undefined);
  const days = [0, 1, 2, 3, 4, 5, 6].map(one);
  if (days.some(d => d === undefined)) return null;
  const same = (a, b) => (a === null && b === null) || (a && b && a[0] === b[0] && a[1] === b[1]);
  if (![1, 2, 3, 4].every(d => same(days[d], days[0]))) return null;
  const text = r => (r ? [r[0], r[1] % 1440].map(m => String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0')) : null);
  return { week: text(days[0]), sat: text(days[5]), sun: text(days[6]) };
}

function zoneSelect(id, value) {
  const select = el('select', { id });
  const groups = new Map();
  const zones = zoneNames();
  if (!zones.includes(value)) zones.unshift(value);
  for (const z of zones) {
    const region = z.includes('/') ? z.split('/')[0] : 'Other';
    if (!groups.has(region)) groups.set(region, el('optgroup', { label: region }));
    groups.get(region).append(el('option', { value: z, text: z.replace(/_/g, ' ') }));
  }
  select.append(...groups.values());
  select.value = value;
  return select;
}

function hoursRow(prefix, label, range) {
  const open = el('input', { type: 'time', id: prefix + '-open', value: range ? range[0] : '08:00', 'aria-label': label + ' opens' });
  const close = el('input', { type: 'time', id: prefix + '-close', value: range ? range[1] : '17:00', 'aria-label': label + ' closes' });
  const closed = el('input', { type: 'checkbox', id: prefix + '-closed' });
  closed.checked = !range;
  const sync = () => { open.disabled = close.disabled = closed.checked; };
  closed.addEventListener('change', sync);
  sync();
  return el('div', { class: 'row hours' }, el('span', { class: 'name', text: label }),
    el('div', { class: 'hours-row' }, open, el('span', { class: 'to', text: 'to' }), close, el('label', {}, closed, 'Closed')));
}

function hoursSummary(hours) {
  const simple = simpleHours(hours);
  if (!simple) return 'Custom hours';
  const span = r => `${r[0]}–${r[1] === '00:00' ? '24:00' : r[1]}`;
  const same = (a, b) => (!a && !b) || (a && b && a[0] === b[0] && a[1] === b[1]);
  if (simple.week && same(simple.week, simple.sat) && same(simple.week, simple.sun)) {
    return span(simple.week) === '00:00–24:00' ? 'Around the clock' : `Daily ${span(simple.week)}`;
  }
  const part = (name, r) => (r ? `${name} ${span(r)}` : null);
  return [part('Mon–Fri', simple.week), part('Sat', simple.sat), part('Sun', simple.sun)].filter(Boolean).join(', ') || 'Closed all week';
}

function siteEditor(site, i) {
  const p = `e${i}`;
  const simple = simpleHours(site.hours);
  const box = el('details', { class: 'site-edit', 'data-index': i, 'data-custom': simple ? null : JSON.stringify(site.hours) },
    el('summary', {}, el('span', {}, el('span', { class: 'title', text: site.name || 'New site' }),
      el('span', { class: 'sub', text: `${site.zone.replace(/_/g, ' ')} · ${hoursSummary(site.hours)}` }))),
    el('label', { class: 'row' }, el('span', { class: 'name', text: 'Name' }), el('input', { id: p + '-name', class: 'wide', value: site.name || '' })),
    el('label', { class: 'row' }, el('span', { class: 'name' }, 'Short name', el('small', { text: 'Two to four letters for tables' })),
      el('input', { id: p + '-id', value: site.id || '', maxlength: 4 })),
    el('label', { class: 'row' }, el('span', { class: 'name', text: 'Time zone' }), zoneSelect(p + '-zone', site.zone)));
  if (simple) {
    box.append(hoursRow(p + '-wk', 'Monday to Friday', simple.week), hoursRow(p + '-sat', 'Saturday', simple.sat),
      hoursRow(p + '-sun', 'Sunday', simple.sun));
  } else {
    box.append(el('p', { class: 'custom', text: 'This site has custom hours from your setup code, such as split shifts. They are kept as they are; change them in the setup code.' }));
  }
  box.append(
    el('label', { class: 'row' }, el('span', { class: 'name', text: 'Cost per paid agent hour' }),
      el('input', { id: p + '-cost', inputmode: 'decimal', value: site.cost_per_hour ?? '', placeholder: '$ optional' })),
    el('label', { class: 'row' }, el('span', { class: 'name', text: 'Shrinkage, %' }),
      el('input', { id: p + '-shrink', inputmode: 'decimal', value: site.shrinkage != null ? String(Math.round(site.shrinkage * 1000) / 10) : '', placeholder: 'optional' })));
  const removeBtn = el('button', { type: 'button', class: 'btn small danger', text: 'Remove this site' });
  removeBtn.addEventListener('click', () => { box.remove(); });
  box.append(el('div', { class: 'row' }, removeBtn));
  return box;
}

function readEditor() {
  const sites = [];
  for (const box of $('#e-sites').querySelectorAll('details.site-edit')) {
    const i = box.dataset.index;
    const get = k => ($('#e' + i + '-' + k)?.value ?? '').trim();
    const name = get('name');
    const id = get('id').toUpperCase() || name.slice(0, 3).toUpperCase();
    let hours;
    if (box.dataset.custom) {
      hours = JSON.parse(box.dataset.custom);
    } else {
      hours = {};
      for (const [key, part] of [['mon-fri', 'wk'], ['sat', 'sat'], ['sun', 'sun']]) {
        const closed = $('#e' + i + '-' + part + '-closed').checked;
        const open = get(part + '-open'), close = get(part + '-close');
        if (closed) { hours[key] = 'closed'; continue; }
        if (!HM.test(open) || !HM.test(close)) throw new RangeError(`${name || 'A site'}: enter opening and closing times, or tick Closed.`);
        hours[key] = open === '00:00' && (close === '00:00' || close === '24:00') ? '24h' : `${open}-${close === '00:00' ? '24:00' : close}`;
      }
    }
    const cost = get('cost').replace(/[$,]/g, '');
    const shrink = get('shrink').replace('%', '');
    if (cost && !Number.isFinite(Number(cost))) throw new RangeError(`${name}: cost per hour needs a number.`);
    if (shrink && !(Number(shrink) >= 0 && Number(shrink) < 95)) throw new RangeError(`${name}: shrinkage must be between 0 and 95%.`);
    sites.push({ id, name, zone: get('zone'), hours, cost_per_hour: cost ? Number(cost) : null,
      shrinkage: shrink ? Number(shrink) / 100 : null });
  }
  const ids = sites.map(s => s.id);
  const dup = ids.find((id, k) => ids.indexOf(id) !== k);
  if (dup) throw new RangeError(`Two sites share the short name ${dup}. Give each its own.`);
  if (!sites.length) throw new RangeError('Keep at least one site.');
  const { note, ...rest } = plain(cfg);   // saving from the editor means the sites are now yours as entered
  return { ...rest, sites };
}

function openEditor() {
  const box = $('#e-sites');
  box.replaceChildren(...cfg.sites.map(siteEditor));
  $('#e-code').value = JSON.stringify(plain(cfg), null, 2);
  showError('e-error', null);
  resetArmed = false;
  $('#e-reset').textContent = 'Go back to example sites';
  $('#s-editor').hidden = false;
  $('#s-edit').hidden = true;
  $('#s-editor').scrollIntoView({ block: 'start' });
}

function closeEditor() {
  $('#s-editor').hidden = true;
  $('#s-edit').hidden = false;
}

export function init() {
  ({ cfg, custom } = current());
  takeSetupLink();
  $('#s-edit').addEventListener('click', openEditor);
  $('#e-cancel').addEventListener('click', closeEditor);
  $('#e-add').addEventListener('click', () => {
    const zone = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return 'UTC'; } })();
    const i = Date.now() % 100000;
    const box = siteEditor({ id: '', name: '', zone: isZone(zone) ? zone : 'UTC', hours: { 'mon-fri': '08:00-17:00' } }, i);
    box.open = true;
    $('#e-sites').append(box);
    box.querySelector('input').focus();
  });
  $('#e-save').addEventListener('click', () => {
    try {
      use(readEditor(), 'Sites saved on this device.');
      closeEditor();
    } catch (e) {
      showError('e-error', e);
    }
  });
  $('#e-copy').addEventListener('click', async () => {
    const code = $('#e-code');
    try {
      await navigator.clipboard.writeText(code.value);
      toast('Setup code copied.');
    } catch (e) {
      code.focus();
      code.select();
      toast('Select all and copy the code.');
    }
  });
  $('#e-link').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(setupLink());
      toast('Setup link copied. Open it on the other device.');
    } catch (e) {
      const code = $('#e-code');
      code.value = setupLink();
      code.focus();
      code.select();
      toast('Select all and copy the link.');
    }
  });
  $('#e-load').addEventListener('click', () => {
    try {
      // Takes a setup code (the text above) or a whole setup link.
      const raw = $('#e-code').value.trim();
      const at = raw.indexOf('#setup=');
      use(at >= 0 ? decode(raw.slice(at + 7)) : JSON.parse(raw), 'Sites loaded.');
      closeEditor();
    } catch (e) {
      showError('e-error', new RangeError('That setup code could not be used: ' + (e.message || e)));
    }
  });
  $('#e-reset').addEventListener('click', () => {
    if (!resetArmed) {
      resetArmed = true;
      $('#e-reset').textContent = 'Tap again to replace your sites';
      return;
    }
    remove('config');
    ({ cfg, custom } = current());
    render();
    closeEditor();
    toast('Back to the example sites.');
  });
}

function setupLink() {
  return location.origin + location.pathname + '#setup=' + encode(plain(cfg));
}

