"""Suivi : enregistrement des paris, cote de clôture (CLV), règlement, statistiques."""
from __future__ import annotations

from datetime import datetime, timezone

from . import store, value as V
from .devig import fair_probs
from .engine import groups, parse_ts

BETS = "bets.jsonl"          # un pari recommandé par ligne (mis à jour sur place)
LINES = "ref_lines.jsonl"    # dernières lignes sharp vues pour les matchs suivis


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
                r["close"] = {"book": k, "p_fair": p, "seen_at": now.isoformat(),
                              **V.clv(r["odds"], p)}
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


def stats(root) -> dict:
    rows = store.read(root, BETS)
    closed = [r for r in rows if r.get("close")]
    clvs = [r["close"]["clv_odds"] for r in closed]
    settled = [{"stake": r["stake"], "odds": r["odds"], "won": r["result"]["won"]}
               for r in rows if r["status"] == "settled" and r.get("result")]
    return {
        "bets_total": len(rows), "bets_open": sum(r["status"] == "open" for r in rows),
        "bets_settled": len(settled),
        "clv": V.mean_ci(clvs), "ev_expected": V.mean_ci([r["ev"] for r in rows]),
        "roi": V.roi(settled),
        "note": "CLV >0 de façon significative (IC95 % > 0) = avantage prouvé ; sinon indéterminé. "
                "Il faut typiquement 200+ paris avec clôture pour conclure.",
    }
