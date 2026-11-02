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
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://prod-public-api.livescore.com/v1/api/app/date"
SLUG = {"FOOTBALL": "soccer", "BASKETBALL": "basketball", "TENNIS": "tennis", "ICE_HOCKEY": "hockey"}
FINAL = {"FOOTBALL": {"FT", "AET", "AP"}, "BASKETBALL": {"FT", "OT", "AOT"}, "TENNIS": {"FT"},
         "ICE_HOCKEY": {"FT", "OT", "AP"}}
# Hockey (vérifié le 02/11/2026) : Tr1OR = score à 60 min ; Tr1 = score final, prolongation comprise et +1 au vainqueur
# des tirs au but (« AP » : 3-2 pour 2-2 à 60 min) : 1N2 = 60 min, vainqueur = prolongation et tirs au but inclus.
# Compétitions féminines / jeunes : LiveScore ne marque pas toujours les équipes (« Arsenal WFC », ligue « Naisten… »).
_SPECIAL = re.compile(r"(women|womens|woman|feminin|femenin|frauen|damen|naisten|kvinn|kvinde|dames|vrouwen|"
                      r"damallsvenskan|toppserien|\bwsl\b|nwsl|u-? ?\d{2}\b|youth|reserve|primavera|"
                      r"\bwfc\b|\bw\b|\bwnba\b|\bncaaw\b)")


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
    """TOUS les matchs (finis ou non : un match reporté reste un candidat d'appariement, pour que son homonyme ne soit
    jamais pris à sa place) -> [{sport, id, commence, homes, aways, status, is_final, final, regular, winner,
    special, doubles}]."""
    out = []
    stages = payload.get("Stages") if isinstance(payload, dict) else None
    if not isinstance(stages, list):
        raise SourceError("livescore : Stages absent")
    for st in stages:
        if not isinstance(st, dict):
            continue
        comp = f"{st.get('Cnm') or ''} {st.get('Snm') or ''}".strip()
        for e in st.get("Events") or []:
            if not isinstance(e, dict):
                continue
            start, homes, aways = _start(e.get("Esd")), _names(e, "T1"), _names(e, "T2")
            if not start or not homes or not aways:
                continue
            final = (_int(e.get("Tr1")), _int(e.get("Tr2")))
            regular = (_int(e.get("Tr1OR")), _int(e.get("Tr2OR")))
            if e.get("Eps") == "FT" and sport == "FOOTBALL" and None in regular:
                regular = final  # fin du temps réglementaire : score final = score à 90 min
            epr = e.get("Epr")
            is_final = (e.get("Eps") in FINAL.get(sport, ()) and (epr is None or str(epr) == "2")
                        and None not in final)
            names = " ".join(homes + aways + [comp]).lower()
            out.append({"sport": sport, "id": str(e.get("Eid") or ""), "commence": start, "homes": homes,
                        "aways": aways, "status": e.get("Eps"), "is_final": is_final, "final": final,
                        "regular": None if None in regular else regular,
                        "winner": _int(e.get("Ewt")),
                        "special": bool(_SPECIAL.search(names)),
                        "doubles": len(e.get("T1") or []) > 1 or len(e.get("T2") or []) > 1 or " / " in names,
                        "competition": comp})
    return out


def fetch(sport: str, day: str, timeout: int = 30, pause: float = 1.0) -> list[dict]:
    """day = AAAAMMJJ (UTC)."""
    url = f"{BASE}/{SLUG[sport]}/{day}/0?countryCode=FR&locale=fr"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (autonome, reglement des paris)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise SourceError(f"livescore {SLUG[sport]} {day}: HTTP {e.code}") from None
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise SourceError(f"livescore {SLUG[sport]} {day}: {type(e).__name__}") from None
    finally:
        time.sleep(pause)
    return parse(data, sport)


def outcome(res: dict, market: str) -> str | None:
    """Issue gagnante (home/draw/away) selon le règlement des bookmakers, ou None si non réglable."""
    sport = res["sport"]
    if not res.get("is_final"):
        return None
    if market == "1x2":
        if sport not in ("FOOTBALL", "BASKETBALL", "ICE_HOCKEY") or not res.get("regular"):
            return None  # 1N2 = temps réglementaire seulement
        h, a = res["regular"]
        win = "home" if h > a else "away" if a > h else "draw"
        if res.get("status") == "FT" and res.get("winner") in (1, 2) and res["final"] == res["regular"] \
                and win != {1: "home", 2: "away"}[res["winner"]]:
            return None  # vainqueur déclaré et score en désaccord : à la main
        return win
    if market == "ml":
        if sport not in ("BASKETBALL", "TENNIS", "ICE_HOCKEY"):
            return None  # rugby, handball, volley… : non lus sur LiveScore ou règles variables -> à la main
        h, a = res["final"]
        win = None if h == a else "home" if h > a else "away"
        if res.get("winner") is not None and res["winner"] != {"home": 1, "away": 2}.get(win):
            return None  # vainqueur déclaré (Ewt) absent ou contraire au score (abandon ?) : à la main
        return win
    return None
