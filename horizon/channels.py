"""Channel models beyond inbound voice.

Web chat:        an agent works several chats at once. Each agent counts as
                 `concurrency` seats, using the handle time measured at that
                 concurrency (chats take longer when agents juggle more).
Async messaging: WhatsApp, Instagram, Messenger and 1:1 SMS conversations pause
                 for minutes or hours between replies, so there's no queue in the
                 Erlang sense. It's workload against capacity, with a backlog.
SMS batch:       an outbound send creates a wave of replies; size the send so
                 the wave fits the spare capacity.
Outbound:        hours to work a list, and what those hours bring in.
"""

import math
from dataclasses import dataclass

from .erlang import Metrics, required_agents


# --- Web chat -------------------------------------------------------------

@dataclass(frozen=True)
class Chat:
    agents: int
    concurrency: int
    aht: float
    seats: Metrics      # service metrics for the seats (agents x concurrency)


def chat_requirement(chats, aht, concurrency, sl=0.8, target=60.0, interval=1800.0,
                     patience=None, **goals):
    """Agents for live chat when each one handles up to `concurrency` chats at once."""
    if concurrency < 1 or int(concurrency) != concurrency:
        raise ValueError('concurrency must be a whole number of 1 or more')
    seats = required_agents(chats, aht, sl, target, interval, patience, **goals)
    return Chat(int(math.ceil(seats.agents / concurrency)), int(concurrency), aht, seats)


def chats_per_agent_minute(concurrency, aht):
    """Throughput of one fully busy agent. Higher concurrency only helps if this goes up."""
    return concurrency / (aht / 60.0)


def compare_concurrency(chats, aht_by_concurrency, sl=0.8, target=60.0, interval=1800.0,
                        patience=None, **goals):
    """Agents needed at each concurrency level, given the handle time measured at each.
    `aht_by_concurrency` maps concurrency to handle time, e.g. {1: 360, 2: 480, 3: 840}."""
    return [chat_requirement(chats, aht, c, sl, target, interval, patience, **goals)
            for c, aht in sorted(aht_by_concurrency.items())]


# --- Async messaging ------------------------------------------------------

def messaging_agents(conversations, touches, seconds_per_touch, interval=1800.0, occupancy=0.85):
    """Agents needed to keep up with async conversations arriving in one interval.

    touches:           agent replies per conversation
    seconds_per_touch: agent working time per reply (not elapsed time)
    occupancy:         share of logged-in time agents can spend replying
    """
    if not 0 < occupancy <= 1:
        raise ValueError('occupancy must be above 0 and at most 1')
    return conversations * touches * seconds_per_touch / (interval * occupancy)


@dataclass(frozen=True)
class BacklogInterval:
    arrived: float          # agent-seconds of new work
    capacity: float         # agent-seconds available
    worked: float
    backlog: float          # agent-seconds still waiting at the end of the interval
    clear_minutes: float    # minutes to clear that backlog at this interval's capacity


def messaging_backlog(conversations, agents, touches, seconds_per_touch, interval=1800.0,
                      occupancy=0.85, start_backlog=0.0):
    """Interval-by-interval backlog for async messaging.

    `conversations` and `agents` are lists, one entry per interval. `clear_minutes`
    is a rough reply-time signal: how long the work already waiting would take with
    the agents on hand. Compare it with your reply target (and WhatsApp's 24-hour
    customer service window) to see where work can be moved to another site or hour.
    """
    if len(conversations) != len(agents):
        raise ValueError('conversations and agents need one entry per interval')
    backlog = float(start_backlog)
    out = []
    for arriving, staffed in zip(conversations, agents):
        work = arriving * touches * seconds_per_touch
        capacity = staffed * interval * occupancy
        worked = min(backlog + work, capacity)
        backlog = backlog + work - worked
        rate = staffed * occupancy
        clear = backlog / rate / 60.0 if rate > 0 else (math.inf if backlog > 0 else 0.0)
        out.append(BacklogInterval(work, capacity, worked, backlog, clear))
    return out


