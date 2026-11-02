"""Garde-fous de sélection : fraîcheur de la cote du book et conformité du groupe (book, famille de marché)."""
import unittest
from datetime import datetime, timezone

from autonome import consensus as CS, live


def c(book, group, ev, age=None):
    return {"book": book, "group": group, "ev": ev, "book_age_min": age}


class Gate(unittest.TestCase):
    def setUp(self):
        # PMU 1X2 bien traduit : médiane −8 % ; « btts » mal traduit : médiane +6 % (aberrante)
        self.measured = ([c("pmu_fr", "1x2", x) for x in (-0.12, -0.10, -0.08, -0.06, 0.05)] +
                         [c("pmu_fr", "btts", x) for x in (0.02, 0.04, 0.06, 0.08, 0.10)] +
                         [c("unibet_fr", "ou@2.5", x) for x in (-0.1, 0.05)])  # trop peu de mesures

    def test_conform_group_kept(self):
        kept, why = live.gate([c("pmu_fr", "1x2", 0.05)], self.measured)
        self.assertEqual(len(kept), 1)
        self.assertEqual(why, {"cote_trop_vieille": 0, "groupe_non_conforme": 0})

    def test_aberrant_or_thin_group_blocked(self):
        kept, why = live.gate([c("pmu_fr", "btts", 0.10), c("unibet_fr", "ou@2.5", 0.05)], self.measured)
        self.assertEqual(kept, [])
        self.assertEqual(why["groupe_non_conforme"], 2)

    def test_old_book_odds_blocked(self):
        kept, why = live.gate([c("pmu_fr", "1x2", 0.05, age=90), c("pmu_fr", "1x2", 0.05, age=10)], self.measured)
        self.assertEqual(len(kept), 1)
        self.assertEqual(why["cote_trop_vieille"], 1)

    def test_consensus_old_snapshot_never_picked(self):
        books = {f"b{i}": {"1x2": {"home": 2.0 + i / 100, "draw": 3.4, "away": 3.8 - i / 100}} for i in range(1, 8)}
        books["b0"] = {"1x2": {"home": 2.5, "draw": 3.4, "away": 3.8}}
        m = {"commence": "2026-11-02T20:00:00Z", "home": "A", "away": "B", "books": books, "renc": "r",
             "sport": "FOOTBALL", "url": "u", "snapshot_age_min": 10}
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        self.assertTrue(CS.evaluate(m, now, 100))
        self.assertEqual(CS.evaluate({**m, "snapshot_age_min": 90}, now, 100), [])
        self.assertTrue(CS.evaluate({**m, "snapshot_age_min": 90}, now, 100, {"diagnostic": True}))


if __name__ == "__main__":
    unittest.main()
