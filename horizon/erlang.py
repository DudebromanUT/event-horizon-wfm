"""Queueing math for one interval: Erlang C, Erlang A, a staffing solver and a simulator.

Pure Python 3.10 with no dependencies, so the same numbers come out in
Pythonista on a phone, on a Mac, in GitHub Actions or inside Claude.

Units: times are in seconds, and `calls` is the number offered in one interval
of `interval` seconds. Service level (`sl`) is the share of *offered* calls
answered within `target` seconds, so abandoned calls count against it.

Erlang C assumes nobody hangs up. Erlang A (the Palm/Erlang-A queue, M/M/N+M)
adds callers who give up after an exponentially distributed wait with mean
`patience` seconds. Estimate patience from interval data as total seconds all
callers waited (answered and abandoned) divided by the number of abandons.
"""

import heapq
import math
import random
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class Metrics:
    model: str                  # 'C' or 'A'
    agents: int
    calls: float
    aht: float
    interval: float
    target: float
    patience: Optional[float]
    load: float                 # offered workload in Erlangs
    p_wait: float               # share of calls that wait at all
    sl: float                   # answered within target / offered
    asa: float                  # average wait of answered calls, seconds
    abandon: float              # share of offered calls that hang up
    occupancy: float            # share of agent time spent handling calls

    def as_dict(self):
        return asdict(self)


def workload(calls, aht, interval=1800.0):
    """Offered workload in Erlangs: the average number of agents busy if nobody waited."""
    return calls * aht / interval


def _check(calls, aht, agents, target, interval, patience):
    if calls < 0:
        raise ValueError('calls cannot be negative')
    if aht <= 0:
        raise ValueError('aht must be positive')
    if interval <= 0:
        raise ValueError('interval must be positive')
    if target < 0:
        raise ValueError('target cannot be negative')
    if patience is not None and patience <= 0:
        raise ValueError('patience must be positive (or None for Erlang C)')
    if agents is not None and (agents < 0 or int(agents) != agents):
        raise ValueError('agents must be a whole number of zero or more')


