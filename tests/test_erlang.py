import math
import os
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from horizon.erlang import (erlang_a, erlang_c, metrics, required_agents, simulate,
                            staffing_table, workload)


def erlang_c_exact(calls, aht, n, interval=1800):
    """Textbook Erlang C with exact fractions, as an independent check."""
    a = Fraction(calls) * Fraction(aht) / Fraction(interval)
    term, total = Fraction(1), Fraction(0)
    for k in range(n):
        total += term
        term = term * a / (k + 1)
    top = term * n / (n - a)
    return float(top / (total + top))


def erlang_a_reference(calls, aht, n, patience, target, interval=1800, extra=400):
    """Erlang A service level by brute force: a truncated birth-death chain for the
    queue, then uniformization of each waiting caller's progress to the front."""
    lam, mu, theta = calls / interval, 1.0 / aht, 1.0 / patience
    k_max = n + extra
    w = [1.0]
    for k in range(1, k_max + 1):
        w.append(w[-1] * lam / (mu * min(k, n) + theta * max(k - n, 0)))
    z = sum(w)
    pi = [x / z for x in w]
    waiting_max = k_max - n
    rate = n * mu + (waiting_max + 1) * theta
    v = [pi[n + j] for j in range(waiting_max + 1)]
    served, total = 0.0, 0.0
    pois = math.exp(-rate * target)
    for step in range(int(rate * target + 12 * math.sqrt(rate * target) + 40)):
        total += pois * served
        nxt = [0.0] * len(v)
        for j, mass in enumerate(v):
            forward = n * mu + j * theta
            nxt[j] += mass * (1 - (forward + theta) / rate)
            if j == 0:
                served += mass * forward / rate
            else:
                nxt[j - 1] += mass * forward / rate
        v = nxt
        pois *= rate * target / (step + 1)
    queue = sum(j * pi[n + j] for j in range(waiting_max + 1))
    return {'sl': sum(pi[:n]) + total, 'abandon': theta * queue / lam}


class ErlangCTest(unittest.TestCase):
    def test_hand_checked_staffing(self):
        # 100 calls per half hour at 5:00, 80/20: the walkthrough example.
        self.assertEqual(required_agents(100, 300).agents, 21)
        self.assertEqual(required_agents(80, 300).agents, 18)
        self.assertEqual(required_agents(80, 330).agents, 19)
        m = erlang_c(100, 300, 21)
        self.assertAlmostEqual(m.sl, 0.8263, places=4)
        self.assertAlmostEqual(m.asa, 16.05, places=2)
        self.assertAlmostEqual(m.occupancy, 0.7937, places=4)
        self.assertLess(erlang_c(80, 300, 17).sl, 0.80)

    def test_matches_exact_fractions(self):
        for calls, aht, n in [(100, 300, 18), (100, 300, 25), (37, 412, 11), (900, 280, 150), (4, 600, 2)]:
            self.assertAlmostEqual(erlang_c(calls, aht, n).p_wait, erlang_c_exact(calls, aht, n), places=12)

    def test_large_queue_is_stable(self):
        m = required_agents(6000, 300)          # 1,000 Erlangs
        self.assertTrue(1000 < m.agents < 1060)
        self.assertTrue(0.8 <= m.sl < 0.9)
        self.assertFalse(math.isnan(m.asa))

    def test_overloaded_and_empty(self):
        m = erlang_c(100, 300, 16)              # 16 agents for 16.7 Erlangs
        self.assertEqual(m.sl, 0.0)
        self.assertEqual(m.asa, math.inf)
        idle = erlang_c(0, 300, 5)
        self.assertEqual((idle.sl, idle.asa, idle.occupancy), (1.0, 0.0, 0.0))
        self.assertEqual(required_agents(0, 300).agents, 0)

    def test_goals_beyond_service_level(self):
        m = required_agents(100, 300, sl=0.8, max_asa=10)
        self.assertLessEqual(m.asa, 10)
        self.assertEqual(m.agents, 22)
        capped = required_agents(600, 300, sl=0.5, max_occupancy=0.85)
        self.assertLessEqual(capped.occupancy, 0.85)
        self.assertGreaterEqual(capped.agents, math.ceil(workload(600, 300) / 0.85))

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            erlang_c(100, 0, 10)
        with self.assertRaises(ValueError):
            erlang_c(100, 300, 2.5)
        with self.assertRaises(ValueError):
            erlang_a(100, 300, 10, 0)


