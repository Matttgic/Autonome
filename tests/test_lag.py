"""Mesure du retard des books sur Polymarket (cas construits à la main, scénarios de la 10e revue)."""
import unittest
from datetime import datetime, timedelta, timezone

from autonome import lag as L

T0 = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def comp(p, odds, book="pmu_fr", age=None, sel="home"):
    return {"book": book, "event_id": "pm|x", "group": "1x2", "selection": sel, "p_fair": p, "odds": odds,
            "commence": "2026-11-02T20:00:00Z", "ref_sport": "FOOTBALL", "book_age_min": age}


def at(m):
    return T0 + timedelta(minutes=m)


class Lag(unittest.TestCase):
    def run_seq(self, seq):
        st, out = {}, []
        for m, p, o in seq:
            out += L.update(st, [comp(p, o)], at(m))
        return st, out

    def test_followed_with_bounds(self):
        _, out = self.run_seq([(0, .50, 1.90), (4, .53, 1.90), (8, .53, 1.90), (12, .53, 1.80)])
        self.assertEqual([r["outcome"] for r in out], ["followed"])
        self.assertEqual((out[0]["lag_min"], out[0]["lag_min_lo"]), (8.0, 4.0))

    def test_same_pass_follow_is_counted(self):
        _, out = self.run_seq([(0, .50, 1.90), (3, .55, 1.75)])
        self.assertEqual(out[0]["outcome"], "followed")
        self.assertTrue(out[0]["same_pass"])
        self.assertEqual((out[0]["lag_min_lo"], out[0]["lag_min"]), (0.0, 3.0))

    def test_gap_is_never_a_delay(self):
        _, out = self.run_seq([(0, .50, 1.90), (4, .53, 1.90), (300, .53, 1.80)])
        self.assertEqual([r["outcome"] for r in out], ["unobserved"])

    def test_reversal_restarts_and_opposite(self):
        _, out = self.run_seq([(0, .50, 1.90), (4, .53, 1.90), (8, .47, 1.90), (12, .47, 2.00)])
        self.assertEqual([r["outcome"] for r in out], ["followed"])           # suit la référence retournée (↓)
        _, out = self.run_seq([(0, .50, 1.90), (4, .53, 1.90), (8, .53, 2.00)])
        self.assertEqual([r["outcome"] for r in out], ["opposite"])

    def test_reverted_and_tiny_changes(self):
        _, out = self.run_seq([(0, .50, 1.90), (4, .53, 1.90), (8, .505, 1.90)])
        self.assertEqual([r["outcome"] for r in out], ["reverted"])
        _, out = self.run_seq([(0, .50, 1.90), (4, .53, 1.90), (8, .53, 1.89)])  # 0,3 point : pas un changement
        self.assertEqual(out, [])

    def test_kickoff(self):
        st = {}
        L.update(st, [comp(.50, 1.90)], datetime(2026, 11, 2, 19, 0, tzinfo=timezone.utc))
        L.update(st, [comp(.47, 1.90)], datetime(2026, 11, 2, 19, 20, tzinfo=timezone.utc))
        L.update(st, [comp(.47, 1.90)], datetime(2026, 11, 2, 19, 39, tzinfo=timezone.utc))
        out = L.update(st, [], datetime(2026, 11, 2, 20, 1, tzinfo=timezone.utc))
        self.assertEqual((out[0]["outcome"], out[0]["waited_min"]), ("not_followed", 19.0))
        self.assertEqual(st, {})
        st = {}
        L.update(st, [comp(.50, 1.90)], at(0))
        L.update(st, [comp(.47, 1.90)], at(4))
        out = L.update(st, [], datetime(2026, 11, 2, 20, 1, tzinfo=timezone.utc))      # plus vu depuis 12:04
        self.assertEqual(out[0]["outcome"], "unobserved")

    def test_coteur_and_other_outcomes_ignored(self):
        st = {}
        self.assertEqual(L.update(st, [comp(.5, 1.9, age=10), comp(.3, 3.4, sel="draw")], T0), [])
        self.assertEqual(st, {})

    def test_summary(self):
        recs = [{"at": T0.isoformat(), "book": "pmu_fr", "src": "direct", "outcome": "followed", "lag_min": x}
                for x in (4, 8, 30)]
        recs += [{"at": T0.isoformat(), "book": "pmu_fr", "src": "direct", "outcome": o}
                 for o in ("not_followed", "reverted", "unobserved")]
        s = L.summary(recs, T0)[0]
        self.assertEqual((s["followed"], s["not_followed"], s["reverted"], s["median_min"], s["p75_min"]), (3, 1, 1, 8, 30))
        self.assertAlmostEqual(s["within_15"], 0.5)                              # 2 rapides sur 4 tranchés


if __name__ == "__main__":
    unittest.main()
