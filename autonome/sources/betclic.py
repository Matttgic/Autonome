"""Betclic (ANJ) par son API publique gRPC-web, sans compte ni clé, en stdlib.

Porté de Matttgic/cotes-value (cotes/direct/betclic.py, en production depuis le 18/10/2026, dernière détection le
02/11/2026) : mêmes en-têtes, mêmes numéros de champs protobuf, mêmes libellés de marchés. Le site betclic.fr répond 403
aux serveurs GitHub (CloudFront) ; cette API, elle, répond à une requête HTTP ordinaire. Le propriétaire a autorisé ce
contournement le 02/11/2026. Aucune empreinte de navigateur n'est imitée.

Flux : une liste par sport (pages de 40), puis le détail (« Le Top ») des seuls matchs appariés à la référence. Chaque
réponse est un flux de notifications : on lit la première trame puis on ferme. Un 403/429 arrête la source.

Marchés gardés (clés communes avec polymarket.build_reference) : 1x2 (foot, temps réglementaire), ml (tennis, basket ;
hockey seulement si prolongation incluse), dc, btts, ou@L, team_ou@side@L (lignes x,5), ah@fav@L (foot). Mi-temps,
périodes, buteurs, combinaisons : ignorés. Libellé non reconnu = marché absent (jamais deviné).
"""
from __future__ import annotations

import http.client
import re
import struct
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://offering.begmedia.com/web/offering.access.api/offering.access.api.MatchService"
LISTE = "GetMatchesBySportWithNotifications"
DETAIL = "GetMatchWithNotification"
PAGE = 40
LISTE_MAX = 640
SPORTS = {"FOOTBALL": "football", "TENNIS": "tennis", "BASKETBALL": "basketball", "ICE_HOCKEY": "ice_hockey"}
URL_SPORT = {"FOOTBALL": "football-sfootball", "TENNIS": "tennis-stennis", "BASKETBALL": "basket-ball-sbasketball",
             "ICE_HOCKEY": "hockey-sur-glace-sice_hockey"}
HEADERS = {"Content-Type": "application/grpc-web+proto", "Accept": "*/*", "x-grpc-web": "1",
           "x-bg-ref-platform": "DESKTOP", "x-bg-regulation": "FR", "x-bg-ref-brand": "BETCLIC",
           "x-bg-ref-regulator-zone": "FR", "Origin": "https://www.betclic.fr", "Referer": "https://www.betclic.fr/",
           "User-Agent": "Mozilla/5.0", "Accept-Language": "fr-FR,fr;q=0.9"}


class SourceError(RuntimeError):
    pass


# --- protobuf minimal ---------------------------------------------------------------------------------------------
def _varint(v: int) -> bytes:
    out = bytearray()
    while v > 0x7F:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.append(v & 0x7F)
    return bytes(out)


def f_varint(n: int, v: int) -> bytes:
    return _varint(n << 3) + _varint(v)


def f_bytes(n: int, v) -> bytes:
    b = v.encode("utf-8") if isinstance(v, str) else v
    return _varint((n << 3) | 2) + _varint(len(b)) + b


def f_double(n: int, v: float) -> bytes:
    return _varint((n << 3) | 1) + struct.pack("<d", float(v))


def frame(payload: bytes) -> bytes:
    return b"\x00" + struct.pack(">I", len(payload)) + payload


def _read_varint(data: bytes, pos: int):
    res = shift = 0
    while pos < len(data):
        b = data[pos]
        res |= (b & 0x7F) << shift
        pos += 1
        if not b & 0x80:
            break
        shift += 7
        if shift > 70:
            break
    return res, pos


def decode(data: bytes) -> dict:
    fields: dict = {}
    pos = 0
    while pos < len(data):
        tag, pos = _read_varint(data, pos)
        num, wire = tag >> 3, tag & 7
        if num == 0:
            break
        if wire == 0:
            val, pos = _read_varint(data, pos)
        elif wire == 1:
            if pos + 8 > len(data):
                break
            val, pos = data[pos:pos + 8], pos + 8
        elif wire == 2:
            ln, pos = _read_varint(data, pos)
            if pos + ln > len(data):
                break
            val, pos = data[pos:pos + ln], pos + ln
        elif wire == 5:
            if pos + 4 > len(data):
                break
            val, pos = data[pos:pos + 4], pos + 4
        else:
            break
        fields.setdefault(num, []).append(val)
    return fields


