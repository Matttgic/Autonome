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
        self.assertEqual(set(res), {"1", "2", "3", "4", "5", "6"})    # le reporté reste candidat d'appariement
        self.assertFalse(res["4"]["is_final"])
        self.assertIsNone(LS.outcome(res["4"], "1x2"))
        self.assertEqual(res["1"]["commence"], "2026-11-02T19:45:00Z")
        self.assertEqual(res["2"]["regular"], (1, 1))
        self.assertEqual(LS.outcome(res["2"], "1x2"), "draw")      # 1N2 = 90 min, pas le score après prolongation
        self.assertEqual(LS.outcome(res["3"], "1x2"), "draw")
        self.assertEqual(res["5"]["homes"], ["Bayern Munich"])     # Nm et NmEn identiques : une seule variante
        self.assertEqual(res["5"]["aways"], ["Mainz", "Mainz 05"])

    def test_tennis_retirement_and_basket_overtime(self):
        t = {r["id"]: r for r in LS.parse(TENNIS, "TENNIS")}
        self.assertEqual([k for k, r in t.items() if r["is_final"]], ["10"])
        self.assertIsNone(LS.outcome(t["11"], "ml"))
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


class ReviewRegressions(unittest.TestCase):
    """Défauts trouvés par la revue adverse du 2026-11-02 (scénarios reproduits sur des formats réels)."""

    def test_women_match_never_settles_men_bet(self):
        # LiveScore : marqueur seulement dans NmEn, Nm sans marqueur ; match masculin reporté à la même heure
        d = {"Stages": [{"Snm": "Super League", "Cnm": "Angleterre", "Events": [
            ev("30", 20261101120000, "FT", "Arsenal WFC", "Aston Villa WFC", (1, 1), (1, 1),
               en=("Arsenal W", "Aston Villa W")),
            ev("31", 20261101120000, "Postp.", "Arsenal", "Aston Villa", (0, 0))]}]}
        rows = [bet("ARSENAL", "ASTON VILLA", "1x2", "home", "2026-11-01T12:00:00Z")]
        self.assertEqual(CS.settle(rows, LS.parse(d, "FOOTBALL"), NOW), 0)
        d["Stages"][0]["Events"].pop()                       # même sans le match masculin : jamais le match féminin
        self.assertEqual(CS.settle(rows, LS.parse(d, "FOOTBALL"), NOW), 0)

    def test_women_league_without_marker(self):
        d = {"Stages": [{"Snm": "Naisten Liiga", "Cnm": "Finlande", "Events": [
            ev("32", 20261101120000, "FT", "HJK", "KuPS", (2, 0), (2, 0))]}]}
        rows = [bet("HJK", "KUPS", "1x2", "home", "2026-11-01T12:00:00Z")]
        self.assertEqual(CS.settle(rows, LS.parse(d, "FOOTBALL"), NOW), 0)

    def test_postponed_namesake_blocks(self):
        d = {"Stages": [{"Snm": "L2", "Events": [
            ev("33", 20261101150000, "FT", "Paris FC", "Monaco", (3, 1), (3, 1)),
            ev("34", 20261101150000, "Postp.", "Paris FC B", "Monaco B", (0, 0))]}]}
        rows = [bet("PARIS FC", "MONACO", "1x2", "home", "2026-11-01T15:00:00Z")]
        self.assertEqual(CS.settle(rows, LS.parse(d, "FOOTBALL"), NOW), 1)   # réserve B : autre équipe
        d["Stages"][0]["Events"][1] = ev("34", 20261101150000, "Postp.", "Paris FC", "AS Monaco", (0, 0))
        rows = [bet("PARIS FC", "MONACO", "1x2", "home", "2026-11-01T15:00:00Z")]
        self.assertEqual(CS.settle(rows, LS.parse(d, "FOOTBALL"), NOW), 0)   # deux candidats : à la main

    def test_singles_bet_never_settled_on_doubles(self):
        e = ev("35", 20261101100000, "FT", "Lucas Miedler", "Learner Tien", (2, 0))
        e["T1"].append({"Nm": "Neil Oberleitner"})
        e["T2"].append({"Nm": "Ryan Seggerman"})
        rows = [bet("Miedler L.", "Tien L.", "ml", "home", "2026-11-01T10:00:00Z", "TENNIS")]
        self.assertEqual(CS.settle(rows, LS.parse({"Stages": [{"Events": [e]}]}, "TENNIS"), NOW), 0)

    def test_provisional_and_contradicted_scores(self):
        e = ev("36", 20261101150000, "OT", "LePy", "Helsingin NMKY", (80, 78), (70, 70))
        e["Epr"] = 1                                          # prolongation en cours
        self.assertIsNone(LS.outcome(LS.parse({"Stages": [{"Events": [e]}]}, "BASKETBALL")[0], "ml"))
        t = ev("37", 20261101100000, "FT", "A Un", "B Deux", (1, 0))
        t["Ewt"] = 2                                          # vainqueur déclaré contraire au score
        self.assertIsNone(LS.outcome(LS.parse({"Stages": [{"Events": [t]}]}, "TENNIS")[0], "ml"))
        t["Ewt"] = 1
        self.assertEqual(LS.outcome(LS.parse({"Stages": [{"Events": [t]}]}, "TENNIS")[0], "ml"), "home")

    def test_http_code_in_error(self):
        import urllib.error

        def boom(*a, **k):
            raise urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
        with mock.patch("urllib.request.urlopen", boom), mock.patch.object(LS.time, "sleep", lambda s: None):
            with self.assertRaises(LS.SourceError) as cm:
                LS.fetch("FOOTBALL", "20261101")
        self.assertIn("HTTP 403", str(cm.exception))

    def test_markers_extended(self):
        from autonome.match import markers, sim
        self.assertTrue(markers("Jong Ajax Amsterdam"))
        self.assertTrue(markers("Juventus Next Gen"))
        self.assertTrue(markers("Girona FC B"))
        self.assertTrue(markers("France U-20"))
        self.assertTrue(markers("Arsenal WFC"))
        self.assertEqual(sim("JUVENTUS", "Juventus Next Gen"), 0.0)
        self.assertFalse(markers("Boca Juniors") - {"juniors"})  # « Juniors » : déjà marqué avant, inchangé


class PolymarketWide(unittest.TestCase):
    def test_women_youth_excluded(self):
        women = [{**e, "title": e["title"].replace("Beta SC", "Beta SC Women"),
                  "tags": [{"slug": "soccer", "label": "Soccer"}]} for e in GAMMA]
        wsl = [{**e, "seriesSlug": "wsl-2026"} for e in GAMMA]
        self.assertEqual(len(pm.build_reference(GAMMA)), 1)
        self.assertEqual(pm.build_reference(women), [])
        self.assertEqual(pm.build_reference(wsl), [])
        for slug in ("cwbb-2026", "bkfibaw-2026", "wnba-2026"):
            self.assertEqual(pm.build_reference([{**e, "seriesSlug": slug} for e in GAMMA]), [])
        self.assertEqual(len(pm.build_reference([{**e, "title": e["title"].replace("FC Alpha", "Wolves")}
                                                  for e in GAMMA])), 1)   # « Wolves » n'est pas « W »

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
