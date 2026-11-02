"""Unibet.fr (agréé ANJ) : page publique /paris-football rendue côté serveur (aucune connexion, aucun JS exécuté).

Faits vérifiés le 2026-11-02 depuis GitHub Actions : /paris-football → HTTP 200, ~54 matchs mis en avant avec leur
1X2 (« psel-outcome ») + liste JSON-LD (SportsEvent : nom, URL, heure locale Paris). Les sous-pages (compétition,
match) renvoient 503 depuis GitHub : seules les cotes de la page principale sont lisibles. Cote « - » = absente.
"""
from __future__ import annotations

import html as H
import http.client
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = "https://www.unibet.fr"
PAGES = ["/paris-football"]
UA = "autonome/0.3 (outil perso; 1 requete / 5 s)"
PARIS = ZoneInfo("Europe/Paris")


class SourceError(RuntimeError):
    pass


def fetch(path: str, timeout: int = 30, pause: float = 5.0) -> str:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(5_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise SourceError(f"unibet {path}: HTTP {e.code}") from None
    except (OSError, http.client.HTTPException) as e:
        raise SourceError(f"unibet {path}: {type(e).__name__}") from None
    finally:
        time.sleep(pause)


def _odd(t: str) -> float | None:
    try:
        x = float(t.strip().replace(",", "."))
    except ValueError:
        return None
    return x if x > 1.0 else None


def _starts(page: str) -> dict[str, str]:
    """URL relative -> heure UTC ISO, depuis le JSON-LD SportsEvent (heure locale de Paris, sans fuseau)."""
    out = {}
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for e in data if isinstance(data, list) else [data]:
            if isinstance(e, dict) and e.get("@type") == "SportsEvent" and e.get("url") and e.get("startDate"):
                try:
                    t = datetime.fromisoformat(e["startDate"])
                except ValueError:
                    continue
                t = (t.replace(tzinfo=PARIS) if t.tzinfo is None else t).astimezone(ZoneInfo("UTC"))
                out[e["url"].replace(BASE, "")] = t.isoformat().replace("+00:00", "Z")
    return out


def parse_page(page: str) -> list[dict]:
    starts = _starts(page)
    out = []
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)  # commentaires Angular entre les balises
    for blk in page.split('class="psel-event"')[1:]:
        try:
            href = re.search(r'class="psel-event__link"[^>]*href="([^"]+)"', blk)
            names = [H.unescape(x).strip() for x in re.findall(r'psel-opponent__name">([^<]*)<', blk)]
            if not href or len(names) != 2 or href.group(1) not in starts:
                continue
            tab = re.search(r'<table class="psel-market[^"]*"(.*?)</table>', blk, re.S)
            if not tab:
                continue
            outs = re.findall(r'psel-outcome__label">([^<]*)</span><span class="psel-outcome__data">([^<]*)<', tab.group(1))
            labels = [H.unescape(l).strip() for l, _ in outs]
            if len(outs) != 3 or labels != [names[0], "N", names[1]]:
                continue  # pas un 1X2 complet et étiqueté : ignoré (jamais deviné)
            odds = {k: _odd(o) for k, (_, o) in zip(("home", "draw", "away"), outs)}
            comp = re.search(r'psel-event-info__competition">([^<]*)<', blk)
            out.append({"id": "ub|" + href.group(1).rstrip("/").split("/")[-2], "url": BASE + href.group(1),
                        "commence": starts[href.group(1)], "home": names[0], "away": names[1],
                        "competition": H.unescape(comp.group(1)) if comp else "",
                        "odds": {"1x2": {k: v for k, v in odds.items() if v}}})
        except (AttributeError, IndexError, ValueError):
            continue
    return out