def _text(v) -> str | None:
    if not isinstance(v, (bytes, bytearray)):
        return None
    try:
        t = v.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return t if t and all(c.isprintable() or c in "\n\r\t" for c in t) else None


def _odds(v) -> float | None:
    if isinstance(v, (bytes, bytearray)) and len(v) == 8:
        x = struct.unpack("<d", v)[0]
        if 1.0 < x < 1000:
            return round(x, 2)
    return None


def first_frame(chunks) -> bytes | None:
    buf = bytearray()
    for c in chunks:
        if not c:
            continue
        buf.extend(c)
        if len(buf) < 5:
            continue
        ln = struct.unpack(">I", buf[1:5])[0]
        if ln > 5_000_000:
            return None
        if len(buf) >= 5 + ln:
            return bytes(buf[:5 + ln])
    return None


def _payload(fr: bytes | None) -> bytes:
    if not fr or len(fr) < 5 or fr[0] == 0x80:  # 0x80 = trame de fin (trailers), pas des données
        return b""
    return fr[5:5 + struct.unpack(">I", fr[1:5])[0]]


def _subs(fields: dict, n: int) -> list[bytes]:
    return [v for v in fields.get(n, []) if isinstance(v, (bytes, bytearray))]


# --- liste et détail ----------------------------------------------------------------------------------------------
def _match(data: bytes) -> dict | None:
    f = decode(data)
    mid = (f.get(1) or [None])[0]
    if not isinstance(mid, int):
        return None
    start = next((t for t in map(_text, f.get(3, [])) if t and "T" in t), None)
    comp = comp_id = None
    for c in _subs(f, 8)[:1]:
        cf = decode(c)
        comp = _text((cf.get(2) or [b""])[0])
        comp_id = (cf.get(1) or [None])[0]
    teams = [t for t in (_text((decode(x).get(3) or [b""])[0]) for x in _subs(f, 12)) if t]
    if len(teams) < 2:
        name = next((t for t in map(_text, f.get(2, [])) if t and " - " in t), None)
        if not name:
            return None
        teams = [x.strip() for x in name.split(" - ", 1)]
    return {"id": mid, "home": teams[0], "away": teams[1], "start": start, "competition": comp,
            "competition_id": comp_id if isinstance(comp_id, int) else None}


def list_matches(fr: bytes | None) -> list[dict]:
    out = []
    for env in _subs(decode(_payload(fr)), 1):
        for m in _subs(decode(env), 3):
            x = _match(m)
            if x:
                out.append(x)
    return out


def _selection(data: bytes) -> dict | None:
    f = decode(data)
    if 14 in f and f[14][0] != 1:
        return None  # sélection suspendue / fermée
    name = None
    for n in (10, 11, 2, 3):
        if n in f:
            name = _text(f[n][0])
            if name:
                break
    odds = _odds(f[12][0]) if 12 in f else None
    return {"name": name, "odds": odds} if name and odds else None


def _selections(market: bytes) -> list[dict]:
    f = decode(market)
    out = [s for s in map(_selection, _subs(f, 16)) if s]
    if out:
        return out
    for grp in _subs(f, 10):  # totaux : sélections groupées par ligne
        for item in _subs(decode(grp), 1):
            for cand in _subs(decode(item), 1) or [item]:
                s = _selection(cand)
                if s:
                    out.append(s)
    return out


def detail_markets(fr: bytes | None) -> list[dict]:
    """[{name, selections:[{name, odds}]}] du premier match détaillé (sélections ouvertes seulement)."""
    out, seen = [], set()
    for env in _subs(decode(_payload(fr)), 1):
        for m in _subs(decode(env), 1):
            for menv in _subs(decode(m), 11):
                fe = decode(menv)
                for raw in _subs(fe, 3) + _subs(fe, 1):
                    f = decode(raw)
                    if 9 in f and f[9][0] == 3:
                        continue
                    name = next((t for t in (_text(f[n][0]) for n in (2, 3) if n in f) if t and len(t) > 2), None)
                    sels = _selections(raw) if name else []
                    key = (name, tuple((s["name"], s["odds"]) for s in sels))
                    if name and sels and key not in seen:
                        seen.add(key)
                        out.append({"name": name, "selections": sels})
    return out


