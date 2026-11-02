"""Garde-fous de sélection : fraîcheur de la cote du book et conformité du groupe (book, sport, famille de marché).
Cas tirés des deux revues adverses du 2026-11-02 (données synthétiques)."""
import unittest
from datetime import datetime, timezone

from autonome import consensus as CS, live


def c(book, group, ev, ev_id="e1", odds=2.0, age=None, sport="FOOTBALL", mins=600):
    return {"book": book, "group": group, "ev": ev, "event_id": ev_id, "odds": odds, "book_age_min": age,
            "ref_sport": sport, "minutes_to_start": mins, "home": "A", "away": "B"}


def matches(book, group, evs, sport="FOOTBALL", odds=2.0):
    """Une cote par match (event_id distincts)."""
    return [c(book, group, e, f"m{i}", odds, sport=sport) for i, e in enumerate(evs)]


class Gate(unittest.TestCase):
    def test_conform_group_kept(self):
        measured = matches("pmu_fr", "1x2", (-0.12, -0.10, -0.08, -0.06, 0.05))
        kept, why, detail = live.gate([c("pmu_fr", "1x2", 0.05, "m4")], measured)
        self.assertEqual(len(kept), 1)
        self.assertEqual((why, detail), ({"cote_trop_vieille": 0, "groupe_non_conforme": 0}, []))

    def test_aberrant_group_blocked_and_reported(self):
        measured = matches("pmu_fr", "btts", (0.02, 0.04, 0.06, 0.08, 0.10))  # médiane +6 % : mal traduit
        kept, why, detail = live.gate([c("pmu_fr", "btts", 0.10, "m4")], measured)
        self.assertEqual(kept, [])
        self.assertEqual(detail[0]["raison"], "groupe_non_conforme")
        self.assertAlmostEqual(detail[0]["ev_mediane_groupe"], 0.06)

    def test_single_match_is_not_enough(self):
        # 6 lignes plus/moins d'UN seul match (peut-être mal apparié) : pas une preuve de conformité
        measured = [c("pmu_fr", f"ou@{x}.5", -0.08, "m1") for x in range(6)]
        self.assertEqual(live.gate([c("pmu_fr", "ou@2.5", 0.06, "m1")], measured)[0], [])

    def test_longshots_do_not_poison_median(self):
        # cotes > max_odds (5) à forte marge : hors de la population des candidats, ignorées
        measured = matches("netbet_fr", "team_ou", (-0.10, -0.08, -0.12)) + \
            [c("netbet_fr", "team_ou", -0.40, f"x{i}", odds=9.0) for i in range(8)]
        self.assertEqual(len(live.gate([c("netbet_fr", "team_ou", 0.06, "m0")], measured)[0]), 1)

    def test_groups_split_by_sport(self):
        measured = matches("betclic_fr", "ml", (-0.06, -0.05, -0.07), sport="TENNIS") + \
            matches("betclic_fr", "ml", (0.08, 0.10, 0.12), sport="BASKETBALL")  # basket inversé chez ce book
        cands = [c("betclic_fr", "ml", 0.04, "m0", sport="TENNIS"), c("betclic_fr", "ml", 0.12, "m2", sport="BASKETBALL")]
        kept = live.gate(cands, measured)[0]
        self.assertEqual([k["ref_sport"] for k in kept], ["TENNIS"])

    def test_old_book_odds_blocked_more_strictly_near_kickoff(self):
        measured = matches("pmu_fr", "1x2", (-0.10, -0.08, -0.06))
        far, near = c("pmu_fr", "1x2", 0.05, "m0", age=50, mins=600), c("pmu_fr", "1x2", 0.05, "m1", age=30, mins=60)
        ok = c("pmu_fr", "1x2", 0.05, "m2", age=10, mins=60)
        kept, why, _ = live.gate([far, near, ok], measured)
        self.assertEqual([k["event_id"] for k in kept], ["m0", "m2"])   # 50 min ok à 10 h ; 30 min trop vieux à 1 h
        self.assertEqual(why["cote_trop_vieille"], 1)
        self.assertEqual(live.book_age_limit(600), 60)
        self.assertEqual(live.book_age_limit(60), 15)

    def test_consensus_old_or_unknown_snapshot_never_picked(self):
        books = {f"b{i}": {"1x2": {"home": 2.0 + i / 100, "draw": 3.4, "away": 3.8 - i / 100}} for i in range(1, 8)}
        books["b0"] = {"1x2": {"home": 2.5, "draw": 3.4, "away": 3.8}}
        m = {"commence": "2026-11-02T20:00:00Z", "home": "A", "away": "B", "books": books, "renc": "r",
             "sport": "FOOTBALL", "url": "u", "snapshot_age_min": 10}
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        self.assertTrue(CS.evaluate(m, now, 100))
        self.assertEqual(CS.evaluate({**m, "snapshot_age_min": 90}, now, 100), [])
        no_age = {k: v for k, v in m.items() if k != "snapshot_age_min"}
        self.assertEqual(CS.evaluate(no_age, now, 100), [])
        self.assertTrue(CS.evaluate({**m, "snapshot_age_min": 90}, now, 100, {"diagnostic": True}))


if __name__ == "__main__":
    unittest.main()
