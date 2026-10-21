/* What-if: AI containment and assist, pooling queues, lending agents, chat concurrency. */

import { $, $$, el, setText, showError } from './dom.js';
import { bind, flag, number, percent, signedPercent } from './form.js';
import { compareConcurrency, containment, moveAgents, pooling, staffCost } from './engine.js';
import { money, num, pct, secs } from './format.js';
import { hbars } from './chart.js';
import { load, save } from './store.js';

const DASH = '—';
const MODES = ['ai', 'pool', 'move', 'chat'];

function guard(form, errorId, fn) {
  return v => {
    try {
      fn(v);
      flag(form, null);
      showError(errorId, null);
    } catch (e) {
      flag(form, e);
      showError(errorId, e);
    }
  };
}

// --- AI ---------------------------------------------------------------------------

function ai(v) {
  const r = containment({
    calls: number(v, 'a-calls', 'Calls per interval', { min: 0 }),
    aht: number(v, 'a-aht', 'Handle time', { min: 1 }),
    sl: percent(v, 'a-sl', 'Service level'),
    target: number(v, 'a-target', 'Answered within', { min: 0 }),
    patience: number(v, 'a-pat', 'Average patience', { required: false, min: 1 }),
    contained: percent(v, 'a-contained', 'Bot resolves'),
    recontact: percent(v, 'a-recontact', 'Still reach an agent', { required: false }) || 0,
    ahtChange: signedPercent(v, 'a-ahtchange', 'Handle time change'),
    assistSeconds: number(v, 'a-assist', 'Agent assist', { required: false, min: 0 }) || 0,
  });
  const cost = number(v, 'a-cost', 'Cost per paid agent hour', { required: false, min: 0 });
  setText('a-before', String(r.before.agents));
  setText('a-after', String(r.after.agents));
  hbars($('#a-bars'), [
    { label: 'Calls that never reach an agent', value: r.effective, text: pct(r.effective, 0) },
    { label: 'Agents saved', value: Math.max(0, r.savedShare), text: `${pct(r.savedShare, 0)} (${r.saved})`, pick: true },
  ], Math.max(r.effective, r.savedShare, 0.01));
  let note = `Left for agents: ${num(Math.round(r.callsAfter * 10) / 10)} calls at ${secs(r.ahtAfter)} each.`;
  if (cost) note += ` That saves ${money(staffCost(r.saved, cost))} of agent time per half hour.`;
  setText('a-note', note);
}

// --- Pool -------------------------------------------------------------------------

const POOL_DEFAULT = { queues: [['120', '330'], ['80', '330'], ['40', '330']] };

function poolRows() {
  const box = $('#p-queues');
  const state = load('pool-queues', POOL_DEFAULT);
  $$('.row', box).forEach(r => r.remove());
  state.queues.forEach(([calls, aht], i) => {
    const remove = el('button', { type: 'button', class: 'btn quiet small', 'aria-label': `Remove queue ${i + 1}` }, 'Remove');
    remove.addEventListener('click', () => {
      const s = load('pool-queues', POOL_DEFAULT);
      if (s.queues.length <= 1) return;
      s.queues.splice(i, 1);
      save('pool-queues', s);
      poolRows();
      poolRun();
    });
    box.append(el('div', { class: 'row' },
      el('span', { class: 'name', text: `Queue ${i + 1}` }),
      el('input', { id: `p-calls-${i}`, inputmode: 'decimal', value: calls, 'aria-label': `Queue ${i + 1} calls per interval`, placeholder: 'calls' }),
      el('input', { id: `p-aht-${i}`, inputmode: 'numeric', value: aht, 'aria-label': `Queue ${i + 1} handle time in seconds`, placeholder: 'AHT s' }),
      state.queues.length > 1 ? remove : null));
  });
}

let poolRun = () => {};

function pool(v) {
  const queues = [];
  const raw = [];
  for (let i = 0; v[`p-calls-${i}`] != null; i++) {
    raw.push([v[`p-calls-${i}`], v[`p-aht-${i}`]]);
    queues.push({ calls: number(v, `p-calls-${i}`, `Queue ${i + 1} calls`, { min: 0 }),
      aht: number(v, `p-aht-${i}`, `Queue ${i + 1} handle time`, { min: 1 }) });
  }
  save('pool-queues', { queues: raw });
  const p = pooling(queues, {
    sl: percent(v, 'p-sl', 'Service level'), target: number(v, 'p-target', 'Answered within', { min: 0 }),
    patience: number(v, 'p-pat', 'Average patience', { required: false, min: 1 }),
  });
  setText('p-apart', String(p.agentsSeparate));
  setText('p-pooled', String(p.pooled.agents));
  setText('p-saved', p.agentsSeparate ? `${p.saved} (${pct(p.saved / p.agentsSeparate, 0)})` : '0');
  const each = p.separate.map((m, i) => `${m.agents}`).join(' + ');
  setText('p-note', `Apart: ${each} agents. Pooled, one queue at ${secs(p.pooled.aht)} handle time. ` +
    'This assumes cross-trained agents keep the same handle time.');
}