def _idle(model, agents, calls, aht, interval, target, patience):
    return Metrics(model, agents, calls, aht, interval, target, patience,
                   0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


def erlang_c(calls, aht, agents, target=20.0, interval=1800.0):
    """Erlang C: callers wait as long as it takes."""
    _check(calls, aht, agents, target, interval, None)
    agents = int(agents)
    a = workload(calls, aht, interval)
    if a == 0:
        return _idle('C', agents, calls, aht, interval, target, None)
    if agents <= a:
        # The queue grows without limit: nobody is answered within any target.
        occ = 1.0 if agents else 0.0
        return Metrics('C', agents, calls, aht, interval, target, None,
                       a, 1.0, 0.0, math.inf, 0.0, occ)
    # 1/ErlangB by recursion: stable for thousands of agents, no factorials.
    inv_b = 1.0
    for k in range(1, agents + 1):
        inv_b = 1.0 + inv_b * k / a
    p_wait = agents / (inv_b * (agents - a) + a)
    sl = 1.0 - p_wait * math.exp(-(agents - a) * target / aht)
    asa = p_wait * aht / (agents - a)
    return Metrics('C', agents, calls, aht, interval, target, None,
                   a, p_wait, sl, asa, 0.0, a / agents)


def erlang_a(calls, aht, agents, patience, target=20.0, interval=1800.0):
    """Erlang A: callers hang up after an exponential wait with mean `patience`.

    Exact for the M/M/N+M model. The steady-state queue length comes from the
    birth-death chain; for a caller who arrives behind j others, the chance of
    being answered is b/(b+j+1) with b = N*mu/theta, and the time to answer is
    a sum of exponentials whose tail is a negative binomial sum, so service
    level needs no numerical integration.
    """
    _check(calls, aht, agents, target, interval, patience)
    agents = int(agents)
    if calls == 0:
        return _idle('A', agents, calls, aht, interval, target, patience)
    lam = calls / interval
    mu = 1.0 / aht
    theta = 1.0 / patience
    n = agents
    a = lam / mu

    # Log weights of each state, relative to state n (all agents busy, nobody waiting).
    below = [0.0] * n                     # states 0..n-1
    lw = 0.0
    for k in range(n, 0, -1):
        lw += math.log(k / a)
        below[k - 1] = lw
    above = [0.0]                         # states n, n+1, ...: index j = callers waiting
    lmax = max(below) if below else 0.0
    lmax = max(lmax, 0.0)
    lw = 0.0
    j = 0
    while True:
        j += 1
        rate_out = n * mu + j * theta
        lw += math.log(lam / rate_out)
        above.append(lw)
        if lw > lmax:
            lmax = lw
        if (rate_out > lam and lw < lmax - 40.0) or j >= 2_000_000:
            break

    z = math.fsum(math.exp(v - lmax) for v in below) + math.fsum(math.exp(v - lmax) for v in above)
    p_below = [math.exp(v - lmax) / z for v in below]
    p0 = math.fsum(p_below)               # arrives to a free agent

    b = n * mu / theta
    served = p0
    served_in_target = p0
    wait_of_served = 0.0
    busy = math.fsum(k * p for k, p in enumerate(p_below))
    if target > 0:
        log_x_p = -(n * mu + theta) * target
        log_1mx = math.log(-math.expm1(-theta * target))
    log_u = 0.0
    tail = 0.0                            # P(still waiting at target | j callers ahead)
    mean_wait = 0.0                       # E[wait | answered, j ahead]
    for jj, v in enumerate(above):
        p = math.exp(v - lmax) / z
        busy += n * p
        answer = b / (b + jj + 1)         # chance this caller is answered at all
        served += p * answer
        mean_wait += 1.0 / (n * mu + (jj + 1) * theta)
        wait_of_served += p * answer * mean_wait
        if target > 0:
            log_u = log_x_p if jj == 0 else log_u + math.log((b + jj) / jj) + log_1mx
            tail += math.exp(log_u)
            served_in_target += p * answer * max(0.0, 1.0 - tail)

    abandon = max(0.0, 1.0 - served)
    asa = wait_of_served / served if served > 0 else math.inf
    occupancy = busy / n if n else 0.0
    return Metrics('A', agents, calls, aht, interval, target, patience,
                   a, 1.0 - p0, served_in_target, asa, abandon, occupancy)


def metrics(calls, aht, agents, target=20.0, interval=1800.0, patience=None):
    """Erlang A when patience is known, Erlang C otherwise."""
    if patience is None:
        return erlang_c(calls, aht, agents, target, interval)
    return erlang_a(calls, aht, agents, patience, target, interval)


def meets(m, sl=None, max_occupancy=None, max_abandon=None, max_asa=None):
    return ((sl is None or m.sl >= sl)
            and (max_occupancy is None or m.occupancy <= max_occupancy)
            and (max_abandon is None or m.abandon <= max_abandon)
            and (max_asa is None or m.asa <= max_asa))


def required_agents(calls, aht, sl=0.8, target=20.0, interval=1800.0, patience=None,
                    max_occupancy=None, max_abandon=None, max_asa=None):
    """Fewest agents that meet every goal given. Returns that staffing level's Metrics."""
    _check(calls, aht, None, target, interval, patience)
    a = workload(calls, aht, interval)
    if a == 0:
        return metrics(calls, aht, 0, target, interval, patience)
    if patience is None:
        n = int(math.floor(a)) + 1
        if max_occupancy:
            n = max(n, int(math.ceil(a / max_occupancy - 1e-9)))
    else:
        # Answered share is at most n/a, so service level sl needs at least sl*a agents.
        n = max(1, int(math.floor(a * sl))) if sl else 1
    limit = int(2 * a + 12 * math.sqrt(a) + 60)
    while n <= limit:
        m = metrics(calls, aht, n, target, interval, patience)
        if meets(m, sl, max_occupancy, max_abandon, max_asa):
            return m
        n += 1
    raise ValueError('no staffing level meets all of these goals')


def staffing_table(calls, aht, around, spread=3, target=20.0, interval=1800.0, patience=None):
    """Metrics for `around - spread` .. `around + spread` agents: the service-level cliff."""
    low = max(0, around - spread)
    return [metrics(calls, aht, n, target, interval, patience) for n in range(low, around + spread + 1)]


def simulate(calls, aht, agents, patience=None, target=20.0, interval=1800.0,
             n_calls=200_000, seed=7, aht_cv=None):
    """First-come-first-served queue by simulation, to check the formulas or relax them.

    `aht_cv` swaps exponential handle times for lognormal ones with that
    coefficient of variation (real handle times are rarely exponential).
    """
    _check(calls, aht, agents, target, interval, patience)
    if calls == 0 or agents == 0:
        raise ValueError('simulate needs calls and agents')
    rng = random.Random(seed)
    lam = calls / interval
    if aht_cv is None:
        def service():
            return rng.expovariate(1.0 / aht)
    else:
        sigma = math.sqrt(math.log(1.0 + aht_cv ** 2))
        mu_ln = math.log(aht) - sigma ** 2 / 2.0

        def service():
            return rng.lognormvariate(mu_ln, sigma)
    free = [0.0] * int(agents)            # when each agent next becomes free
    t = 0.0
    warm = n_calls // 50
    offered = answered = within = abandoned = 0
    total_wait = busy_time = 0.0
    start = None
    for i in range(n_calls + warm):
        t += rng.expovariate(lam)
        wait = max(0.0, free[0] - t)
        tau = rng.expovariate(1.0 / patience) if patience else math.inf
        counted = i >= warm
        if counted and start is None:
            start = t
        if tau < wait:
            if counted:
                offered += 1
                abandoned += 1
            continue
        s = service()
        heapq.heapreplace(free, t + wait + s)
        if counted:
            offered += 1
            answered += 1
            total_wait += wait
            busy_time += s
            if wait <= target:
                within += 1
    span = t - start if start is not None else 0.0
    return {'sl': within / offered, 'abandon': abandoned / offered,
            'asa': total_wait / answered if answered else math.inf,
            'occupancy': busy_time / (agents * span) if span > 0 else 0.0}
