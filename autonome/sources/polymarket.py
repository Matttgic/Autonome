"""Référence Polymarket (API publique Gamma, sans clé ni compte).

Faits vérifiés le 2026-11-02 : pour chaque match des grands championnats, Polymarket publie un groupe
d'événements (« A vs. B », « - Halftime Result », « - More Markets » : plus/moins, les 2 marquent, buts par équipe,
handicaps, 1re mi-temps…) avec carnet d'ordres. Ex. Lorient–Brest : 1X2 185 k$, More Markets 299 k$ de liquidité.

Probabilité juste d'une jambe binaire = milieu (bid+ask)/2 ; bornes prudentes = bid / ask. Le 1X2 (3 marchés « oui »)
est normalisé par la somme des milieux. Une jambe sans prix, trop large ou peu liquide est absente (jamais inventée).
"""
from __future__ import annotations

import http.client
from datetime import datetime, timedelta, timezone
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
UA = "autonome/0.3 (outil perso; requetes espacees)"
TAGS = ["ligue-1", "epl", "la-liga", "bundesliga", "serie-a", "ucl", "uel", "mls", "brazil-serie-a", "primeira-liga",
        "efl-championship"]
TAGS_2WAY = ["nba", "nhl", "tennis", "ufc", "ncaa-basketball", "boxing", "volleyball", "table-tennis", "darts"]
# volley, tennis de table, fléchettes : date de fin = début + 7 j (lecture par étiquette, pas par fenêtre) ; vainqueur sans nul
TAG_SPORT = {"nba": "BASKETBALL", "ncaa-basketball": "BASKETBALL", "nhl": "ICE_HOCKEY", "tennis": "TENNIS",
             "ufc": "MMA", "boxing": "BOXING", "basketball": "BASKETBALL", "hockey": "ICE_HOCKEY",
             "american_football": "AMERICAN_FOOTBALL", "volleyball": "VOLLEYBALL", "table-tennis": "TABLE_TENNIS",
             "darts": "DARTS"}
# Lecture large par étiquette (idée reprise de cotes-value) : TOUS les championnats d'un sport en une requête paginée,
# bornée par la date de fin (= heure du match en foot/basket ; pas au tennis : début + 7 j, d'où les TAGS_2WAY).
# Fenêtre 72 h : couvre le consensus (48 h, un match couvert par Polymarket n'y entre pas), la fiche 72 h et les boosts.
# Mesure du 02/11 : foot dans les 30 h = 92 matchs contre 6 avec la liste TAGS (Ligue 2, Liga 2, Pologne, Danemark…).
# Identifiants lus sur GET /sports : 100350 porté par les 185 ligues de football, 28 par les 61 ligues de basket.
WINDOW_TAGS = {"soccer": 100350, "basketball": 28, "hockey": 100088, "american_football": 450}
# hockey 100088 (KHL, SHL, Liiga, DEL, AHL… : vainqueur prolongation et tirs au but inclus, vérifié le 02/11/2026 dans
# les règles des marchés), NFL 450 (prolongation incluse). Handball et rugby écartés : le nul existe.
# Féminines, jeunes, réserves : jamais confondues avec l'équipe première d'un bookmaker (leçon des revues adverses).
_EXCLUDE = re.compile(r"\b(women|womens|woman|wsl|wsl2|nwsl|uwcl|feminin\w*|femenin\w*|frauen|u1[5-9]|u2[0-3]|youth|"
                      r"reserves?|wwc\w*|fifaw|aseanw|tpew|cwbb|bkfibaw|wnba|ncaaw|jong|next gen|futuro|"
                      r"vbligueaw|vbbundesligaw|vb2bundesligaw|weuq|uwec|weuc|wwoh|aflw)\b")
MAX_SPREAD = 0.03
MIN_LIQ = 2000.0


class SourceError(RuntimeError):
    pass


def get(path: str, timeout: int = 30, pause: float = 1.0):
    req = urllib.request.Request(GAMMA + path, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except (OSError, http.client.HTTPException, ValueError) as e:  # URLError, reset, IncompleteRead, JSON, UTF-8
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
            "legs": [x for l in legs for x in l["legs"]], "spread": sum(l["spread"] for l in legs)}


def _line(x) -> str:
    return f"{float(x):g}"


def build_reference(raw_events: list[dict], max_spread: float = MAX_SPREAD, min_liq: float = MIN_LIQ) -> list[dict]:
    """Regroupe les événements Gamma par match -> [{key, commence, home, away, markets:{canon:{sel:jambe}}}]."""
    games: dict[str, dict] = {}
    for e in raw_events:
        try:
            datetime.fromisoformat(str(e.get("startTime")).replace("Z", "+00:00")).astimezone(timezone.utc)
            if not str(e.get("startTime", "")).endswith(("Z", "+00:00")):
                continue  # heure sans fuseau : ignorée
            _add_event(games, e, max_spread, min_liq)
        except (TypeError, ValueError, KeyError, AttributeError):
            continue  # événement malformé ignoré, jamais bloquant
    return [g for g in games.values() if g["markets"] and g["main"]]


