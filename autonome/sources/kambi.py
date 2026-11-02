"""PMU Sport (agréé ANJ) = plateforme Kambi. Le site pmu.fr/sport charge ses cotes, pour tout visiteur anonyme,
depuis le flux public eu.offering-api.kambicdn.com/offering/v2018/pmusportsfr/… (observé en rendant la page publique
dans un navigateur, 2026-11-02). Lu depuis GitHub Actions : HTTP 200, sans connexion, User-Agent honnête, requêtes
espacées. Cotes en millièmes (2180 = 2,18). Aucune cote devinée : issue absente ou fermée = absente.
"""
from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HOST = "https://eu.offering-api.kambicdn.com/offering/v2018"
UA = "autonome/0.5 (outil perso; requetes espacees)"
PARAMS = {"channel_id": "1", "client_id": "200", "lang": "fr_MC", "market": "FR"}


class SourceError(RuntimeError):
    pass


def get(offering: str, path: str, pause: float = 1.0, **extra):
    q = urllib.parse.urlencode({**PARAMS, **extra})
    req = urllib.request.Request(f"{HOST}/{offering}/{path}?{q}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read(20_000_000))
    except urllib.error.HTTPError as e:
        raise SourceError(f"kambi {offering} {path.split('?')[0]}: HTTP {e.code}") from None
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise SourceError(f"kambi {offering} {path.split('?')[0]}: {type(e).__name__}") from None
    finally:
        time.sleep(pause)


def sports(offering: str) -> list[dict]:
    """[{id, name, termKey, boCount}] des sports proposés."""
    g = get(offering, "group.json")
    return [{"id": s["id"], "name": s.get("name"), "termKey": s.get("termKey"), "boCount": s.get("boCount", 0)}
            for s in (g.get("group") or {}).get("groups", [])]


def _odds(o: dict) -> float | None:
    if o.get("status") not in (None, "OPEN") or not isinstance(o.get("odds"), (int, float)):
        return None
    x = o["odds"] / 1000.0
    return x if x > 1.0 else None


def _line(o: dict) -> str | None:
    return f"{o['line'] / 1000:g}" if isinstance(o.get("line"), (int, float)) else None


def _put(out, key, sel, v):
    if v:
        out.setdefault(key, {})[sel] = v


def map_offers(event: dict, offers: list[dict]) -> dict[str, dict[str, float]]:
    """Paris Kambi -> clés canoniques (communes avec polymarket.build_reference)."""
    home, away, sport = event.get("homeName"), event.get("awayName"), event.get("sport")
    out: dict = {}
    for bo in offers:
        crit = (bo.get("criterion") or {}).get("englishLabel") or ""
        typ = (bo.get("betOfferType") or {}).get("englishName") or ""
        outs = [o for o in bo.get("outcomes") or [] if isinstance(o, dict)]
        by = {o.get("type"): o for o in outs}
        if typ == "Match" and crit == "Full Time" and set(by) == {"OT_ONE", "OT_CROSS", "OT_TWO"}:
            for t, s in (("OT_ONE", "home"), ("OT_CROSS", "draw"), ("OT_TWO", "away")):
                _put(out, "1x2", s, _odds(by[t]))
        elif typ == "Match" and crit == "Half Time" and set(by) == {"OT_ONE", "OT_CROSS", "OT_TWO"}:
            for t, s in (("OT_ONE", "home"), ("OT_CROSS", "draw"), ("OT_TWO", "away")):
                _put(out, "ht1x2", s, _odds(by[t]))
        elif typ == "Match" and set(by) == {"OT_ONE", "OT_TWO"} and (
                crit == "Match Odds" and sport in ("TENNIS", "UFC_MMA", "BOXING", "TABLE_TENNIS", "DARTS", "SNOOKER", "ESPORTS")
                or (crit.startswith("Match Odds") and "Overtime" in crit and sport in ("BASKETBALL", "ICE_HOCKEY", "AMERICAN_FOOTBALL"))
                or (crit == "Match Odds" and sport == "BASKETBALL")):
            _put(out, "ml", "home", _odds(by["OT_ONE"]))
            _put(out, "ml", "away", _odds(by["OT_TWO"]))
        elif typ == "Double Chance" and crit == "Double Chance":
            for t, s in (("OT_ONE_OR_CROSS", "1X"), ("OT_CROSS_OR_TWO", "X2"), ("OT_ONE_OR_TWO", "12")):
                if t in by:
                    _put(out, "dc", s, _odds(by[t]))
        elif typ == "Yes/No" and crit == "Both Teams To Score" and {"OT_YES", "OT_NO"} <= set(by):
            _put(out, "btts", "yes", _odds(by["OT_YES"]))
            _put(out, "btts", "no", _odds(by["OT_NO"]))
        elif typ == "Over/Under" and {"OT_OVER", "OT_UNDER"} <= set(by) and _line(by["OT_OVER"]) == _line(by["OT_UNDER"]):
            ln = _line(by["OT_OVER"])
            key = None
            if crit == "Total Goals":
                key = f"ou@{ln}"
            elif crit == "Total Goals - 1st Half":
                key = f"ht_ou@{ln}"
            elif crit == f"Total Goals by {home}":
                key = f"team_ou@home@{ln}"
            elif crit == f"Total Goals by {away}":
                key = f"team_ou@away@{ln}"
            if key and ln and float(ln) % 1 == 0.5:
                _put(out, key, "over", _odds(by["OT_OVER"]))
                _put(out, key, "under", _odds(by["OT_UNDER"]))
    return out


def to_events(data: dict, offering: str) -> list[dict]:
    evs = {e["id"]: e for e in data.get("events") or [] if isinstance(e, dict) and e.get("id")}
    offers: dict = {}
    for bo in data.get("betOffers") or []:
        if isinstance(bo, dict) and bo.get("eventId") in evs:
            offers.setdefault(bo["eventId"], []).append(bo)
    out = []
    for eid, e in evs.items():
        if e.get("state") not in (None, "NOT_STARTED") or not e.get("homeName") or not e.get("awayName"):
            continue
        try:
            start = datetime.fromisoformat(e["start"].replace("Z", "+00:00")).astimezone(timezone.utc)
        except (KeyError, ValueError, AttributeError):
            continue
        out.append({"id": f"kb|{offering}|{eid}", "kambi_id": eid, "sport": e.get("sport"),
                    "competition": " / ".join(p.get("name", "") for p in e.get("path") or [])[:80],
                    "commence": start.isoformat().replace("+00:00", "Z"), "home": e["homeName"], "away": e["awayName"],
                    "url": "https://www.pmu.fr/sport/", "odds": map_offers(e, offers.get(eid, []))})
    return out


def fetch_main(offering: str = "pmusportsfr", min_bo: int = 1) -> tuple[list[dict], list[str]]:
    """Marchés principaux de tous les sports (une requête par sport)."""
    errors, out = [], []
    try:
        sp = sports(offering)
    except SourceError as e:
        return [], [str(e)]
    for s in sp:
        if s["boCount"] < min_bo:
            continue
        try:
            d = get(offering, f"betoffer/group/{s['id']}.json", excludeLive="true", excludeOngoing="true",
                    excludePrePacks="true", includeParticipants="true", onlyMain="true")
            out += to_events(d, offering)
        except SourceError as e:
            errors.append(str(e))
    return out, errors


def fetch_full(offering: str, event: dict) -> dict:
    """Tous les marchés d'un événement (une requête)."""
    d = get(offering, f"betoffer/event/{event['kambi_id']}.json", includeParticipants="true", onlyMain="false",
            pause=0.7)
    full = to_events(d, offering)
    return full[0] if full else event
