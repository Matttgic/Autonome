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
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from ..match import sim

PAGES = ["https://www.winamax.fr/paris-sportifs"]
SPORTS = {1: "FOOTBALL", 2: "BASKETBALL", 4: "ICE_HOCKEY", 5: "TENNIS"}
MAIN = {"FOOTBALL": 1, "TENNIS": 186, "BASKETBALL": 219, "ICE_HOCKEY": 406}
UA = "Mozilla/5.0 (autonome, outil perso, requêtes espacées)"


class SourceError(RuntimeError):
    pass


MAX_BYTES = 15_000_000


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise SourceError(f"winamax {url.rsplit('/', 1)[-1]}: HTTP {e.code}") from None
    except (OSError, http.client.HTTPException) as e:
        raise SourceError(f"winamax {url.rsplit('/', 1)[-1]}: {type(e).__name__}") from None
    if len(body) > MAX_BYTES:
        raise SourceError(f"winamax : page tronquée (> {MAX_BYTES} octets)")
    return body.decode("utf-8", "replace")


def state(html: str) -> dict:
    """État préchargé ; SourceError si introuvable ou illisible (jamais un « 0 match » silencieux)."""
    m = re.search(r"PRELOADED_STATE\s*=\s*\{", html)
    if not m:
        raise SourceError(f"winamax : état PRELOADED_STATE introuvable ({len(html)} caractères)")
    try:
        d, _ = json.JSONDecoder().raw_decode(html[m.end() - 1:])
    except ValueError:
        raise SourceError("winamax : état PRELOADED_STATE illisible ou tronqué") from None
    if not isinstance(d, dict):
        raise SourceError("winamax : état de forme inattendue")
    return d


def _odds(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if 1.0 < v < 1000 else None


def _table(st: dict, k: str) -> dict:
    v = st.get(k)
    return v if isinstance(v, dict) else {}


def _event(m: dict, bets: dict, outcomes: dict, odds: dict, tournaments: dict, now: datetime, hours: float):
    if m.get("status") != "PREMATCH":
        return None
    try:
        sport = SPORTS.get(int(m.get("sportId")))
    except (TypeError, ValueError):
        return None
    home, away = m.get("competitor1Name"), m.get("competitor2Name")
    if not sport or not home or not away:
        return None
    ts = float(m["matchStart"])
    start = datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts, timezone.utc)  # secondes ou millisecondes
    if not now < start <= now + timedelta(hours=hours):
        return None
    b = bets.get(str(m.get("mainBetId")))
    if not isinstance(b, dict) or b.get("available") is False or int(b.get("marketId")) != MAIN[sport]:
        return None
    sels, n_raw = {}, 0
    for oid in b.get("outcomes") or []:
        n_raw += 1
        o = outcomes.get(str(oid))
        v = _odds(odds.get(str(oid)))
        if not isinstance(o, dict) or o.get("available") is False or v is None:
            continue
        code, label = str(o.get("code") or "").lower(), str(o.get("label") or "")
        by_code = {"1": "home", "x": "draw", "n": "draw", "2": "away", "1714": "home", "1715": "away"}.get(code)
        by_label = None
        if label:
            sh, sa = sim(label, str(home)), sim(label, str(away))
            by_label = "home" if sh >= 0.6 and sh > sa else "away" if sa >= 0.6 and sa > sh else None
        if by_code in ("home", "away") and label and by_label != by_code and not label.lower().startswith(("nul", "match nul")):
            continue  # libellé qui ne désigne pas l'équipe du code : issue ignorée
        side = by_code or by_label
        if side:
            sels[side] = v
    if sport == "FOOTBALL":
        if set(sels) != {"home", "draw", "away"} or n_raw != 3:
            return None
        key = "1x2"
    else:
        if set(sels) != {"home", "away"} or n_raw != 2:
            return None
        key = "ml"
    t = tournaments.get(str(m.get("tournamentId")))
    comp = str((t or {}).get("tournamentName") or "") if isinstance(t, dict) else ""
    return {"id": f"wx|{m.get('matchId')}", "sport": sport, "competition": comp,
            "home": str(home), "away": str(away), "commence": start.isoformat().replace("+00:00", "Z"),
            "url": f"https://www.winamax.fr/paris-sportifs/match/{m.get('matchId')}", "odds": {key: sels}}


def events_from(st: dict, now: datetime, hours: float = 30) -> list[dict]:
    bets, outcomes, odds, tours = (_table(st, k) for k in ("bets", "outcomes", "odds", "tournaments"))
    out = []
    for m in _table(st, "matches").values():
        if not isinstance(m, dict):
            continue
        try:
            e = _event(m, bets, outcomes, odds, tours, now, hours)
        except (KeyError, TypeError, ValueError, OverflowError, OSError, AttributeError):
            continue  # une entrée malformée ne fait jamais perdre la page
        if e:
            out.append(e)
    return out
