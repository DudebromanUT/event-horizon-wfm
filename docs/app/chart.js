/* Charts drawn as plain SVG and HTML.
 * cliff():  service level at each staffing level, the recommendation in the accent and the rest
 *           neutral, the goal as a reference line, a tooltip on every bar (pointer and keyboard).
 * hbars():  labeled horizontal bars on one scale. */

import { svg, el } from './dom.js';
import { pct, secs } from './format.js';

function topRounded(x, y, w, h, r) {
  r = Math.max(0, Math.min(r, w / 2, h));
  return `M${x},${y + h}L${x},${y + r}Q${x},${y} ${x + r},${y}L${x + w - r},${y}Q${x + w},${y} ${x + w},${y + r}L${x + w},${y + h}Z`;
}

function describe(r) {
  const parts = [`${r.agents} agents`, `service level ${pct(r.sl)}`, `average wait ${secs(r.asa)}`];
  if (r.patience != null) parts.push(`hang-ups ${pct(r.abandon)}`);
  parts.push(`occupancy ${pct(r.occupancy, 0)}`);
  return parts.join(', ');
}

export function cliff(box, tip, rows, { goal, pick }) {
  box.replaceChildren();
  tip.hidden = true;
  if (!rows.length) return;
  const W = Math.max(260, Math.round(box.clientWidth || 340));
  const H = 188;
  const m = { top: 26, right: 6, bottom: 26, left: 38 };
  const pw = W - m.left - m.right, ph = H - m.top - m.bottom;
  const band = pw / rows.length;
  const bw = Math.min(24, band * 0.6);
  const y = v => m.top + ph * (1 - v);

  const chart = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img',
    'aria-label': `Service level from ${rows[0].agents} to ${rows[rows.length - 1].agents} agents. ` +
      `${pick} agents is the fewest that meets the goal.` });

  for (const v of [0.5, 1]) {
    chart.append(svg('line', { class: 'grid', x1: m.left, x2: W - m.right, y1: y(v), y2: y(v) }));
    chart.append(svg('text', { x: m.left - 6, y: y(v) + 4, 'text-anchor': 'end' }, `${v * 100}%`));
  }
  chart.append(svg('text', { x: m.left - 6, y: y(0) + 4, 'text-anchor': 'end' }, '0%'));

  rows.forEach((r, i) => {
    const cx = m.left + band * (i + 0.5);
    const top = y(Math.max(0, Math.min(1, r.sl)));
    const h = y(0) - top;
    const chosen = r.agents === pick;
    const hit = svg('rect', { class: 'hit', x: m.left + band * i, y: m.top, width: band, height: ph, tabindex: 0,
      'aria-label': describe(r) });
    chart.append(hit);
    chart.append(svg('path', { class: 'bar' + (chosen ? ' pick' : ''), d: topRounded(cx - bw / 2, top, bw, Math.max(h, 1), 4) }));
    chart.append(svg('text', { x: cx, y: H - 8, 'text-anchor': 'middle', class: chosen ? 'value' : null }, String(r.agents)));
    if (chosen) chart.append(svg('text', { class: 'value', x: cx, y: top - 7, 'text-anchor': 'middle' }, pct(r.sl)));
    const show = () => {
      tip.replaceChildren(el('strong', { text: `${r.agents} agents` }),
        el('span', { text: `Service level ${pct(r.sl)}` }), el('span', { text: `Avg wait ${secs(r.asa)}` }),
        r.patience != null ? el('span', { text: `Hang-ups ${pct(r.abandon)}` }) : null,
        el('span', { text: `Occupancy ${pct(r.occupancy, 0)}` }));
      tip.hidden = false;
      const fig = box.parentElement.getBoundingClientRect(), chartBox = box.getBoundingClientRect();
      const scale = chartBox.width / W;
      const left = chartBox.left - fig.left + cx * scale - tip.offsetWidth / 2;
      tip.style.left = Math.max(4, Math.min(fig.width - tip.offsetWidth - 4, left)) + 'px';
      tip.style.top = Math.max(4, chartBox.top - fig.top + top * scale - tip.offsetHeight - 10) + 'px';
    };
    const hide = () => { tip.hidden = true; };
    hit.addEventListener('pointerenter', show);
    hit.addEventListener('pointerdown', show);
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('focus', show);
    hit.addEventListener('blur', hide);
  });

  chart.append(svg('line', { class: 'base', x1: m.left, x2: W - m.right, y1: y(0), y2: y(0) }));
  const gy = y(goal);
  chart.append(svg('line', { class: 'goal', x1: m.left, x2: W - m.right, y1: gy, y2: gy }));
  chart.append(svg('text', { class: 'goal-label', x: m.left + 4, y: gy - 5 }, `Goal ${pct(goal, 0)}`));
  box.append(chart);
}

/* items: [{label, value, text, pick}] on one scale from 0 to `max`. */
export function hbars(list, items, max) {
  const top = max || Math.max(...items.map(i => i.value), 1e-9);
  list.replaceChildren(...items.map(i => {
    const fill = el('div', { class: 'fill' });
    fill.style.width = Math.max(1.5, Math.min(100, 100 * i.value / top)) + '%';
    return el('li', { class: i.pick ? 'pick' : null },
      el('div', { class: 'label' }, el('span', { text: i.label }), el('b', { text: i.text })),
      el('div', { class: 'track' }, fill));
  }));
}