// --- Move -------------------------------------------------------------------------

function move(v) {
  const target = number(v, 'm-target', 'Answered within', { min: 0 });
  const patience = number(v, 'm-pat', 'Average patience', { required: false, min: 1 });
  const sl = percent(v, 'm-sl', 'Service level goal');
  const queue = side => ({
    name: (v[`m-${side}-name`] || '').trim() || (side === 'from' ? 'From' : 'To'),
    calls: number(v, `m-${side}-calls`, 'Calls per interval', { min: 0 }),
    aht: number(v, `m-${side}-aht`, 'Handle time', { min: 1 }),
    agents: number(v, `m-${side}-agents`, 'Agents on it now', { min: 0, integer: true }),
    target, patience,
  });
  const source = queue('from'), dest = queue('to');
  const n = number(v, 'm-n', 'Agents to lend', { min: 0, integer: true });
  const mv = moveAgents(source, dest, n, number(v, 'm-borrowed', 'Their handle time there', { required: false, min: 1 }));
  const cell = m => [el('td', { text: String(m.agents) }),
    el('td', { text: pct(m.sl), class: m.sl < sl ? 'bad' : null }),
    el('td', { text: patience == null ? DASH : pct(m.abandon) })];
  $('#m-table tbody').replaceChildren(
    el('tr', {}, el('td', { text: source.name }), ...cell(mv.sourceBefore)),
    el('tr', { class: 'pick' }, el('td', { text: `after lending ${n}` }), ...cell(mv.sourceAfter)),
    el('tr', {}, el('td', { text: dest.name }), ...cell(mv.destBefore)),
    el('tr', { class: 'pick' }, el('td', { text: `after borrowing ${n}` }), ...cell(mv.destAfter)));
}

// --- Chat -------------------------------------------------------------------------

function chat(v) {
  const ahts = {};
  for (const c of [1, 2, 3, 4]) {
    const aht = number(v, `h-aht${c}`, `Handle time at ${c} chats`, { required: c === 1, min: 1 });
    if (aht != null) ahts[c] = aht;
  }
  const rows = compareConcurrency(number(v, 'h-chats', 'Chats per interval', { min: 0 }), ahts, {
    sl: percent(v, 'h-sl', 'Service level'), target: number(v, 'h-target', 'First reply within', { min: 0 }),
    patience: number(v, 'h-pat', 'Average patience', { required: false, min: 1 }),
  });
  const best = rows.reduce((b, r) => (r.agents < b.agents ? r : b), rows[0]);
  hbars($('#h-bars'), rows.map(r => ({
    label: `${r.concurrency} at once, ${secs(r.aht)} each`, value: r.agents, text: `${r.agents} agents`, pick: r === best,
  })));
  const worse = rows.filter(r => r.concurrency > best.concurrency && r.agents > best.agents);
  setText('h-note', `Fewest agents at ${best.concurrency} chat${best.concurrency === 1 ? '' : 's'} at once.` +
    (worse.length ? ` Going to ${worse[0].concurrency} needs ${worse[0].agents - best.agents} more, because each chat runs that much longer.` : ''));
}

// --- Modes ------------------------------------------------------------------------

function showMode(mode) {
  if (!MODES.includes(mode)) mode = 'ai';
  for (const m of MODES) $('#w-' + m).hidden = m !== mode;
  for (const b of $$('#w-mode button')) b.setAttribute('aria-pressed', String(b.dataset.mode === mode));
  save('whatif-mode', mode);
}

export function init() {
  for (const b of $$('#w-mode button')) b.addEventListener('click', () => showMode(b.dataset.mode));
  showMode(load('whatif-mode', 'ai'));
  bind($('#a-form'), 'whatif-ai', guard($('#a-form'), 'a-error', ai));
  poolRows();
  poolRun = bind($('#p-form'), 'whatif-pool', guard($('#p-form'), 'p-error', pool));
  $('#p-add').addEventListener('click', () => {
    const s = load('pool-queues', POOL_DEFAULT);
    if (s.queues.length >= 8) return;
    s.queues.push(['50', '300']);
    save('pool-queues', s);
    poolRows();
    poolRun();
  });
  bind($('#m-form'), 'whatif-move', guard($('#m-form'), 'm-error', move));
  bind($('#h-form'), 'whatif-chat', guard($('#h-form'), 'h-error', chat));
}
