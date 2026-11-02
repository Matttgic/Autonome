#!/usr/bin/env python3
"""Backtest honnête sur les archives publiques football-data.co.uk (22 divisions, 2012/13 -> saison en cours).

Usage : python tools/backtest_fd.py [--cache .cache/footballdata] [--offline]
Télécharge 1 archive zip par saison (1 requête / 4 s, User-Agent honnête) si absente du cache, puis imprime
un rapport Markdown (chiffres réels) sur la sortie standard. Rien n'est inventé : une cote absente exclut le match
de l'analyse concernée, et chaque tableau indique son effectif n.
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autonome import backtest as B  # noqa: E402
from autonome.devig import METHODS  # noqa: E402
from autonome.sources import footballdata as FD  # noqa: E402

SEASONS = ["1213", "1314", "1415", "1516", "1617", "1718", "1819", "1920", "2021", "2122", "2223", "2324",
           "2425", "2526", "2627"]
BOOKS_1X2 = ["PS", "BFE", "B365", "BW", "IW", "WH", "VC", "1XB", "BV", "BFD", "BMGM", "CL", "LB", "Max", "Avg"]


def load(cache: Path, offline: bool) -> tuple[list[dict], list[dict]]:
    cache.mkdir(parents=True, exist_ok=True)
    x12, ou = [], []
    for s in SEASONS:
        p = cache / f"{s}.zip"
        if not p.exists():
            if offline:
                print(f"[absent] {p}", file=sys.stderr)
                continue
            body, _ = FD.fetch(FD.SEASON_ZIP_URL.format(season=s))
            p.write_bytes(body)
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                rows = FD.read_csv(z.read(name))
                for r in rows:
                    res = FD.result_index(r)
                    base = {"season": s, "div": name.rsplit(".", 1)[0], "res": res}
                    o12, oou = {}, {}
                    for b in BOOKS_1X2:
                        for c in (False, True):
                            k = b + ("C" if c else "")
                            v = FD.odds_1x2(r, b, c)
                            if v:
                                o12[k] = v
                            v = FD.odds_ou25(r, b, c)
                            if v:
                                oou[k] = v
                    x12.append({**base, "odds": o12})
                    try:
                        tg = float(r["FTHG"]) + float(r["FTAG"])
                        ou_res = 0 if tg > 2.5 else 1
                    except (KeyError, TypeError, ValueError):
                        ou_res = None
                    ou.append({**base, "res": ou_res, "odds": oou})
    return x12, ou


def sel(recs, seasons):
    return [r for r in recs if r["season"] in seasons]


def pct(x, d=2):
    return "n/a" if x is None else f"{x * 100:+.{d}f} %"


def ci(m):
    if m.get("ci95") is None:
        return "n/a"
    return f"[{m['ci95'][0] * 100:+.2f} ; {m['ci95'][1] * 100:+.2f}]"


def sim_row(label, res):
    return (f"| {label} | {res['n']} / {res['matches']} | {pct(res['ev_expected'])} | {pct(res['clv_ev']['mean'])} "
            f"{ci(res['clv_ev'])} | {pct(res['roi']['mean'])} {ci(res['roi'])} | "
            f"{res['avg_odds']:.2f} |" if res["n"] else f"| {label} | 0 / {res['matches']} | — | — | — | — |")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=".cache/footballdata")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    x12, ou = load(Path(a.cache), a.offline)
    out = []
    w = out.append
    TR_DV, TE_DV = SEASONS[:7], SEASONS[7:14]          # dé-vig : 2012/13-2018/19 vs 2019/20-2025/26
    TR_ST, TE_ST = ["1920", "2021", "2122"], ["2223", "2324", "2425", "2526"]
    RECENT = ["2425", "2526"]

    w("### 1. Couverture (matchs avec cotes non vides)\n")
    w("| Saison | matchs | PS avant | PS clôture | BFE avant | BFE clôture | B365 clôture |")
    w("|---|---|---|---|---|---|---|")
    for s in SEASONS:
        rs = sel(x12, [s])
        c = lambda k: sum(1 for r in rs if r["odds"].get(k))  # noqa: E731
        w(f"| {s[:2]}/{s[2:]} | {len(rs)} | {c('PS')} | {c('PSC')} | {c('BFE')} | {c('BFEC')} | {c('B365C')} |")

    w("\n### 2. Méthodes de dé-vig (Pinnacle), séparation temporelle\n")
    w("Choix sur 2012/13-2018/19, vérification sur 2019/20-2025/26 (log-loss : plus bas = mieux).\n")
    w("| Source | Méthode | log-loss train (n) | log-loss test (n) | Brier test |")
    w("|---|---|---|---|---|")
    best = {}
    for key in ("PSC", "PS"):
        scores = {}
        for m in METHODS:
            tr = B.score_source(sel(x12, TR_DV), key, m)
            te = B.score_source(sel(x12, TE_DV), key, m)
            scores[m] = tr["logloss"]
            w(f"| {key} | {m} | {tr['logloss']:.5f} ({tr['n']}) | {te['logloss']:.5f} ({te['n']}) | {te['brier']:.5f} |")
        best[key] = min(scores, key=scores.get)
    bm = best["PSC"]
    w(f"\nMéthode retenue (meilleure sur train, PS clôture) : **{bm}**.\n")

    w("### 3. Qualité comparée des références (échantillon commun 2024/25-2025/26, méthode " + bm + ")\n")
    keys = ["PSC", "PS", "BFEC", "BFE", "B365C", "B365", "AvgC", "Avg"]
    common = B.usable(sel(x12, RECENT), *keys)
    w(f"Échantillon commun : n = {len(common)} matchs.\n")
    w("| Source | log-loss | Brier | marge moyenne |")
    w("|---|---|---|---|")
    for k in keys:
        s = B.score_source(common, k, bm)
        w(f"| {k} | {s['logloss']:.5f} | {s['brier']:.5f} | {pct(B.margin(common, k)['mean'])} |")
    w("\nDérive moyenne |p_clôture − p_avant| (toutes issues) : PS "
      f"{pct(B.drift(common, 'PS', 'PSC', bm)['mean'])}, BFE {pct(B.drift(common, 'BFE', 'BFEC', bm)['mean'])}, "
      f"BFE avant vs PS clôture {pct(B.drift(common, 'BFE', 'PSC', bm)['mean'])}.\n")

    w("### 4. Calibration de Pinnacle clôture dé-viguée (test 2019/20-2025/26)\n")
    w("| tranche p | n issues | p moyenne | fréquence observée ± 1,96·se |")
    w("|---|---|---|---|")
    for b in B.calibration(sel(x12, TE_DV), "PSC", bm, [i / 10 for i in range(11)]):
        w(f"| {b['lo']:.1f}-{b['hi']:.1f} | {b['n']} | {b['mean_p']:.4f} | {b['freq']:.4f} ± {1.96 * b['se']:.4f} |")

    w("\n### 5. Value « avant clôture » chez des books grand public, mesurée contre la clôture Pinnacle\n")
    w("Mise plate 1 u, 1 pari max par match (meilleure EV), cotes 1,40-6,00, EV = pire des 3 dé-vig (comme le moteur). "
      "Seuil choisi sur 2019/20-2021/22 (meilleure CLV-EV avec n ≥ 300), résultat sur 2022/23-2025/26. "
      "CLV-EV = cote prise × p juste de clôture PS − 1 (proxy de l'EV réelle) ; ROI = résultat réel.\n")
    grid = [0.0, 0.02, 0.03, 0.05, 0.08]
    plans = [("PS", "B365", "PSC", "1X2 réf PS avant → Bet365 avant"),
             ("PS", "Avg", "PSC", "1X2 réf PS avant → cote moyenne du marché"),
             ("PS", "Max", "PSC", "1X2 réf PS avant → meilleure cote du marché (borne haute, irréaliste)"),
             ("PS", "B365C", "PSC", "1X2 réf PS avant → Bet365 à la clôture (pari tardif, référence périmée)"),
             ("PSC", "B365C", "PSC", "1X2 réf PS clôture → Bet365 clôture (comparaison simultanée à la clôture)")]
    for fk, bk, ck, label in plans:
        w(f"\n**{label}**\n")
        w("| seuil | période | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |")
        w("|---|---|---|---|---|---|---|")
        kw = dict(min_odds=1.4, max_odds=6.0, max_ref_overround=0.08)
        trs = {t: B.simulate(sel(x12, TR_ST), fk, bk, ck, t, **kw) for t in grid}
        ok = [t for t in grid if trs[t]["n"] >= 300]
        tbest = max(ok, key=lambda t: trs[t]["clv_ev"]["mean"]) if ok else None
        for t in grid:
            te = B.simulate(sel(x12, TE_ST), fk, bk, ck, t, **kw)
            mark = " ← retenu" if t == tbest else ""
            w(sim_row(f"{t:.0%}{mark} | train", trs[t]))
            w(sim_row(f"{t:.0%}{mark} | **test**", te))

    w("\n### 6. Configuration « live » réelle 2026/27 : référence Betfair Exchange (Pinnacle absent)\n")
    w("Réf = BFE avant (relevé ven./mar.), jugé contre PS clôture. Les cotes BFE « avant » sont souvent illiquides "
      "(marge médiane 2 %, p95 17-52 % selon la saison) : filtre sur la marge de la référence. "
      "Filtre et seuil choisis sur 2024/25, vérifiés sur 2025/26 (seul recouvrement BFE + PS).\n")
    for bk, label in (("B365", "pari Bet365 au moment du relevé"), ("B365C", "pari Bet365 à la clôture (joué plus tard)")):
        w(f"\n**{label}**\n")
        w("| marge réf max | seuil | période | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |")
        w("|---|---|---|---|---|---|---|---|")
        for mo in (0.015, 0.03, 0.08):
            for t in (0.0, 0.02, 0.03, 0.05):
                for per, ss in (("train", ["2425"]), ("**test**", ["2526"])):
                    r = B.simulate(sel(x12, ss), "BFE", bk, "PSC", t, min_odds=1.4, max_odds=6.0, max_ref_overround=mo)
                    w(sim_row(f"{mo:.1%} | {t:.0%} | {per}", r))
    liq = [r for r in common if B.overround(r["odds"]["BFE"]) <= 0.015]
    w(f"\nSous-échantillon liquide (marge BFE avant ≤ 1,5 %, n = {len(liq)}) : log-loss PS avant "
      f"{B.score_source(liq, 'PS', bm)['logloss']:.5f}, BFE avant {B.score_source(liq, 'BFE', bm)['logloss']:.5f}, "
      f"PS clôture {B.score_source(liq, 'PSC', bm)['logloss']:.5f}.\n")

    w("\n### 7. +/-2,5 buts : réf PS avant → Bet365 avant, jugé contre PS clôture (2019/20-2025/26)\n")
    w("| seuil | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |")
    w("|---|---|---|---|---|---|")
    for t in grid:
        w(sim_row(f"{t:.0%}", B.simulate(sel(ou, TE_DV), "PS", "B365", "PSC", t, min_odds=1.4, max_odds=6.0,
                                          max_ref_overround=0.08)))
    print("\n".join(out))


if __name__ == "__main__":
    main()
