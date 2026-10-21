/* Calc: staffing for one interval, with the service-level cliff, the Erlang C comparison, and money. */

import { $, el, setText, showError, svg } from './dom.js';
import { bind, flag, number, percent } from './form.js';
import { cheapestStaffing, costAt, fte, requiredAgents, roundUpFte, staffCost, staffingTable } from './engine.js';
import { goalLabel, money, num, pct, secs } from './format.js';
import { cliff } from './chart.js';

const DASH = '—';
let lastChart = null;
let peekText = '';
let onCalcTab = true;
let heroVisible = true;

function read(v) {
  return {
    calls: number(v, 'c-calls', 'Calls per interval', { min: 0 }),
    aht: number(v, 'c-aht', 'Handle time', { min: 1 }),
    interval: Number(v['c-interval'] || 1800),
    sl: percent(v, 'c-sl', 'Service level'),
    target: number(v, 'c-target', 'Answered within', { min: 0 }),
    maxAbandon: percent(v, 'c-maxab', 'Most hang-ups allowed', { required: false }),
    maxOccupancy: percent(v, 'c-maxocc', 'Highest occupancy', { required: false }),
    patience: number(v, 'c-pat', 'Average patience', { required: false, min: 1 }),
    shrinkage: percent(v, 'c-shrink', 'Shrinkage', { required: false, max: 95 }),
    cost: number(v, 'c-cost', 'Cost per paid agent hour', { required: false, min: 0 }),
    abandonCost: number(v, 'c-abcost', 'Cost of one hang-up', { required: false, min: 0 }),
  };
}

function row(label, value) {
  return el('div', {}, el('dt', { text: label }), el('dd', { text: value }));
}

function verdict(q, m) {
  const node = $('#calc-verdict');
  let good = true, text;
  if (q.patience != null && q.maxAbandon == null && m.abandon > 0.05) {
    good = false;
    text = `${pct(m.abandon)} of callers hang up to make this goal. Set a hang-up limit to stop that.`;
  } else if (q.maxOccupancy == null && m.occupancy > 0.9) {
    good = false;
    text = `Agents would be busy ${pct(m.occupancy, 0)} of the time. Set an occupancy limit to protect them.`;
  } else {
    const parts = [`Meets ${goalLabel(q.sl, q.target)}`];
    if (q.patience != null && q.maxAbandon != null) parts.push(`hang-ups at or under ${pct(q.maxAbandon, 0)}`);
    if (q.maxOccupancy != null) parts.push(`occupancy at or under ${pct(q.maxOccupancy, 0)}`);
    text = parts.join(', ') + '.';
  }
  node.className = 'verdict ' + (good ? 'ok' : 'warn');
  const icon = svg('svg', { viewBox: '0 0 20 20', 'aria-hidden': 'true' });
  icon.append(svg('path', { d: good ? 'M4 10.5l4 4 8-9' : 'M10 4v7M10 15.5v.5' }));
  node.replaceChildren(icon, el('span', { text }));
}

