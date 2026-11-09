"""Suivi : enregistrement des paris, statistiques (CLV, ROI) et garde-fou « référence suspecte »."""
from __future__ import annotations

from datetime import datetime, timezone

from . import store, value as V

BETS = "bets.jsonl"          # un pari recommandé par ligne (mis à jour sur place)
CLOSE_MAX_MIN = 90          # au-delà, la dernière observation n'est pas une clôture
A_REGLER_H = 48             # pari encore ouvert 48 h après le début : le règlement automatique a échoué


def record_bets(root, new_bets: list[dict]) -> None:
    rows = store.read(root, BETS)
    have = {r["bet_id"] for r in rows}
    for b in new_bets:
        if b["bet_id"] not in have:
            rows.append({**b, "status": "open", "close": None, "result": None})
    store.write_all(root, BETS, rows)


# Référence suspecte (bilan du 08/11/2026) : les 6 alertes à EV > 30 % étaient des erreurs de référence — 5 matchs de
# tennis dont le marché Polymarket était figé à 0,49/0,50 (forfait ou annulation probable : remboursé 50/50) et un
# marché « nul » à 96 %. Ces paris ne sont plus proposés (live.gate) et sont exclus de la CLV et de l'EV attendue.
SUSPECT = {"max_ev_alert": 0.30, "fige_band": 0.016, "fige_book_p": 0.45}


def suspect(x: dict, cfg: dict | None = None) -> str | None:
    """Raison pour laquelle la référence d'un pari/candidat est douteuse, sinon None."""
    c = {**SUSPECT, **(cfg or {})}
    if x.get("ref_kind", "polymarket") != "polymarket":  # consensus et boosts : leurs propres plafonds (40 %, 50 %)
        return None
    p, odds = x.get("p_fair"), x.get("odds") or 0
    if (str(x.get("group", "")).split("@")[0] == "ml" and p is not None and odds > 1
            and abs(p - 0.5) <= c["fige_band"] and 1 / odds < c["fige_book_p"]):
        return "marche_fige_50_50"
    if (x.get("ev") or 0) > c["max_ev_alert"]:
        return "ev_trop_grande"
    return None


def a_regler(r: dict, now: datetime) -> bool:
    """Pari ouvert plus de 48 h après le début, sauf match signalé reporté (`reporte`) : « à régler » à la main.
    Statut affiché seulement (le pari reste « open » et peut encore être réglé automatiquement)."""
    if r.get("status") != "open" or r.get("reporte"):
        return False
    try:
        start = datetime.fromisoformat(str(r["commence"]).replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError):
        return False
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    return (now - start).total_seconds() > A_REGLER_H * 3600


def stats(root, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    allrows = store.read(root, BETS)
    rows = [r for r in allrows if not suspect(r)]
    closed = [r for r in rows if r.get("close")]
    good = [r for r in closed if r["close"]["minutes_to_start"] <= CLOSE_MAX_MIN]  # clôture quasi réelle
    clvs = [r["close"]["clv_odds"] for r in good if r.get("ref_kind") != "consensus-anj"]  # sharp seulement
    by_kind = {k: V.mean_ci([r["close"]["clv_odds"] for r in good if r["ref_kind"] == k])
               for k in sorted({r["ref_kind"] for r in good})}
    settled = [{"stake": r["stake"], "odds": r["odds"], "won": r["result"]["won"]}
               for r in rows if r["status"] == "settled" and r.get("result")]
    return {
        "bets_total": len(rows), "bets_suspect": len(allrows) - len(rows),
        "bets_open": sum(r["status"] == "open" and not a_regler(r, now) for r in rows),
        "bets_a_regler": sum(a_regler(r, now) for r in rows),  # compté à part : hors ROI tant qu'il n'est pas réglé
        "bets_settled": len(settled),
        "clv": V.mean_ci(clvs), "clv_by_ref_kind": by_kind,
        "clv_coverage": f"{len(good)}/{len(rows)} paris ont une clôture sharp ≤{CLOSE_MAX_MIN} min avant le match "
                        f"({len(closed)} ont une observation plus lointaine, exclue)", "ev_expected": V.mean_ci([r["ev"] for r in rows]),
        "roi": V.roi(settled),
        "note": "CLV sur paris avec clôture ≤90 min seulement (couverture ci-dessus ; les autres sont exclus, donc biais "
                "possible). IC95 % indicatif, non corrigé des consultations répétées ; CLV ≠ rentabilité (limites de mise, "
                "fiscalité non modélisées). 200+ paris avec clôture nécessaires avant toute conclusion.",
    }
