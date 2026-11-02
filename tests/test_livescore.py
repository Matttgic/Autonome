"""Règlement des paris « consensus » via LiveScore + lecture large Polymarket.
Données synthétiques au FORMAT réel (champs vérifiés le 2026-11-02) : aucun vrai score ni vraie cote."""
import unittest
from datetime import datetime, timezone
from unittest import mock

from autonome import consensus as CS
from autonome.sources import livescore as LS, polymarket as pm
from tests.test_live import GAMMA, mkt

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def ev(eid, esd, eps, t1, t2, tr, tr_or=None, en=None):
    e = {"Eid": eid, "Esd": esd, "Eps": eps, "T1": [{"Nm": t1}], "T2": [{"Nm": t2}], "Tr1": str(tr[0]), "Tr2": str(tr[1])}
    if en:
        e["T1"][0]["NmEn"], e["T2"][0]["NmEn"] = en
    if tr_or:
        e["Tr1OR"], e["Tr2OR"] = str(tr_or[0]), str(tr_or[1])
    return e


SOCCER = {"Stages": [{"Snm": "Ligue 2", "Cnm": "France", "Events": [
    ev("1", 20261102194500, "FT", "Stade de Reims", "FC Sochaux-Montbéliard", (2, 1), (2, 1)),
    ev("2", 20261102180000, "AET", "Alpha FC", "Beta FC", (2, 1), (1, 1)),          # prolongation : 1-1 à 90 min
    ev("3", 20261102180000, "AP", "Gamma FC", "Delta FC", (0, 0), (0, 0)),          # tirs au but
    ev("4", 20261102180000, "Postp.", "Epsilon FC", "Zeta FC", (0, 0)),             # reporté : ignoré
    ev("5", 20261102180000, "FT", "Bayern Munich", "Mainz", (3, 0), en=("Bayern Munich", "Mainz 05")),
    ev("6", 20261102180000, "FT", "Bayern Munich II", "Mainz II", (0, 2)),          # réserves, même heure
    {"Eid": "7", "Eps": "FT"},                                                      # malformé : ignoré
]}]}
TENNIS = {"Stages": [{"Snm": "Paris", "Events": [
    ev("10", 20261102100500, "FT", "Rinky Hijikata", "Vit Kopriva", (2, 0)),
    ev("11", 20261102120000, "Ret.", "Joueur Un", "Joueur Deux", (1, 0)),            # abandon : jamais réglé auto
]}]}
BASKET = {"Stages": [{"Snm": "Korisliiga", "Events": [
    ev("20", 20261102150000, "OT", "LePy", "Helsingin NMKY", (73, 71), (65, 65)),
]}]}


def bet(home, away, group, sel, commence="2026-11-02T19:45:00Z", sport="FOOTBALL"):
    return {"bet_id": f"cons|{home}|{group}|{sel}|x", "status": "open", "ref_kind": "consensus-anj", "sport": sport,
            "home": home, "away": away, "group": group, "selection": sel, "commence": commence, "odds": 2.0,
            "stake": 1.0, "result": None}


class Parse(unittest.TestCase):
    def test_statuses_and_regular_time(self):
        res = {r["id"]: r for r in LS.parse(SOCCER, "FOOTBALL")}
        self.assertEqual(set(res), {"1", "2", "3", "5", "6"})
        self.assertEqual(res["1"]["commence"], "2026-11-02T19:45:00Z")
        self.assertEqual(res["2"]["regular"], (1, 1))
        self.assertEqual(LS.outcome(res["2"], "1x2"), "draw")      # 1N2 = 90 min, pas le score après prolongation
        self.assertEqual(LS.outcome(res["3"], "1x2"), "draw")
        self.assertEqual(res["5"]["homes"], ["Bayern Munich"])     # Nm et NmEn identiques : une seule variante
        self.assertEqual(res["5"]["aways"], ["Mainz", "Mainz 05"])

    def test_tennis_retirement_and_basket_overtime(self):
        self.assertEqual([r["id"] for r in LS.parse(TENNIS, "TENNIS")], ["10"])
        b = LS.parse(BASKET, "BASKETBALL")[0]
        self.assertEqual(LS.outcome(b, "ml"), "home")              # vainqueur : prolongation incluse
        self.assertEqual(LS.outcome(b, "1x2"), "draw")             # 1N2 basket : 65-65 à la fin du temps réglementaire
        self.assertIsNone(LS.outcome({**b, "sport": "ICE_HOCKEY"}, "ml"))

    def test_bad_payload(self):
        with self.assertRaises(LS.SourceError):
            LS.parse({"x": 1}, "FOOTBALL")


