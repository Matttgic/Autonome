"""Résultats LiveScore (API publique de l'application, sans clé ni compte) pour régler les paris « consensus ».

Idée reprise de Matttgic/cotes-value (cotes/livescore.py), réécrite en stdlib. Format vérifié le 2026-11-02 :
GET {BASE}/{soccer|basketball|tennis}/AAAAMMJJ/0 -> {"Stages": [{"Snm", "Cnm", "Events": [...]}]}, un jour UTC.
Événement : Eid, Esd (début UTC AAAAMMJJhhmmss), Eps (statut), T1/T2 [{Nm (fr), NmEn}], Tr1/Tr2 (score final),
Tr1OR/Tr2OR (score du temps réglementaire, prolongation et tirs au but exclus), sets au tennis.

Seuls les statuts finaux sans ambiguïté sont retenus : un match reporté, annulé, arrêté ou un abandon au tennis n'est
jamais réglé automatiquement (règles des bookmakers variables) : il reste ouvert, à régler à la main.
"""
from __future__ import annotations

import http.client
import json
import time
import urllib.request
from datetime import datetime, timezone

BASE = "https://prod-public-api.livescore.com/v1/api/app/date"
SLUG = {"FOOTBALL": "soccer", "BASKETBALL": "basketball", "TENNIS": "tennis"}
FINAL = {"FOOTBALL": {"FT", "AET", "AP"}, "BASKETBALL": {"FT", "OT", "AOT"}, "TENNIS": {"FT"}}


class SourceError(RuntimeError):
    pass


def _int(x):
    try:
        n = int(str(x).strip())
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _start(x) -> str | None:
    try:
        return datetime.strptime(str(x), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _names(e: dict, key: str) -> list[str]:
    out = []
    for field in ("Nm", "NmEn"):
        ts = e.get(key) or []
        vals = [str(t.get(field)) for t in ts if isinstance(t, dict) and t.get(field)]
        if ts and len(vals) == len(ts):  # double au tennis : « A / B »
            v = " / ".join(vals)
            if v not in out:
                out.append(v)
    return out


def parse(payload, sport: str) -> list[dict]:
    """Matchs terminés -> [{sport, id, commence, homes, aways, status, final, regular}] (scores entiers ou None)."""
    out = []
    stages = payload.get("Stages") if isinstance(payload, dict) else None
    if not isinstance(stages, list):
        raise SourceError("livescore : Stages absent")
    for st in stages:
        for e in (st.get("Events") or []) if isinstance(st, dict) else []:
            if not isinstance(e, dict) or e.get("Eps") not in FINAL.get(sport, ()):
                continue
            start, homes, aways = _start(e.get("Esd")), _names(e, "T1"), _names(e, "T2")
            final = (_int(e.get("Tr1")), _int(e.get("Tr2")))
            if not start or not homes or not aways or None in final:
                continue
            regular = (_int(e.get("Tr1OR")), _int(e.get("Tr2OR")))
            if e.get("Eps") == "FT" and sport == "FOOTBALL" and None in regular:
                regular = final  # fin du temps réglementaire : score final = score à 90 min
            out.append({"sport": sport, "id": str(e.get("Eid") or ""), "commence": start, "homes": homes,
                        "aways": aways, "status": e["Eps"], "final": final,
                        "regular": None if None in regular else regular,
                        "competition": f"{st.get('Cnm') or ''} {st.get('Snm') or ''}".strip()})
    return out


def fetch(sport: str, day: str, timeout: int = 30, pause: float = 1.0) -> list[dict]:
    """day = AAAAMMJJ (UTC)."""
    url = f"{BASE}/{SLUG[sport]}/{day}/0?countryCode=FR&locale=fr"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (autonome, reglement des paris)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise SourceError(f"livescore {SLUG[sport]} {day}: {type(e).__name__}") from None
    finally:
        time.sleep(pause)
    return parse(data, sport)


def outcome(res: dict, market: str) -> str | None:
    """Issue gagnante (home/draw/away) selon le règlement des bookmakers, ou None si non réglable."""
    sport = res["sport"]
    if market == "1x2":
        if sport not in ("FOOTBALL", "BASKETBALL") or not res.get("regular"):
            return None  # 1N2 = temps réglementaire seulement
        h, a = res["regular"]
        return "home" if h > a else "away" if a > h else "draw"
    if market == "ml":
        if sport not in ("BASKETBALL", "TENNIS"):
            return None  # hockey, rugby… : prolongation/tirs au but selon le book -> à la main
        h, a = res["final"]
        return None if h == a else "home" if h > a else "away"
    return None