# --- traduction vers les clés canoniques ------------------------------------------------------------------------
_PERIOD = re.compile(r"^\s*(?:1[èe]re|2[èe]me|3[èe]me|[1-4](?:er|è|e|ème|eme)?)\s+"
                     r"(?:mi-temps|p[ée]riode|qt|quart|set)", re.I)
_EXCLUDE = ("buteur", "décisif", "decisif", "passeur", "mi-temps", "mi temps", "&", " ou ", " et ", "+ de 2", "écart de jeux",
            "quand", "comment", "intervalle", "multi", "choix", "cage", "pénalty", "penalty", "prolifique", "corner",
            "carton", "tir", "minute", "période", "periode", "set ", "qt")


def _low(s: str) -> str:
    return unicodedata.normalize("NFC", s or "").strip().lower()


def _side(name: str, home: str, away: str) -> str | None:
    b = _low(name)
    if b in ("nul", "match nul", "n", "x"):
        return "draw"
    if b == _low(home):
        return "home"
    if b == _low(away):
        return "away"
    return None


def _line(name: str) -> str | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)", name)
    if not m:
        return None
    x = float(m.group(1).replace(",", "."))
    return f"{x:g}" if x % 1 == 0.5 else None  # lignes entières / quarts (remboursements) : ignorées


def _ou(name: str) -> str | None:
    b = _low(name).replace("＋", "+").replace("−", "-").replace("–", "-")
    if b.startswith(("+", "plus")):
        return "over"
    if b.startswith(("-", "moins")):
        return "under"
    return None


_WIN = re.compile(r"^(.+?)\s+gagne de\s+(\d+)\s*(?:buts?)?\s*ou\s*\+\s*$", re.I)
_NOLOSE = re.compile(r"^(.+?)\s+ne perd pas(?:\s+ou perd de\s+(\d+)\s*(?:buts?)?\s*(?:exactement|ou\s*-)?)?\s*$", re.I)


def map_markets(markets: list[dict], home: str, away: str, sport: str) -> dict[str, dict[str, float]]:
    out: dict = {}

    def put(key, sel, odds):
        out.setdefault(key, {})[sel] = odds

    for mk in markets:
        name, sels = mk.get("name") or "", mk.get("selections") or []
        if _PERIOD.match(name):
            continue  # périodes, mi-temps, sets : non comparés
        b = _low(name)
        if b.startswith(("résultat du match", "resultat du match", "vainqueur du match")) and "rembours" not in b:
            sides = {_side(s["name"], home, away): s["odds"] for s in sels}
            if sport == "FOOTBALL" and set(sides) == {"home", "draw", "away"} and len(sels) == 3 and "prolong" not in b:
                for k, v in sides.items():
                    put("1x2", k, v)
            elif set(sides) == {"home", "away"} and len(sels) == 2 and (
                    sport in ("TENNIS", "BASKETBALL") or (sport == "ICE_HOCKEY" and "prolong" in b)):
                for k, v in sides.items():
                    put("ml", k, v)
            continue
        if any(w in b for w in _EXCLUDE):
            continue
        if sport != "FOOTBALL":
            continue  # marchés secondaires : football seulement (unités et prolongations sûres)
        if b.startswith("double chance"):
            for s in sels:
                parts = re.split(r"\s+ou\s+", s["name"].strip(), maxsplit=1, flags=re.I)
                if len(parts) == 2:
                    k = {frozenset({"home", "draw"}): "1X", frozenset({"draw", "away"}): "X2",
                         frozenset({"home", "away"}): "12"}.get(frozenset(_side(p, home, away) for p in parts))
                    if k:
                        put("dc", k, s["odds"])
        elif b.startswith(("les 2 équipes marquent", "les deux équipes marquent")):
            yn = {_low(s["name"]): s["odds"] for s in sels}
            if set(yn) == {"oui", "non"}:
                put("btts", "yes", yn["oui"])
                put("btts", "no", yn["non"])
        elif re.match(r"(?:[ée]cart de buts|[ée]cart entre les [ée]quipes|vainqueur avec handicap)", b):
            lines: dict = {}
            for s in sels:
                t = s["name"].strip()
                w, nl = _WIN.match(t), _NOLOSE.match(t)
                if w and int(w.group(2)) >= 2:
                    team, n, role = w.group(1), int(w.group(2)), "fav"
                elif nl and nl.group(2):
                    team, n, role = nl.group(1), int(nl.group(2)) + 1, "dog"  # perd de n−1 ou − = +(n−0,5)
                else:
                    continue
                side = _side(team, home, away)
                if side in ("home", "away"):
                    fav = side if role == "fav" else {"home": "away", "away": "home"}[side]
                    lines.setdefault((fav, f"{-(n - 0.5):g}"), {})[role] = s["odds"]
            for (fav, ln), pair in lines.items():
                if set(pair) == {"fav", "dog"}:
                    out[f"ah@{fav}@{ln}"] = pair
        elif re.match(r"(?:nombre total de buts|total de buts|nombre de buts)\b", b) or re.search(r" - (?:nombre )?total de buts", b):
            team = None
            if " - " in name:
                left, right = [x.strip() for x in name.split(" - ", 1)]
                cand = right if re.match(r"(?:nombre|total)", _low(left)) else left
                team = _side(re.sub(r"\s*\(.*\)\s*$", "", cand), home, away)
                if team not in ("home", "away"):
                    continue
            for s in sels:
                ln, d = _line(s["name"]), _ou(s["name"])
                if ln and d:
                    put(f"team_ou@{team}@{ln}" if team else f"ou@{ln}", d, s["odds"])
    return {k: v for k, v in out.items() if len(v) >= 2 and all(isinstance(x, float) for x in v.values())}