class Settle(unittest.TestCase):
    def setUp(self):
        self.res = LS.parse(SOCCER, "FOOTBALL") + LS.parse(TENNIS, "TENNIS") + LS.parse(BASKET, "BASKETBALL")

    def test_settles_football_by_regular_time(self):
        rows = [bet("REIMS", "SOCHAUX", "1x2", "home"), bet("Alpha", "Beta", "1x2", "home", "2026-11-02T18:00:00Z")]
        self.assertEqual(CS.settle(rows, self.res, NOW), 2)
        self.assertTrue(rows[0]["result"]["won"])
        self.assertEqual(rows[0]["result"]["score"], "2-1")
        self.assertFalse(rows[1]["result"]["won"])                 # 1-1 à 90 min : le domicile ne gagne pas

    def test_reserve_never_used_for_first_team(self):
        rows = [bet("Bayern Munich", "Mainz", "1x2", "home", "2026-11-02T18:00:00Z")]
        CS.settle(rows, self.res, NOW)
        self.assertTrue(rows[0]["result"]["won"])                  # 3-0 de l'équipe première, pas 0-2 des réserves
        self.assertIn("LiveScore 5", rows[0]["result"]["source"])

    def test_reversed_tennis_is_oriented(self):
        rows = [bet("Kopriva V.", "Hijikata R.", "ml", "home", "2026-11-02T10:05:00Z", "TENNIS")]
        self.assertEqual(CS.settle(rows, self.res, NOW), 1)
        self.assertFalse(rows[0]["result"]["won"])                 # Kopriva a perdu
        self.assertEqual(rows[0]["result"]["score"], "0-2")

    def test_not_settled_when_unsafe(self):
        rows = [bet("Joueur Un", "Joueur Deux", "ml", "home", "2026-11-02T12:00:00Z", "TENNIS"),   # abandon
                bet("Epsilon", "Zeta", "1x2", "home", "2026-11-02T18:00:00Z"),                       # reporté
                bet("REIMS", "SOCHAUX", "1x2", "home", "2026-11-03T10:00:00Z"),                      # trop tôt
                bet("REIMS", "SOCHAUX", "1x2", "home", "2026-11-02T21:00:00Z"),                      # autre heure
                bet("SOCHAUX", "REIMS", "1x2", "home"),                                              # sens inversé (1N2)
                bet("REIMS", "SOCHAUX", "ml", "home", sport="ICE_HOCKEY")]                           # sport non géré
        self.assertEqual(CS.settle(rows, self.res, NOW), 0)
        self.assertTrue(all(r["status"] == "open" for r in rows))

    def test_ambiguous_match_left_open(self):
        twin = {**LS.parse(SOCCER, "FOOTBALL")[0], "id": "99", "final": (0, 3), "regular": (0, 3)}
        rows = [bet("REIMS", "SOCHAUX", "1x2", "home")]
        self.assertEqual(CS.settle(rows, self.res + [twin], NOW), 0)

    def test_days_to_fetch(self):
        rows = [bet("REIMS", "SOCHAUX", "1x2", "home", "2026-11-02T23:50:00Z"),
                bet("A", "B", "ml", "home", "2026-11-03T11:00:00Z", "TENNIS"),            # pas encore 3 h
                bet("A", "B", "ml", "home", "2026-11-02T10:00:00Z", "ICE_HOCKEY")]        # sport non géré
        self.assertEqual(CS.days_to_fetch(rows, NOW), {("FOOTBALL", "20261102"), ("FOOTBALL", "20261103")})


class PolymarketWide(unittest.TestCase):
    def test_women_youth_excluded(self):
        women = [{**e, "title": e["title"].replace("Beta SC", "Beta SC Women"),
                  "tags": [{"slug": "soccer", "label": "Soccer"}]} for e in GAMMA]
        wsl = [{**e, "seriesSlug": "wsl-2026"} for e in GAMMA]
        self.assertEqual(len(pm.build_reference(GAMMA)), 1)
        self.assertEqual(pm.build_reference(women), [])
        self.assertEqual(pm.build_reference(wsl), [])

    def test_non_soccer_tag_never_read_as_3way(self):
        basket = [{**e, "_tag": "basketball"} for e in GAMMA]
        self.assertEqual(pm.build_reference(basket), [])
        ml = {"title": "LePy vs. Helsingin NMKY", "slug": "bk-lepy", "startTime": "2026-11-02T15:00:00Z",
              "_tag": "basketball",
              "markets": [mkt("9", "", 0.55, 0.57, '["LePy", "Helsingin NMKY"]')]}
        g = pm.build_reference([ml])
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["sport"], "BASKETBALL")

    def test_fetch_window_falls_back_to_tags(self):
        calls = []

        def fake_get(path, timeout=30, pause=1.0):
            calls.append(path)
            if "tag_id=" in path:
                raise pm.SourceError("polymarket /events: URLError")
            return []
        with mock.patch.object(pm, "get", fake_get):
            ref, errors = pm.fetch(tags=["ligue-1", "nba"])
        self.assertEqual(ref, [])
        self.assertTrue(any("tag_slug=ligue-1" in c for c in calls))   # repli sur la liste de championnats
        self.assertEqual(len(errors), 2)

    def test_fetch_window_paginates_and_skips_soccer_tags(self):
        calls = []

        def fake_get(path, timeout=30, pause=1.0):
            calls.append(path)
            if "tag_id=100350" in path and "offset=0" in path:
                return [{"id": i} for i in range(100)]
            return []
        with mock.patch.object(pm, "get", fake_get):
            pm.fetch(tags=["ligue-1", "nba"])
        self.assertTrue(any("tag_id=100350" in c and "offset=100" in c for c in calls))
        self.assertFalse(any("tag_slug=ligue-1" in c for c in calls))  # foot déjà lu en entier
        self.assertTrue(any("tag_slug=nba" in c for c in calls))


if __name__ == "__main__":
    unittest.main()
