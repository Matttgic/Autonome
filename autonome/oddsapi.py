"""Source The Odds API (officielle, clé gratuite 500 crédits/mois). Stdlib uniquement."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.the-odds-api.com/v4"


class OddsApiError(RuntimeError):
    pass


class Client:
    def __init__(self, key: str | None = None, timeout: int = 25):
        self.key = key or os.environ.get("ODDS_API_KEY", "")
        self.timeout = timeout
        self.remaining: int | None = None
        self.used: int | None = None

    def _get(self, path: str, **params):
        if not self.key:
            raise OddsApiError("ODDS_API_KEY manquante")
        q = urllib.parse.urlencode({**params, "apiKey": self.key})
        req = urllib.request.Request(f"{BASE}{path}?{q}", headers={"User-Agent": "autonome/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self.remaining = _int(r.headers.get("x-requests-remaining"), self.remaining)
                self.used = _int(r.headers.get("x-requests-used"), self.used)
                return json.load(r)
        except urllib.error.HTTPError as e:  # ne jamais inclure l'URL (clé) dans le message
            raise OddsApiError(f"HTTP {e.code} sur {path}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise OddsApiError(f"réseau: {type(e).__name__} sur {path}") from None

    def sports(self) -> list[dict]:  # gratuit (0 crédit)
        return self._get("/sports")

    def odds(self, sport: str, markets: str = "h2h", regions: str = "eu") -> list[dict]:
        return self._get(f"/sports/{sport}/odds", regions=regions, markets=markets,
                         oddsFormat="decimal", dateFormat="iso")

    def scores(self, sport: str, days_from: int = 3) -> list[dict]:
        return self._get(f"/sports/{sport}/scores", daysFrom=days_from, dateFormat="iso")


def _int(v, default):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def normalize(raw_event: dict) -> dict:
    """Format API -> format interne.

    books[book] = {"last_update": iso, "h2h": {nom: cote}, "totals": {point: {"Over": c, "Under": c}}}
    """
    books: dict[str, dict] = {}
    for b in raw_event.get("bookmakers", []):
        entry: dict = {"last_update": b.get("last_update"), "title": b.get("title", b["key"])}
        for m in b.get("markets", []):
            if m["key"] == "h2h":
                entry["h2h"] = {o["name"]: float(o["price"]) for o in m["outcomes"]}
            elif m["key"] == "totals":
                t: dict = {}
                for o in m["outcomes"]:
                    t.setdefault(str(o["point"]), {})[o["name"]] = float(o["price"])
                entry["totals"] = t
        books[b["key"]] = entry
    return {"id": raw_event["id"], "sport": raw_event.get("sport_key"), "commence": raw_event["commence_time"],
            "home": raw_event.get("home_team"), "away": raw_event.get("away_team"), "books": books}


def result_of(score_event: dict) -> dict | None:
    """Résultat 'home'/'away'/'draw' + total buts, si l'événement est terminé."""
    if not score_event.get("completed") or not score_event.get("scores"):
        return None
    sc = {s["name"]: float(s["score"]) for s in score_event["scores"]}
    h, a = sc.get(score_event["home_team"]), sc.get(score_event["away_team"])
    if h is None or a is None:
        return None
    return {"home_score": h, "away_score": a, "total": h + a}
