"""Pipeline sans clé : Polymarket (référence) vs NetBet. Données synthétiques au format réel (aucune vraie cote)."""
import json
import tempfile
import unittest
from datetime import datetime, timezone

from autonome import live, store, tracker
from autonome.match import pair, sim, slug_hits
from autonome.sources import netbet as nb, polymarket as pm

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def mkt(mid, title, bid, ask, outs='["Yes", "No"]', t="moneyline", line=None, liq=10000):
    return {"id": mid, "groupItemTitle": title, "bestBid": bid, "bestAsk": ask, "outcomes": outs,
            "sportsMarketType": t, "line": line, "liquidityNum": liq, "active": True, "closed": False}


GAMMA = [
    {"title": "FC Alpha vs. Beta SC", "slug": "x-alp-bet", "startTime": "2026-11-02T19:45:00Z",
     "markets": [mkt("1", "FC Alpha", 0.39, 0.41), mkt("2", "Draw (FC Alpha vs. Beta SC)", 0.29, 0.31),
                 mkt("3", "Beta SC", 0.31, 0.33)]},
    {"title": "FC Alpha vs. Beta SC - More Markets", "slug": "x-alp-bet-more", "startTime": "2026-11-02T19:45:00Z",
     "markets": [mkt("4", "O/U 2.5", 0.49, 0.51, '["Over", "Under"]', "totals", 2.5),
                 mkt("5", "Both Teams to Score", 0.50, 0.60, t="both_teams_to_score"),  # écart 0.10 -> rejeté
                 mkt("6", "O/U 3.5", 0.20, 0.22, '["Over", "Under"]', "totals", 3.5, liq=500)]},  # peu liquide
]


class Reference(unittest.TestCase):
    def test_build_reference_hand(self):
        g = pm.build_reference(GAMMA)
        self.assertEqual(len(g), 1)
        m = g[0]["markets"]
        # milieux .40/.30/.32, S = 1.02 -> p(home) = .40/1.02 = .392157 ; bornes .39/1.02 et .41/1.02
        self.assertAlmostEqual(m["1x2"]["home"]["p"], 0.392157, places=6)
        self.assertAlmostEqual(m["1x2"]["home"]["lo"], 0.382353, places=6)
        self.assertAlmostEqual(m["dc"]["1X"]["p"], 0.70 / 1.02, places=6)
        self.assertAlmostEqual(m["ou@2.5"]["under"]["p"], 0.5)
        self.assertAlmostEqual(m["ou@2.5"]["under"]["lo"], 0.49)   # 1 - ask
        self.assertNotIn("btts", m)       # écart trop large : absent, pas inventé
        self.assertNotIn("ou@3.5", m)     # liquidité insuffisante
        self.assertEqual(m["dc"]["12"]["legs"], [["1", 0], ["3", 0]])

    def test_resolved(self):
        self.assertEqual(pm.resolved({"closed": True, "outcomePrices": '["1", "0"]'}), [1.0, 0.0])
        self.assertIsNone(pm.resolved({"closed": False, "outcomePrices": '["1", "0"]'}))
        self.assertIsNone(pm.resolved({"closed": True, "outcomePrices": '["0.7", "0.3"]'}))


def book(odds, start="2026-11-02T19:45:00Z"):
    return {"id": "nb|9", "url": "/evenement/9-alpha-beta", "commence": start, "home": "Alpha", "away": "Beta",
            "competition": "Test", "odds": odds}


class Compare(unittest.TestCase):
    def test_value_hand(self):
        ref = {"key": "pm|k", "commence": "2026-11-02T19:45:00Z", "home": "FC Alpha", "away": "Beta SC",
               "markets": {"ou@2.5": {"over": {"p": 0.5, "lo": 0.49, "hi": 0.51, "legs": [["4", 0]], "spread": 0.02}}}}
        out = live.compare(ref, book({"ou@2.5": {"over": 2.20}}), "netbet_fr", NOW)
        self.assertEqual(len(out), 1)
        b = out[0]
        self.assertAlmostEqual(b["ev"], 0.10)          # 0.5*2.2-1
        self.assertAlmostEqual(b["ev_cons"], 0.078)    # 0.49*2.2-1
        self.assertEqual(b["stake"], 1.5)              # (0.078/1.2)*0.25*100 = 1.625 -> 1.5
        self.assertEqual(b["label"], "Plus de 2.5 buts")

    def test_rejections(self):
        ref = {"key": "pm|k", "commence": "2026-11-02T19:45:00Z", "home": "A", "away": "B",
               "markets": {"ou@2.5": {"over": {"p": 0.5, "lo": 0.46, "hi": 0.54, "legs": [["4", 0]], "spread": 0.08}}}}
        self.assertEqual(live.compare(ref, book({"ou@2.5": {"over": 2.20}}), "nb", NOW), [])  # écart trop large
        ref["markets"]["ou@2.5"]["over"].update(lo=0.49, spread=0.02)
        self.assertEqual(live.compare(ref, book({"ou@2.5": {"over": 2.02}}), "nb", NOW), [])  # EV 1 % < 3 %
        late = dict(ref, commence="2026-11-02T12:10:00Z")
        self.assertEqual(live.compare(late, book({"ou@2.5": {"over": 2.5}}), "nb", NOW), [])  # trop proche

    def test_closing_and_settle(self):
        d = tempfile.mkdtemp()
        ref = {"key": "pm|k", "commence": "2026-11-02T19:45:00Z", "home": "A", "away": "B",
               "markets": {"dc": {"12": {"p": 0.5, "lo": 0.49, "hi": 0.51, "legs": [["1", 0], ["3", 0]], "spread": 0.02}}}}
        b = live.compare(ref, book({"dc": {"12": 2.2}}), "nb", NOW)[0]
        tracker.record_bets(d, [b])
        ref2 = json.loads(json.dumps(ref))
        ref2["markets"]["dc"]["12"]["p"] = 0.55
        later = datetime(2026, 11, 2, 19, 0, tzinfo=timezone.utc)
        self.assertEqual(live.update_closing(d, [ref2], later), 1)
        r = store.read(d, tracker.BETS)[0]
        self.assertAlmostEqual(r["close"]["clv_odds"], 2.2 * 0.55 - 1)  # cote prise / cote juste clôture - 1
        self.assertAlmostEqual(r["close"]["minutes_to_start"], 45)
        res = {"1": {"closed": True, "outcomePrices": '["0", "1"]'}, "3": {"closed": True, "outcomePrices": '["1", "0"]'}}
        after = datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(live.settle(d, res.get, after), 1)
        r = store.read(d, tracker.BETS)[0]
        self.assertTrue(r["result"]["won"])           # victoire extérieure -> « 1 ou 2 » gagné
        s = tracker.stats(d)
        self.assertEqual(s["clv"]["n"], 1)
        self.assertAlmostEqual(s["roi"]["roi"], 1.2)


