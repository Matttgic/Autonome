"""Winamax : état PRELOADED_STATE de la page publique (structure de Grotonome/cotes-value ; valeurs synthétiques)."""
import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from autonome.sources import winamax as W

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
T = int(datetime(2026, 11, 2, 19, 45, tzinfo=timezone.utc).timestamp())


def page(matches, bets, outcomes, odds):
    st = {"matches": matches, "bets": bets, "outcomes": outcomes, "odds": odds}
    return "<script>var PRELOADED_STATE = " + json.dumps(st) + ";</script>"


def foot(mid=1, market=1, codes=("1", "x", "2"), labels=("Lorient", "Match nul", "Brest"), status="PREMATCH", start=T):
    oids = [mid * 10 + i for i in range(len(codes))]
    return ({str(mid): {"matchId": mid, "sportId": 1, "status": status, "matchStart": start, "competitor1Name": "Lorient",
                        "competitor2Name": "Brest", "mainBetId": 100 + mid}},
            {str(100 + mid): {"matchId": mid, "marketId": market, "outcomes": oids}},
            {str(o): {"code": c, "label": lab} for o, c, lab in zip(oids, codes, labels)},
            {str(o): v for o, v in zip(oids, (2.35, 3.1, 2.83))})


class Parse(unittest.TestCase):
    def test_main_1x2(self):
        evs = W.events_from(W.state(page(*foot())), NOW)
        self.assertEqual(evs[0]["odds"], {"1x2": {"home": 2.35, "draw": 3.1, "away": 2.83}})
        self.assertEqual((evs[0]["home"], evs[0]["commence"]), ("Lorient", "2026-11-02T19:45:00Z"))

    def test_refused(self):
        self.assertEqual(W.events_from(W.state(page(*foot(market=60))), NOW), [])           # 1X2 mi-temps
        self.assertEqual(W.events_from(W.state(page(*foot(status="LIVE"))), NOW), [])
        self.assertEqual(W.events_from(W.state(page(*foot(start=T - 86400))), NOW), [])
        self.assertEqual(W.events_from(W.state(page(*foot(labels=("Brest", "Match nul", "Lorient")))), NOW), [])
        self.assertEqual(W.events_from(W.state("<html>pas d'état</html>"), NOW), [])

    def test_tennis_winner(self):
        m = {"5": {"matchId": 5, "sportId": 5, "status": "PREMATCH", "matchStart": T, "competitor1Name": "Sinner J.",
                   "competitor2Name": "Alcaraz C.", "mainBetId": 9}}
        b = {"9": {"matchId": 5, "marketId": 186, "outcomes": [91, 92]}}
        o = {"91": {"code": "1", "label": "Sinner J."}, "92": {"code": "2", "label": "Alcaraz C."}}
        self.assertEqual(W.events_from(W.state(page(m, b, o, {"91": 1.3, "92": 3.4})), NOW)[0]["odds"],
                         {"ml": {"home": 1.3, "away": 3.4}})

    def test_http_error_has_code(self):
        import urllib.error

        def boom(*a, **k):
            raise urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
        with mock.patch("urllib.request.urlopen", boom), self.assertRaises(W.SourceError) as cm:
            W.fetch(W.PAGES[0])
        self.assertIn("HTTP 403", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
