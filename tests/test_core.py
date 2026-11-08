import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from autonome import devig, engine, store, tracker, value as V

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


class Devig(unittest.TestCase):
    def test_overround_hand(self):  # 2/1.91 - 1 = 0.0471204
        self.assertAlmostEqual(devig.overround([1.91, 1.91]), 0.0471204, places=6)

    def test_multiplicative_hand(self):  # 1/2, 1/3.5, 1/4 ; S = 1.0357143
        p = devig.multiplicative([2.0, 3.5, 4.0])
        for got, want in zip(p, [0.4827586, 0.2758621, 0.2413793]):
            self.assertAlmostEqual(got, want, places=6)

    def test_symmetric_all_methods(self):
        for m in devig.METHODS.values():
            self.assertAlmostEqual(m([1.91, 1.91])[0], 0.5, places=9)

    def test_sum_to_one_and_longshot(self):
        odds = [1.30, 4.5, 9.0]
        mult = devig.multiplicative(odds)
        for name, fn in devig.METHODS.items():
            p = fn(odds)
            self.assertAlmostEqual(sum(p), 1.0, places=9, msg=name)
            if name != "multiplicative":  # biais favori/outsider : l'outsider pèse moins
                self.assertLess(p[2], mult[2], name)

    def test_no_margin_unchanged(self):
        self.assertEqual(devig.shin([2.0, 2.0]), [0.5, 0.5])

    def test_invalid(self):
        with self.assertRaises(ValueError):
            devig.implied([1.0, 2.0])


class Value(unittest.TestCase):
    def test_ev(self):
        self.assertAlmostEqual(V.ev(0.55, 2.0), 0.10)

    def test_kelly_and_stake_cap(self):
        self.assertAlmostEqual(V.kelly_fraction(0.55, 2.0), 0.10)
        self.assertEqual(V.stake(0.55, 2.0, 100.0), 2.0)  # 0.25*10 = 2.5 € plafonné à 2 %
        self.assertAlmostEqual(V.kelly_fraction(0.40, 2.0), 0.0)  # EV négative -> 0
        self.assertEqual(V.stake(0.40, 2.0, 100.0), 0.0)

    def test_clv_hand(self):  # pris 2.10, clôture juste p=0.5 (cote 2.00) -> +5 %
        c = V.clv(2.10, 0.5)
        self.assertAlmostEqual(c["clv_odds"], 0.05)
        self.assertAlmostEqual(c["ev_vs_close"], 0.05)

    def test_roi(self):
        r = V.roi([{"stake": 1, "odds": 2.0, "won": True}, {"stake": 1, "odds": 2.0, "won": False},
                   {"stake": 5, "odds": 3.0, "won": None}])
        self.assertEqual(r["n"], 2)
        self.assertAlmostEqual(r["roi"], 0.0)

    def test_mean_ci(self):
        r = V.mean_ci([0.1, 0.1, 0.1, 0.1])
        self.assertAlmostEqual(r["mean"], 0.1)
        self.assertEqual(V.mean_ci([1.0])["ci95"], None)
        self.assertEqual(V.mean_ci([])["mean"], None)


def mk_event(ref_age_min=10, start_in_h=5, fr_home=2.10, pin=(1.90, 2.00)):
    return {"id": "e1", "sport": "tennis_x", "commence": iso(NOW + timedelta(hours=start_in_h)),
            "home": "A", "away": "B", "books": {
                "pinnacle": {"last_update": iso(NOW - timedelta(minutes=ref_age_min)),
                             "h2h": {"A": pin[0], "B": pin[1]}},
                "winamax_fr": {"last_update": iso(NOW - timedelta(minutes=5)), "h2h": {"A": fr_home, "B": 1.80}},
                "othercom": {"last_update": iso(NOW), "h2h": {"A": 3.0, "B": 1.2}}}}


def cand(**kw):
    return {"bet_id": "a", "event_id": "e1", "group": "h2h", "ref_kind": "sharp", "ev": 0.07, "book": "winamax_fr", **kw}


class Engine(unittest.TestCase):
    def test_select_daily_dedup_and_limit(self):
        a = cand()
        b = cand(bet_id="x", book="betclic_fr", ev=0.08)
        picks = engine.select_daily([a, b], {}, set())
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["book"], "betclic_fr")
        self.assertEqual(engine.select_daily([a], {}, {a["bet_id"]}), [])
        self.assertEqual(engine.select_daily([a], {"max_bets_per_day": 5}, set(), done_today=5), [])  # limite entre runs


class Tracker(unittest.TestCase):
    def test_record_bets_idempotent(self):
        d = tempfile.mkdtemp()
        bet = {**cand(), "stake": 1.5, "odds": 2.1}
        tracker.record_bets(d, [bet])
        tracker.record_bets(d, [bet])
        rows = store.read(d, tracker.BETS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "open")


if __name__ == "__main__":
    unittest.main()
