"""Sélection quotidienne des paris candidats (un pari par match/marché, limite journalière)."""
from __future__ import annotations

MAX_BETS_PER_DAY = 5


def select_daily(cands: list[dict], cfg: dict, already: set[str], done_today: int = 0) -> list[dict]:
    """Garde au plus un pari par (match, marché), le meilleur EV ; limite quotidienne."""
    best: dict[tuple, dict] = {}
    for c in cands:
        if c["bet_id"] in already:
            continue
        key = (c["event_id"], c["group"])
        if key not in best or c["ev"] > best[key]["ev"]:
            best[key] = c
    ranked = sorted(best.values(), key=lambda c: (c["ref_kind"] != "sharp", -c["ev"]))
    return ranked[: max(0, cfg.get("max_bets_per_day", MAX_BETS_PER_DAY) - done_today)]
