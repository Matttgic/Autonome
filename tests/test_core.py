import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from autonome import devig, engine, oddsapi, store, tracker, value as V

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


class Engine(unittest.TestCase):
    def test_detects_value_hand(self):
        # Pinnacle 1.90/2.00 : q=.526316/.5 ; S=1.026316 ; p_mult(A)=.512821 ; EV mult = .512821*2.10-1 = +7.69 %
        out = engine.find_value(mk_event(), {}, NOW)
        self.assertEqual(len(out), 1)
        b = out[0]
        self.assertEqual((b["selection"], b["book"], b["ref_kind"]), ("A", "winamax_fr", "sharp"))
        self.assertLessEqual(b["ev"], 0.076924)       # conservateur: <= EV multiplicatif
        self.assertGreater(b["ev"], 0.05)
        self.assertAlmostEqual(b["ref_overround"], 0.02632, places=4)
        self.assertEqual(b["stake"], 1.5)             # kelly 0.25*~.08/1.1*100 -> arrondi 0.5

    def test_no_value_when_odds_fair(self):
        self.assertEqual(engine.find_value(mk_event(fr_home=1.85), {}, NOW), [])

    def test_stale_reference_ignored(self):
        self.assertEqual(engine.find_value(mk_event(ref_age_min=500), {}, NOW), [])

    def test_time_window(self):
        self.assertEqual(engine.find_value(mk_event(start_in_h=0.1), {}, NOW), [])
        self.assertEqual(engine.find_value(mk_event(start_in_h=200), {}, NOW), [])

    def test_high_ref_margin_rejected(self):
        self.assertEqual(engine.find_value(mk_event(pin=(1.60, 1.60)), {}, NOW), [])

    def test_odds_bounds(self):
        self.assertEqual(engine.find_value(mk_event(fr_home=2.10), {"max_odds": 2.0}, NOW), [])

    def test_consensus_needs_enough_books(self):
        ev = mk_event()
        del ev["books"]["pinnacle"]
        self.assertEqual(engine.find_value(ev, {}, NOW), [])  # 1 seul book non FR -> pas de référence

    def test_select_daily_dedup_and_limit(self):
        a = engine.find_value(mk_event(), {}, NOW)[0]
        b = {**a, "bet_id": "x", "book": "betclic_fr", "ev": a["ev"] + 0.01}
        picks = engine.select_daily([a, b], {}, set())
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["book"], "betclic_fr")
        self.assertEqual(engine.select_daily([a], {}, {a["bet_id"]}), [])


class Tracker(unittest.TestCase):
    def test_closing_and_settle(self):
        d = tempfile.mkdtemp()
        bet = engine.find_value(mk_event(), {}, NOW)[0]
        tracker.record_bets(d, [bet])
        tracker.record_bets(d, [bet])  # idempotent
        self.assertEqual(len(store.read(d, tracker.BETS)), 1)
        later = mk_event(pin=(1.80, 2.15))  # la ligne sharp a baissé pour A -> CLV positive
        self.assertEqual(tracker.update_closing(d, later, {}, NOW), 1)
        r = store.read(d, tracker.BETS)[0]
        # q = .555556/.465116 ; S=1.020672 ; p_mult=.544 ; shin proche ; clv = 2.10*p - 1 > 0.1
        self.assertGreater(r["close"]["clv_odds"], 0.10)
        tracker.settle(d, "e1", {"home_score": 2.0, "away_score": 1.0, "total": 3.0})
        s = tracker.stats(d)
        self.assertEqual(s["bets_settled"], 1)
        self.assertAlmostEqual(s["roi"]["roi"], 1.1)  # gagné à 2.10

    def test_totals_settlement(self):
        d = tempfile.mkdtemp()
        base = {"event_id": "e", "sport": "s", "commence": "x", "home": "A", "away": "B", "stake": 1, "odds": 2.0,
                "ev": 0.1, "bet_id": "1", "book": "k"}
        tracker.record_bets(d, [{**base, "group": "totals@2.5", "selection": "Over"},
                                {**base, "bet_id": "2", "group": "totals@3", "selection": "Over"}])
        tracker.settle(d, "e", {"home_score": 2, "away_score": 1, "total": 3.0})
        rows = {r["bet_id"]: r["result"]["won"] for r in store.read(d, tracker.BETS)}
        self.assertEqual(rows, {"1": True, "2": None})  # 3 > 2.5 gagné ; 3 == 3 remboursé


class Api(unittest.TestCase):
    def test_normalize_shape(self):  # fixture au format documenté de The Odds API (valeurs fictives de test)
        raw = {"id": "z", "sport_key": "s", "commence_time": "2026-11-03T18:00:00Z", "home_team": "H", "away_team": "A",
               "bookmakers": [{"key": "pinnacle", "title": "Pinnacle", "last_update": "2026-11-02T11:00:00Z",
                               "markets": [{"key": "h2h", "outcomes": [{"name": "H", "price": 2.0}, {"name": "A", "price": 1.9}]},
                                           {"key": "totals", "outcomes": [{"name": "Over", "price": 1.9, "point": 2.5},
                                                                          {"name": "Under", "price": 2.0, "point": 2.5}]}]}]}
        e = oddsapi.normalize(raw)
        self.assertEqual(e["books"]["pinnacle"]["h2h"], {"H": 2.0, "A": 1.9})
        self.assertEqual(set(engine.groups(e["books"]["pinnacle"])), {"h2h", "totals@2.5"})

    def test_result_of(self):
        ev = {"completed": True, "home_team": "H", "away_team": "A", "scores": [{"name": "H", "score": "1"}, {"name": "A", "score": "0"}]}
        self.assertEqual(oddsapi.result_of(ev)["total"], 1.0)
        self.assertIsNone(oddsapi.result_of({"completed": False}))


if __name__ == "__main__":
    unittest.main()
