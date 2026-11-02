"""Stratégies fictives « Valeur 4 % » et « Témoin » (données synthétiques, calculs vérifiables à la main)."""
import unittest
from datetime import datetime, timezone

from autonome import paper as PP

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def match(renc, outlier_home=2.0, age=10):
    books = {f"b{i}": {"1x2": {"home": 1.80 + i / 100, "draw": 3.6, "away": 4.6 - i / 100}} for i in range(1, 8)}
    books["x"] = {"1x2": {"home": outlier_home, "draw": 3.5, "away": 4.4}}
    return {"renc": renc, "commence": "2026-11-02T20:00:00Z", "home": "A", "away": "B", "sport": "FOOTBALL",
            "url": "u", "books": books, "snapshot_age_min": age}


class Paper(unittest.TestCase):
    def test_valeur_takes_outlier_once(self):
        got = [p for p in PP.picks([match("r1")], NOW, set()) if p["strategy"] == "paper-valeur4"]
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["book"], got[0]["selection"], got[0]["odds"]), ("x", "home", 2.0))
        self.assertTrue(0.04 <= got[0]["ev"] <= 0.40)
        self.assertTrue(2.5 <= got[0]["stake"] <= 20.0)          # Kelly ¼ entre 0,25 % et 2 % de 1 000 €
        done = {("paper-valeur4", got[0]["event_id"])}
        self.assertEqual([p for p in PP.picks([match("r1")], NOW, done) if p["strategy"] == "paper-valeur4"], [])

    def test_no_value_no_old_snapshot(self):
        self.assertEqual([p for p in PP.picks([match("r1", 1.83)], NOW, set()) if p["strategy"] == "paper-valeur4"], [])
        self.assertEqual(PP.picks([match("r1", age=90)], NOW, set()), [])

    def test_temoin_deterministic_one_in_three(self):
        ms = [match(f"r{i}", 1.83) for i in range(300)]
        t1 = [p["bet_id"] for p in PP.picks(ms, NOW, set()) if p["strategy"] == "paper-temoin"]
        t2 = [p["bet_id"] for p in PP.picks(ms, NOW, set()) if p["strategy"] == "paper-temoin"]
        self.assertEqual(t1, t2)                                   # graine fixe : même tirage
        self.assertTrue(70 <= len(t1) <= 130)                      # ~1 match sur 3
        self.assertTrue(all(1.5 <= p["odds"] <= 4.5 for p in PP.picks(ms, NOW, set())))

    def test_summary_hand(self):
        rows = [{"strategy": "paper-valeur4", "status": "settled", "stake": 10, "odds": 2.5, "result": {"won": True},
                 "close": {"clv_odds": 0.03}},
                {"strategy": "paper-valeur4", "status": "settled", "stake": 10, "odds": 3.0, "result": {"won": False}},
                {"strategy": "paper-valeur4", "status": "settled", "stake": 10, "odds": 2.0, "result": {"won": None}},
                {"strategy": "paper-valeur4", "status": "open", "stake": 10, "odds": 2.0, "result": None,
                 "close": {"clv_odds": 0.05}}]
        v = PP.summary(rows)[0]
        self.assertAlmostEqual(v["roi"], (15 - 10) / 20)         # +15 −10 sur 20 € misés ; remboursé exclu
        self.assertAlmostEqual(v["hit"], 0.5)
        self.assertAlmostEqual(v["bankroll"], 1005.0)
        self.assertEqual((v["n"], v["open"], v["settled"], v["clv"]), (4, 1, 2, 0.03))  # CLV des seuls réglés

    def test_matched_control_and_abandon(self):
        ps = PP.picks([match("r1")], NOW, set())
        v = [p for p in ps if p["strategy"] == "paper-valeur4"][0]
        t = [p for p in ps if p["strategy"] == "paper-temoin-apparie"][0]
        self.assertEqual((t["event_id"], t["stake"]), (v["event_id"], v["stake"]))      # même match, même mise
        self.assertTrue(1.5 <= t["odds"] <= 4.5)
        rows = [{**v, "status": "open"}]
        self.assertEqual(PP.abandon(rows, datetime(2026, 11, 5, tzinfo=timezone.utc)), 1)
        self.assertEqual(rows[0]["status"], "unsettled")

    def test_unsettleable_sport_never_taken(self):
        self.assertEqual(PP.picks([{**match("r1"), "sport": "VOLLEYBALL"}], NOW, set()), [])


if __name__ == "__main__":
    unittest.main()