class ErlangATest(unittest.TestCase):
    def test_matches_brute_force(self):
        for calls, aht, n, patience, target in [(100, 300, 19, 120, 20), (60, 240, 9, 90, 20),
                                                (100, 300, 15, 120, 30), (30, 500, 6, 300, 60),
                                                (200, 300, 30, 45, 10)]:
            m = erlang_a(calls, aht, n, patience, target)
            ref = erlang_a_reference(calls, aht, n, patience, target)
            self.assertAlmostEqual(m.sl, ref['sl'], places=9, msg=(calls, aht, n, patience))
            self.assertAlmostEqual(m.abandon, ref['abandon'], places=9, msg=(calls, aht, n, patience))

    def test_matches_simulation(self):
        # Overloaded queues have long busy periods, so they need more simulated calls.
        # Tolerances are about twice the worst miss seen across six seeds.
        for calls, aht, n, patience, n_calls in [(100, 300, 19, 120, 150_000), (60, 240, 9, 90, 150_000),
                                                 (400, 420, 90, 180, 600_000)]:
            m = erlang_a(calls, aht, n, patience)
            sim = simulate(calls, aht, n, patience, n_calls=n_calls, seed=11)
            self.assertAlmostEqual(m.sl, sim['sl'], delta=0.015)
            self.assertAlmostEqual(m.abandon, sim['abandon'], delta=0.006)
            self.assertAlmostEqual(m.asa, sim['asa'], delta=max(0.6, 0.12 * m.asa))
            self.assertAlmostEqual(m.occupancy, sim['occupancy'], delta=0.008)

    def test_becomes_erlang_c_when_nobody_hangs_up(self):
        a, c = erlang_a(100, 300, 21, 1e7), erlang_c(100, 300, 21)
        self.assertAlmostEqual(a.sl, c.sl, places=4)
        self.assertAlmostEqual(a.asa, c.asa, places=2)
        self.assertLess(a.abandon, 1e-4)

    def test_carried_load_balances(self):
        m = erlang_a(100, 300, 18, 120)
        self.assertAlmostEqual(m.occupancy * m.agents, m.load * (1 - m.abandon), places=9)

    def test_more_agents_always_help(self):
        rows = staffing_table(100, 300, 19, spread=4, patience=120)
        self.assertEqual([r.agents for r in rows], list(range(15, 24)))
        for lower, higher in zip(rows, rows[1:]):
            self.assertGreater(higher.sl, lower.sl)
            self.assertLess(higher.abandon, lower.abandon)

    def test_hang_ups_cut_the_requirement(self):
        # Erlang C says 21; with callers who give up after 2 minutes, 19 hits 80/20.
        self.assertEqual(required_agents(100, 300, patience=120).agents, 19)
        self.assertEqual(required_agents(100, 300, patience=300).agents, 20)
        m = required_agents(100, 300, patience=120, max_abandon=0.03)
        self.assertEqual(m.agents, 21)

    def test_edges(self):
        nobody = erlang_a(50, 300, 0, 120)
        self.assertEqual((nobody.sl, nobody.abandon), (0.0, 1.0))
        instant = erlang_a(100, 300, 20, 120, target=0)
        self.assertAlmostEqual(instant.sl, 1 - instant.p_wait, places=12)
        overloaded = erlang_a(100, 300, 10, 120)    # stable even with fewer agents than workload
        self.assertGreater(overloaded.abandon, 0.3)
        self.assertLess(overloaded.occupancy, 1.0 + 1e-12)
        self.assertEqual(metrics(100, 300, 21).model, 'C')
        self.assertEqual(metrics(100, 300, 21, patience=60).model, 'A')

    def test_service_level_alone_can_be_met_by_hang_ups(self):
        # 1,000 Erlangs: 80/20 is "met" with fewer agents than workload because callers
        # give up. That's why the app pairs service level with abandon and occupancy caps.
        big = required_agents(6000, 300, patience=180)
        self.assertEqual(big.agents, 936)
        self.assertGreater(big.abandon, 0.06)
        self.assertGreater(big.occupancy, 0.99)
        self.assertEqual(required_agents(6000, 300, patience=180, max_abandon=0.02).agents, 990)
        capped = required_agents(6000, 300, patience=180, max_occupancy=0.9)
        self.assertLessEqual(capped.occupancy, 0.9)


class SimulationTest(unittest.TestCase):
    def test_erlang_c_simulation_agrees(self):
        sim = simulate(100, 300, 21, n_calls=150_000, seed=3)
        self.assertAlmostEqual(sim['sl'], erlang_c(100, 300, 21).sl, delta=0.015)

    def test_lognormal_handle_times_run(self):
        sim = simulate(100, 300, 21, patience=120, n_calls=40_000, aht_cv=0.6, seed=5)
        self.assertTrue(0.0 < sim['sl'] <= 1.0)


if __name__ == '__main__':
    unittest.main()
