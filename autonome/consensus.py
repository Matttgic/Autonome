"""Référence « consensus ANJ » pour les matchs sans marché Polymarket (sports de niche, petits championnats).

Proba juste = moyenne des probabilités dé-viguées (Shin) de chaque bookmaker ayant le marché complet, en excluant le
bookmaker évalué (leave-one-out). Une cote nettement au-dessus de cette cote juste signale une erreur ou un retard de
mise à jour. Référence plus faible que Polymarket : seuils plus hauts et suivi CLV séparé (ref_kind « consensus »).
"""
from __future__ import annotations

from datetime import datetime

from . import value as V
from .devig import shin

CFG = {"min_books": 6, "min_ev": 0.07, "max_ev": 0.4, "min_odds": 1.3, "max_odds": 6.0,
       "min_minutes_to_start": 20, "max_hours_to_start": 48, "max_dispersion": 0.04}


def evaluate(match: dict, now: datetime, bankroll: float, cfg=None) -> list[dict]:
    c = {**CFG, **(cfg or {})}
    start = datetime.fromisoformat(match["commence"].replace("Z", "+00:00"))
    mins = (start - now).total_seconds() / 60
    if not c["min_minutes_to_start"] <= mins <= c["max_hours_to_start"] * 60:
        return []
    out = []
    for mk in ("1x2", "ml"):
        names = ["home", "draw", "away"] if mk == "1x2" else ["home", "away"]
        full = {bk: o[mk] for bk, o in match["books"].items() if mk in o and all(n in o[mk] for n in names)}
        if len(full) - 1 < c["min_books"]:  # au moins min_books AUTRES bookmakers
            continue
        fair = {bk: dict(zip(names, shin([o[n] for n in names]))) for bk, o in full.items()}
        for bk, o in full.items():
            others = [fair[b] for b in fair if b != bk]
            for n in names:
                ps = [f[n] for f in others]
                p = sum(ps) / len(ps)
                disp = max(ps) - min(ps)
                odds = o[n]
                if disp > c["max_dispersion"] or not c["min_odds"] <= odds <= c["max_odds"]:
                    continue  # bookmakers en désaccord : consensus peu fiable
                ev = V.ev(p, odds)
                if not c["min_ev"] <= ev <= c["max_ev"]:
                    continue
                p_cons = p - disp / 2
                stake = V.stake(p_cons, odds, bankroll)
                if stake <= 0 and not c.get("diagnostic"):
                    continue
                label = {"home": match["home"], "away": match["away"], "draw": "Nul"}[n]
                out.append({"bet_id": f"cons|{match['renc']}|{mk}|{n}|{bk}", "event_id": f"cons|{match['renc']}",
                            "book_event": match["renc"], "sport": match["sport"], "commence": match["commence"],
                            "home": match["home"], "away": match["away"], "group": mk, "selection": n,
                            "label": f"{'1N2' if mk == '1x2' else 'Vainqueur'} : {label}", "book": bk,
                            "url": match["url"], "odds": odds, "ref_kind": "consensus-anj",
                            "ref_books": sorted(b for b in fair if b != bk), "ref_overround": 0.0,
                            "devig_method": f"Shin, moyenne de {len(others)} bookmakers ANJ (hors {bk})",
                            "p_fair": p, "p_cons": p_cons, "p_hi": p + disp / 2, "spread": disp,
                            "fair_odds": 1 / p, "ev": ev, "ev_cons": V.ev(p_cons, odds), "legs": [],
                            "stake": stake, "found_at": now.isoformat(), "coteur_renc": match["renc"]})
    return out


def closing(rows: list[dict], matches: list[dict], now: datetime) -> int:
    """Clôture des paris « consensus » : consensus recalculé sur l'instantané coteur le plus récent."""
    by = {m["renc"]: m for m in matches}
    n = 0
    for r in rows:
        if r.get("status") != "open" or r.get("ref_kind") != "consensus-anj" or r.get("coteur_renc") not in by:
            continue
        m = by[r["coteur_renc"]]
        mins = (datetime.fromisoformat(m["commence"].replace("Z", "+00:00")) - now).total_seconds() / 60
        if mins <= 0:
            continue
        names = ["home", "draw", "away"] if r["group"] == "1x2" else ["home", "away"]
        fair = [dict(zip(names, shin([o[r["group"]][x] for x in names]))) for bk, o in m["books"].items()
                if bk != r["book"] and r["group"] in o and all(x in o[r["group"]] for x in names)]
        if len(fair) < CFG["min_books"]:
            continue
        p = sum(f[r["selection"]] for f in fair) / len(fair)
        r["close"] = {"book": "consensus-anj", "p_fair": p, "seen_at": now.isoformat(), "minutes_to_start": mins,
                      "ref_age_min": 0.0, **V.clv(r["odds"], p)}
        n += 1
    return n