NUXT = ('<script>window.__NUXT__=(function(a,b){return {state:{e:{matchId:"77",id:"9",start:"2026-11-02T20:45:00.000+01:00",'
        'competitionLabel:"L1",actors:[{type:"home",label:"Alpha"},{type:"away",label:"Beta"}],markets:['
        '{selection_order_type:"1x2",bets:[{label:"Qui va gagner le match ?",selections:[{label:"Alpha",odds_display:"2.37"},'
        '{label:"Nul",odds_display:a},{label:"Beta",odds_display:"-"}]}]},'
        '{selection_order_type:"over_under",bets:[{label:"Plus ou moins de 2.5 buts ?",selections:[{label:"Plus de 2.5",'
        'odds_display:"1.90"},{label:"Moins de 2.5",odds_display:"1.85"}]},'
        '{label:"Plus ou moins de 1.5 buts pour Beta ? (temps réglementaire)",selections:[{label:"Plus de 1.5",odds_display:"2.40"},'
        '{label:"Moins de 1.5",odds_display:"1.50"}]}]},'
        '{selection_order_type:"handicap_2ways",bets:[{label:"Handicap (-1.5) - Qui va gagner le match ?",selections:['
        '{label:"(-1.5) Alpha",odds_display:"4.60"},{label:"(+1.5) Beta",odds_display:"1.08"}]}]}]}}}}("3.05",null));</script>')


class NetBet(unittest.TestCase):
    def test_parse_event(self):
        e = nb.parse_event_page(NUXT, "/evenement/9-alpha-beta")[0]
        self.assertEqual(e["commence"], "2026-11-02T19:45:00Z")   # 20:45 Paris = 19:45 UTC
        self.assertEqual(e["odds"]["1x2"], {"home": 2.37, "draw": 3.05})  # « - » = fermé -> absent
        self.assertEqual(e["odds"]["ou@2.5"], {"over": 1.90, "under": 1.85})
        self.assertEqual(e["odds"]["team_ou@away@1.5"], {"over": 2.40, "under": 1.50})
        self.assertEqual(e["odds"]["ah@home@-1.5"], {"fav": 4.60, "dog": 1.08})

    def test_event_urls(self):
        h = 'x \\u002Fevenement\\u002F11538955-ligue-1-2026-2027-vainqueur y /evenement/12-lorient-brest'
        self.assertEqual(nb.event_urls(h), ["/evenement/12-lorient-brest"])


class Matching(unittest.TestCase):
    def test_names(self):
        self.assertGreater(sim("Stade Brestois 29", "Brest"), 0.8)
        self.assertGreater(sim("Paris Saint-Germain FC", "Paris SG"), 0.9)
        self.assertLess(sim("Paris FC", "Paris SG"), 0.5)
        self.assertLess(sim("Manchester City FC", "Man Utd"), 0.5)
        self.assertLess(sim("Real Madrid CF", "Atletico Madrid"), 0.5)
        self.assertTrue(slug_hits("/evenement/1-rennes-lille", "Stade Rennais FC 1901", "Lille OSC"))
        self.assertFalse(slug_hits("/evenement/1-lens-marseille", "Lille OSC", "Olympique de Marseille"))

    def test_pair_requires_time_and_both_teams(self):
        ref = [{"commence": "2026-11-02T19:45:00Z", "home": "FC Lorient", "away": "Stade Brestois 29"}]
        ok = {"commence": "2026-11-02T19:45:00Z", "home": "Lorient", "away": "Brest"}
        late = dict(ok, commence="2026-11-02T21:00:00Z")
        swapped = dict(ok, home="Brest", away="Lorient")
        self.assertEqual(len(pair(ref, [ok])), 1)
        self.assertEqual(pair(ref, [late]), [])
        self.assertEqual(pair(ref, [swapped]), [])


if __name__ == "__main__":
    unittest.main()
