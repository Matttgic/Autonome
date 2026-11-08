"""Tests sans réseau : adaptateur football-data, backtest.

Les lignes CSV ci-dessous reprennent le FORMAT des fichiers football-data (en-têtes réels) avec des valeurs
fictives choisies pour un calcul à la main ; ce ne sont pas des cotes réelles.
"""
import unittest
from datetime import datetime, timezone
from math import log

from autonome import backtest as B, devig
from autonome.sources import footballdata as FD

HEADER = ("Div,Date,Time,HomeTeam,AwayTeam,PSH,PSD,PSA,BFEH,BFED,BFEA,AvgH,AvgD,AvgA,P>2.5,P<2.5,BFE>2.5,BFE<2.5,"
          "PSCH,PSCD,PSCA,B365AHH,B365AHA,FTR,FTHG,FTAG")
ROW1 = "F1,31/10/2026,15:00,Lyon,Nantes,2.0,3.5,4.0,2.04,3.6,4.1,1.95,3.4,3.8,1.9,1.9,1.95,1.95,2.1,3.4,3.9,1.9,1.9,H,2,1"
ROW2 = "E0,30/08/2026,15:00,Arsenal,Chelsea,,,,1.5,4.0,6.0,1.45,4.2,6.5,,,1.6,2.2,,,,,,D,0,0"
CSV = "﻿" + HEADER + "\n" + ROW1 + "\n" + ROW2 + "\n,,,,\n"
NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class FootballData(unittest.TestCase):
    def setUp(self):
        self.rows = FD.read_csv(CSV)
        self.header = list(self.rows[0])

    def test_read_skips_empty_and_bom(self):
        self.assertEqual(len(self.rows), 2)
        self.assertEqual(self.header[0], "Div")

    def test_prefixes_exclude_closing_and_ah(self):
        self.assertEqual(FD.prefixes(self.header), ["Avg", "BFE", "PS"])  # PSC = clôture, B365AH = handicap

    def test_odds_parsing(self):
        r = self.rows[0]
        self.assertEqual(FD.odds_1x2(r, "PS"), [2.0, 3.5, 4.0])
        self.assertEqual(FD.odds_1x2(r, "PS", closing=True), [2.1, 3.4, 3.9])
        self.assertEqual(FD.odds_ou25(r, "PS"), [1.9, 1.9])          # colonnes P>2.5 / P<2.5
        self.assertIsNone(FD.odds_1x2(self.rows[1], "PS"))           # absent = None, jamais imputé
        self.assertEqual(FD.result_index(r), 0)

    def test_kickoff_uk_to_utc(self):
        # 31/10/2026 : heure d'hiver UK (GMT, changement le 25/10) -> 15:00Z ; 30/08 : BST (UTC+1) -> 14:00Z
        self.assertEqual(FD.kickoff_utc("31/10/2026", "15:00").isoformat(), "2026-10-31T15:00:00+00:00")
        self.assertEqual(FD.kickoff_utc("30/08/26", "15:00").isoformat(), "2026-08-30T14:00:00+00:00")
        self.assertIsNone(FD.kickoff_utc("30/08/26", ""))

    def test_to_event_shape(self):
        e = FD.to_event(self.rows[0], self.header)
        self.assertEqual(e["commence"], "2026-10-31T15:00:00Z")
        self.assertEqual(e["league"], "France Ligue 1")
        self.assertEqual(e["books"]["pinnacle"]["h2h"], {"Lyon": 2.0, "Draw": 3.5, "Nantes": 4.0})
        self.assertEqual(e["books"]["pinnacle"]["totals"], {"2.5": {"Over": 1.9, "Under": 1.9}})
        self.assertIn("betfair_ex_eu", e["books"])
        self.assertIn("market_avg", e["books"])


class Backtest(unittest.TestCase):
    def test_logloss_brier_hand(self):
        self.assertAlmostEqual(B.logloss([[0.5, 0.3, 0.2]], [0]), -log(0.5))
        self.assertAlmostEqual(B.brier([[0.5, 0.3, 0.2]], [0]), 0.25 + 0.09 + 0.04)

    def test_fast_devig_matches_reference(self):
        for odds in ([2.0, 3.5, 4.0], [1.3, 4.5, 9.0], [1.91, 1.91], [2.04, 3.6, 4.1]):
            for m in devig.METHODS:
                for a, b in zip(B.fair(odds, m), devig.METHODS[m](odds)):
                    self.assertAlmostEqual(a, b, places=12)

    def test_calibration_hand(self):
        recs = [{"res": 0, "odds": {"X": [2.0, 2.0]}}, {"res": 1, "odds": {"X": [2.0, 2.0]}}]
        cal = B.calibration(recs, "X", "multiplicative", [0.0, 0.5, 1.0])
        self.assertEqual(cal, [{"lo": 0.5, "hi": 1.0, "n": 4, "mean_p": 0.5, "freq": 0.5, "se": 0.25}])

    def test_simulate_hand(self):
        # réf 2.0/2.0 -> p = 0.5 ; Bet 2.2/1.8 -> EV issue 0 = +10 %, issue 1 = -10 % ; clôture 2.0/2.0 -> CLV +10 %
        mk = lambda res, ref=(2.0, 2.0): {"res": res, "odds": {"R": list(ref), "K": [2.2, 1.8], "C": [2.0, 2.0]}}
        out = B.simulate([mk(0), mk(1), mk(0, (1.8, 1.8))], "R", "K", "C", 0.05, max_ref_overround=0.08)
        self.assertEqual(out["n"], 2)                      # 3e match : marge réf 11,1 % > 8 % -> exclu
        self.assertAlmostEqual(out["ev_expected"], 0.10)
        self.assertAlmostEqual(out["clv_ev"]["mean"], 0.10)
        self.assertAlmostEqual(out["roi"]["mean"], (1.2 - 1.0) / 2)  # un gagné à 2.2, un perdu
        self.assertEqual(B.simulate([mk(0)], "R", "K", "C", 0.15)["n"], 0)

    def test_drift_and_missing(self):
        recs = [{"res": 0, "odds": {"A": [2.0, 2.0], "B": [1.8, 2.25]}}, {"res": None, "odds": {}}]
        # B : q = .5556/.4444 (somme 1) -> |.5556-.5| = |.4444-.5| = .0556
        self.assertAlmostEqual(B.drift(recs, "A", "B", "multiplicative")["mean"], 1 / 1.8 - 0.5, places=9)
        self.assertEqual(len(B.usable(recs, "A")), 1)


if __name__ == "__main__":
    unittest.main()
