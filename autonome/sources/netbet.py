"""NetBet.fr (agréé ANJ) : lecture des pages PUBLIQUES (aucune connexion), état Nuxt analysé sans exécution.

Faits vérifiés le 2026-11-02 depuis GitHub Actions (workflow probe/capture) : pages lisibles (HTTP 200) ;
une page de compétition liste les URL /evenement/<id>-<slug> ; une page d'événement contient ~80 marchés
(1X2, double chance, plus/moins, les 2 marquent, buts par équipe, mi-temps, handicaps) avec les cotes affichées.
Cote affichée « - » = sélection fermée -> absente. Une requête toutes les `pause` s, User-Agent honnête.
"""
from __future__ import annotations

import http.client
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .jslit import JsLitError, parse_nuxt

BASE = "https://www.netbet.fr"
MAX_BYTES = 5_000_000
UA = "autonome/0.3 (outil perso; 1 requete / 5 s)"
COMPETITIONS = ["/football/france/ligue-1-mcdonald-s-r", "/football/angleterre/premier-league", "/football/espagne/laliga",
                "/football/allemagne/bundesliga", "/football/italie/serie-a",
                "/football/ligue-des-champions/ligue-des-champions", "/football/ligue-europa/ligue-europa"]


class SourceError(RuntimeError):
    pass


def fetch(path: str, timeout: int = 30, pause: float = 5.0) -> str:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read(MAX_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise SourceError(f"netbet {path}: HTTP {e.code}") from None
    except (OSError, http.client.HTTPException) as e:  # URLError, timeout, reset, lecture incomplète
        raise SourceError(f"netbet {path}: {type(e).__name__}") from None
    finally:
        time.sleep(pause)
    return html


_EV_URL = re.compile(r"(?:\\u002F|/)evenement(?:\\u002F|/)(\d+)-([a-z0-9-]+)")


def event_urls(html: str) -> list[str]:
    """URL d'événements de match (les « vainqueur/meilleur buteur » de saison sont exclus)."""
    out = []
    for i, slug in dict.fromkeys(_EV_URL.findall(html)):
        if re.search(r"20\d\d-20\d\d", slug):
            continue
        out.append(f"/evenement/{i}-{slug}")
    return list(dict.fromkeys(out))


def _odd(s: dict) -> float | None:
    v = s.get("odds_display") or s.get("oddsDisplay")
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return x if x > 1.0 else None


def _num(t: str) -> str:
    return f"{float(t):g}"


def map_markets(ev: dict) -> dict[str, dict[str, float]]:
    """Marchés NetBet -> clés canoniques communes avec la référence (cf. polymarket.build_reference)."""
    home, away = ev["home"], ev["away"]
    out: dict[str, dict[str, float]] = {}

    def put(key, sel, o):
        if o:
            out.setdefault(key, {})[sel] = o

    for m in ev.get("markets") or []:
        if not isinstance(m, dict):
            continue
        t = m.get("selection_order_type")
        for b in m.get("bets") or []:
            if not isinstance(b, dict):
                continue
            lab = (b.get("label") or "").strip()
            sels = [x for x in (b.get("selections") or []) if isinstance(x, dict)]
            if t == "1x2" and lab in ("Qui va gagner le match ?", "Qui va gagner la 1ère mi-temps ?") and len(sels) == 3:
                key = "1x2" if "match" in lab else "ht1x2"
                for s, n in zip(sels, ("home", "draw", "away")):
                    put(key, n, _odd(s))
            elif t == "double_chance" and lab == "Double Chance" and len(sels) == 3:
                for s, n in zip(sels, ("1X", "X2", "12")):
                    put("dc", n, _odd(s))
            elif t == "yes_no" and lab == "Les 2 équipes marquent ?" and len(sels) == 2:
                for s, n in zip(sels, ("yes", "no")):
                    put("btts", n, _odd(s))
            elif t == "over_under" and len(sels) == 2:
                mm = re.fullmatch(r"Plus ou moins de (\d+(?:\.\d+)?) buts \?", lab)
                mh = re.fullmatch(r"Plus ou moins de (\d+(?:\.\d+)?) buts en 1ère mi-temps \?", lab)
                mt = re.fullmatch(r"Plus ou moins de (\d+(?:\.\d+)?) buts pour (.+) \? \(temps réglementaire\)", lab)
                key = None
                if mm:
                    key = f"ou@{_num(mm.group(1))}"
                elif mh:
                    key = f"ht_ou@{_num(mh.group(1))}"
                elif mt and mt.group(2) in (home, away):
                    key = f"team_ou@{'home' if mt.group(2) == home else 'away'}@{_num(mt.group(1))}"
                if key and (sels[0].get("label") or "").startswith("Plus") and (sels[1].get("label") or "").startswith("Moins"):
                    put(key, "over", _odd(sels[0]))
                    put(key, "under", _odd(sels[1]))
            elif t == "handicap_2ways" and len(sels) == 2:
                mh = re.fullmatch(r"Handicap \((-?\d+(?:\.\d+)?)\) - Qui va gagner le match \?", lab)
                if mh and float(mh.group(1)) < 0:
                    line = _num(mh.group(1))
                    l0 = sels[0].get("label") or ""
                    fav = "home" if l0.endswith(home) else "away" if l0.endswith(away) else None
                    if fav and l0.startswith(f"({line})"):
                        put(f"ah@{fav}@{line}", "fav", _odd(sels[0]))
                        put(f"ah@{fav}@{line}", "dog", _odd(sels[1]))
    return out


def _find_events(o, acc, seen=None):
    """Parcours itératif, chaque objet visité une fois (résiste aux cycles et aux partages)."""
    seen, stack = set(), [o]
    while stack:
        x = stack.pop()
        if id(x) in seen:
            continue
        seen.add(id(x))
        if isinstance(x, dict):
            if "matchId" in x and "markets" in x and "actors" in x:
                acc[str(x["matchId"])] = x
            stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
        elif isinstance(x, list):
            stack.extend(v for v in x if isinstance(v, (dict, list)))


def parse_event_page(html: str, url: str) -> list[dict]:
    try:
        state = parse_nuxt(html)
    except JsLitError as e:
        raise SourceError(f"netbet {url}: état illisible ({e})") from None
    acc: dict[str, dict] = {}
    _find_events(state, acc)
    out = []
    for e in acc.values():
        try:
            ev = _event(e, url)
        except (TypeError, ValueError, AttributeError, KeyError):
            continue  # événement malformé : ignoré, jamais bloquant
        if ev:
            out.append(ev)
    return out


def _event(e: dict, url: str) -> dict | None:
    actors = {a.get("type"): a.get("label") for a in e.get("actors") or [] if isinstance(a, dict)}
    if not actors.get("home") or not actors.get("away") or not e.get("start"):
        return None
    start = datetime.fromisoformat(e["start"]).astimezone(timezone.utc)
    ev = {"id": f"nb|{e['matchId']}", "url": url,
          "commence": start.isoformat().replace("+00:00", "Z"), "home": actors["home"], "away": actors["away"],
          "competition": e.get("competitionLabel"), "markets": e.get("markets", [])}
    ev["odds"] = map_markets(ev)
    del ev["markets"]
    return ev
