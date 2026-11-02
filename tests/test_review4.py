"""Régressions de la 4e revue adverse (PMU/coteur/consensus/appariement)."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from autonome.match import pair, sim
from autonome.sources import coteur_odds, kambi

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


class Names(unittest.TestCase):
    def test_markers_and_initials(self):
        self.assertEqual(sim("Arsenal", "Arsenal W"), 0.0)
        self.assertEqual(sim("Juventus", "Juventus U19"), 0.0)
        self.assertEqual(sim("Paris Saint-Germain", "Paris Saint-Germain (Nikkitta)"), 0.0)
        self.assertEqual(sim("Serena Williams", "Williams V."), 0.0)
        self.assertGreater(sim("Venus Williams", "Williams V."), 0.8)
        self.assertGreater(sim("Viktorija Golubic", "Golubic V."), 0.8)

    def test_sport_must_match(self):
        ref = [{"commence": "2026-11-02T19:45:00Z", "home": "Paris Saint-Germain FC", "away": "Olympique de Marseille",
                "sport": "FOOTBALL"}]
        hb = [{"commence": "2026-11-02T19:45:00Z", "home": "PSG", "away": "Marseille", "sport": "HANDBALL"}]
        self.assertEqual(pair(ref, hb), [])


def bo(crit, o1, o2, n1="A", n2="B"):
    return {"eventId": 5, "criterion": {"englishLabel": crit}, "betOfferType": {"englishName": "Match"},
            "outcomes": [{"type": "OT_ONE", "odds": o1, "participant": n1}, {"type": "OT_TWO", "odds": o2, "participant": n2}]}


def ev(sport="ICE_HOCKEY"):
    return {"id": 5, "homeName": "Carlos Alcaraz", "awayName": "Jannik Sinner", "start": "2026-11-02T19:00:00Z",
            "sport": sport, "state": "NOT_STARTED"}


class KambiTraps(unittest.TestCase):
    def test_excluding_overtime_refused(self):
        d = {"events": [ev()], "betOffers": [bo("Match Odds - Excluding Overtime", 1800, 2000)]}
        self.assertNotIn("ml", kambi.to_events(d, "x")[0]["odds"])

    def test_swapped_outcome_label_realigned(self):
        d = {"events": [ev("TENNIS")], "betOffers": [bo("Match Odds", 2800, 1450, "Jannik Sinner", "Carlos Alcaraz")]}
        self.assertEqual(kambi.to_events(d, "x")[0]["odds"]["ml"], {"home": 1.45, "away": 2.8})

    def test_malformed_never_crashes(self):
        d = {"events": [ev(), {"id": [1]}, {"id": 6, "start": "x"}],
             "betOffers": [{"eventId": [5]}, "x", {"eventId": 5, "criterion": "str", "outcomes": [{"type": []}]}]}
        kambi.to_events(d, "x")


class Snapshot(unittest.TestCase):
    def test_malformed_snapshot(self):
        d = tempfile.mkdtemp()
        for content in ["{tronqué", "[]", json.dumps({"collected_at": "2026-11-02T11:00:00", "matches": {
                "1": "x", "2": {"name": "A - B", "ts": 10 ** 20, "odds": {"1n2": [1]}}}})]:
            Path(d, "c.json").write_text(content)
            coteur_odds.load(Path(d, "c.json"), NOW)   # ne lève jamais

    def test_foot_12_is_not_a_winner_market(self):
        d = tempfile.mkdtemp()
        Path(d, "c.json").write_text(json.dumps({"collected_at": "2026-11-02T11:00:00Z", "matches": {"7": {
            "sport": "foot", "name": "A - B", "ts": "1793642400", "href": "/cote/a-b-7",
            "odds": {"12|": [{"book": 24, "odds": {"1": 1.3, "2": 1.3}, "upd": "2026-11-02T10:00:00Z", "off": False}]}}}}))
        by, ms, _ = coteur_odds.load(Path(d, "c.json"), NOW)
        self.assertEqual(ms, [])


if __name__ == "__main__":
    unittest.main()
