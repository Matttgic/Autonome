"""Mesure du retard des books sur Polymarket (cas construits à la main)."""
import unittest
from datetime import datetime, timedelta, timezone

from autonome import lag as L

T0 = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def comp(p, odds, book="pmu_fr", age=None):
    return {"book": book, "event_id": "pm|x", "group": "1x2", "selection": "home", "p_fair": p, "odds": odds,
            "commence": "2026-11-02T20:00:00Z", "ref_sport": "FOOTBALL", "book_age_min": age}


class Lag(unittest.TestCase):
    def test_followed_move(self):
        st = {}
        self.assertEqual(L.update(st, [comp(0.50, 1.90)], T0), [])
        self.assertEqual(L.update(st, [comp(0.53, 1.90)], T0 + timedelta(minutes=4)), [])   # référence +3 pts
        self.assertEqual(L.update(st, [comp(0.53, 1.90)], T0 + timedelta(minutes=8)), [])   # book inchangé
        rec = L.update(st, [comp(0.53, 1.80)], T0 + timedelta(minutes=12))                  # book suit (proba ↑)
        self.assertEqual(len(rec), 1)
        self.assertTrue(rec[0]["followed"])
        self.assertEqual(rec[0]["lag_min"], 8.0)
        self.assertEqual((rec[0]["family"], rec[0]["src"]), ("1x2", "direct"))

    def test_not_followed_before_kickoff(self):
        st = {}
        L.update(st, [comp(0.50, 1.90)], T0)
        L.update(st, [comp(0.47, 1.90)], T0 + timedelta(hours=1))
        rec = L.update(st, [], datetime(2026, 11, 2, 20, 1, tzinfo=timezone.utc))
        self.assertEqual(len(rec), 1)
        self.assertFalse(rec[0]["followed"])
        self.assertEqual(rec[0]["waited_min"], 421.0)
        self.assertEqual(st, {})                                                              # nettoyé

    def test_reverted_or_opposite_moves_are_not_lags(self):
        st = {}
        L.update(st, [comp(0.50, 1.90)], T0)
        L.update(st, [comp(0.53, 1.90)], T0 + timedelta(minutes=4))
        L.update(st, [comp(0.505, 1.90)], T0 + timedelta(minutes=8))                         # référence revenue
        self.assertEqual(L.update(st, [comp(0.505, 1.80)], T0 + timedelta(minutes=12)), [])
        L.update(st, [comp(0.53, 1.80)], T0 + timedelta(minutes=16))                          # nouveau mouvement ↑
        self.assertEqual(L.update(st, [comp(0.53, 1.95)], T0 + timedelta(minutes=20)), [])  # book va à l'opposé

    def test_coteur_snapshot_time_and_summary(self):
        st = {}
        L.update(st, [comp(0.50, 1.90, "betsson_fr", age=0)], T0)
        L.update(st, [comp(0.53, 1.90, "betsson_fr", age=0)], T0 + timedelta(minutes=5))
        # instantané pris AVANT le mouvement : aucune info, pas de délai négatif
        self.assertEqual(L.update(st, [comp(0.53, 1.80, "betsson_fr", age=10)], T0 + timedelta(minutes=10)), [])
        recs = [{"at": T0.isoformat(), "book": "pmu_fr", "followed": True, "lag_min": x, "src": "direct"} for x in (4, 8, 30)]
        recs.append({"at": T0.isoformat(), "book": "pmu_fr", "followed": False, "lag_min": None, "src": "direct"})
        s = L.summary(recs, T0)[0]
        self.assertEqual((s["followed"], s["not_followed"], s["median_min"], s["p75_min"]), (3, 1, 8, 30))
        self.assertAlmostEqual(s["within_15"], 0.5)


if __name__ == "__main__":
    unittest.main()
