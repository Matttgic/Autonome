#!/usr/bin/env python3
"""Backtest des cotes boostées Winamax (archive coteur.com) contre Polymarket (prix ~60 min avant le match).

Usage : python tools/boost_backtest.py page_cotes_boostees.html sortie.json
Pour chaque boost « un match » de football reconnu par les gabarits de autonome/boosts.py :
  - match retrouvé parmi les événements Polymarket clos (titre, sens domicile/extérieur) ;
  - prix CLOB à T-60 min (prices-history) des marchés 1X2, plus/moins, 2 marquent, buts par équipe ;
  - modèle Dixon-Coles calé -> proba juste du boost -> EV ; résultat réel via le marché « score exact » résolu.
Requêtes publiques, 4 fils, pause 0,2 s. Aucune cote inventée : toute donnée manquante exclut le boost.
"""
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autonome import boosts as BO, scoremodel as SM  # noqa: E402
from autonome.sources import coteur  # noqa: E402

TAGS = ["ligue-1", "epl", "la-liga", "bundesliga", "serie-a", "ucl", "uel"]
SINCE = "2026-08-01"


def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "autonome-backtest/0.1"})
    for k in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001
            time.sleep(1 + k)
    return None


def closed_events():
    out = {}
    for t in TAGS:
        off = 0
        while True:
            d = get(f"https://gamma-api.polymarket.com/events?tag_slug={t}&closed=true&limit=100&offset={off}"
                    f"&order=startTime&ascending=false")
            if not d:
                break
            for e in d:
                out[e["id"]] = e
            off += 100
            if (d[-1].get("startTime") or "") < SINCE or off > 3000:
                break
            time.sleep(0.3)
    return list(out.values())


def games_from(events):
    g = {}
    for e in events:
        base, _, suf = (e.get("title") or "").partition(" - ")
        if " vs. " not in base or not e.get("startTime") or e["startTime"] < SINCE:
            continue
        h, a = [x.strip() for x in base.split(" vs. ", 1)]
        x = g.setdefault(f"{base}|{e['startTime'][:16]}", {"key": base, "home": h, "away": a, "commence": e["startTime"],
                                                         "ev": {}})
        x["ev"][suf or "main"] = e
    return [x for x in g.values() if "main" in x["ev"]]


def price_at(tok, st):
    d = get(f"https://clob.polymarket.com/prices-history?market={tok}&startTs={st - 7 * 3600}&endTs={st - 3600}&fidelity=10")
    pts = [p for p in (d or {}).get("history", []) if p["t"] <= st - 3600]
    return pts[-1]["p"] if pts else None


def leg(p):
    return {"p": p, "lo": p, "hi": p, "legs": [], "spread": 0.0}


def markets_at(game):
    st = int(datetime.fromisoformat(game["commence"].replace("Z", "+00:00")).timestamp())
    mk, h, a = {}, game["home"], game["away"]
    q = {}
    for m in game["ev"]["main"].get("markets", []):
        lab = m.get("groupItemTitle") or ""
        sel = "draw" if lab.lower().startswith("draw") else "home" if lab == h else "away" if lab == a else None
        if sel:
            q[sel] = price_at(json.loads(m["clobTokenIds"])[0], st)
    if len(q) == 3 and all(q.values()):
        s = sum(q.values())
        mk["1x2"] = {k: leg(v / s) for k, v in q.items()}
    else:
        return None
    for m in (game["ev"].get("More Markets") or {}).get("markets", []):
        t, lab = m.get("sportsMarketType"), m.get("groupItemTitle") or ""
        line = m.get("line")
        want = (t == "totals" and line in (1.5, 2.5, 3.5)) or t == "both_teams_to_score" or \
               (t == "soccer_team_totals" and line in (0.5, 1.5))
        if not want:
            continue
        p = price_at(json.loads(m["clobTokenIds"])[0], st)
        if p is None:
            continue
        if t == "totals":
            mk[f"ou@{line:g}"] = {"over": leg(p), "under": leg(1 - p)}
        elif t == "both_teams_to_score":
            mk["btts"] = {"yes": leg(p), "no": leg(1 - p)}
        else:
            side = "home" if lab.startswith(h) else "away" if lab.startswith(a) else None
            if side:
                mk[f"team_ou@{side}@{line:g}"] = {"over": leg(p), "under": leg(1 - p)}
    return mk


def final_score(game):
    ex = game["ev"].get("Exact Score")
    for m in (ex or {}).get("markets", []):
        try:
            if json.loads(m.get("outcomePrices") or "[]")[0] in ("1", 1, "1.0"):
                r = re.search(r" (\d+) - (\d+) ", m.get("groupItemTitle") or "")
                return (int(r.group(1)), int(r.group(2))) if r else None
        except (ValueError, IndexError):
            pass
    return None


def main(page, out):
    boosts = coteur.parse(open(page, encoding="utf-8", errors="replace").read(), limit=10000)
    games = games_from(closed_events())
    print(f"boosts {len(boosts)} ; matchs Polymarket clos depuis {SINCE} : {len(games)}", file=sys.stderr)
    todo = []
    for b in boosts:
        legs, why = BO.translate(b, games, allow_team_legs=False)
        if legs and len(legs) == 1:
            todo.append((b, legs[0]))
    print(f"boosts un-match reconnus et appariés : {len(todo)}", file=sys.stderr)
    need = {id(l[0]): l[0] for _, l in todo}

    def prep(g):
        return id(g), markets_at(g), final_score(g)
    with ThreadPoolExecutor(4) as ex:
        res = {k: (m, s) for k, m, s in ex.map(prep, need.values())}
    rows = []
    for b, (g, pred, side, args) in todo:
        mk, score = res[id(g)]
        if not mk:
            continue
        f = SM.fit(mk)
        if not f or f["max_err"] > 0.03:
            continue
        fn = BO.PRED[pred](side, args)
        p = SM.prob(f["grid"], fn)
        rows.append({"match": f"{g['home']} – {g['away']}", "commence": g["commence"], "text": b["text"],
                     "odds": b["odds"], "p": p, "ev": p * b["odds"] - 1, "fit_err": f["max_err"],
                     "won": (fn(*score) if score else None)})
    json.dump(rows, open(out, "w"), ensure_ascii=False, indent=1)
    n = len(rows)
    if n:
        evs = sorted(r["ev"] for r in rows)
        settled = [r for r in rows if r["won"] is not None]
        pnl = sum((r["odds"] - 1) if r["won"] else -1 for r in settled)
        print(f"boosts évalués {n} ; EV moyenne {sum(evs) / n:+.1%} ; médiane {evs[n // 2]:+.1%} ; "
              f"part EV>0 {sum(e > 0 for e in evs) / n:.0%} ; part EV>5% {sum(e > 0.05 for e in evs) / n:.0%}")
        print(f"réglés {len(settled)} ; ROI réel à mise fixe {pnl / max(1, len(settled)):+.1%}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
