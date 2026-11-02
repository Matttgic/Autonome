"""Pipeline sans clé : référence Polymarket (milieu bid/ask) vs cotes publiques NetBet (ANJ).

Chaque pari candidat porte tout le détail vérifiable : bid/ask de la référence, proba juste (milieu), proba
prudente (borne bid/ask défavorable), cote du book, EV au milieu et EV prudente, jambes Polymarket pour le
règlement et la clôture.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import store, value as V
from .match import pair
from .tracker import BETS

CFG = {
    "min_ev": 0.03,          # EV au milieu
    "min_ev_cons": 0.005,    # EV avec la borne prudente (bid/ask défavorable) : doit rester positive
    "max_spread": 0.03,
    "min_odds": 1.30, "max_odds": 5.0,
    "min_minutes_to_start": 20, "max_hours_to_start": 30,
    "bankroll": 100.0, "kelly_mult": 0.25, "stake_cap_pct": 0.02,
    "max_bets_per_day": 6,
    # Garde-fous repris de cotes-value (controle.py) et Revue/Cotescope (fraîcheur) :
    "max_book_age_min": 45,      # cote de book relevée il y a plus longtemps (instantané coteur) : mesurée, jamais proposée
    "conf_min_n": 5, "conf_median_lo": -0.25, "conf_median_hi": -0.01,
}

SEL_FR = {"home": "{home}", "draw": "Nul", "away": "{away}", "1X": "{home} ou nul", "X2": "Nul ou {away}",
          "12": "{home} ou {away}", "yes": "Oui", "no": "Non", "over": "Plus", "under": "Moins"}


def label(group: str, sel: str, home: str, away: str) -> str:
    kind, *rest = group.split("@")
    if kind in ("ou", "ht_ou"):
        base = f"{'Plus' if sel == 'over' else 'Moins'} de {rest[0]} buts"
        return base + (" (1re mi-temps)" if kind == "ht_ou" else "")
    if kind == "team_ou":
        team = home if rest[0] == "home" else away
        return f"{team} : {'plus' if sel == 'over' else 'moins'} de {rest[1]} buts"
    if kind == "ah":
        fav = home if rest[0] == "home" else away
        dog = away if rest[0] == "home" else home
        return f"Handicap {fav} ({rest[1]})" if sel == "fav" else f"Handicap {dog} (+{rest[1].lstrip('-')})"
    if kind == "ml":
        return f"Vainqueur : {home if sel == 'home' else away}"
    name = {"1x2": "1X2", "ht1x2": "1X2 mi-temps", "dc": "Double chance", "btts": "Les 2 marquent"}.get(kind, kind)
    return f"{name} : {SEL_FR.get(sel, sel).format(home=home, away=away)}"


def _mins(iso: str, now: datetime) -> float:
    return (datetime.fromisoformat(iso.replace("Z", "+00:00")) - now).total_seconds() / 60


def compare(ref: dict, book: dict, book_key: str, now: datetime, cfg: dict | None = None) -> list[dict]:
    c = {**CFG, **(cfg or {})}
    mins = _mins(ref["commence"], now)
    if not c["min_minutes_to_start"] <= mins <= c["max_hours_to_start"] * 60:
        return []
    out = []
    for group, sels in book["odds"].items():
        rm = ref["markets"].get(group)
        if not rm:
            continue
        for sel, odds in sels.items():
            leg = rm.get(sel)
            if not leg or odds is None or leg["spread"] > c["max_spread"]:
                continue
            if not c["min_odds"] <= odds <= c["max_odds"]:
                continue
            ev_mid, ev_cons = V.ev(leg["p"], odds), V.ev(leg["lo"], odds)
            if ev_mid < c["min_ev"] or ev_cons < c["min_ev_cons"]:
                continue
            stake = V.stake(leg["lo"], odds, c["bankroll"], c["kelly_mult"], c["stake_cap_pct"])
            if stake <= 0 and not c.get("diagnostic"):
                continue
            out.append({
                "bet_id": f"{book['id']}|{group}|{sel}|{book_key}", "event_id": ref["key"], "book_event": book["id"],
                "sport": book.get("competition") or "", "commence": ref["commence"],
                "home": book["home"], "away": book["away"], "ref_home": ref["home"], "ref_away": ref["away"],
                "group": group, "selection": sel, "label": label(group, sel, book["home"], book["away"]),
                "book": book_key, "url": book.get("url"), "odds": odds,
                "ref_kind": "polymarket", "ref_books": ["polymarket"], "ref_overround": 0.0,
                "devig_method": "milieu bid/ask", "p_fair": leg["p"], "p_cons": leg["lo"], "p_hi": leg["hi"],
                "spread": leg["spread"], "fair_odds": 1 / leg["p"], "ev": ev_mid, "ev_cons": ev_cons,
                "legs": leg["legs"], "stake": stake, "found_at": now.isoformat(),
                "book_age_min": book.get("snapshot_age_min"),
            })
    return out


def scan(ref_games: list[dict], book_events: list[dict], book_key: str, now: datetime, cfg=None):
    trip = pair(ref_games, book_events, with_swap=True)
    pairs, cands = [], []
    for r, e, swap in trip:
        if swap:  # sport à 2 issues listé dans l'autre sens : on retourne le match côté book
            o = dict(e["odds"])
            if "ml" in o:
                o["ml"] = {{"home": "away", "away": "home"}[k]: v for k, v in o["ml"].items()}
            o = {k: v for k, v in o.items() if k == "ml"}  # seuls les marchés symétriques sont retournés sans risque
            e = {**e, "home": e["away"], "away": e["home"], "odds": o}
        pairs.append((r, e))
        cands += compare(r, e, book_key, now, cfg)
    return pairs, cands


def update_closing(root, ref_games: list[dict], now: datetime) -> int:
    """Clôture = dernier milieu Polymarket vu avant le coup d'envoi (relevé à chaque exécution horaire)."""
    from .boosts import reprice
    by_key = {g["key"]: g for g in ref_games}
    rows = store.read(root, BETS)
    n, cache = 0, {}
    for r in rows:
        if r["status"] == "open" and r.get("ref_kind") == "polymarket-modele":
            mins = _mins(r["commence"], now)
            p = reprice(r.get("boost_legs") or [], ref_games, cache) if mins > 0 else None
            if p:
                r["close"] = {"book": "polymarket-modele", "p_fair": p, "seen_at": now.isoformat(),
                              "minutes_to_start": mins, "ref_age_min": 0.0, **V.clv(r["odds"], p)}
                n += 1
            continue
        g = by_key.get(r["event_id"])
        if r["status"] != "open" or not g or r.get("ref_kind") != "polymarket":
            continue
        mins = _mins(g["commence"], now)
        leg = (g["markets"].get(r["group"]) or {}).get(r["selection"])
        if mins <= 0 or not leg:
            continue
        r["close"] = {"book": "polymarket", "p_fair": leg["p"], "seen_at": now.isoformat(), "minutes_to_start": mins,
                      "ref_age_min": _age(g.get("updated"), now), "spread": leg["spread"], **V.clv(r["odds"], leg["p"])}
        n += 1
    store.write_all(root, BETS, rows)
    return n


