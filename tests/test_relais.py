"""Fiabilité (lot AU-L2, 09/11/2026) : groupes PMU en 404 mis en pause, erreurs répétées visibles sur la page,
version des règles sur les nouveaux paris. Formats réels (messages d'erreur de runs.jsonl, réponses Kambi), aucun réseau."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from autonome import site, store, tracker
from autonome.sources import kambi
from tests.test_kambi import DATA

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
SPORTS = {"group": {"groups": [{"id": 1000093199, "name": "Football", "termKey": "football", "boCount": 120},
                               {"id": 1000093246, "name": "Sport vide", "termKey": "x", "boCount": 3},
                               {"id": 1000093211, "name": "Autre", "termKey": "y", "boCount": 0}]}}


def fake_get(offering, path, pause=1.0, **extra):
    if path == "group.json":
        return SPORTS
    if path == "betoffer/group/1000093199.json":
        return DATA
    raise kambi.SourceError(f"kambi {offering} {path}: HTTP 404")


class KambiPauses(unittest.TestCase):
    def test_status_and_skip(self):
        st = {}
        with mock.patch.object(kambi, "get", side_effect=fake_get) as g:
            evs, err = kambi.fetch_main("pmusportsfr", status=st)
            self.assertEqual(st, {"1000093199": "ok", "1000093246": "404"})  # boCount 0 : jamais demandé
            self.assertEqual(err, ["kambi pmusportsfr betoffer/group/1000093246.json: HTTP 404"])
            self.assertTrue(evs)
            n = g.call_count
            kambi.fetch_main("pmusportsfr", skip={"1000093246"}, status=(st := {}))
            self.assertEqual(g.call_count - n, 2)  # group.json + football seulement
            self.assertEqual(st, {"1000093199": "ok"})

    def test_three_404_in_a_row_pause_one_hour(self):
        p = {}
        for i in range(2):
            p = kambi.update_pauses(p, {"1000093246": "404"}, NOW + timedelta(minutes=3 * i))
            self.assertEqual(kambi.paused(p, NOW + timedelta(minutes=3 * i)), set())
        p = kambi.update_pauses(p, {"1000093246": "404", "1000093199": "ok"}, NOW + timedelta(minutes=6))
        self.assertEqual(kambi.paused(p, NOW + timedelta(minutes=7)), {"1000093246"})
        self.assertEqual(kambi.paused(p, NOW + timedelta(minutes=67)), set())  # 1 h après : redemandé
        # 404 puis offre revenue : le compteur repart de zéro
        q = kambi.update_pauses({}, {"1000093216": "404"}, NOW)
        q = kambi.update_pauses(q, {"1000093216": "404"}, NOW)
        q = kambi.update_pauses(q, {"1000093216": "ok"}, NOW)
        q = kambi.update_pauses(q, {"1000093216": "404"}, NOW)
        self.assertEqual(q, {"1000093216": {"n": 1, "until": ""}})
        # autre erreur (réseau) : ni pause ni remise à zéro
        self.assertEqual(kambi.update_pauses(dict(q), {"1000093216": "erreur"}, NOW), q)


class RepeatedErrors(unittest.TestCase):
    def test_counted_once_per_pass(self):
        e404 = "kambi pmusportsfr betoffer/group/1000093246.json: HTTP 404"
        runs = [{"at": "x", "errors": [e404, e404]} for _ in range(4)] + \
               [{"at": "x", "errors": ["netbet : budget de temps atteint"]} for _ in range(2)] + [{"at": "x"}, "bad"]
        r = site.repeated(runs, last=50, min_n=3)
        self.assertEqual(r, {"sur": 7, "n": 1, "top": [{"erreur": e404, "passages": 4}]})
        self.assertEqual(site.repeated([], last=50)["n"], 0)

    def test_on_site_json(self):
        d = tempfile.mkdtemp()
        store.write_all(d, "runs.jsonl", [{"at": NOW.isoformat(), "errors": ["unibet x: HTTP 503"]}] * 3)
        out = site.build(d, {"errors": [], "pmu_groupes_en_pause": 2}, {}, NOW)
        self.assertEqual(out["sante"]["pmu_groupes_en_pause"], 2)
        self.assertEqual(out["sante"]["erreurs_repetees"]["top"], [{"erreur": "unibet x: HTTP 503", "passages": 3}])


class RulesVersion(unittest.TestCase):
    def test_new_bets_only(self):
        d = tempfile.mkdtemp()
        store.write_all(d, tracker.BETS, [{"bet_id": "ancien", "status": "settled"}])
        tracker.record_bets(d, [{"bet_id": "ancien"}, {"bet_id": "nouveau"}])
        rows = {r["bet_id"]: r for r in store.read(d, tracker.BETS)}
        self.assertNotIn("version_regles", rows["ancien"])
        self.assertEqual(rows["nouveau"]["version_regles"], tracker.VERSION_REGLES)
        self.assertEqual(rows["nouveau"]["status"], "open")


if __name__ == "__main__":
    unittest.main()
