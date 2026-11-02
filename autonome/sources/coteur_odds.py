"""Instantané coteur.com (tools/coteur_stream.py, workflow coteur) -> événements par bookmaker ANJ.

Cotes du marché principal (1N2 en foot, vainqueur en tennis/basket…) de ~20 bookmakers ANJ dont Winamax et Betclic.
Filtres : cote marquée désactivée (= retirée par le book), cote inchangée depuis plus de 48 h, ou instantané trop vieux =>
ignorée (une cote figée n'est jamais présentée comme une value).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

BOOKS = {20: "unibet_fr", 21: "pmu_fr", 22: "parionssport_fr", 24: "betclic_fr", 30: "netbet_fr", 32: "genybet_fr",
         33: "winamax_fr", 34: "zebet_fr", 36: "pokerstars_fr", 37: "vbet_fr", 38: "barrierebet_fr", 42: "feelingbet_fr",
         43: "betsson_fr", 44: "olybet_fr", 46: "daznbet_fr"}   # 45 (Bet365) et 23 (Bwin) : non agréés / absents -> exclus
SPORT = {"foot": "FOOTBALL", "tennis": "TENNIS", "basket": "BASKETBALL", "hockey": "ICE_HOCKEY", "rugby": "RUGBY",
         "handball": "HANDBALL", "volley": "VOLLEYBALL"}


def _ts(s):
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def load(path, now: datetime, max_snapshot_h: float = 3.0, max_age_h: float = 6.0):
    """-> (événements par book {book: [event]}, matchs bruts avec cotes fraîches, raison si inutilisable)."""
    p = Path(path)
    if not p.exists():
        return {}, [], "pas d'instantané coteur"
    try:
        d = json.loads(p.read_text())
    except (ValueError, OSError) as e:
        return {}, [], f"instantané coteur illisible ({type(e).__name__})"
    if not isinstance(d, dict) or not isinstance(d.get("matches"), dict):
        return {}, [], "instantané coteur de forme inattendue"
    snap = _ts(d.get("collected_at"))
    if not snap or (now - snap).total_seconds() > max_snapshot_h * 3600:
        return {}, [], f"instantané coteur trop vieux ({d.get('collected_at')})"
    by_book: dict[str, list] = {}
    matches = []
    for rid, m in (d.get("matches") or {}).items():
        try:
            name = m.get("name") or ""
            if " - " not in name or not m.get("ts"):
                continue
            home, away = [x.strip() for x in name.split(" - ", 1)]
            start = datetime.fromtimestamp(int(m["ts"]), timezone.utc).isoformat().replace("+00:00", "Z")
            fresh, fresh_upd = {}, {}
            for key, vals in (m.get("odds") or {}).items():
                typ, _, special = str(key).partition("|")
                if typ not in ("1n2", "12") or special:
                    continue
                if typ == "12" and m.get("sport") == "foot":
                    continue  # « 12 » en football = double chance, pas un vainqueur
                for v in vals:
                    u = _ts(v.get("upd"))
                    if v.get("off") or not u or (snap - u).total_seconds() > max_age_h * 3600 or v.get("book") not in BOOKS:
                        continue
                    o = v.get("odds") or {}
                    if typ == "1n2":
                        sel = {"home": o.get("1"), "draw": o.get("0"), "away": o.get("2")}
                        mk = "1x2"
                    else:
                        sel = {"home": o.get("1"), "away": o.get("2")}
                        mk = "ml"
                    sel = {k: float(x) for k, x in sel.items() if isinstance(x, (int, float)) and 1.0 < x < 1000}
                    bk = BOOKS[v["book"]]
                    if sel and u > fresh_upd.get((bk, mk), u.min.replace(tzinfo=timezone.utc)):
                        fresh.setdefault(bk, {})[mk] = sel  # doublon : on garde la plus récente
                        fresh_upd[(bk, mk)] = u
            if not fresh:
                continue
            base = {"commence": start, "home": home, "away": away, "competition": str(m.get("compet") or ""),
                    "snapshot_age_min": (now - snap).total_seconds() / 60,
                    "sport": SPORT.get(m.get("sport"), (m.get("sport") or "").upper()),
                    "url": "https://www.coteur.com" + (m.get("href") or ""), "renc": rid}
            matches.append({**base, "books": fresh})
            for bk, odds in fresh.items():
                by_book.setdefault(bk, []).append({**base, "id": f"ct|{rid}|{bk}", "odds": odds})
        except Exception:  # noqa: BLE001 - un match malformé n'invalide pas l'instantané
            continue
    return by_book, matches, None
