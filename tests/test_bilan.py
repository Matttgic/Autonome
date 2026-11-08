"""Bilan du 08/11/2026 : références douteuses écartées, historique et santé par jour pour la page mobile.
Cas recalculés à la main (formats repris de bets.jsonl, valeurs synthétiques)."""
import tempfile
import unittest
from datetime import datetime, timezone

from autonome import live, site, store, tracker


def bet(**k):
    b = {"bet_id": k.get("id", "b"), "event_id": "e", "group": "ml", "selection": "A", "home": "A", "away": "B",
         "label": "Vainqueur : A", "book": "pmu_fr", "sport": "Tennis", "ref_kind": "polymarket", "odds": 1.79,
         "p_fair": 0.595, "p_cons": 0.59, "fair_odds": 1 / 0.595, "ev": 0.595 * 1.79 - 1, "ev_cons": 0.59 * 1.79 - 1,
         "stake": 2.0, "status": "open", "result": None, "found_at": "2026-11-08T03:41:00+00:00",
         "commence": "2026-11-08T21:30:00Z", "legs": []}
    b.update(k)
    return b


class Suspect(unittest.TestCase):
    def test_frozen_tennis_market(self):
        # Berrettini 5.0 contre une référence Polymarket figée à 0,495 : le book donne 20 % -> figé, pas une value
        self.assertEqual(tracker.suspect(bet(odds=5.0, p_fair=0.495, ev=1.475)), "marche_fige_50_50")
        # même référence, book à 1,95 (51 %) : vrai match équilibré, pas écarté pour ça (EV -3,5 %)
        self.assertIsNone(tracker.suspect(bet(odds=1.95, p_fair=0.495, ev=0.495 * 1.95 - 1)))
        # 1N2 à 0,50 : la règle « figé » ne vise que les vainqueurs à 2 issues
        self.assertIsNone(tracker.suspect(bet(group="1x2", odds=2.2, p_fair=0.5, ev=0.10)))

    def test_ev_cap(self):
        self.assertEqual(tracker.suspect(bet(group="1x2", odds=2.7, p_fair=0.96, ev=1.59)), "ev_trop_grande")
        self.assertIsNone(tracker.suspect(bet(group="1x2", odds=3.07, p_fair=0.3731, ev=0.1455)))
        self.assertIsNone(tracker.suspect(bet(ref_kind="consensus-anj", ev=0.35)))  # consensus : son propre plafond
        self.assertIsNone(tracker.suspect(bet(ref_kind="polymarket-modele", group="boost", ev=0.45)))  # boosts : 50 %
        self.assertIsNone(tracker.suspect(bet(ev=None, p_fair=None)))  # vieille ligne incomplète : pas de crash
        # figé à 0,485 contre un book à 2,40 (42 %) : écarté aussi (revue du 08/11)
        self.assertEqual(tracker.suspect(bet(odds=2.4, p_fair=0.485, ev=0.164)), "marche_fige_50_50")

    def test_gate_rejects_and_stats_exclude(self):
        good = {**bet(ev=0.05), "book_age_min": None, "minutes_to_start": 600, "ref_sport": "TENNIS"}
        bad = {**good, "odds": 4.5, "p_fair": 0.495, "ev": 1.2275, "event_id": "x"}
        measured = [{**good, "event_id": f"m{i}", "ev": -0.05} for i in range(3)]
        kept, why, detail = live.gate([good, bad], measured)
        self.assertEqual([k["event_id"] for k in kept], ["e"])
        self.assertEqual(why["marche_fige_50_50"], 1)
        with tempfile.TemporaryDirectory() as d:
            won = {"won": True, "payout": 1.0}
            store.write_all(d, tracker.BETS, [
                bet(id="ok", status="settled", result=won, odds=1.48, p_fair=0.72, ev=0.0656,
                    close={"minutes_to_start": 2, "clv_odds": 0.1766, "p_fair": 0.795}),
                bet(id="ko", status="settled", result={"won": None, "payout": 0.5}, odds=3.7, p_fair=0.495, ev=0.8315,
                    close={"minutes_to_start": 0, "clv_odds": 0.8315, "p_fair": 0.495})])
            st = tracker.stats(d)
            self.assertEqual((st["bets_total"], st["bets_suspect"]), (1, 1))
            self.assertAlmostEqual(st["clv"]["mean"], 0.1766)  # le pari douteux (+83 %) ne gonfle plus la CLV
            self.assertAlmostEqual(st["roi"]["pnl"], 2 * 0.48)


