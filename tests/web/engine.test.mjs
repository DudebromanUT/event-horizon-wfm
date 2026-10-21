/* The web app's JavaScript engine gives the same answers as the Python engine.
 * tests/web/golden.json holds Python's answers (scripts/golden.py writes it).
 *
 *   Run: node --test tests/web/ */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import * as E from '../../docs/app/engine.js';
import * as C from '../../docs/app/clock.js';
import * as F from '../../docs/app/format.js';

const golden = JSON.parse(fs.readFileSync(new URL('./golden.json', import.meta.url), 'utf8'));
const S = golden.staffing, K = golden.clock;

// Numbers agree to 1e-9 relative; libm differences between Python and V8 sit far below that.
function same(actual, expected, path = '$') {
  if (expected === 'inf') expected = Infinity;
  if (typeof expected === 'number') {
    assert.equal(typeof actual, 'number', path + ' should be a number');
    if (expected === Infinity || actual === Infinity) return assert.equal(actual, expected, path);
    const tol = 1e-9 * Math.max(1, Math.abs(expected), Math.abs(actual));
    assert.ok(Math.abs(actual - expected) <= tol, `${path}: ${actual} != ${expected}`);
  } else if (Array.isArray(expected)) {
    assert.equal(actual.length, expected.length, path + ' length');
    expected.forEach((e, i) => same(actual[i], e, `${path}[${i}]`));
  } else if (expected && typeof expected === 'object') {
    for (const k of Object.keys(expected)) same(actual[k], expected[k], `${path}.${k}`);
  } else {
    assert.equal(actual, expected, path);
  }
}

const py = m => ({ model: m.model, agents: m.agents, load: m.load, p_wait: m.pWait, sl: m.sl, asa: m.asa,
  abandon: m.abandon, occupancy: m.occupancy });

const goals = kw => ({ calls: kw.calls, aht: kw.aht, sl: kw.sl ?? 0.8, target: kw.target ?? 20,
  interval: kw.interval ?? 1800, patience: kw.patience ?? null, maxOccupancy: kw.max_occupancy ?? null,
  maxAbandon: kw.max_abandon ?? null, maxAsa: kw.max_asa ?? null });

test('Erlang C matches Python', () => {
  S.erlang_c.forEach((c, i) => same(py(E.erlangC(...c.in)), c.out, `erlang_c[${i}]`));
});

test('Erlang A matches Python', () => {
  S.erlang_a.forEach((c, i) => same(py(E.erlangA(...c.in)), c.out, `erlang_a[${i}]`));
});

test('staffing solver matches Python', () => {
  S.required.forEach((c, i) => same(py(E.requiredAgents(goals(c.in))), c.out, `required[${i}]`));
  S.tables.forEach((c, i) => same(E.staffingTable(c.in.calls, c.in.aht, c.in.around, c.in.spread, 20, 1800,
    c.in.patience ?? null).map(py), c.out, `tables[${i}]`));
});

test('money matches Python', () => {
  S.cheapest.forEach((c, i) => {
    const best = E.cheapestStaffing(...c.in);
    same({ agents: best.agents, staff: best.staff, abandons: best.abandons, total: best.total, sl: best.metrics.sl,
      abandon: best.metrics.abandon, at_10: E.costAt(10, ...c.in).total }, c.out, `cheapest[${i}]`);
  });
  same(E.fte(...S.money[0].fte), S.money[0].out, 'fte');
  same(E.staffCost(...S.money[1].staff_cost), S.money[1].out, 'staff_cost');
});

test('what-ifs match Python', () => {
  S.pooling.forEach((c, i) => {
    const p = E.pooling(c.in.queues.map(([calls, aht]) => ({ calls, aht })), goals({ ...c.in.goals }));
    same({ separate: p.separate.map(m => m.agents), pooled: p.pooled.agents, pooled_aht: p.pooled.aht, saved: p.saved },
      c.out, `pooling[${i}]`);
  });
  S.containment.forEach((c, i) => {
    const k = c.in;
    const r = E.containment({ ...goals(k), contained: k.contained ?? 0, ahtChange: k.aht_change ?? 0,
      assistSeconds: k.assist_seconds ?? 0, recontact: k.recontact ?? 0 });
    same({ before: r.before.agents, after: r.after.agents, effective: r.effective, calls_after: r.callsAfter,
      aht_after: r.ahtAfter, saved: r.saved, saved_share: r.savedShare }, c.out, `containment[${i}]`);
  });
  S.move.forEach((c, i) => {
    const mv = E.moveAgents(c.in.source, c.in.dest, c.in.n, c.in.borrowed_aht);
    same({ source_before: py(mv.sourceBefore), source_after: py(mv.sourceAfter), dest_before: py(mv.destBefore),
      dest_after: py(mv.destAfter) }, c.out, `move[${i}]`);
  });
  S.chat.forEach((c, i) => {
    const rows = E.compareConcurrency(c.in.chats, c.in.aht_by_concurrency, { sl: c.in.sl, target: c.in.target });
    same(rows.map(r => ({ concurrency: r.concurrency, agents: r.agents, seats: r.seats.agents })), c.out, `chat[${i}]`);
  });
});

