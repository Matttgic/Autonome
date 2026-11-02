import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from autonome import consensus
from autonome.devig import shin
from autonome.sources import coteur_odds

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def match(outlier):
    books = {f"b{i}_fr": {"ml": {"home": 1.80 + 0.01 * i, "away": 1.95 - 0.01 * i}} for i in range(6)}
    books["x_fr"] = {"ml": {"home": outlier, "away": 1.70}}
    return {"renc": "1", "commence": "2026-11-02T18:00:00Z", "home": "A", "away": "B", "sport": "TENNIS",
            "competition": "T", "url": "u", "books": books}


class Consensus(unittest.TestCase):
    def test_outlier_detected_hand(self):
        p = sum(shin([1.80 + 0.01 * i, 1.95 - 0.01 * i])[0] for i in range(6)) / 6  # moyenne des 6 autres books
        out = consensus.evaluate(match(2.30), NOW, 1000)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["book"], "x_fr")
        self.assertAlmostEqual(out[0]["ev"], p * 2.30 - 1)
        self.assertNotIn("x_fr", out[0]["ref_books"])     # leave-one-out

    def test_no_alert_without_enough_books_or_edge(self):
        m = match(2.30)
        del m["books"]["b0_fr"]
        self.assertEqual(consensus.evaluate(m, NOW, 1000), [])  # 5 autres books < 6
        self.assertEqual(consensus.evaluate(match(1.90), NOW, 1000), [])


class Snapshot(unittest.TestCase):
    def test_load_filters(self):
        d = tempfile.mkdtemp()
        snap = {"collected_at": "2026-11-02T11:00:00Z", "matches": {"7": {
            "sport": "foot", "href": "/cote/a-b-7", "name": "A - B", "ts": "1793642400", "compet": "L1",
            "odds": {"1n2|": [{"book": 24, "odds": {"1": 2.1, "0": 3.2, "2": 3.4}, "upd": "2026-11-02T10:00:00Z", "off": False},
                              {"book": 33, "odds": {"1": 2.5, "0": 3.2, "2": 3.4}, "upd": "2026-10-29T10:00:00Z", "off": True},
                              {"book": 45, "odds": {"1": 2.2, "0": 3.2, "2": 3.4}, "upd": "2026-11-02T10:00:00Z", "off": False}]}}}}
        Path(d, "c.json").write_text(json.dumps(snap))
        by, ms, why = coteur_odds.load(Path(d, "c.json"), NOW)
        self.assertIsNone(why)
        self.assertEqual(set(by), {"betclic_fr"})   # Winamax désactivé, Bet365 non agréé : exclus
        self.assertEqual(by["betclic_fr"][0]["odds"]["1x2"], {"home": 2.1, "draw": 3.2, "away": 3.4})
        _, _, why = coteur_odds.load(Path(d, "c.json"), datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc))
        self.assertIn("trop vieux", why)


if __name__ == "__main__":
    unittest.main()


class Clones(unittest.TestCase):
    def test_identical_books_count_once(self):
        m = match(2.30)
        for i in range(6):
            m["books"][f"b{i}_fr"] = {"ml": {"home": 1.80, "away": 1.95}}   # 6 clones = 1 seule voix
        self.assertEqual(consensus.evaluate(m, NOW, 1000), [])
