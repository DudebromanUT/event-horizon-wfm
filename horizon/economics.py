"""Agents into FTE and dollars, and the staffing level that costs the least overall.

`cost_per_hour` is the loaded cost of one paid agent hour. `cost_per_abandon`
is what one hang-up costs the business: a lost sale on a merchant line, a
missed payment on collections, a repeat contact on customer service.
"""

import math
from dataclasses import dataclass

from .erlang import Metrics, erlang_a, required_agents


def fte(agents, shrinkage):
    """Scheduled FTE needed to keep `agents` on the queue after shrinkage (0.35 = 35%)."""
    if not 0.0 <= shrinkage < 1.0:
        raise ValueError('shrinkage must be at least 0 and below 1')
    return agents / (1.0 - shrinkage)


def staff_cost(agents, cost_per_hour, interval=1800.0, shrinkage=0.0):
    """Paid cost of keeping `agents` on the queue for one interval, shrinkage included."""
    return fte(agents, shrinkage) * cost_per_hour * interval / 3600.0


def per_year(value_per_interval, open_hours_per_week, interval=1800.0, weeks=52):
    """Scale a per-interval figure to a year of open hours."""
    return value_per_interval * open_hours_per_week * 3600.0 / interval * weeks


@dataclass(frozen=True)
class CostPoint:
    agents: int
    staff: float            # agent cost for the interval
    abandons: float         # expected hang-ups in the interval
    abandon_cost: float
    total: float
    metrics: Metrics


def cost_at(agents, calls, aht, patience, cost_per_hour, cost_per_abandon,
            target=20.0, interval=1800.0, shrinkage=0.0):
    m = erlang_a(calls, aht, agents, patience, target, interval)
    staff = staff_cost(agents, cost_per_hour, interval, shrinkage)
    abandons = calls * m.abandon
    return CostPoint(agents, staff, abandons, abandons * cost_per_abandon,
                     staff + abandons * cost_per_abandon, m)


def cost_curve(calls, aht, patience, cost_per_hour, cost_per_abandon, target=20.0,
               interval=1800.0, shrinkage=0.0):
    """Total cost at every staffing level from zero up to the point where no extra
    agent can pay for itself: once all remaining hang-up cost is below the cost of
    one agent, every larger staffing level costs more than the best one found."""
    if cost_per_hour <= 0:
        raise ValueError('cost_per_hour must be positive')
    one_agent = staff_cost(1, cost_per_hour, interval, shrinkage)
    points = []
    n = 0
    while True:
        p = cost_at(n, calls, aht, patience, cost_per_hour, cost_per_abandon, target, interval, shrinkage)
        points.append(p)
        if p.abandon_cost < one_agent:
            return points
        n += 1


def cheapest_staffing(calls, aht, patience, cost_per_hour, cost_per_abandon, target=20.0,
                      interval=1800.0, shrinkage=0.0):
    """Staffing level with the lowest agent cost plus hang-up cost (needs Erlang A)."""
    if patience is None:
        raise ValueError('cheapest staffing needs a patience: without hang-ups there is no abandon cost')
    return min(cost_curve(calls, aht, patience, cost_per_hour, cost_per_abandon, target,
                          interval, shrinkage), key=lambda p: p.total)


def cost_of_goal(calls, aht, cost_per_hour, sl, target=20.0, interval=1800.0, shrinkage=0.0,
                 patience=None, **goals):
    """Agents and agent cost per interval for a service-level goal."""
    m = required_agents(calls, aht, sl, target, interval, patience, **goals)
    return m, staff_cost(m.agents, cost_per_hour, interval, shrinkage)


def round_up_fte(value, step=0.5):
    """Round FTE up to the nearest `step`, the way headcount actually gets hired."""
    return math.ceil(value / step - 1e-9) * step
