/* Staffing math for one interval: Erlang C, Erlang A, the staffing solver, money and what-ifs.
 * A line-for-line port of the Python engine in horizon/. tests/web/engine.test.mjs checks that
 * both give the same answers on every case in tests/web/golden.json.
 *
 * Times are in seconds; `calls` is the number offered in one interval of `interval` seconds.
 * Service level (sl) is the share of offered calls answered within `target` seconds, so
 * hang-ups count against it. */

export function workload(calls, aht, interval = 1800) {
  return calls * aht / interval;
}

function check(calls, aht, agents, target, interval, patience) {
  if (!(calls >= 0)) throw new RangeError('Calls cannot be negative.');
  if (!(aht > 0)) throw new RangeError('Handle time must be above zero.');
  if (!(interval > 0)) throw new RangeError('The interval must be above zero.');
  if (!(target >= 0)) throw new RangeError('The answer target cannot be negative.');
  if (patience != null && !(patience > 0)) throw new RangeError('Patience must be above zero, or left blank.');
  if (agents != null && !(Number.isInteger(agents) && agents >= 0)) throw new RangeError('Agents must be a whole number.');
}

// Compensated summation, close to Python's math.fsum.
function fsum(values) {
  let sum = 0, carry = 0;
  for (const v of values) {
    const t = sum + v;
    carry += Math.abs(sum) >= Math.abs(v) ? (sum - t) + v : (v - t) + sum;
    sum = t;
  }
  return sum + carry;
}

function result(model, agents, calls, aht, interval, target, patience, load, pWait, sl, asa, abandon, occupancy) {
  return { model, agents, calls, aht, interval, target, patience, load, pWait, sl, asa, abandon, occupancy };
}

/* Erlang C: callers wait as long as it takes. */
export function erlangC(calls, aht, agents, target = 20, interval = 1800) {
  check(calls, aht, agents, target, interval, null);
  const a = workload(calls, aht, interval);
  if (a === 0) return result('C', agents, calls, aht, interval, target, null, 0, 0, 1, 0, 0, 0);
  if (agents <= a) {
    // The queue grows without limit: nobody is answered within any target.
    return result('C', agents, calls, aht, interval, target, null, a, 1, 0, Infinity, 0, agents ? 1 : 0);
  }
  let invB = 1;                       // 1/ErlangB by recursion: stable for thousands of agents
  for (let k = 1; k <= agents; k++) invB = 1 + invB * k / a;
  const pWait = agents / (invB * (agents - a) + a);
  const sl = 1 - pWait * Math.exp(-(agents - a) * target / aht);
  return result('C', agents, calls, aht, interval, target, null, a, pWait, sl, pWait * aht / (agents - a), 0, a / agents);
}

/* Erlang A (M/M/N+M): callers hang up after an exponential wait with mean `patience`.
 * Exact for that model; see horizon/erlang.py for the derivation. */
export function erlangA(calls, aht, agents, patience, target = 20, interval = 1800) {
  check(calls, aht, agents, target, interval, patience);
  if (calls === 0) return result('A', agents, calls, aht, interval, target, patience, 0, 0, 1, 0, 0, 0);
  const lam = calls / interval, mu = 1 / aht, theta = 1 / patience, n = agents, a = lam / mu;

  // Log weights of each state, relative to state n (all agents busy, nobody waiting).
  const below = new Array(n);
  let lw = 0;
  for (let k = n; k > 0; k--) {
    lw += Math.log(k / a);
    below[k - 1] = lw;
  }
  let lmax = 0;
  for (const v of below) if (v > lmax) lmax = v;
  const above = [0];
  lw = 0;
  let j = 0;
  for (;;) {
    j += 1;
    const rateOut = n * mu + j * theta;
    lw += Math.log(lam / rateOut);
    above.push(lw);
    if (lw > lmax) lmax = lw;
    if ((rateOut > lam && lw < lmax - 40) || j >= 2000000) break;
  }

  const z = fsum(below.map(v => Math.exp(v - lmax))) + fsum(above.map(v => Math.exp(v - lmax)));
  const pBelow = below.map(v => Math.exp(v - lmax) / z);
  const p0 = fsum(pBelow);            // arrives to a free agent

  const b = n * mu / theta;
  let served = p0, servedInTarget = p0, waitOfServed = 0;
  let busy = fsum(pBelow.map((p, k) => k * p));
  let logXp = 0, log1mx = 0;
  if (target > 0) {
    logXp = -(n * mu + theta) * target;
    log1mx = Math.log(-Math.expm1(-theta * target));
  }
  let logU = 0, tail = 0, meanWait = 0;
  for (let jj = 0; jj < above.length; jj++) {
    const p = Math.exp(above[jj] - lmax) / z;
    busy += n * p;
    const answer = b / (b + jj + 1);  // chance this caller is answered at all
    served += p * answer;
    meanWait += 1 / (n * mu + (jj + 1) * theta);
    waitOfServed += p * answer * meanWait;
    if (target > 0) {
      logU = jj === 0 ? logXp : logU + Math.log((b + jj) / jj) + log1mx;
      tail += Math.exp(logU);
      servedInTarget += p * answer * Math.max(0, 1 - tail);
    }
  }
  const abandon = Math.max(0, 1 - served);
  const asa = served > 0 ? waitOfServed / served : Infinity;
  return result('A', agents, calls, aht, interval, target, patience, a, 1 - p0, servedInTarget, asa, abandon,
    n ? busy / n : 0);
}

