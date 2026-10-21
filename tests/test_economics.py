import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from horizon.economics import (cheapest_staffing, cost_at, cost_curve, cost_of_goal, fte, per_year,
                               round_up_fte, staff_cost)
from horizon.erlang import required_agents
from horizon.whatif import Queue, containment, move_agents, pooling


class MoneyTest(unittest.TestCase):
    def test_fte_and_cost(self):
        self.assertAlmostEqual(fte(19, 0.35), 29.2308, places=4)
        self.assertAlmostEqual(staff_cost(10, 28), 140.0)
        self.assertAlmostEqual(staff_cost(10, 28, shrinkage=0.3), 200.0)
        self.assertAlmostEqual(per_year(100.0, 60), 100.0 * 120 * 52)
        self.assertEqual(round_up_fte(29.23), 29.5)
        with self.assertRaises(ValueError):
            fte(10, 1.0)

    def test_merchant_counter_line(self):
        # 60 calls/30 min, 4:00, merchants give up after ~1:30, $28/hr, $75 per hang-up.
        best = cheapest_staffing(60, 240, 90, 28, 75)
        self.assertEqual(best.agents, 15)
        self.assertGreater(best.metrics.sl, 0.99)
        self.assertAlmostEqual(best.total, 225, delta=1)
        goal = required_agents(60, 240, patience=90)
        self.assertEqual(goal.agents, 10)
        at_goal = cost_at(goal.agents, 60, 240, 90, 28, 75)
        self.assertAlmostEqual(at_goal.total, 476, delta=2)

    def test_service_lines_have_flat_curves(self):
        best = cheapest_staffing(100, 300, 180, 28, 4)
        self.assertEqual(best.agents, 16)
        at_goal = cost_at(required_agents(100, 300, patience=180).agents, 100, 300, 180, 28, 4)
        self.assertLess(at_goal.total - best.total, 15)
        self.assertEqual(cheapest_staffing(100, 360, 150, 28, 30).agents, 27)

    def test_curve_stops_only_when_nothing_cheaper_remains(self):
        curve = cost_curve(60, 240, 90, 28, 75)
        best = min(curve, key=lambda p: p.total)
        beyond = [cost_at(n, 60, 240, 90, 28, 75).total for n in range(curve[-1].agents + 1, 60)]
        self.assertTrue(all(t > best.total for t in beyond))

    def test_needs_patience_and_positive_cost(self):
        with self.assertRaises(ValueError):
            cheapest_staffing(60, 240, None, 28, 75)
        with self.assertRaises(ValueError):
            cost_curve(60, 240, 90, 0, 75)

    def test_cost_of_goal(self):
        m, cost = cost_of_goal(100, 300, 28, 0.8)
        self.assertEqual(m.agents, 21)
        self.assertAlmostEqual(cost, 21 * 14)


class WhatIfTest(unittest.TestCase):
    def test_pooling(self):
        p = pooling([(100, 300)] * 3)
        self.assertEqual((p.agents_separate, p.pooled.agents, p.saved), (63, 57, 6))
        self.assertEqual(pooling([(120, 330), (80, 330), (40, 330)]).saved, 7)
        small = pooling([(30, 330), (20, 330), (10, 330)])
        self.assertEqual((small.agents_separate, small.pooled.agents), (19, 15))
        mixed = pooling([(100, 240), (100, 360)])
        self.assertAlmostEqual(mixed.pooled.aht, 300)

    def test_containment_and_assist(self):
        self.assertEqual(containment(100, 300, contained=0.2).after.agents, 18)
        harder = containment(100, 300, contained=0.2, aht_change=0.10)
        self.assertEqual((harder.before.agents, harder.after.agents), (21, 19))
        self.assertAlmostEqual(harder.saved_share, 2 / 21)
        assist = containment(100, 300, assist_seconds=30)
        self.assertEqual(assist.after.agents, 19)
        comeback = containment(100, 300, contained=0.2, recontact=0.5)
        self.assertAlmostEqual(comeback.effective_containment, 0.1)
        self.assertAlmostEqual(comeback.calls_after, 90)
        with self.assertRaises(ValueError):
            containment(100, 300, contained=1.5)
        with self.assertRaises(ValueError):
            containment(100, 300, assist_seconds=300)

    def test_move_agents(self):
        cs = Queue('CS', 100, 300, 22, patience=180)
        fraud = Queue('Fraud', 40, 420, 9, patience=120)
        move = move_agents(cs, fraud, 2)
        self.assertLess(move.source_after.sl, move.source_before.sl)
        self.assertGreater(move.dest_after.sl, move.dest_before.sl)
        slower = move_agents(cs, fraud, 2, borrowed_aht=540)
        self.assertLess(slower.dest_after.sl, move.dest_after.sl)
        self.assertAlmostEqual(slower.dest_after.aht, (9 * 420 + 2 * 540) / 11)
        with self.assertRaises(ValueError):
            move_agents(cs, fraud, 23)


if __name__ == '__main__':
    unittest.main()
