"""Boosts : gabarits, modèle de score, seuils. Données synthétiques (aucune vraie cote)."""
import unittest
from datetime import datetime, timezone

from autonome import boosts, scoremodel as SM
from autonome.sources import coteur

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def leg(p):
    return {"p": p, "lo": p, "hi": p, "legs": [], "spread": 0.0}


def game(key, home, away, lh, la, start="2026-11-02T19:45:00Z"):
    g = SM.grid(lh, la, 0.0)
    pr = lambda f: SM.prob(g, f)  # noqa: E731
    m = {"1x2": {"home": leg(pr(lambda i, j: i > j)), "draw": leg(pr(lambda i, j: i == j)),
                 "away": leg(pr(lambda i, j: i < j))},
         "ou@2.5": {"over": leg(pr(lambda i, j: i + j > 2.5)), "under": leg(pr(lambda i, j: i + j < 2.5))},
         "ou@1.5": {"over": leg(pr(lambda i, j: i + j > 1.5)), "under": leg(pr(lambda i, j: i + j < 1.5))},
         "btts": {"yes": leg(pr(lambda i, j: i > 0 and j > 0)), "no": leg(pr(lambda i, j: i == 0 or j == 0))}}
    return {"key": key, "home": home, "away": away, "commence": start, "markets": m}


GAMES = [game("g1", "FC Lorient", "Stade Brestois 29", 1.5, 1.0), game("g2", "Newcastle United FC", "Everton FC", 1.8, 0.9),
         game("g3", "Paris Saint-Germain FC", "ES Troyes AC", 2.8, 0.5, "2026-11-07T19:45:00Z"),
         game("g4", "Villarreal CF", "Paris Saint-Germain FC", 1.0, 1.9, "2026-11-03T20:00:00Z")]


class Model(unittest.TestCase):
    def test_fit_recovers_parameters(self):
        f = SM.fit(GAMES[0]["markets"])
        self.assertLess(f["max_err"], 0.005)
        self.assertAlmostEqual(f["lh"], 1.5, delta=0.1)
        self.assertAlmostEqual(f["la"], 1.0, delta=0.1)

    def test_hand_probability(self):
        # Poisson indépendants λ=1 et 1 : P(0-0) = e^-2 = 0.135335
        self.assertAlmostEqual(SM.grid(1.0, 1.0, 0.0)[0][0], 0.135335, places=5)


class Templates(unittest.TestCase):
    def ev(self, event, text, odds=3.0):
        return boosts.evaluate({"id": "b", "book": "winamax", "event": event, "text": text, "odds": odds,
                                "max_stake": 20}, GAMES, {})

    def test_single_win_over(self):
        r = self.ev("Lorient - Brest", "Lorient gagne et plus de 2,5 buts dans le match")
        g = SM.grid(1.5, 1.0, 0.0)
        self.assertAlmostEqual(r["p_fair"], SM.prob(g, lambda i, j: i > j and i + j > 2.5), delta=0.01)
        self.assertEqual(r["legs"][0]["side"], "home")

    def test_away_win_to_nil(self):
        r = self.ev("Lorient - Brest", "Brest gagne sans encaisser de but")
        self.assertEqual(r["legs"][0]["side"], "away")
        self.assertEqual(r["legs"][0]["pred"], "win_nil")

    def test_multi_next_match_and_product(self):
        r = self.ev("Football", "Le Paris SG et Newcastle gagnent chacun leur match")
        self.assertEqual([x["game"] for x in r["legs"]], ["g4", "g2"])  # prochain match du PSG = Villarreal
        self.assertAlmostEqual(r["p_fair"], r["legs"][0]["p"] * r["legs"][1]["p"])

    def test_unknown_never_guessed(self):
        for ev, t in [("Lorient - Brest", "K. Mbappé buteur"), ("Lyon - Nice", "Lyon gagne"),
                      ("Lorient - Brest", "Marseille gagne")]:
            self.assertFalse(self.ev(ev, t)["evaluable"], t)

    def test_to_bet_thresholds_and_max_stake(self):
        r = self.ev("Newcastle - Everton", "Newcastle gagne", odds=3.0)   # p≈0.58 -> EV ≈ +74 %
        b = boosts.to_bet(r, NOW, bankroll=10000)
        self.assertEqual(b["stake"], 20)                                   # plafonné par la mise max du boost
        r2 = self.ev("Newcastle - Everton", "Newcastle gagne", odds=1.6)
        self.assertIsNone(boosts.to_bet(r2, NOW, 100))                     # EV < 5 %


