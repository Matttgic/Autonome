"""Source football-data.co.uk : fichiers CSV publics statiques (sans clé, sans compte). Stdlib uniquement.

Faits vérifiés (2026-11-02, voir docs/RECHERCHE.md) :
- `fixtures.csv` = matchs à venir des 22 divisions principales, cotes 1X2 / +-2,5 buts / handicap asiatique
  relevées le vendredi après-midi (week-end) et le mardi (milieu de semaine). En-tête HTTP Last-Modified = date du relevé.
- Saison 2026/27 : plus de colonnes Pinnacle (PS*) ; la référence « sharp » disponible est Betfair Exchange (BFE*).
- Heures de coup d'envoi en heure du Royaume-Uni (Europe/London).
- Aucun bookmaker agréé ANJ dans ces fichiers.
"""
from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

FIXTURES_URL = "https://football-data.co.uk/fixtures.csv"
SEASON_ZIP_URL = "https://football-data.co.uk/mmz4281/{season}/data.zip"
UA = "autonome/0.2 (outil perso de recherche; 1 requete / 4 s)"
UK = ZoneInfo("Europe/London")
PARIS = ZoneInfo("Europe/Paris")

# Préfixe de colonne -> clé de book du format interne. Inconnu -> "fd_<prefixe>".
BOOK_KEYS = {"PS": "pinnacle", "BFE": "betfair_ex_eu", "B365": "bet365", "BW": "bwin", "BV": "betvictor",
             "BFD": "betfred", "PP": "paddypower", "WH": "williamhill", "IW": "interwetten", "VC": "betvictor_vc",
             "1XB": "1xbet", "BMGM": "betmgm", "CL": "coral", "LB": "ladbrokes", "BF": "betfair_sb",
             "Max": "market_max", "Avg": "market_avg"}
TOTALS_ALIAS = {"P": "PS"}  # Pinnacle +-2,5 buts = colonnes P>2.5 / PC>2.5
LEAGUES = {"E0": "Angleterre Premier League", "E1": "Angleterre Championship", "E2": "Angleterre League One",
           "E3": "Angleterre League Two", "EC": "Angleterre National League", "SC0": "Écosse Premiership",
           "SC1": "Écosse Championship", "SC2": "Écosse League One", "SC3": "Écosse League Two",
           "D1": "Allemagne Bundesliga", "D2": "Allemagne 2. Bundesliga", "I1": "Italie Serie A", "I2": "Italie Serie B",
           "SP1": "Espagne Liga", "SP2": "Espagne Liga 2", "F1": "France Ligue 1", "F2": "France Ligue 2",
           "N1": "Pays-Bas Eredivisie", "B1": "Belgique Pro League", "P1": "Portugal Liga", "T1": "Turquie Süper Lig",
           "G1": "Grèce Super League"}


class SourceError(RuntimeError):
    pass


def fetch(url: str, timeout: int = 30, pause: float = 4.0) -> tuple[bytes, datetime | None]:
    """GET poli (User-Agent honnête, pause après la requête). Renvoie (contenu, Last-Modified UTC ou None).

    Aucun contournement : 403/429/captcha -> SourceError("bloqué ...").
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            lm = r.headers.get("Last-Modified")
    except urllib.error.HTTPError as e:
        raise SourceError(f"{'bloqué' if e.code in (401, 403, 429) else 'erreur'} HTTP {e.code} sur {url}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise SourceError(f"réseau: {type(e).__name__} sur {url}") from None
    finally:
        time.sleep(pause)
    snap = None
    if lm:
        try:
            snap = parsedate_to_datetime(lm).astimezone(timezone.utc)
        except (TypeError, ValueError):
            snap = None
    return body, snap


def read_csv(data: bytes | str) -> list[dict]:
    text = data.decode("utf-8-sig", "replace") if isinstance(data, bytes) else data.lstrip("﻿")
    return [r for r in csv.DictReader(io.StringIO(text)) if (r.get("HomeTeam") or "").strip()]


def _f(row: dict, col: str) -> float | None:
    v = (row.get(col) or "").strip()
    try:
        x = float(v)
    except ValueError:
        return None
    return x if x > 1.0 else None


def prefixes(header) -> list[str]:
    """Préfixes de books 1X2 « avant clôture » présents (colonnes P+H, P+D, P+A ; exclut les variantes C de clôture)."""
    cols = set(header)
    found = [c[:-1] for c in cols if c.endswith("H") and len(c) > 1 and c[:-1] + "D" in cols and c[:-1] + "A" in cols]
    return sorted(p for p in found if not (p.endswith("C") and p[:-1] in found))


def odds_1x2(row: dict, prefix: str, closing: bool = False) -> list[float] | None:
    p = prefix + ("C" if closing else "")
    o = [_f(row, p + s) for s in "HDA"]
    return o if all(o) else None


def odds_ou25(row: dict, prefix: str, closing: bool = False) -> list[float] | None:
    """[Plus de 2,5 ; Moins de 2,5] ou None."""
    p = {v: k for k, v in TOTALS_ALIAS.items()}.get(prefix, prefix) + ("C" if closing else "")
    o = [_f(row, p + ">2.5"), _f(row, p + "<2.5")]
    return o if all(o) else None


def parse_date(d: str) -> datetime:
    d = d.strip()
    return datetime.strptime(d, "%d/%m/%Y" if len(d.split("/")[-1]) == 4 else "%d/%m/%y")


def kickoff_utc(date: str, hhmm: str | None) -> datetime | None:
    """Date/heure UK -> UTC. Heure absente -> None (le match n'est pas daté précisément : on le signale)."""
    if not (hhmm or "").strip():
        return None
    h, m = (int(x) for x in hhmm.strip().split(":")[:2])
    return parse_date(date).replace(hour=h, minute=m, tzinfo=UK).astimezone(timezone.utc)


def result_index(row: dict) -> int | None:
    return {"H": 0, "D": 1, "A": 2}.get((row.get("FTR") or "").strip())


def to_event(row: dict, header, snapshot: datetime | None = None, closing: bool = False) -> dict | None:
    """Ligne CSV -> format interne du moteur (mêmes clés que oddsapi.normalize). None si heure absente."""
    ko = kickoff_utc(row.get("Date", ""), row.get("Time"))
    if ko is None:
        return None
    home, away = row["HomeTeam"].strip(), row["AwayTeam"].strip()
    lu = snapshot.isoformat() if snapshot else None
    books: dict[str, dict] = {}
    pre = prefixes(header)
    for p in pre + [a for a in TOTALS_ALIAS.values() if a not in pre]:
        entry: dict = {"last_update": lu, "title": p}
        o = odds_1x2(row, p, closing)
        if o:
            entry["h2h"] = {home: o[0], "Draw": o[1], away: o[2]}
        t = odds_ou25(row, p, closing)
        if t:
            entry["totals"] = {"2.5": {"Over": t[0], "Under": t[1]}}
        if len(entry) > 2:
            books[BOOK_KEYS.get(p, "fd_" + p.lower())] = entry
    div = row.get("Div", "?").strip()
    return {"id": f"fd|{div}|{ko.strftime('%Y-%m-%dT%H:%M')}|{home}|{away}", "sport": f"soccer_fd_{div}",
            "league": LEAGUES.get(div, div), "commence": ko.isoformat().replace("+00:00", "Z"),
            "home": home, "away": away, "books": books}


def load_fixtures(data: bytes | str, snapshot: datetime | None = None) -> list[dict]:
    rows = read_csv(data)
    if not rows:
        return []
    header = list(rows[0].keys())
    return [e for e in (to_event(r, header, snapshot) for r in rows) if e]
