"""Référence Polymarket (API publique Gamma, sans clé ni compte).

Faits vérifiés le 2026-11-02 : pour chaque match des grands championnats, Polymarket publie un groupe
d'événements (« A vs. B », « - Halftime Result », « - More Markets » : plus/moins, les 2 marquent, buts par équipe,
handicaps, 1re mi-temps…) avec carnet d'ordres. Ex. Lorient–Brest : 1X2 185 k$, More Markets 299 k$ de liquidité.

Probabilité juste d'une jambe binaire = milieu (bid+ask)/2 ; bornes prudentes = bid / ask. Le 1X2 (3 marchés « oui »)
est normalisé par la somme des milieux. Une jambe sans prix, trop large ou peu liquide est absente (jamais inventée).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
UA = "autonome/0.3 (outil perso; requetes espacees)"
TAGS = ["ligue-1", "epl", "la-liga", "bundesliga", "serie-a", "ucl", "uel"]
MAX_SPREAD = 0.03
MIN_LIQ = 2000.0


class SourceError(RuntimeError):
    pass


def get(path: str, timeout: int = 30, pause: float = 1.0):
    req = urllib.request.Request(GAMMA + path, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise SourceError(f"polymarket {path.split('?')[0]}: {type(e).__name__}") from None
    time.sleep(pause)
    return data


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _quote(m: dict, max_spread: float, min_liq: float) -> dict | None:
    bid, ask = _f(m.get("bestBid")), _f(m.get("bestAsk"))
    liq = _f(m.get("liquidityNum") or m.get("liquidity")) or 0.0
    if bid is None or ask is None or not 0 < bid < ask < 1 or ask - bid > max_spread or liq < min_liq:
        return None
    if not m.get("active", True) or m.get("closed"):
        return None
    return {"id": str(m.get("id")), "bid": bid, "ask": ask, "mid": (bid + ask) / 2, "liq": liq}


def _leg(q: dict, idx: int) -> dict:
    """Jambe = issue idx (0 = première issue / « oui ») d'un marché binaire."""
    if idx == 0:
        return {"p": q["mid"], "lo": q["bid"], "hi": q["ask"], "legs": [[q["id"], 0]], "spread": q["ask"] - q["bid"]}
    return {"p": 1 - q["mid"], "lo": 1 - q["ask"], "hi": 1 - q["bid"], "legs": [[q["id"], 1]],
            "spread": q["ask"] - q["bid"]}


def _sum(*legs: dict) -> dict:
    return {"p": sum(l["p"] for l in legs), "lo": sum(l["lo"] for l in legs), "hi": sum(l["hi"] for l in legs),
            "legs": [x for l in legs for x in l["legs"]], "spread": max(l["spread"] for l in legs)}


def _line(x) -> str:
    return f"{float(x):g}"


def build_reference(raw_events: list[dict], max_spread: float = MAX_SPREAD, min_liq: float = MIN_LIQ) -> list[dict]:
    """Regroupe les événements Gamma par match -> [{key, commence, home, away, markets:{canon:{sel:jambe}}}]."""
    games: dict[str, dict] = {}
    for e in raw_events:
        title = e.get("title", "")
        base, _, suffix = title.partition(" - ")
        if " vs. " not in base:
            continue
        home, away = [x.strip() for x in base.split(" vs. ", 1)]
        start = e.get("startTime")
        if not start:
            continue
        g = games.setdefault(f"{base}|{start[:16]}", {"key": f"pm|{e.get('slug', base)}", "commence": start,
                                                       "home": home, "away": away, "markets": {}, "updated": ""})
        if not suffix:
            g["key"] = f"pm|{e.get('slug')}"
        g["updated"] = max(g["updated"], e.get("updatedAt") or "")
        mk = g["markets"]
        ms = e.get("markets", [])
        if not suffix or suffix == "Halftime Result":
            q = {}
            for m in ms:
                lab = (m.get("groupItemTitle") or "")
                sel = "draw" if lab.lower().startswith("draw") else "home" if lab == home else "away" if lab == away else None
                qq = _quote(m, max_spread, min_liq)
                if sel and qq:
                    q[sel] = qq
            if len(q) == 3:
                s = sum(v["mid"] for v in q.values())
                if 0.97 <= s <= 1.03:
                    legs = {k: {"p": v["mid"] / s, "lo": v["bid"] / s, "hi": v["ask"] / s, "legs": [[v["id"], 0]],
                                "spread": v["ask"] - v["bid"]} for k, v in q.items()}
                    key = "1x2" if not suffix else "ht1x2"
                    mk[key] = legs
                    if key == "1x2":
                        mk["dc"] = {"1X": _sum(legs["home"], legs["draw"]), "X2": _sum(legs["draw"], legs["away"]),
                                    "12": _sum(legs["home"], legs["away"])}
        elif suffix == "More Markets":
            for m in ms:
                t, lab = m.get("sportsMarketType"), (m.get("groupItemTitle") or "")
                q = _quote(m, max_spread, min_liq)
                if not q:
                    continue
                try:
                    outs = json.loads(m.get("outcomes") or "[]")
                except json.JSONDecodeError:
                    continue
                if t == "totals" and outs == ["Over", "Under"]:
                    mk[f"ou@{_line(m['line'])}"] = {"over": _leg(q, 0), "under": _leg(q, 1)}
                elif t == "first_half_totals" and outs == ["Over", "Under"]:
                    mk[f"ht_ou@{_line(m['line'])}"] = {"over": _leg(q, 0), "under": _leg(q, 1)}
                elif t == "both_teams_to_score" and outs == ["Yes", "No"]:
                    mk["btts"] = {"yes": _leg(q, 0), "no": _leg(q, 1)}
                elif t == "soccer_team_totals" and outs == ["Over", "Under"]:
                    side = "home" if lab.startswith(home) else "away" if lab.startswith(away) else None
                    if side:
                        mk[f"team_ou@{side}@{_line(m['line'])}"] = {"over": _leg(q, 0), "under": _leg(q, 1)}
                elif t == "spreads" and m.get("line") is not None and len(outs) == 2:
                    fav = "home" if outs[0] == home else "away" if outs[0] == away else None
                    if fav:  # issue 0 = fav gagne avec plus de |ligne| buts d'écart
                        mk[f"ah@{fav}@{_line(m['line'])}"] = {"fav": _leg(q, 0), "dog": _leg(q, 1)}
    return [g for g in games.values() if g["markets"]]


def fetch(tags=TAGS) -> tuple[list[dict], list[str]]:
    raw, errors = [], []
    for t in tags:
        try:
            raw += get(f"/events?tag_slug={t}&closed=false&limit=300")
        except SourceError as ex:
            errors.append(str(ex))
    seen, uniq = set(), []
    for e in raw:
        if e.get("id") not in seen:
            seen.add(e.get("id"))
            uniq.append(e)
    return build_reference(uniq), errors


def resolved(market: dict) -> list[float] | None:
    """Prix de résolution [p0, p1] d'un marché clos (1/0, ou 0.5/0.5 si annulé), sinon None."""
    if not market.get("closed"):
        return None
    try:
        p = [float(x) for x in json.loads(market.get("outcomePrices") or "[]")]
    except (json.JSONDecodeError, ValueError):
        return None
    return p if len(p) == 2 and abs(sum(p) - 1) < 1e-6 and all(x in (0.0, 0.5, 1.0) for x in p) else None


_ = re  # (réservé)
