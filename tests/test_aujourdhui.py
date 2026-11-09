"""Page d'entrée « Aujourd'hui » (lot AU-L5) : bloc `aujourdhui` de site.json au schéma commun des 3 dépôts.
Valeurs synthétiques au format réel (méta de runs.jsonl, paris de bets.jsonl) : aucune vraie cote."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from autonome import site, store, tracker

NOW = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)
META = {"at": NOW.isoformat(), "ref_games": 120, "pmu_events": 43, "coteur_books": {"betclic_fr": 300, "vbet_fr": 0},
        "errors": []}


def st(n=0, mean=None, ci=None, roi_n=0, roi=None):
    return {"clv": {"n": n, "mean": mean, "ci95": ci}, "roi": {"n": roi_n, "roi": roi}}


class Verdict(unittest.TestCase):
    def test_templates(self):
        self.assertEqual(site.verdict(st()), "Autonome : aucun pari avec clôture mesurée pour l'instant (0 / 460 nécessaires).")
        self.assertEqual(site.verdict(st(10, 0.0415, [-0.0336, 0.1166], 8, -0.0329)),
                         "Autonome : CLV moyenne +4,2 % (IC 95 % −3,4 % à +11,7 %) sur 10 paris, ROI −3,3 % sur 8 réglés ;"
                         " 10 / 460 nécessaires : trop tôt pour conclure.")
        self.assertTrue(site.verdict(st(500, 0.02, [0.005, 0.035])).endswith("avantage démontré (borne basse de l'IC > 0)."))
        self.assertTrue(site.verdict(st(500, 0.01, [-0.005, 0.025])).endswith("pas d'avantage démontré."))


class Health(unittest.TestCase):
    def test_states(self):
        self.assertEqual(site._sante(META, [], NOW),
                         {"etat": "ok", "message": "PMU : 43 matchs lus ; coteur.com : 1 bookmakers lus",
                          "derniere_collecte": NOW.isoformat()})
        self.assertEqual(site._sante({**META, "ref_games": 0}, [], NOW)["etat"], "panne")
        s = site._sante({**META, "pmu_events": 0}, ["netbet", "winamax"], NOW)
        self.assertEqual((s["etat"], s["message"]), ("degrade", "PMU non lu(s) au dernier passage ; en pause : netbet, winamax"))


class Block(unittest.TestCase):
    def test_schema_and_limits(self):
        d = tempfile.mkdtemp()
        start = (NOW + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        bets = [{"bet_id": f"b{i}", "event_id": f"e{i}", "status": "open", "ref_kind": "polymarket", "home": f"A{i}",
                 "away": f"B{i}", "label": "1X2 : A", "book": "pmu_fr", "odds": 2.1, "fair_odds": 1.95, "ev": 0.077,
                 "stake": 1.0, "commence": start, "url": "javascript:alert(1)" if i == 0 else "https://www.pmu.fr/sport/",
                 "result": None, "close": None, "found_at": NOW.isoformat()} for i in range(7)]
        store.write_all(d, tracker.BETS, bets)
        out = site.build(d, META, {}, NOW)
        a = out["aujourdhui"]
        self.assertEqual(set(a), {"depot", "url", "genere_le", "sante", "a_jouer", "verdict"})
        self.assertEqual(len(a["a_jouer"]), 5)
        self.assertEqual(set(a["a_jouer"][0]), {"match", "debut", "bookmaker", "pari", "cote", "cote_juste", "ev", "lien"})
        self.assertEqual(a["a_jouer"][0]["bookmaker"], "PMU")
        self.assertIsNone(a["a_jouer"][0]["lien"])                      # seul un lien https:// est publié
        self.assertEqual(a["a_jouer"][1]["lien"], "https://www.pmu.fr/sport/")
        self.assertLess(len(json.dumps(a, ensure_ascii=False).encode("utf-8")), 20_000)
        self.assertEqual(out["bilan"]["n_requis"], site.N_REQUIS)


if __name__ == "__main__":
    unittest.main()
