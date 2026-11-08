"""Régressions issues de la revue adverse indépendante."""
import tempfile
import unittest

from autonome import store, tracker, value as V


class Regress(unittest.TestCase):
    def test_student_conservative(self):  # vrai t(.975): df=11 -> 2.201, df=14 -> 2.145, df=26 -> 2.056
        for df, true in [(11, 2.201), (14, 2.145), (26, 2.056), (100, 1.984)]:
            self.assertGreaterEqual(V._t(df), true - 0.005, df)

    def test_far_observation_excluded_from_clv_stats(self):
        d = tempfile.mkdtemp()
        row = {"bet_id": "b", "event_id": "e", "group": "h2h", "selection": "A", "odds": 2.1, "ev": 0.05, "stake": 1.0,
               "ref_kind": "sharp", "status": "open", "result": None,
               "close": {"book": "pinnacle", "p_fair": 0.55, "minutes_to_start": 300, **V.clv(2.1, 0.55)}}
        store.write_all(d, tracker.BETS, [row])
        s = tracker.stats(d)
        self.assertEqual(s["clv"]["n"], 0)            # 300 min > 90 : pas une clôture
        self.assertIn("0/1", s["clv_coverage"])


if __name__ == "__main__":
    unittest.main()
