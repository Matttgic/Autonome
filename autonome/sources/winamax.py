"""Winamax (ANJ) : page publique « paris-sportifs », lue par une requête ordinaire, sans exécuter de JavaScript.

La page embarque son état dans `PRELOADED_STATE` (JSON : matches, bets, outcomes, odds — même structure que celle lue
par Grotonome, src/grotonome/sources/parse.py). Elle répond 403 aux serveurs GitHub la plupart du temps, mais pas
toujours (200 relevé par Grotonome le 02/11/2026 à 02:20 UTC) : on la tente, et un 403/429 met la source en pause 6 h
(backoff.jsonl). Aucune imitation d'empreinte de navigateur (refusée par le classifieur de la session).

Seul le pari principal de chaque match (`mainBetId`) est lu, avec son identifiant de marché Sportradar : 1 (1X2, football),
186 (vainqueur, tennis), 219 (vainqueur prolongation incluse, basket), 406 (vainqueur prolongation et tirs au but
inclus, hockey). Issue non reconnue = marché absent.
"""
from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

PAGES = ["https://www.winamax.fr/paris-sportifs"]
SPORTS = {1: "FOOTBALL", 2: "BASKETBALL", 4: "ICE_HOCKEY", 5: "TENNIS"}
MAIN = {"FOOTBALL": 1, "TENNIS": 186, "BASKETBALL": 219, "ICE_HOCKEY": 406}
UA = "Mozilla/5.0 (autonome, outil perso, requêtes espacées)"


class SourceError(RuntimeError):
    pass


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(15_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise SourceError(f"winamax {url.rsplit('/', 1)[-1]}: HTTP {e.code}") from None
    except (OSError, http.client.HTTPException) as e:
        raise SourceError(f"winamax {url.rsplit('/', 1)[-1]}: {type(e).__name__}") from None


def state(html: str) -> dict:
    i = html.find("PRELOADED_STATE")
    j = html.find("{", i) if i >= 0 else -1
    if j < 0:
        return {}
    try:
        d, _ = json.JSONDecoder().raw_decode(html[j:])
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _odds(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if 1.0 < v < 1000 else None


def events_from(st: dict, now: datetime, hours: float = 30) -> list[dict]:
    bets, outcomes, odds = (st.get(k) or {} for k in ("bets", "outcomes", "odds"))
    out = []
    for m in (st.get("matches") or {}).values():
        if not isinstance(m, dict) or m.get("status") != "PREMATCH":
            continue
        sport = SPORTS.get(m.get("sportId"))
        home, away = m.get("competitor1Name"), m.get("competitor2Name")
        if not sport or not home or not away:
            continue
        try:
            start = datetime.fromtimestamp(float(m["matchStart"]), timezone.utc)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
        if not now < start <= now + timedelta(hours=hours):
            continue
        b = bets.get(str(m.get("mainBetId"))) or {}
        try:
            mid = int(b.get("marketId"))
        except (TypeError, ValueError):
            continue
        if not isinstance(b, dict) or b.get("available") is False or mid != MAIN[sport]:
            continue
        sels, n_raw = {}, 0
        for oid in b.get("outcomes") or []:
            n_raw += 1
            o = outcomes.get(str(oid)) or {}
            v = _odds(odds.get(str(oid)))
            if not isinstance(o, dict) or o.get("available") is False or v is None:
                continue
            code, label = str(o.get("code") or "").lower(), str(o.get("label") or "")
            by_code = {"1": "home", "x": "draw", "2": "away", "1714": "home", "1715": "away"}.get(code)
            by_label = "home" if label == home else "away" if label == away else None
            if by_code and by_label and by_code != by_label:
                continue  # code et libellé en désaccord : issue ignorée
            side = by_code or by_label
            if side:
                sels[side] = v
        if sport == "FOOTBALL":
            if set(sels) != {"home", "draw", "away"} or n_raw != 3:
                continue
            key = "1x2"
        else:
            if set(sels) != {"home", "away"} or n_raw != 2:
                continue
            key = "ml"
        out.append({"id": f"wx|{m.get('matchId')}", "sport": sport, "competition": str(m.get("tournamentId") or ""),
                    "home": str(home), "away": str(away), "commence": start.isoformat().replace("+00:00", "Z"),
                    "url": f"https://www.winamax.fr/paris-sportifs/match/{m.get('matchId')}", "odds": {key: sels}})
    return out