# --- réseau -----------------------------------------------------------------------------------------------------
def post(method: str, payload: bytes, timeout: float = 12, pause: float = 0.4) -> bytes:
    req = urllib.request.Request(f"{BASE}/{method}", data=frame(payload), headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            fr = first_frame(iter(lambda: r.read(65536), b""))
    except urllib.error.HTTPError as e:
        raise SourceError(f"betclic {method}: HTTP {e.code}") from None
    except (OSError, http.client.HTTPException) as e:
        raise SourceError(f"betclic {method}: {type(e).__name__}") from None
    finally:
        time.sleep(pause)
    if not fr:
        raise SourceError(f"betclic {method}: trame incomplète")
    return fr


def _start(s) -> datetime | None:
    try:
        t = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", str(s)).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(timezone.utc) if t.tzinfo else None


def _slug(s) -> str:
    b = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", b).strip("-")


def fetch_list(now: datetime, hours: float = 30, sports=SPORTS) -> tuple[list[dict], list[str]]:
    """Matchs à venir dans l'horizon -> événements sans cotes (le détail les remplit)."""
    out, errors = [], []
    horizon = now + timedelta(hours=hours)
    for sport, slug in sports.items():
        for off in range(0, LISTE_MAX + 1, PAGE):
            try:
                ms = list_matches(post(LISTE, f_bytes(1, slug) + f_bytes(2, "fr") + f_varint(4, off) + f_varint(5, PAGE)))
            except SourceError as e:
                errors.append(str(e))
                if "HTTP 403" in str(e) or "HTTP 429" in str(e):
                    return out, errors
                break
            starts = []
            for m in ms:
                st = _start(m["start"])
                if not st:
                    continue
                starts.append(st)
                if now < st <= horizon:
                    url = None
                    if m["competition"] and m["competition_id"]:
                        url = (f"https://www.betclic.fr/{URL_SPORT[sport]}/{_slug(m['competition'])}-c{m['competition_id']}"
                               f"/{_slug(m['home'] + ' ' + m['away'])}-m{m['id']}")
                    out.append({"id": f"bc|{m['id']}", "betclic_id": m["id"], "sport": sport,
                                "competition": m["competition"] or "", "home": m["home"], "away": m["away"],
                                "commence": st.isoformat().replace("+00:00", "Z"), "url": url, "odds": {}})
            if len(ms) < PAGE or (starts and min(starts) > horizon):
                break
    return out, errors


def fetch_detail(event: dict) -> dict:
    fr = post(DETAIL, f_varint(1, int(event["betclic_id"])) + f_bytes(2, "fr"))
    return {**event, "odds": map_markets(detail_markets(fr), event["home"], event["away"], event["sport"])}
