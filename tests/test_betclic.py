"""Betclic gRPC-web : trames synthétiques au FORMAT réel (champs repris des tests de cotes-value), aucune vraie cote."""
import unittest
from datetime import datetime, timezone
from unittest import mock

from autonome.sources import betclic as B

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def sel(name, odds, active=True):
    return B.f_bytes(10, name) + B.f_double(12, odds) + B.f_varint(14, 1 if active else 2)


def match(mid, home, away, start="2026-11-02T20:00:00Z", comp="Ligue 1", comp_id=4):
    return (B.f_varint(1, mid) + B.f_bytes(3, start)
            + B.f_bytes(8, B.f_varint(1, comp_id) + B.f_bytes(2, comp))
            + B.f_bytes(12, B.f_bytes(3, home)) + B.f_bytes(12, B.f_bytes(3, away)))


def liste(*ms):
    return B.frame(B.f_bytes(1, b"".join(B.f_bytes(3, m) for m in ms)))


def detail(*markets):
    env = b""
    for name, sels in markets:
        mk = B.f_bytes(2, name) + b"".join(B.f_bytes(16, s) for s in sels)
        env += B.f_bytes(3, mk)
    return B.frame(B.f_bytes(1, B.f_bytes(1, B.f_bytes(11, env))))


def mk(name, *pairs):
    return {"name": name, "selections": [{"name": n, "odds": o} for n, o in pairs]}


class Decode(unittest.TestCase):
    def test_list_and_first_frame_only(self):
        a, b = liste(match(7, "Lens", "Lille")), liste(match(8, "Nice", "Rennes"))
        self.assertEqual(B.first_frame([(a + b)[:9], (a + b)[9:]]), a)
        m = B.list_matches(a)[0]
        self.assertEqual((m["id"], m["home"], m["away"], m["competition"], m["competition_id"]),
                         (7, "Lens", "Lille", "Ligue 1", 4))

    def test_detail_drops_suspended_selection(self):
        fr = detail(("Résultat du match (t. rég)", [sel("Lens", 1.8), sel("Nul", 3.4), sel("Lille", 4.2, False),
                                                    sel("Lille", 4.5)]))
        self.assertEqual(B.map_markets(B.detail_markets(fr), "Lens", "Lille", "FOOTBALL"),
                         {"1x2": {"home": 1.8, "draw": 3.4, "away": 4.5}})

    def test_grouped_totals_without_field_16(self):
        item = B.f_bytes(1, sel("+ de 2,5", 1.9)) + B.f_bytes(1, sel("- de 2,5", 1.85))
        market = B.f_bytes(2, "Nombre total de buts (t. rég)") + B.f_bytes(10, B.f_bytes(1, item))
        fr = B.frame(B.f_bytes(1, B.f_bytes(1, B.f_bytes(11, B.f_bytes(3, market)))))
        self.assertEqual(B.map_markets(B.detail_markets(fr), "Lens", "Lille", "FOOTBALL"),
                         {"ou@2.5": {"over": 1.9, "under": 1.85}})


