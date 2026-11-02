"""Régressions de la 2e revue adverse (pipeline live)."""
import tempfile
import unittest
from datetime import datetime, timezone

from autonome import live, notify, store, tracker
from autonome.match import pair
from autonome.sources import netbet as nb, polymarket as pm
from autonome.sources.jslit import JsLitError, parse_nuxt


class R(unittest.TestCase):
    def test_void_double_chance_is_void(self):
        d = tempfile.mkdtemp()
        tracker.record_bets(d, [{"bet_id": "b", "event_id": "e", "group": "dc", "selection": "12", "odds": 1.3,
                                 "stake": 1, "ev": 0.05, "ref_kind": "polymarket", "commence": "2026-11-01T10:00:00Z",
                                 "legs": [["1", 0], ["3", 0]], "home": "A", "away": "B"}])
        res = {"1": {"closed": True, "outcomePrices": '["0.5", "0.5"]'}, "3": {"closed": True, "outcomePrices": '["0.5", "0.5"]'}}
        live.settle(d, res.get, datetime(2026, 11, 2, tzinfo=timezone.utc))
        self.assertIsNone(store.read(d, tracker.BETS)[0]["result"]["won"])

    def test_derby_orientation_refused(self):
        ref = [{"commence": "2026-11-02T19:45:00Z", "home": "Inter Milan", "away": "AC Milan"}]
        book = [{"commence": "2026-11-02T19:45:00Z", "home": "AC Milan", "away": "Inter Milan"}]
        self.assertEqual(pair(ref, book), [])

    def test_jslit_bounds(self):
        for bad in ['window.__NUXT__=(function(a){return {x:Array(1000000000000)}}(1))',
                    'window.__NUXT__=(function(a){a[999999999999]=1;return {}}([]))',
                    'window.__NUXT__=' + "[" * 5000 + "]" * 5000]:
            with self.assertRaises(JsLitError):
                parse_nuxt(bad)
        self.assertEqual(parse_nuxt("window.__NUXT__={s:'l\\'a\\x41'}")["s"], "l'aA")

    def test_malformed_sources_never_crash(self):
        bad = [{"title": None}, {"title": "A vs. B - More Markets", "startTime": "2026-11-02T19:45:00Z",
                                 "markets": [{"sportsMarketType": "totals", "bestBid": 0.4, "bestAsk": 0.41,
                                              "liquidityNum": 9e9, "outcomes": ["Over", "Under"], "line": None}]},
               {"title": "A vs. B", "markets": None, "startTime": "x", "slug": "s"}]
        self.assertEqual(pm.build_reference(bad), [])  # aucun événement principal valide
        cyc = 'window.__NUXT__=(function(a){a.s=a;return {e:a,f:{matchId:1,markets:[null,{bets:[null]}],actors:[null],start:"demain"}}}({}))'
        self.assertEqual(nb.parse_event_page(cyc, "/evenement/1-a-b"), [])

    def test_markdown_escaped(self):
        s = notify.md("Alpha @victim [clic](https://evil) <img> | x")
        for ch in "@[]<>|":
            self.assertNotIn(" " + ch, " " + s.replace("\\" + ch, ""))

    def test_dc_spread_is_sum(self):
        g = pm.build_reference([{"title": "A vs. B", "slug": "s", "startTime": "2026-11-02T19:45:00Z", "markets": [
            {"id": i, "groupItemTitle": n, "bestBid": b, "bestAsk": b + 0.025, "liquidityNum": 9999, "active": True}
            for i, n, b in (("1", "A", 0.39), ("2", "Draw (A vs. B)", 0.29), ("3", "B", 0.31))]}])[0]
        self.assertAlmostEqual(g["markets"]["dc"]["12"]["spread"], 0.05)


if __name__ == "__main__":
    unittest.main()
