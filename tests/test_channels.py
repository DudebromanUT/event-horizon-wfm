import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from horizon.channels import (best_attempt_slots, chat_requirement, chats_per_agent_minute,
                              compare_concurrency, decay_curve, messaging_agents, messaging_backlog,
                              outbound_plan, reach_probability, sms_batch_limit)
from horizon.erlang import required_agents


class ChatTest(unittest.TestCase):
    def test_more_concurrency_can_be_slower(self):
        self.assertAlmostEqual(chats_per_agent_minute(2, 480), 0.25)
        self.assertAlmostEqual(chats_per_agent_minute(3, 840), 3 / 14)
        two, three = compare_concurrency(60, {2: 480, 3: 840})
        self.assertLess(two.agents, three.agents)

    def test_seats_round_up_to_agents(self):
        chat = chat_requirement(60, 480, 2, sl=0.8, target=60)
        seats = required_agents(60, 480, 0.8, 60)
        self.assertEqual(chat.seats.agents, seats.agents)
        self.assertEqual(chat.agents, math.ceil(seats.agents / 2))
        with self.assertRaises(ValueError):
            chat_requirement(60, 480, 0)


class MessagingTest(unittest.TestCase):
    def test_workload_agents(self):
        # 120 conversations, 3 replies each, 90 seconds of agent time per reply.
        self.assertAlmostEqual(messaging_agents(120, 3, 90), 120 * 3 * 90 / (1800 * 0.85))

    def test_backlog_builds_and_clears(self):
        rows = messaging_backlog([100, 200, 50, 0], [10, 10, 10, 10], touches=3, seconds_per_touch=60,
                                 occupancy=1.0)
        # Capacity is 18,000 agent-seconds per interval; work is 18,000 / 36,000 / 9,000 / 0.
        self.assertEqual([r.backlog for r in rows], [0.0, 18000.0, 9000.0, 0.0])
        self.assertAlmostEqual(rows[1].clear_minutes, 30.0)
        self.assertEqual(rows[3].clear_minutes, 0.0)
        empty = messaging_backlog([10], [0], 1, 60)
        self.assertEqual(empty[0].clear_minutes, math.inf)


class SmsBatchTest(unittest.TestCase):
    def test_send_limit(self):
        curve = [0.5, 0.3, 0.2]
        spare = [5 * 1800, 5 * 1800, 1 * 1800]       # five spare agents, then five, then one
        send, binding = sms_batch_limit(spare, reply_rate=0.04, seconds_per_reply=120, reply_curve=curve)
        self.assertEqual(binding, 2)
        self.assertEqual(send, int(1800 / (0.04 * 0.2 * 120)))
        self.assertEqual(sms_batch_limit([100], 0.0, 120, [1.0]), (None, None))

    def test_decay_curve(self):
        curve = decay_curve(4, half_life=1.0, within=0.8)
        self.assertAlmostEqual(sum(curve), 0.8)
        self.assertAlmostEqual(curve[0] / curve[1], 2.0)


class OutboundTest(unittest.TestCase):
    def test_plan(self):
        plan = outbound_plan(records=10000, attempts_per_record=2, connect_rate=0.2, right_party_rate=0.5,
                             right_party_seconds=300, other_connect_seconds=60, promise_rate=0.3,
                             kept_rate=0.6, average_payment=120, utilization=0.8)
        self.assertAlmostEqual(plan.connects, 4000)
        self.assertAlmostEqual(plan.right_party, 2000)
        seconds = 2000 * 300 + 2000 * 60
        self.assertAlmostEqual(plan.agent_hours, seconds / 3600 / 0.8)
        self.assertAlmostEqual(plan.collected, 2000 * 0.3 * 0.6 * 120)
        self.assertAlmostEqual(plan.collected_per_hour, plan.collected / plan.agent_hours)

    def test_attempt_caps(self):
        self.assertAlmostEqual(reach_probability([0.1] * 7), 1 - 0.9 ** 7)
        slots = {'Tue 10:00': 0.04, 'Tue 18:00': 0.09, 'Sat 10:00': 0.11, 'Wed 13:00': 0.03}
        chosen, reach = best_attempt_slots(slots, 2)
        self.assertEqual(chosen, ['Sat 10:00', 'Tue 18:00'])
        self.assertAlmostEqual(reach, 1 - 0.89 * 0.91)


if __name__ == '__main__':
    unittest.main()