def _two_way(games: dict, e: dict, max_spread: float, min_liq: float) -> bool:
    """Sports à deux issues (tennis, NBA, NHL, UFC…) : un marché « moneyline » dont les issues sont les 2 noms."""
    ml = [m for m in e.get("markets") or [] if m.get("sportsMarketType") == "moneyline"]
    if len(ml) != 1:
        return False
    m = ml[0]
    outs = m.get("outcomes") or "[]"
    outs = json.loads(outs) if isinstance(outs, str) else list(outs)
    if len(outs) != 2 or outs[0] in ("Yes", "No") or not e.get("startTime") or not e.get("slug"):
        return False
    q = _quote(m, max_spread, min_liq)
    if not q:
        return True  # c'est bien un match à 2 issues, mais pas assez liquide : ignoré
    a, b = outs
    games[f"2w|{e['slug']}"] = {"key": f"pm|{e['slug']}", "commence": e["startTime"], "home": a, "away": b,
                                "sport": TAG_SPORT.get(e.get("_tag"), None),
                                "two_way": True, "main": True, "updated": e.get("updatedAt") or "",
                                "markets": {"ml": {"home": _leg(q, 0), "away": _leg(q, 1)}}}
    return True


def _excluded(e: dict) -> bool:
    txt = " ".join([str(e.get("title") or ""), str(e.get("seriesSlug") or "")] +
                   [f"{t.get('slug', '')} {t.get('label', '')}" for t in e.get("tags") or [] if isinstance(t, dict)])
    return bool(_EXCLUDE.search(re.sub(r"[^a-z0-9]+", " ", txt.lower().replace("'", ""))))


def _add_event(games: dict, e: dict, max_spread: float, min_liq: float) -> None:
    if _excluded(e):
        return
    if _two_way(games, e, max_spread, min_liq):
        return
    if e.get("_tag") in TAG_SPORT:
        return  # basket, tennis, NHL… : jamais lus comme un match de football à 3 issues
    title = e.get("title") or ""
    base, _, suffix = title.partition(" - ")
    if " vs. " not in base:
        return
    home, away = [x.strip() for x in base.split(" vs. ", 1)]
    start = e.get("startTime")
    if not start:
        return
    g = games.setdefault(f"{base}|{start[:16]}", {"key": f"pm|{e.get('slug', base)}", "commence": start, "sport": "FOOTBALL",
                                                   "home": home, "away": away, "markets": {}, "updated": "",
                                                   "main": False})
    if not suffix:  # clé stable = slug de l'événement principal (sans lui, le match est ignoré)
        if not e.get("slug"):
            return
        g["key"], g["main"] = f"pm|{e['slug']}", True
    g["updated"] = max(g["updated"], e.get("updatedAt") or "")
    mk = g["markets"]
    ms = e.get("markets", [])
    if not suffix or suffix == "Halftime Result":
        q = {}
        for m in ms or []:
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
        for m in ms or []:
            try:
                _add_more(mk, m, home, away, max_spread, min_liq)
            except (TypeError, ValueError, KeyError, AttributeError):
                continue  # un marché malformé n'invalide pas les autres


def _add_more(mk: dict, m: dict, home: str, away: str, max_spread: float, min_liq: float) -> None:
    t, lab = m.get("sportsMarketType"), (m.get("groupItemTitle") or "")
    q = _quote(m, max_spread, min_liq)
    if not q:
        return
    outs = m.get("outcomes") or "[]"
    outs = json.loads(outs) if isinstance(outs, str) else list(outs)
    if t in ("totals", "first_half_totals", "soccer_team_totals") and _f(m.get("line")) is None:
        return
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
    elif t == "spreads" and _f(m.get("line")) is not None and _f(m.get("line")) < 0 and len(outs) == 2:
        fav = "home" if outs[0] == home else "away" if outs[0] == away else None
        if fav:  # issue 0 = fav gagne avec plus de |ligne| buts d'écart
            mk[f"ah@{fav}@{_line(m['line'])}"] = {"fav": _leg(q, 0), "dog": _leg(q, 1)}


def fetch_window(tag_id: int, label: str, now: datetime | None = None, hours: float = 72,
                 max_pages: int = 20) -> list[dict]:
    """Événements non clos d'une étiquette dont la date de fin tombe dans [maintenant − 1 h ; + hours]."""
    now = now or datetime.now(timezone.utc)
    out = []
    for i in range(max_pages):
        q = urllib.parse.urlencode({"tag_id": tag_id, "active": "true", "closed": "false", "limit": 100,
                                    "offset": 100 * i,
                                    "end_date_min": (now - timedelta(hours=1)).isoformat(timespec="seconds"),
                                    "end_date_max": (now + timedelta(hours=hours)).isoformat(timespec="seconds")})
        page = get(f"/events?{q}", pause=0.5)
        if not isinstance(page, list):
            raise SourceError(f"polymarket tag {tag_id}: réponse inattendue")
        out += [{**e, "_tag": label} for e in page if isinstance(e, dict)]
        if len(page) < 100:
            return out
    raise SourceError(f"polymarket tag {tag_id}: liste tronquée ({100 * max_pages} événements)")


def fetch(tags=TAGS + TAGS_2WAY, window_tags=WINDOW_TAGS) -> tuple[list[dict], list[str]]:
    raw, errors = [], []
    done_window = set()
    for label, tag_id in (window_tags or {}).items():
        try:
            raw += fetch_window(tag_id, label)
            done_window.add(label)
        except SourceError as ex:
            errors.append(str(ex))  # repli : la liste de championnats ci-dessous
    if "soccer" in done_window:
        tags = [t for t in tags if t not in TAGS]  # déjà couverts par la lecture large
    for t in tags:
        for off in (0, 300, 600):  # pagination : une page tronquée ferait perdre l'événement principal
            try:
                page = get(f"/events?tag_slug={t}&closed=false&limit=300&offset={off}")
            except SourceError as ex:
                errors.append(str(ex))
                break
            for e in page if isinstance(page, list) else []:
                if isinstance(e, dict):
                    e.setdefault("_tag", t)
                    raw.append(e)
            if not isinstance(page, list) or len(page) < 300:
                break
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
