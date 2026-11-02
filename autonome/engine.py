"""Détection de value : cotes ANJ vs probabilité juste de la référence sharp."""
from __future__ import annotations

from datetime import datetime, timezone

from . import value as V

DEFAULT_CFG = {
    "sharp_books": ["pinnacle"],
    "exchange_books": ["matchbook", "betfair_ex_eu", "smarkets"],
    "fr_books": ["winamax_fr", "betclic_fr", "unibet_fr", "parionssport_fr", "zebet", "pmu", "netbet_fr",
                 "genybet", "olybet_fr", "betsson", "vbet"],
    "min_ev": 0.02,
    "min_ev_exchange": 0.03,
    "min_ev_consensus": 0.05,
    "consensus_min_books": 5,
    "min_odds": 1.40,
    "max_odds": 6.0,
    "max_ref_overround": 0.08,
    "max_ref_age_min": 90,
    "max_book_age_min": 180,
    "min_minutes_to_start": 20,
    "max_hours_to_start": 72,
    "bankroll": 100.0,
    "kelly_mult": 0.25,
    "stake_cap_pct": 0.02,
    "max_bets_per_day": 5,
}


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _age_min(ts: str | None, now: datetime) -> float | None:
    t = parse_ts(ts)
    return None if t is None else (now - t).total_seconds() / 60.0


def groups(book: dict) -> dict[str, dict[str, float]]:
    """Marchés exhaustifs d'un book : {'h2h': {...}, 'totals@2.5': {'Over':..,'Under':..}}."""
    out: dict[str, dict[str, float]] = {}
    if book.get("h2h"):
        out["h2h"] = book["h2h"]
    for pt, sel in (book.get("totals") or {}).items():
        if len(sel) == 2:
            out[f"totals@{pt}"] = sel
    return out


def pick_reference(event: dict, group: str, cfg: dict, now: datetime):
    """Renvoie (kind, ref_book(s), {sélection: cote}) ou None. Ordre: sharp > exchange > consensus."""
    books = event["books"]
    for kind, keys in (("sharp", cfg["sharp_books"]), ("exchange", cfg["exchange_books"])):
        for k in keys:
            b = books.get(k)
            if not b:
                continue
            g = groups(b).get(group)
            age = _age_min(b.get("last_update"), now)
            if g and (age is None or age <= cfg["max_ref_age_min"]):
                return kind, [k], g
    # consensus : moyenne des probas justes des books non FR avec ce marché
    others = {k: groups(b)[group] for k, b in books.items()
              if k not in cfg["fr_books"] and not k.endswith("_fr") and group in groups(b)}
    if len(others) >= cfg["consensus_min_books"]:
        names = sorted(next(iter(others.values())))
        usable = {k: g for k, g in others.items() if sorted(g) == names}
        if len(usable) >= cfg["consensus_min_books"]:
            from .devig import shin
            acc = {n: 0.0 for n in names}
            for g in usable.values():
                p = shin([g[n] for n in names])
                for n, x in zip(names, p):
                    acc[n] += x / len(usable)
            return "consensus", sorted(usable), {n: 1.0 / acc[n] for n in names}  # cotes justes (marge 0)
    return None


def find_value(event: dict, cfg: dict, now: datetime | None = None) -> list[dict]:
    cfg = {**DEFAULT_CFG, **cfg}
    now = now or datetime.now(timezone.utc)
    start = parse_ts(event["commence"])
    mins = (start - now).total_seconds() / 60.0
    if mins < cfg["min_minutes_to_start"] or mins > cfg["max_hours_to_start"] * 60:
        return []
    out = []
    fr = [k for k in event["books"] if k in cfg["fr_books"] or k.endswith("_fr")]
    all_groups = {g for k in fr for g in groups(event["books"][k])}
    for group in sorted(all_groups):
        ref = pick_reference(event, group, cfg, now)
        if not ref:
            continue
        kind, ref_keys, ref_sel = ref
        names = sorted(ref_sel)
        ref_odds = [ref_sel[n] for n in names]
        from .devig import overround
        ov = overround(ref_odds)
        if kind != "consensus" and ov > cfg["max_ref_overround"]:
            continue
        min_ev = {"sharp": cfg["min_ev"], "exchange": cfg["min_ev_exchange"], "consensus": cfg["min_ev_consensus"]}[kind]
        for bk in fr:
            b = event["books"][bk]
            g = groups(b).get(group)
            if not g or sorted(g) != names:
                continue
            age = _age_min(b.get("last_update"), now)
            if age is not None and age > cfg["max_book_age_min"]:
                continue
            for i, n in enumerate(names):
                odds = g[n]
                if not (cfg["min_odds"] <= odds <= cfg["max_odds"]):
                    continue
                res = V.conservative_ev(ref_odds, i, odds)
                if kind == "consensus":  # cotes déjà sans marge : une seule valeur
                    res["ev"] = V.ev(1.0 / ref_odds[i], odds)
                    res["p_fair"] = 1.0 / ref_odds[i]
                    res["method"] = "consensus-shin"
                if res["ev"] < min_ev:
                    continue
                stake = V.stake(res["p_fair"], odds, cfg["bankroll"], cfg["kelly_mult"], cfg["stake_cap_pct"])
                if stake <= 0:
                    continue
                out.append({
                    "bet_id": f"{event['id']}|{group}|{n}|{bk}",
                    "event_id": event["id"], "sport": event["sport"], "commence": event["commence"],
                    "home": event["home"], "away": event["away"],
                    "group": group, "selection": n, "book": bk, "odds": odds,
                    "ref_kind": kind, "ref_books": ref_keys, "ref_odds": dict(zip(names, ref_odds)),
                    "ref_overround": round(ov, 5), "p_fair": res["p_fair"], "fair_odds": 1 / res["p_fair"],
                    "devig_method": res["method"], "ev": res["ev"], "stake": stake,
                    "per_method": res.get("per_method"), "found_at": now.isoformat(),
                })
    return out


def select_daily(cands: list[dict], cfg: dict, already: set[str]) -> list[dict]:
    """Garde au plus un pari par (match, marché), le meilleur EV ; limite quotidienne."""
    cfg = {**DEFAULT_CFG, **cfg}
    best: dict[tuple, dict] = {}
    for c in cands:
        if c["bet_id"] in already:
            continue
        key = (c["event_id"], c["group"])
        if key not in best or c["ev"] > best[key]["ev"]:
            best[key] = c
    ranked = sorted(best.values(), key=lambda c: (c["ref_kind"] != "sharp", -c["ev"]))
    return ranked[: cfg["max_bets_per_day"]]