function render(q, m, c) {
  setText('calc-model', q.patience == null ? 'Erlang C · nobody hangs up' : `Erlang A · callers hang up after ${secs(q.patience)} on average`);
  setText('calc-agents', String(m.agents));
  setText('k-sl', pct(m.sl));
  setText('k-asa', secs(m.asa));
  setText('k-ab', q.patience == null ? DASH : pct(m.abandon));
  setText('k-occ', pct(m.occupancy, 0));
  verdict(q, m);
  setText('c-aht-hint', `${secs(q.aht)} talk, hold and wrap`);
  setText('c-pat-hint', q.patience == null
    ? 'How long callers wait before hanging up. Blank means nobody hangs up (Erlang C).'
    : `${secs(q.patience)} before the average caller hangs up. Blank means nobody hangs up.`);

  lastChart = { rows: staffingTable(q.calls, q.aht, m.agents, 4, q.target, q.interval, q.patience), goal: q.sl, pick: m.agents };
  drawChart();

  const list = $('#calc-compare-list');
  const items = [row('Nobody hangs up (Erlang C)', `${c.agents} agents · ${pct(c.sl)} · wait ${secs(c.asa)}`)];
  if (q.patience != null) {
    items.push(row(`Callers hang up after ${secs(q.patience)} (Erlang A)`, `${m.agents} agents · ${pct(m.sl)} · ${pct(m.abandon)} hang up`));
  }
  list.replaceChildren(...items);
  let note = 'Add a caller patience to see how hang-ups change the answer.';
  if (q.patience != null) {
    const gap = c.agents - m.agents;
    note = gap > 0 ? `Erlang C asks for ${gap} more agent${gap === 1 ? '' : 's'} than real callers need at these goals.`
      : gap < 0 ? `Your hang-up limit needs ${-gap} more agent${gap === -1 ? '' : 's'} than Erlang C's answer.`
        : 'Both models land on the same staffing here.';
  }
  let compareNote = $('#calc-compare-note');
  if (!compareNote) {
    compareNote = el('p', { class: 'lede', id: 'calc-compare-note' });
    $('#calc-compare').append(compareNote);
  }
  compareNote.textContent = note;

  const body = $('#calc-table tbody');
  body.replaceChildren(...staffingTable(q.calls, q.aht, m.agents, 3, q.target, q.interval, q.patience).map(r =>
    el('tr', { class: r.agents === m.agents ? 'pick' : null },
      el('td', { text: String(r.agents) }), el('td', { text: pct(r.sl) }), el('td', { text: secs(r.asa) }),
      el('td', { text: q.patience == null ? DASH : pct(r.abandon) }), el('td', { text: pct(r.occupancy, 0) }))));

  const money1 = [];
  const notes = [];
  if (q.shrinkage != null) {
    const need = fte(m.agents, q.shrinkage);
    money1.push(row(`Scheduled at ${pct(q.shrinkage, 0)} shrinkage`, `${need.toFixed(1)} FTE (${num(roundUpFte(need))} to hire)`));
  }
  if (q.cost) {
    const per = staffCost(m.agents, q.cost, q.interval, q.shrinkage || 0);
    money1.push(row('Agent cost per interval', money(per)));
    money1.push(row('Agent cost per open hour', money(per * 3600 / q.interval)));
  } else {
    notes.push('Add a cost per paid hour to see what this staffing costs.');
  }
  if (q.cost && q.abandonCost && q.patience != null) {
    const best = cheapestStaffing(q.calls, q.aht, q.patience, q.cost, q.abandonCost, q.target, q.interval, q.shrinkage || 0);
    const atGoal = costAt(m.agents, q.calls, q.aht, q.patience, q.cost, q.abandonCost, q.target, q.interval, q.shrinkage || 0);
    money1.push(row(`Cheapest at ${money(q.abandonCost)} a hang-up`, `${best.agents} agents · ${pct(best.metrics.sl)} · ${pct(best.metrics.abandon)} hang up`));
    money1.push(row('Agents plus hang-ups, per interval', `${money(best.total)} cheapest vs ${money(atGoal.total)} at your goal`));
  } else if (q.cost && !q.abandonCost) {
    notes.push('Add the cost of one hang-up to find the cheapest staffing level.');
  } else if (q.cost && q.abandonCost && q.patience == null) {
    notes.push('The cheapest staffing level needs a caller patience, so hang-ups have a cost.');
  }
  $('#calc-money-list').replaceChildren(...money1);
  setText('calc-money-note', notes.join(' '));

  peekText = `${m.agents} agents · ${pct(m.sl)}`;
  updatePeek();
}

function drawChart() {
  if (!lastChart) return;
  cliff($('#cliff'), $('#cliff-tip'), lastChart.rows, { goal: lastChart.goal, pick: lastChart.pick });
}

function update(v) {
  const form = $('#calc-form');
  try {
    const q = read(v);
    const goals = { calls: q.calls, aht: q.aht, sl: q.sl, target: q.target, interval: q.interval,
      maxOccupancy: q.maxOccupancy };
    const m = requiredAgents({ ...goals, patience: q.patience, maxAbandon: q.patience == null ? null : q.maxAbandon });
    const c = q.patience == null ? m : requiredAgents({ ...goals, patience: null });
    flag(form, null);
    showError('calc-error', null);
    render(q, m, c);
  } catch (e) {
    flag(form, e);
    showError('calc-error', e);
  }
}

function updatePeek() {
  const peek = $('#peek');
  peek.textContent = peekText;
  peek.hidden = !(onCalcTab && !heroVisible && peekText);
}

export function onTab(active) {
  onCalcTab = active;
  updatePeek();
}

export function init() {
  bind($('#calc-form'), 'calc', update);
  if ('ResizeObserver' in window) {
    let width = 0;
    new ResizeObserver(entries => {
      const w = Math.round(entries[0].contentRect.width);
      if (w && w !== width) { width = w; drawChart(); }
    }).observe($('#cliff'));
  }
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      heroVisible = entries[0].isIntersecting;
      updatePeek();
    }, { rootMargin: '-60px 0px 0px 0px' }).observe($('#calc-hero'));
  }
}