class Mapping(unittest.TestCase):
    def m(self, markets, sport="FOOTBALL", home="Lens", away="Lille"):
        return B.map_markets(markets, home, away, sport)

    def test_football_markets(self):
        got = self.m([
            mk("Double chance", ("Lens ou Nul", 1.2), ("Nul ou Lille", 1.9), ("Lens ou Lille", 1.3)),
            mk("Les 2 équipes marquent (t. rég)", ("Oui", 1.8), ("Non", 1.95)),
            mk("Total de buts - Lens (t. rég)", ("+ de 1,5", 2.1), ("- de 1,5", 1.7)),
            mk("Lille - Nombre total de buts", ("+ de 0,5", 1.4), ("- de 0,5", 2.8)),
            mk("Écart de buts (t. rég)", ("Lens gagne de 2 buts ou +", 3.2), ("Lille ne perd pas ou perd de 1 but ou -", 1.3),
               ("Lille gagne de 2 buts ou +", 7.0), ("Lens ne perd pas ou perd de 1 but ou -", 1.08)),
        ])
        self.assertEqual(got["dc"], {"1X": 1.2, "X2": 1.9, "12": 1.3})
        self.assertEqual(got["btts"], {"yes": 1.8, "no": 1.95})
        self.assertEqual(got["team_ou@home@1.5"], {"over": 2.1, "under": 1.7})
        self.assertEqual(got["team_ou@away@0.5"], {"over": 1.4, "under": 2.8})
        self.assertEqual(got["ah@home@-1.5"], {"fav": 3.2, "dog": 1.3})
        self.assertEqual(got["ah@away@-1.5"], {"fav": 7.0, "dog": 1.08})

    def test_refused_labels(self):
        got = self.m([
            mk("Les 2 équipes marquent ou + de 2,5 buts dans le match (t. rég)", ("Oui", 1.4), ("Non", 2.6)),
            mk("1ère mi-temps - Résultat", ("Lens", 2.5), ("Nul", 2.0), ("Lille", 4.0)),
            mk("Résultat du match (prolong. incluses)", ("Lens", 1.7), ("Nul", 3.6), ("Lille", 4.8)),
            mk("Nombre total de buts (t. rég)", ("+ de 2", 1.6), ("- de 2", 2.2)),         # ligne entière : remboursable
            mk("Total de buts - Lens II (t. rég)", ("+ de 1,5", 2.0), ("- de 1,5", 1.8)),  # autre équipe
            mk("Buteur", ("Lens", 3.0), ("Lille", 3.0)),
        ])
        self.assertEqual(got, {})

    def test_two_way_sports(self):
        self.assertEqual(self.m([mk("Vainqueur du match", ("Sinner J.", 1.3), ("Alcaraz C.", 3.4))], "TENNIS",
                                "Sinner J.", "Alcaraz C."), {"ml": {"home": 1.3, "away": 3.4}})
        # hockey : vainqueur sans prolongation mentionnée = temps réglementaire possible -> refusé
        self.assertEqual(self.m([mk("Vainqueur du match", ("A", 1.8), ("B", 2.0))], "ICE_HOCKEY", "A", "B"), {})
        self.assertEqual(self.m([mk("Vainqueur du match (prolong. & pen. inclus)", ("A", 1.8), ("B", 2.0))],
                                "ICE_HOCKEY", "A", "B"), {"ml": {"home": 1.8, "away": 2.0}})
        # basket : marchés secondaires non lus (unités, prolongations)
        self.assertEqual(self.m([mk("Nombre total de points", ("+ de 220,5", 1.9), ("- de 220,5", 1.9))],
                                "BASKETBALL", "A", "B"), {})


class Network(unittest.TestCase):
    def test_fetch_list_paginates_within_horizon_and_builds_link(self):
        pages = [liste(*[match(i, f"H{i}", f"A{i}", "2026-11-02T20:00:00Z") for i in range(40)]),
                 liste(match(99, "Late", "Game", "2026-11-05T20:00:00Z"))]
        calls = []

        def fake_post(method, payload, timeout=12, pause=0.4):
            calls.append(method)
            return pages.pop(0) if pages else liste()
        with mock.patch.object(B, "post", fake_post):
            evs, errors = B.fetch_list(NOW, 30, {"FOOTBALL": "football"})
        self.assertEqual(len(evs), 40)
        self.assertEqual(errors, [])
        self.assertEqual(evs[0]["url"], "https://www.betclic.fr/football-sfootball/ligue-1-c4/h0-a0-m0")

    def test_403_stops_source(self):
        def fake_post(method, payload, timeout=12, pause=0.4):
            raise B.SourceError("betclic X: HTTP 403")
        with mock.patch.object(B, "post", fake_post):
            evs, errors = B.fetch_list(NOW, 30)
        self.assertEqual((evs, len(errors)), ([], 1))   # pas d'autre sport tenté


if __name__ == "__main__":
    unittest.main()
