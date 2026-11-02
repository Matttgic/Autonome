"""PMU (Kambi) et sports à deux issues. Données synthétiques au format réel."""
import unittest
from datetime import datetime, timezone

from autonome import live
from autonome.sources import kambi, polymarket as pm


def o(t, odds, line=None, status="OPEN"):
    d = {"type": t, "odds": odds, "status": status}
    if line is not None:
        d["line"] = line
    return d


DATA = {"events": [
    {"id": 1, "homeName": "Lorient", "awayName": "Brest", "start": "2026-11-02T19:45:00Z", "sport": "FOOTBALL",
     "state": "NOT_STARTED", "path": [{"name": "Football"}, {"name": "Ligue 1"}]},
    {"id": 2, "homeName": "Los Angeles Lakers", "awayName": "Toronto Raptors", "start": "2026-11-03T02:10:00Z",
     "sport": "BASKETBALL", "state": "NOT_STARTED", "path": []},
    {"id": 3, "homeName": "A", "awayName": "B", "start": "2026-11-02T10:00:00Z", "sport": "FOOTBALL", "state": "STARTED"}],
    "betOffers": [
    {"eventId": 1, "criterion": {"englishLabel": "Full Time"}, "betOfferType": {"englishName": "Match"},
     "outcomes": [o("OT_ONE", 2280), o("OT_CROSS", 3100), o("OT_TWO", 2880, status="SUSPENDED")]},
    {"eventId": 1, "criterion": {"englishLabel": "Full Time - 1UP"}, "betOfferType": {"englishName": "Match"},
     "outcomes": [o("OT_ONE", 2000), o("OT_TWO", 2500)]},
    {"eventId": 1, "criterion": {"englishLabel": "Total Goals"}, "betOfferType": {"englishName": "Over/Under"},
     "outcomes": [o("OT_OVER", 1940, 2500), o("OT_UNDER", 1650, 2500)]},
    {"eventId": 1, "criterion": {"englishLabel": "Total Goals"}, "betOfferType": {"englishName": "Over/Under"},
     "outcomes": [o("OT_OVER", 1500, 2250), o("OT_UNDER", 2400, 2250)]},
    {"eventId": 1, "criterion": {"englishLabel": "Total Goals by Brest"}, "betOfferType": {"englishName": "Over/Under"},
     "outcomes": [o("OT_OVER", 2200, 1500), o("OT_UNDER", 1460, 1500)]},
    {"eventId": 1, "criterion": {"englishLabel": "Double Chance"}, "betOfferType": {"englishName": "Double Chance"},
     "outcomes": [o("OT_ONE_OR_CROSS", 1320), o("OT_CROSS_OR_TWO", 1500), o("OT_ONE_OR_TWO", 1270)]},
    {"eventId": 2, "criterion": {"englishLabel": "Match Odds - Including Overtime"}, "betOfferType": {"englishName": "Match"},
     "outcomes": [o("OT_ONE", 1600), o("OT_TWO", 2400)]}]}


class Kambi(unittest.TestCase):
    def test_map(self):
        ev = {e["kambi_id"]: e for e in kambi.to_events(DATA, "pmusportsfr")}
        self.assertNotIn(3, ev)                                          # déjà commencé
        f = ev[1]["odds"]
        self.assertEqual(f["1x2"], {"home": 2.28, "draw": 3.10})         # suspendu = absent ; « 1UP » ignoré
        self.assertEqual(f["ou@2.5"], {"over": 1.94, "under": 1.65})
        self.assertNotIn("ou@2.25", f)                                   # quart de ligne ignoré
        self.assertEqual(f["team_ou@away@1.5"], {"over": 2.20, "under": 1.46})
        self.assertEqual(f["dc"], {"1X": 1.32, "X2": 1.50, "12": 1.27})
        self.assertEqual(ev[2]["odds"]["ml"], {"home": 1.60, "away": 2.40})


class TwoWay(unittest.TestCase):
    def test_polymarket_two_way_and_swapped_pairing(self):
        e = {"title": "Raptors vs. Lakers", "slug": "nba-tor-lal", "startTime": "2026-11-03T02:00:00Z",
             "markets": [{"id": "9", "sportsMarketType": "moneyline", "outcomes": '["Raptors", "Lakers"]',
                          "bestBid": 0.39, "bestAsk": 0.41, "liquidityNum": 50000, "active": True}]}
        ref = pm.build_reference([e])
        self.assertTrue(ref[0]["two_way"])
        book = [ev for ev in kambi.to_events(DATA, "pmusportsfr") if ev["kambi_id"] == 2]
        now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        pairs, cands = live.scan(ref, book, "pmu_fr", now, {"min_ev": -9, "min_ev_cons": -9, "diagnostic": True})
        self.assertEqual(len(pairs), 1)
        by = {c["label"]: c for c in cands}
        # Lakers : p = 1 - 0.40 = 0.60, cote PMU 1.60 -> EV = -4 % ; Raptors : p = 0.40, cote 2.40 -> EV = -4 %
        self.assertAlmostEqual(by["Vainqueur : Toronto Raptors"]["ev"], 0.40 * 2.40 - 1)
        self.assertAlmostEqual(by["Vainqueur : Los Angeles Lakers"]["ev"], 0.60 * 1.60 - 1)

    def test_football_never_swapped(self):
        from autonome.match import pair
        ref = [{"commence": "2026-11-02T19:45:00Z", "home": "FC Lorient", "away": "Stade Brestois 29"}]
        self.assertEqual(pair(ref, [{"commence": "2026-11-02T19:45:00Z", "home": "Brest", "away": "Lorient"}]), [])


if __name__ == "__main__":
    unittest.main()