class Page(unittest.TestCase):
    def test_history_hand_computed(self):
        r = bet(status="settled", result={"won": True}, odds=1.77, p_fair=0.5862, stake=1.0,
                close={"minutes_to_start": 2, "clv_odds": 1.77 * 0.695 - 1, "p_fair": 0.695})
        h = site.history([r], 100.0)[0]
        self.assertAlmostEqual(h["kelly"], (0.59 * 1.77 - 1) / 0.77, places=4)  # la mise part de p prudente = 0,59
        self.assertEqual(site.history([bet(status="settled", result=None)], 100.0)[0]["etat"], "inconnu")
        self.assertEqual((h["etat"], h["gain"]), ("gagné", 0.77))
        self.assertAlmostEqual(h["clv"], 0.23015, places=3)  # 1,77 × 0,695 − 1
        far = site.history([bet(close={"minutes_to_start": 300, "clv_odds": 0.1})], 100.0)[0]
        self.assertIsNone(far["clv"])  # clôture trop lointaine : pas une CLV
        lost = site.history([bet(status="settled", result={"won": False})], 100.0)[0]
        self.assertEqual(lost["gain"], -2.0)
        void = site.history([bet(status="settled", result={"won": None})], 100.0)[0]
        self.assertEqual((void["etat"], void["gain"]), ("remboursé", 0.0))

    def test_pourquoi_plain_french(self):
        # Atlanta : p 0,72, Betclic 1,48 (EV +6,56 %), gagné +0,96 €, clôture p 0,795 -> cote juste 1,26
        r = bet(home="Atlanta", away="Indiana", label="Vainqueur : Atlanta", book="betclic_fr", odds=1.48, p_fair=0.72,
                ev=0.0656, ev_cons=0.051, status="settled", result={"won": True},
                close={"minutes_to_start": 2, "clv_odds": 0.1766, "p_fair": 0.795})
        self.assertEqual(site.pourquoi(r),
                         "Sur Polymarket, les parieurs donnent 72,0 % de chances qu'Atlanta gagne : la cote juste est donc 1,39. "
                         "Betclic paie 1,48, plus que ce que ça vaut : sur le long terme, ce genre de pari rapporte +6,6 % "
                         "de la mise en moyenne. Gagné, +0,96 €. Au coup d'envoi, la cote juste était de 1,26 : les 1,48 pris "
                         "valaient mieux que le marché final, bon signe.")
        nul = site.pourquoi(bet(group="1x2", label="1X2 : Nul", odds=3.4, p_fair=0.31, ev=0.054, ev_cons=0.03))
        self.assertIn("31,0 % de chances que le match se termine sur un nul", nul)
        self.assertIn("Mise conseillée 2,00 €", nul)
        fige = site.pourquoi(bet(odds=5.0, p_fair=0.495, ev=1.475))
        self.assertIn("figé à 50/50", fige)
        self.assertEqual(fige.count(". "), 1)  # 2 phrases, sans « rapporte +147 % »
        self.assertIsNone(site.pourquoi(bet(p_fair=None)))

    def test_daily_gaps(self):
        runs = [{"at": "2026-11-04T06:00:00+00:00"}, {"at": "2026-11-04T06:10:00+00:00"},
                {"at": "2026-11-04T10:30:00+00:00"}, {"at": "2026-11-05T00:05:00+00:00"}, {"at": "bad"}]
        now = datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc)
        d = site.daily(runs, [{"found_at": "2026-11-04T07:00:00+00:00"}], now)
        self.assertEqual(d[0], {"jour": "2026-11-04", "passages": 3, "trou_max_min": 260, "alertes": 1})
        # 10:30 -> 00:05 = 815 min (fin le 05) ; puis 55 min sans passage jusqu'à maintenant
        self.assertEqual(d[1], {"jour": "2026-11-05", "passages": 1, "trou_max_min": 815, "alertes": 0})
        # horodatage sans fuseau (lu comme UTC) et journée entière sans passage
        d = site.daily([{"at": "2026-11-02T10:00:00"}, {"at": "2026-11-04T10:00:00Z"}], [], now)
        self.assertEqual([(x["jour"], x["passages"]) for x in d],
                         [("2026-11-02", 1), ("2026-11-03", 0), ("2026-11-04", 1), ("2026-11-05", 0)])


if __name__ == "__main__":
    unittest.main()
