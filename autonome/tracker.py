"""Suivi : enregistrement des paris, cote de clôture (CLV), règlement, statistiques."""
from __future__ import annotations

from datetime import datetime, timezone

from . import store, value as V
from .devig import fair_probs
from .engine import groups, parse_ts

BETS = "bets.jsonl"          # un pari recommandé par ligne (mis à jour sur place)
CLOSE_MAX_MIN = 90          # au-delà, la dernière observation n'est pas une clôture


def record_bets(root, new_bets: list[dict]) -> None:
    rows = store.read(root, BETS)
    have = {r["bet_id"] for r in rows}
    for b in new_bets:
        if b["bet_id"] not in have:
            rows.append({**b, "status": "open", "close": None, "result": None})
    store.write_all(root, BETS, rows)


def update_closing(root, event: dict, cfg: dict, now: datetime | None = None) -> int:
    """Met à jour la clôture sharp des paris ouverts de ce match, tant qu'il n'a pas commencé."""
    now = now or datetime.now(timezone.utc)
    rows = store.read(root, BETS)
    n = 0
    for r in rows:
        if r["status"] != "open" or r["event_id"] != event["id"]:
            continue
        if parse_ts(event["commence"]) <= now:
            continue
        for k in cfg.get("sharp_books", ["pinnacle"]) + cfg.get("exchange_books", []):
            g = groups(event["books"].get(k, {})).get(r["group"])
            if g and r["selection"] in g:
                names = sorted(g)
                p = fair_probs([g[x] for x in names], "shin")[names.index(r["selection"])]
                age = (now - parse_ts(event["books"][k].get("last_update"))).total_seconds() / 60 \
                    if event["books"][k].get("last_update") else None
                if age is None or age > cfg.get("close_max_ref_age_min", 60):
                    continue  # ligne sans horodatage ou périmée : pas une clôture
                mins = (parse_ts(event["commence"]) - now).total_seconds() / 60
                r["close"] = {"book": k, "p_fair": p, "seen_at": now.isoformat(), "minutes_to_start": mins,
                              "ref_age_min": age, **V.clv(r["odds"], p)}
                n += 1
                break
    store.write_all(root, BETS, rows)
    return n


def settle(root, event_id: str, res: dict) -> int:
    rows = store.read(root, BETS)
    n = 0
    for r in rows:
        if r["event_id"] != event_id or r["status"] == "settled":
            continue
        won = None
        if r["group"] == "h2h":
            h, a = res["home_score"], res["away_score"]
            actual = r["home"] if h > a else r["away"] if a > h else "Draw"
            won = r["selection"] == actual
        elif r["group"].startswith("totals@"):
            line = float(r["group"].split("@")[1])
            if res["total"] == line:
                won = None  # push
            else:
                won = (res["total"] > line) == (r["selection"] == "Over")
        r["status"] = "settled"
        r["result"] = {"won": won, **res}
        n += 1
    store.write_all(root, BETS, rows)
    return n


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


def stats(root) -> dict:
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
        "bets_total": len(rows), "bets_suspect": len(allrows) - len(rows), "bets_open": sum(r["status"] == "open" for r in rows),
        "bets_settled": len(settled),
        "clv": V.mean_ci(clvs), "clv_by_ref_kind": by_kind,
        "clv_coverage": f"{len(good)}/{len(rows)} paris ont une clôture sharp ≤{CLOSE_MAX_MIN} min avant le match "
                        f"({len(closed)} ont une observation plus lointaine, exclue)", "ev_expected": V.mean_ci([r["ev"] for r in rows]),
        "roi": V.roi(settled),
        "note": "CLV sur paris avec clôture ≤90 min seulement (couverture ci-dessus ; les autres sont exclus, donc biais "
                "possible). IC95 % indicatif, non corrigé des consultations répétées ; CLV ≠ rentabilité (limites de mise, "
                "fiscalité non modélisées). 200+ paris avec clôture nécessaires avant toute conclusion.",
    }
