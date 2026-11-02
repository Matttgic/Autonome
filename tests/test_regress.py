"""Régressions issues de la revue adverse indépendante."""
import tempfile
import unittest
from datetime import timedelta

from autonome import engine, store, tracker, value as V
from tests.test_core import NOW, iso, mk_event


class Regress(unittest.TestCase):
    def test_student_conservative(self):  # vrai t(.975): df=11 -> 2.201, df=14 -> 2.145, df=26 -> 2.056
        for df, true in [(11, 2.201), (14, 2.145), (26, 2.056), (100, 1.984)]:
            self.assertGreaterEqual(V._t(df), true - 0.005, df)

    def test_ref_without_timestamp_or_negative_margin(self):
        e = mk_event(); e["books"]["pinnacle"]["last_update"] = None
        self.assertEqual(engine.find_value(e, {}, NOW), [])
        self.assertEqual(engine.find_value(mk_event(pin=(2.10, 2.10)), {}, NOW), [])  # marge -4,8 %

    def test_quarter_and_integer_lines_dropped(self):
        b = {"totals": {"2.25": {"Over": 1.9, "Under": 1.9}, "2.0": {"Over": 1.9, "Under": 1.9},
                        "2.5": {"Over": 1.9, "Under": 1.9}}}
        self.assertEqual(list(engine.groups(b)), ["totals@2.5"])

    def test_daily_limit_across_runs(self):
        a = engine.find_value(mk_event(), {}, NOW)[0]
        self.assertEqual(engine.select_daily([a], {"max_bets_per_day": 5}, set(), done_today=5), [])

    def test_stale_closing_not_a_close(self):
        d = tempfile.mkdtemp()
        tracker.record_bets(d, [engine.find_value(mk_event(), {}, NOW)[0]])
        self.assertEqual(tracker.update_closing(d, mk_event(ref_age_min=300, pin=(1.8, 2.15)), {}, NOW), 0)
        self.assertIsNone(store.read(d, tracker.BETS)[0]["close"])

    def test_far_observation_excluded_from_clv_stats(self):
        d = tempfile.mkdtemp()
        tracker.record_bets(d, [engine.find_value(mk_event(), {}, NOW)[0]])  # match dans 5 h
        tracker.update_closing(d, mk_event(pin=(1.8, 2.15)), {}, NOW)
        s = tracker.stats(d)
        self.assertEqual(s["clv"]["n"], 0)            # 300 min > 90 : pas une clôture
        self.assertIn("0/1", s["clv_coverage"])

    def test_none_team_names_do_not_crash_report(self):
        from autonome import report
        b = engine.find_value(mk_event(), {}, NOW)[0]; b["home"] = None
        d = tempfile.mkdtemp(); tracker.record_bets(d, [b])
        self.assertIn("?", report.render(d, [b]))


if __name__ == "__main__":
    unittest.main()
