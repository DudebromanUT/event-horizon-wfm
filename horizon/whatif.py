"""What-ifs: pooling queues, AI containment and agent assist, moving agents between queues."""

from dataclasses import dataclass
from typing import List, Optional

from .erlang import Metrics, metrics, required_agents


@dataclass(frozen=True)
class Pooling:
    separate: List[Metrics]
    pooled: Metrics

    @property
    def agents_separate(self):
        return sum(m.agents for m in self.separate)

    @property
    def saved(self):
        return self.agents_separate - self.pooled.agents


def pooling(queues, sl=0.8, target=20.0, interval=1800.0, patience=None, **goals):
    """Agents for each queue on its own versus one queue answered by everyone.

    `queues` is a list of (calls, aht). The pooled queue uses the call-weighted
    average handle time, so it assumes cross-trained agents handle each call as
    fast as the specialists did; add a handle-time penalty to test that.
    """
    queues = [(c, h) for c, h in queues if c > 0]
    if not queues:
        raise ValueError('pooling needs at least one queue with calls')
    separate = [required_agents(c, h, sl, target, interval, patience, **goals) for c, h in queues]
    total = sum(c for c, _ in queues)
    aht = sum(c * h for c, h in queues) / total
    pooled = required_agents(total, aht, sl, target, interval, patience, **goals)
    return Pooling(separate, pooled)


@dataclass(frozen=True)
class Containment:
    before: Metrics
    after: Metrics
    effective_containment: float    # share of offered calls that never reach an agent
    calls_after: float
    aht_after: float

    @property
    def saved(self):
        return self.before.agents - self.after.agents

    @property
    def saved_share(self):
        return self.saved / self.before.agents if self.before.agents else 0.0


def containment(calls, aht, contained=0.0, aht_change=0.0, assist_seconds=0.0, recontact=0.0,
                sl=0.8, target=20.0, interval=1800.0, patience=None, **goals):
    """Agents before and after a bot and/or agent assist.

    contained:      share of offered contacts the bot resolves (0.20 = 20%)
    recontact:      share of those that reach an agent anyway within your window
    aht_change:     relative change in handle time of the contacts left (0.10 = 10% longer)
    assist_seconds: seconds agent assist takes off every contact that's left
    """
    for name, value in (('contained', contained), ('recontact', recontact)):
        if not 0.0 <= value <= 1.0:
            raise ValueError('%s must be between 0 and 1' % name)
    effective = contained * (1.0 - recontact)
    calls_after = calls * (1.0 - effective)
    aht_after = aht * (1.0 + aht_change) - assist_seconds
    if aht_after <= 0:
        raise ValueError('handle time after changes must stay positive')
    before = required_agents(calls, aht, sl, target, interval, patience, **goals)
    after = required_agents(calls_after, aht_after, sl, target, interval, patience, **goals)
    return Containment(before, after, effective, calls_after, aht_after)


@dataclass(frozen=True)
class Queue:
    name: str
    calls: float
    aht: float
    agents: int
    target: float = 20.0
    interval: float = 1800.0
    patience: Optional[float] = None

    def metrics(self, agents=None):
        return metrics(self.calls, self.aht, self.agents if agents is None else agents,
                       self.target, self.interval, self.patience)


@dataclass(frozen=True)
class Move:
    source_before: Metrics
    source_after: Metrics
    dest_before: Metrics
    dest_after: Metrics


def move_agents(source, dest, n, borrowed_aht=None):
    """Move `n` agents from `source` to `dest`.

    `borrowed_aht` is the handle time of the borrowed agents on the destination
    queue, if they're slower there. The destination then runs at the agent-weighted
    average handle time, a simple approximation that's good enough for a what-if.
    """
    if not 0 <= n <= source.agents:
        raise ValueError('can only move between 0 and %d agents' % source.agents)
    after = dest
    if borrowed_aht is not None and n:
        blended = (dest.agents * dest.aht + n * borrowed_aht) / (dest.agents + n)
        after = Queue(dest.name, dest.calls, blended, dest.agents, dest.target, dest.interval,
                      dest.patience)
    return Move(source.metrics(), source.metrics(source.agents - n),
                dest.metrics(), after.metrics(dest.agents + n))