test('time zone offsets and changes match Python', () => {
  const instants = ['2026-10-19T06:00', '2026-10-25T00:59', '2026-10-25T01:00', '2026-11-01T05:59', '2026-11-01T06:00',
    '2026-11-01T07:59', '2026-11-01T08:00', '2027-01-15T12:00', '2027-03-14T06:59', '2027-03-14T07:00',
    '2027-03-14T08:59', '2027-03-14T09:00', '2027-03-28T00:59', '2027-03-28T01:00', '2027-04-04T12:00',
    '2027-07-07T12:00'].map(t => new Date(t + 'Z'));
  for (const c of K.offsets) same(instants.map(d => C.offset(c.zone, d)), c.out, `offsets ${c.zone}`);
  for (const c of K.changes) {
    const got = C.changes(c.zone, new Date('2026-10-19T00:00Z'), new Date('2027-12-31T00:00Z'))
      .map(x => [x.at.toISOString().slice(0, 16) + 'Z', x.offset]);
    same(got, c.out, `changes ${c.zone}`);
  }
  for (const c of K.to_utc) {
    const [d, t] = c.local.split('T');
    const [y, m, day] = d.split('-').map(Number), [hh, mm] = t.split(':').map(Number);
    assert.equal(C.toUtc(c.zone, y, m, day, hh, mm).toISOString().slice(0, 16) + 'Z', c.out, `to_utc ${c.zone} ${c.local}`);
  }
});

test('opening hours match Python', () => {
  for (const c of K.hours) same(C.parseHours(c.in), c.out, `hours ${JSON.stringify(c.in)}`);
  const sites = Object.fromEntries(K.seven.sites.map(s => [s.id, { ...s, _hours: C.parseHours(s.hours) }]));
  for (const c of K.open) {
    const at = new Date(c.at + 'Z');
    assert.equal(C.isOpen(sites[c.site], at), c.open, `open ${c.site} ${c.at}`);
    const [when, opening] = C.nextOpenChange(sites[c.site], at);
    same(when ? [when.toISOString().slice(0, 16) + 'Z', opening] : null, c.next, `next ${c.site} ${c.at}`);
  }
});

test('the Sites board matches Python', () => {
  const example = C.prepare(JSON.parse(fs.readFileSync(new URL('../../config/operation.example.json', import.meta.url), 'utf8')));
  const seven = C.prepare(K.seven);
  for (const c of K.boards) {
    const board = C.sitesBoard(c.config === 'example' ? example : seven, new Date(c.at + 'Z'));
    assert.deepEqual(board, c.out, `board ${c.config} ${c.at}`);
  }
});

test('formatting matches Python', () => {
  for (const [v, out] of golden.format.secs) assert.equal(F.secs(v), out, `secs(${v})`);
  for (const [v, d, out] of golden.format.pct) assert.equal(F.pct(v, d), out, `pct(${v}, ${d})`);
  for (const [v, out] of golden.format.money) assert.equal(F.money(v), out, `money(${v})`);
});

test('bad input says what to fix', () => {
  assert.throws(() => E.erlangC(100, 0, 10), /Handle time/);
  assert.throws(() => E.erlangA(100, 300, 10, 0), /Patience/);
  assert.throws(() => E.requiredAgents({ calls: 100, aht: 300, sl: 1.5 }), /No staffing level/);
  assert.throws(() => C.prepare({ sites: [{ id: 'X', name: 'X', zone: 'Mars/Base', hours: {} }] }), /not a time zone/);
  assert.throws(() => C.parseHours({ funday: '08:00-17:00' }), /Bad day/);
});