def settle(root, get_market, now: datetime, delay_h: float = 3.0) -> int:
    """Règle via la résolution officielle des marchés Polymarket des jambes. get_market(id) -> dict marché."""
    from .sources.polymarket import resolved
    rows = store.read(root, BETS)
    n = 0
    for r in rows:
        if r["status"] != "open" or r.get("ref_kind") != "polymarket" or _mins(r["commence"], now) > -60 * delay_h:
            continue
        vals = []
        for mid, idx in r["legs"]:
            res = resolved(get_market(mid) or {})
            if res is None:
                break
            vals.append(res[idx])
        if len(vals) != len(r["legs"]):
            continue
        pay = sum(vals)
        won = None if any(v == 0.5 for v in vals) else pay >= 0.999  # une jambe annulée => pari annulé
        r["status"], r["result"] = "settled", {"won": won, "payout": pay, "source": "résolution Polymarket"}
        n += 1
    store.write_all(root, BETS, rows)
    return n


def summarize(cands: list[dict], now: datetime) -> dict:
    """Résumé d'une exécution : distribution de l'EV des cotes du book contre la référence, par famille."""
    fam: dict[str, list[float]] = {}
    for c in cands:
        fam.setdefault(c["group"].split("@")[0], []).append(c["ev"])

    def q(xs, f):
        xs = sorted(xs)
        return round(xs[min(len(xs) - 1, int(f * len(xs)))], 4) if xs else None
    top = sorted(cands, key=lambda c: -c["ev"])[:10]
    for c in cands:
        c.setdefault("book", "?")
    return {"at": now.isoformat(), "n": len(cands), "n_ev_pos": sum(c["ev"] > 0 for c in cands),
            "n_ev_pos_cons": sum(c["ev_cons"] > 0 for c in cands),
            "by_family": {k: {"n": len(v), "median_ev": q(v, 0.5), "p90_ev": q(v, 0.9), "max_ev": max(v)}
                          for k, v in sorted(fam.items())},
            "top": [{k: c[k] for k in ("home", "away", "label", "book", "odds", "fair_odds", "ev", "ev_cons", "spread", "commence")}
                    for c in top]}


def _age(iso, now):
    try:
        return max(0.0, (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 60)
    except (AttributeError, ValueError, TypeError):
        return None


def gate(cands: list[dict], measured: list[dict], cfg: dict | None = None) -> tuple[list[dict], dict]:
    """Écarte les candidats dont la cote de book est trop vieille, ou dont le groupe (book, famille de marché) n'est pas
    « conforme » sur ce passage : un marché bien traduit cote en médiane un peu SOUS la cote juste (EV médiane entre
    conf_median_lo et conf_median_hi sur au moins conf_min_n cotes). Médiane aberrante = traduction ou appariement
    douteux (idée de cotes-value/controle.py). measured = toutes les cotes comparables du passage (diagnostic)."""
    c = {**CFG, **(cfg or {})}
    groups: dict = {}
    for m in measured:
        groups.setdefault((m.get("book"), m["group"].split("@")[0]), []).append(m["ev"])
    status = {}
    for k, v in groups.items():
        v = sorted(v)
        med = v[len(v) // 2]
        status[k] = len(v) >= c["conf_min_n"] and c["conf_median_lo"] <= med <= c["conf_median_hi"]
    kept, why = [], {"cote_trop_vieille": 0, "groupe_non_conforme": 0}
    for x in cands:
        age = x.get("book_age_min")
        if age is not None and age > c["max_book_age_min"]:
            why["cote_trop_vieille"] += 1
        elif not status.get((x.get("book"), x["group"].split("@")[0]), False):
            why["groupe_non_conforme"] += 1
        else:
            kept.append(x)
    return kept, why