# --- SMS batch ------------------------------------------------------------

def decay_curve(intervals, half_life=1.0, within=0.9):
    """A reply curve: the share of all replies landing in each interval after a send.
    Replies fall off by half every `half_life` intervals, and `within` of them land
    inside the window. Replace it with your measured curve once you have one."""
    weights = [0.5 ** (k / half_life) for k in range(intervals)]
    total = sum(weights)
    return [within * w / total for w in weights]


def sms_batch_limit(spare_agent_seconds, reply_rate, seconds_per_reply, reply_curve):
    """Largest send whose replies fit the spare capacity in every interval after it.

    spare_agent_seconds: spare agent-seconds in each interval after the send
    reply_rate:          replies per message sent (0.04 = 4%)
    seconds_per_reply:   agent working time per reply
    reply_curve:         share of replies landing in each of those intervals
    Returns (largest send, index of the interval that limits it).
    """
    if len(spare_agent_seconds) != len(reply_curve):
        raise ValueError('spare capacity and reply curve need the same number of intervals')
    best, binding = math.inf, None
    for k, (spare, share) in enumerate(zip(spare_agent_seconds, reply_curve)):
        load = reply_rate * share * seconds_per_reply
        if load > 0:
            limit = max(0.0, spare) / load
            if limit < best:
                best, binding = limit, k
    return (int(best) if best != math.inf else None), binding


# --- Outbound -------------------------------------------------------------

@dataclass(frozen=True)
class OutboundPlan:
    attempts: float
    connects: float
    right_party: float
    promises: float
    kept: float
    collected: float
    agent_hours: float

    @property
    def right_party_per_hour(self):
        return self.right_party / self.agent_hours if self.agent_hours else 0.0

    @property
    def collected_per_hour(self):
        return self.collected / self.agent_hours if self.agent_hours else 0.0


def outbound_plan(records, attempts_per_record, connect_rate, right_party_rate, right_party_seconds,
                  other_connect_seconds, promise_rate=0.0, kept_rate=0.0, average_payment=0.0,
                  seconds_per_no_answer=0.0, utilization=0.85):
    """Agent hours to work a list and what they bring in.

    connect_rate:          live answers per attempt
    right_party_rate:      right-party contacts per live answer
    right_party_seconds:   talk + wrap for a right-party contact
    other_connect_seconds: talk + wrap for wrong parties, third parties and the like
    seconds_per_no_answer: agent time on attempts that don't connect (0 for predictive,
                           ring time for preview or manual dialing)
    utilization:           share of logged-in time spent on calls (dialer pacing)
    """
    if not 0 < utilization <= 1:
        raise ValueError('utilization must be above 0 and at most 1')
    attempts = records * attempts_per_record
    connects = attempts * connect_rate
    right_party = connects * right_party_rate
    seconds = (right_party * right_party_seconds + (connects - right_party) * other_connect_seconds
               + (attempts - connects) * seconds_per_no_answer)
    promises = right_party * promise_rate
    kept = promises * kept_rate
    return OutboundPlan(attempts, connects, right_party, promises, kept, kept * average_payment,
                        seconds / 3600.0 / utilization)


def reach_probability(rates):
    """Chance of at least one right-party contact from attempts with these per-attempt
    right-party rates (treating attempts as independent)."""
    miss = 1.0
    for p in rates:
        miss *= 1.0 - p
    return 1.0 - miss


def best_attempt_slots(rate_by_slot, attempts):
    """With a cap on attempts, spend them in the slots with the best right-party rates.
    `rate_by_slot` maps a label (e.g. 'Sat 10:00') to its per-attempt right-party rate.
    Returns (chosen labels, chance of reaching the customer)."""
    chosen = sorted(rate_by_slot, key=rate_by_slot.get, reverse=True)[:attempts]
    return chosen, reach_probability(rate_by_slot[s] for s in chosen)
