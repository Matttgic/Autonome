"""Stratégies suivies en paris FICTIFS (aucune alerte), pour mesurer, pas pour parier.

Reprises d'un tableau vu sur Twitter (02/11/2026), règles appliquées à l'identique sur les cotes ANJ de coteur.com :
- « Valeur 4 % » : marge retirée chez chaque bookmaker (Shin), probabilité consensus des AUTRES bookmakers, pari si
  écart ≥ 4 % et cote entre 1,50 et 4,50 ; mise Kelly ¼ plafonnée à 2 % de la bankroll (plancher 0,25 %).
- « Témoin » : groupe de contrôle. Un match éligible sur trois (tirage à graine fixe = empreinte du match), une issue et
  un bookmaker tirés de même parmi les cotes de 1,50 à 4,50 ; mise fixe 1 %. Si une stratégie ne bat pas le Témoin,
  elle ne vaut pas mieux que le hasard.
Bankroll fictive 1 000 €. Un pari par match et par stratégie (première détection). Règlement et clôture : ceux du
consensus (LiveScore, consensus.KINDS). Fichier : paper.jsonl sur la branche data.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from . import consensus as CS
from .live import book_age_limit

FILE = "paper.jsonl"
BANKROLL = 1000.0
VALEUR = {"min_ev": 0.04, "max_ev": 0.40, "min_odds": 1.50, "max_odds": 4.50}
NAMES = {"paper-valeur4": "Valeur 4 % (règle Twitter)", "paper-temoin": "Témoin (hasard, 1 match sur 3)"}


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def _kelly(p: float, odds: float) -> float:
    f = 0.25 * (p * odds - 1) / (odds - 1)
    return round(BANKROLL * min(0.02, max(0.0025, f)), 2) if f > 0 else 0.0


def picks(matches: list[dict], now: datetime, done: set[tuple[str, str]], max_age_min: float = 60) -> list[dict]:
    """Nouveaux paris fictifs des deux stratégies. done = {(stratégie, event_id)} déjà pris."""
    out = []
    for m in matches:
        mins = (datetime.fromisoformat(m["commence"].replace("Z", "+00:00")) - now).total_seconds() / 60
        age = m.get("snapshot_age_min")
        if age is None or age > book_age_limit(mins, max_age_min):
            continue  # cotes trop vieilles : rien de pris (même règle que les vrais paris)
        cands = [c for c in CS.evaluate(m, now, BANKROLL, {"min_ev": -9, "max_ev": 9, "max_dispersion": 9,
                                                              "diagnostic": True})
                 if VALEUR["min_odds"] <= c["odds"] <= VALEUR["max_odds"]]
        if not cands:
            continue
        ev_id = cands[0]["event_id"]
        if ("paper-valeur4", ev_id) not in done:
            val = [c for c in cands if VALEUR["min_ev"] <= c["ev"] <= VALEUR["max_ev"]]
            if val:
                c = max(val, key=lambda c: c["ev"])
                st = _kelly(c["p_fair"], c["odds"])
                if st > 0:
                    out.append({**c, "bet_id": "paper-valeur4|" + c["bet_id"], "ref_kind": "paper-valeur4",
                                "strategy": "paper-valeur4", "stake": st})
        if ("paper-temoin", ev_id) not in done and _h("temoin", ev_id) % 3 == 0:
            c = sorted(cands, key=lambda c: (c["selection"], c["book"]))[_h("temoin-issue", ev_id) % len(cands)]
            out.append({**c, "bet_id": "paper-temoin|" + c["bet_id"], "ref_kind": "paper-temoin",
                        "strategy": "paper-temoin", "stake": round(BANKROLL * 0.01, 2)})
    return out


def summary(rows: list[dict]) -> list[dict]:
    """Bilan par stratégie : paris, réglés, ROI (sur les mises réglées), réussite, CLV moyenne, bankroll fictive."""
    out = []
    for k, name in NAMES.items():
        rs = [r for r in rows if r.get("strategy") == k]
        done = [r for r in rs if r.get("status") == "settled" and r.get("result")]
        pnl = 0.0
        staked = 0.0
        wins = 0
        for r in done:
            won = r["result"].get("won")
            if won is None:
                continue  # remboursé
            staked += r["stake"]
            pnl += r["stake"] * (r["odds"] - 1) if won else -r["stake"]
            wins += bool(won)
        clvs = [r["close"]["clv_odds"] for r in rs if r.get("close")]
        out.append({"strategy": k, "name": name, "n": len(rs), "open": sum(r.get("status") == "open" for r in rs),
                    "settled": len(done), "roi": pnl / staked if staked else None,
                    "hit": wins / len([r for r in done if r["result"].get("won") is not None]) if staked else None,
                    "clv": sum(clvs) / len(clvs) if clvs else None, "n_clv": len(clvs),
                    "bankroll": BANKROLL + pnl})
    return out