/* Erlang A when patience is known, Erlang C otherwise. */
export function metrics(calls, aht, agents, target = 20, interval = 1800, patience = null) {
  return patience == null ? erlangC(calls, aht, agents, target, interval) : erlangA(calls, aht, agents, patience, target, interval);
}

export function meets(m, sl = null, maxOccupancy = null, maxAbandon = null, maxAsa = null) {
  return (sl == null || m.sl >= sl)
    && (maxOccupancy == null || m.occupancy <= maxOccupancy)
    && (maxAbandon == null || m.abandon <= maxAbandon)
    && (maxAsa == null || m.asa <= maxAsa);
}

/* Fewest agents that meet every goal given. */
export function requiredAgents({ calls, aht, sl = 0.8, target = 20, interval = 1800, patience = null,
  maxOccupancy = null, maxAbandon = null, maxAsa = null }) {
  check(calls, aht, null, target, interval, patience);
  const a = workload(calls, aht, interval);
  if (a === 0) return metrics(calls, aht, 0, target, interval, patience);
  let n;
  if (patience == null) {
    n = Math.floor(a) + 1;
    if (maxOccupancy) n = Math.max(n, Math.ceil(a / maxOccupancy - 1e-9));
  } else {
    // Answered share is at most n/a, so service level sl needs at least sl*a agents.
    n = sl ? Math.max(1, Math.floor(a * sl)) : 1;
  }
  const limit = Math.floor(2 * a + 12 * Math.sqrt(a) + 60);
  for (; n <= limit; n++) {
    const m = metrics(calls, aht, n, target, interval, patience);
    if (meets(m, sl, maxOccupancy, maxAbandon, maxAsa)) return m;
  }
  throw new RangeError('No staffing level meets all of these goals.');
}

/* Metrics for around - spread .. around + spread agents: the service-level cliff. */
export function staffingTable(calls, aht, around, spread = 3, target = 20, interval = 1800, patience = null) {
  const rows = [];
  for (let n = Math.max(0, around - spread); n <= around + spread; n++) rows.push(metrics(calls, aht, n, target, interval, patience));
  return rows;
}

// --- Money ---------------------------------------------------------------

export function fte(agents, shrinkage) {
  if (!(shrinkage >= 0 && shrinkage < 1)) throw new RangeError('Shrinkage must be at least 0% and below 100%.');
  return agents / (1 - shrinkage);
}

export function staffCost(agents, costPerHour, interval = 1800, shrinkage = 0) {
  return fte(agents, shrinkage) * costPerHour * interval / 3600;
}

export function roundUpFte(value, step = 0.5) {
  return Math.ceil(value / step - 1e-9) * step;
}

export function costAt(agents, calls, aht, patience, costPerHour, costPerAbandon, target = 20, interval = 1800, shrinkage = 0) {
  const m = erlangA(calls, aht, agents, patience, target, interval);
  const staff = staffCost(agents, costPerHour, interval, shrinkage);
  const abandons = calls * m.abandon;
  return { agents, staff, abandons, abandonCost: abandons * costPerAbandon, total: staff + abandons * costPerAbandon, metrics: m };
}

/* Total cost at every staffing level up to the point where no extra agent can pay for itself. */
export function costCurve(calls, aht, patience, costPerHour, costPerAbandon, target = 20, interval = 1800, shrinkage = 0) {
  if (!(costPerHour > 0)) throw new RangeError('Cost per hour must be above zero.');
  const oneAgent = staffCost(1, costPerHour, interval, shrinkage);
  const points = [];
  for (let n = 0; ; n++) {
    const p = costAt(n, calls, aht, patience, costPerHour, costPerAbandon, target, interval, shrinkage);
    points.push(p);
    if (p.abandonCost < oneAgent) return points;
  }
}

