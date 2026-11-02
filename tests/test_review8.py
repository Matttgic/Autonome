"""Régressions de la 8e revue adverse (2026-11-02) : pagination Gamma, doubles, codes pays, prolongation exclue."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from autonome.match import markers, sim
from autonome.sources import betclic as B, polymarket as pm


class Review8(unittest.TestCase):
    def test_gamma_pages_of_100_sorted_desc(self):
        now = datetime.now(timezone.utc)
        recent = (now + timedelta(hours=5)).isoformat()
        old = (now - timedelta(days=30)).isoformat()
        calls = []

        def fake_get(path, timeout=30, pause=1.0):
            calls.append(path)
            if "tag_slug=tennis" in path:
                self.assertIn("limit=100", path)
                self.assertIn("order=startDate&ascending=false", path)
                off = int(path.split("offset=")[1].split("&")[0])
                return [{"id": f"{off}-{i}", "startTime": recent if off == 0 else old} for i in range(100)]
            return []
        with mock.patch.object(pm, "get", fake_get):
            pm.fetch(tags=["tennis"], window_tags={})
        offsets = [c for c in calls if "tag_slug=tennis" in c]
        self.assertEqual(len(offsets), 2)          # page 2 entièrement passée : arrêt

    def test_doubles_and_country_codes(self):
        self.assertIn("double", markers("Ivanov, Oleksandr/Petrov, Bogdan"))
        self.assertEqual(sim("Ivanov Oleksandr", "Ivanov, Oleksandr/Petrov, Bogdan"), 0.0)
        self.assertEqual(markers("Smyrnov Mykyta (UKR)"), set())
        self.assertGreater(sim("Smyrnov Mykyta", "Smyrnov Mykyta (UKR)"), 0.9)

    def test_overtime_excluded_label_refused(self):
        m = [{"name": "Vainqueur du match (prolongations exclues)", "selections": [{"name": "A", "odds": 1.8},
                                                                                   {"name": "B", "odds": 2.0}]}]
        self.assertEqual(B.map_markets(m, "A", "B", "ICE_HOCKEY"), {})
        m[0]["name"] = "Vainqueur du match (prolong. & pen. inclus)"
        self.assertEqual(B.map_markets(m, "A", "B", "ICE_HOCKEY"), {"ml": {"home": 1.8, "away": 2.0}})


if __name__ == "__main__":
    unittest.main()