class Coteur(unittest.TestCase):
    def test_parse_card(self):
        card = ('<div class="custom-card p-0 overflow-hidden hover-shadow"><img src="/build/images/logo/bookid/33.webp">'
                '<span class="badge text-truncate" style="x">Cote Boostée : Lorient - Brest</span>'
                '<h5 class="card-title h6">Lorient gagne et plus de 2,5 buts dans le match</h5>'
                '<span class="display-6 fw-bold">\n 3.20 \n</span><span class="badge" title="Mise Maximum">Max: 20€</span></div>')
        b = coteur.parse(card)[0]
        self.assertEqual((b["book"], b["event"], b["odds"], b["max_stake"]), ("winamax", "Lorient - Brest", 3.2, 20.0))


if __name__ == "__main__":
    unittest.main()


class Stale(unittest.TestCase):
    def test_respectivement_opponent_must_match(self):
        r = boosts.evaluate({"id": "b", "book": "winamax", "event": "Football", "odds": 3.0, "max_stake": 20,
                             "text": "Le Paris SG et Newcastle gagnent chacun leur match (respectivement contre Lyon et Everton)"},
                            GAMES, {})
        self.assertFalse(r["evaluable"])
        self.assertIn("périmé", r["why"])

    def test_team_legs_refused_when_not_new(self):
        r = boosts.evaluate({"id": "b", "book": "winamax", "event": "Football", "odds": 3.0, "max_stake": 20,
                             "text": "Le Paris SG et Newcastle gagnent chacun leur match"}, GAMES, {}, allow_team_legs=False)
        self.assertFalse(r["evaluable"])
        r = boosts.evaluate({"id": "b", "book": "winamax", "event": "Lorient - Brest", "odds": 3.0, "max_stake": 20,
                             "text": "Lorient gagne"}, GAMES, {}, allow_team_legs=False)
        self.assertTrue(r["evaluable"])  # boost d'un match précis : appariement exact, toujours évaluable


class PlayerTraps(unittest.TestCase):
    def test_player_or_compound_subjects_refused(self):
        for t in ["Kylian Mbappé premier buteur du match et Newcastle gagne", "K. Mbappe buteur et Newcastle gagne",
                  "Newcastle marque le 1er but et gagne le match", "Newcastle ou Everton gagne et plus de 3,5 buts dans le match",
                  "O. Blomberg ou J.P. Hauge buteur et Newcastle gagne"]:
            r = boosts.evaluate({"id": "b", "book": "winamax", "event": "Newcastle - Everton", "text": t, "odds": 3.0,
                                 "max_stake": 20}, GAMES, {})
            self.assertFalse(r["evaluable"], t)


class Settle(unittest.TestCase):
    def test_settle_from_exact_score(self):
        import tempfile
        from autonome import store, tracker
        d = tempfile.mkdtemp()
        r = boosts.evaluate({"id": "b1", "book": "winamax", "event": "Lorient - Brest",
                             "text": "Lorient gagne et plus de 2,5 buts dans le match", "odds": 9.0, "max_stake": 20}, GAMES, {})
        b = boosts.to_bet(r, NOW, 100)
        tracker.record_bets(d, [b])
        ex = {"markets": [{"closed": True, "groupItemTitle": "FC Lorient 2 - 1 Stade Brestois 29", "outcomePrices": '["1", "0"]'},
                          {"closed": True, "groupItemTitle": "FC Lorient 1 - 1 Stade Brestois 29", "outcomePrices": '["0", "1"]'}]}
        later = datetime(2026, 11, 3, 3, 0, tzinfo=timezone.utc)
        early = datetime(2026, 11, 2, 21, 0, tzinfo=timezone.utc)
        self.assertEqual(boosts.settle(d, lambda slug: ex, early), 0)  # moins de 3 h après le coup d'envoi
        rows = store.read(d, tracker.BETS)
        rows[0]["boost_legs"][0]["game"] = "pm|fl1-x"
        store.write_all(d, tracker.BETS, rows)
        self.assertEqual(boosts.settle(d, lambda slug: ex if slug == "fl1-x-exact-score" else None, later), 1)
        self.assertTrue(store.read(d, tracker.BETS)[0]["result"]["won"])   # 2-1 : victoire et 3 buts