export function cheapestStaffing(calls, aht, patience, costPerHour, costPerAbandon, target = 20, interval = 1800, shrinkage = 0) {
  if (patience == null) throw new RangeError('Cheapest staffing needs a patience: without hang-ups there is no hang-up cost.');
  let best = null;
  for (const p of costCurve(calls, aht, patience, costPerHour, costPerAbandon, target, interval, shrinkage)) {
    if (!best || p.total < best.total) best = p;
  }
  return best;
}

// --- What-ifs --------------------------------------------------------------

function goalsOf({ sl = 0.8, target = 20, interval = 1800, patience = null, maxOccupancy = null, maxAbandon = null, maxAsa = null } = {}) {
  return { sl, target, interval, patience, maxOccupancy, maxAbandon, maxAsa };
}

/* Agents for each queue on its own versus one queue answered by everyone. queues: [{calls, aht}] */
export function pooling(queues, goals = {}) {
  const g = goalsOf(goals);
  const kept = queues.filter(q => q.calls > 0);
  if (!kept.length) throw new RangeError('Pooling needs at least one queue with calls.');
  const separate = kept.map(q => requiredAgents({ ...g, calls: q.calls, aht: q.aht }));
  const total = kept.reduce((s, q) => s + q.calls, 0);
  const aht = kept.reduce((s, q) => s + q.calls * q.aht, 0) / total;
  const pooled = requiredAgents({ ...g, calls: total, aht });
  const apart = separate.reduce((s, m) => s + m.agents, 0);
  return { separate, pooled, agentsSeparate: apart, saved: apart - pooled.agents };
}

/* Agents before and after a bot and/or agent assist. */
export function containment({ calls, aht, contained = 0, ahtChange = 0, assistSeconds = 0, recontact = 0, ...goals }) {
  if (!(contained >= 0 && contained <= 1)) throw new RangeError('Containment must be between 0% and 100%.');
  if (!(recontact >= 0 && recontact <= 1)) throw new RangeError('Come-backs must be between 0% and 100%.');
  const g = goalsOf(goals);
  const effective = contained * (1 - recontact);
  const callsAfter = calls * (1 - effective);
  const ahtAfter = aht * (1 + ahtChange) - assistSeconds;
  if (!(ahtAfter > 0)) throw new RangeError('Handle time after the changes must stay above zero.');
  const before = requiredAgents({ ...g, calls, aht });
  const after = requiredAgents({ ...g, calls: callsAfter, aht: ahtAfter });
  const saved = before.agents - after.agents;
  return { before, after, effective, callsAfter, ahtAfter, saved, savedShare: before.agents ? saved / before.agents : 0 };
}

function queueMetrics(q, agents = q.agents, aht = q.aht) {
  return metrics(q.calls, aht, agents, q.target ?? 20, q.interval ?? 1800, q.patience ?? null);
}

/* Move n agents from source to dest. borrowedAht: their handle time on the new queue, if slower. */
export function moveAgents(source, dest, n, borrowedAht = null) {
  if (!(Number.isInteger(n) && n >= 0 && n <= source.agents)) throw new RangeError(`You can move between 0 and ${source.agents} agents.`);
  let aht = dest.aht;
  if (borrowedAht != null && n) aht = (dest.agents * dest.aht + n * borrowedAht) / (dest.agents + n);
  return {
    sourceBefore: queueMetrics(source), sourceAfter: queueMetrics(source, source.agents - n),
    destBefore: queueMetrics(dest), destAfter: queueMetrics(dest, dest.agents + n, aht),
  };
}

/* Agents for live chat when each one handles up to `concurrency` chats at once. */
export function chatRequirement(chats, aht, concurrency, goals = {}) {
  if (!(Number.isInteger(concurrency) && concurrency >= 1)) throw new RangeError('Chats at once must be a whole number of 1 or more.');
  const seats = requiredAgents({ ...goalsOf({ target: 60, ...goals }), calls: chats, aht });
  return { agents: Math.ceil(seats.agents / concurrency), concurrency, aht, seats };
}

/* Agents at each concurrency level, given the handle time measured at each: {1: 360, 2: 480}. */
export function compareConcurrency(chats, ahtByConcurrency, goals = {}) {
  return Object.keys(ahtByConcurrency).map(Number).sort((x, y) => x - y)
    .map(c => chatRequirement(chats, ahtByConcurrency[c], c, goals));
}
