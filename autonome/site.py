"""Résumé compact pour la page mobile (site/index.html) : site.json sur la branche data, réécrit à chaque passage.

La page (GitHub Pages, publiée une seule fois) lit ce fichier sur raw.githubusercontent.com : elle est à jour à chaque
passage sans redéploiement. Quatre onglets tenant chacun sur un écran : Alertes, Marché, Bilan, Santé.
Aucune donnée inventée : ce qui manque est absent (null) et la page l'affiche comme tel.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from . import lag as LG, paper as PP, store, tracker


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def _pnl(r):
    res = r.get("result") or {}
    if r.get("status") != "settled" or "won" not in res:
        return None
    if res["won"] is None:
        return 0.0
    return round(r["stake"] * (r["odds"] - 1), 2) if res["won"] else -float(r["stake"])


def _etat(r):
    if r.get("status") != "settled":
        return "en cours"
    res = r.get("result") or {}
    if "won" not in res:
        return "inconnu"
    won = res["won"]
    return "remboursé" if won is None else "gagné" if won else "perdu"


def history(rows: list[dict], bankroll: float, limit: int = 60) -> list[dict]:
    """Tous les paris (alertes), du plus récent au plus ancien, avec ce qu'il faut pour refaire le calcul à la main :
    p (probabilité juste), p_prudente (borne défavorable du bid/ask), EV = p × cote − 1. La mise (live.compare,
    value.stake) part de p_prudente : Kelly = (p_prudente × cote − 1)/(cote − 1), mise = min(1/4 Kelly, 2 %) × bankroll,
    arrondie à 0,50 € près, minimum 1 €. La mise affichée est celle enregistrée ; la bankroll est celle d'aujourd'hui."""
    out = []
    for r in sorted(rows, key=lambda r: r.get("found_at") or "", reverse=True)[:limit]:
        p, o, cl = r.get("p_fair"), r.get("odds"), r.get("close") or {}
        pk = r.get("p_cons") if r.get("p_cons") is not None else p
        kelly = None if pk is None or not o or o <= 1 else round((pk * o - 1) / (o - 1), 4)
        clv_ok = cl.get("clv_odds") is not None and (cl.get("minutes_to_start") or 1e9) <= tracker.CLOSE_MAX_MIN
        out.append({
            "vu": r.get("found_at"), "debut": r.get("commence"), "match": f"{r.get('home')} – {r.get('away')}",
            "pari": r.get("label") or r.get("selection"), "book": r.get("book"), "sport": r.get("sport"),
            "ref": r.get("ref_kind"), "cote": o, "p": _r(p), "p_prudente": _r(r.get("p_cons")), "juste": _r(r.get("fair_odds"), 3),
            "ev": _r(r.get("ev")), "ev_prudente": _r(r.get("ev_cons")), "kelly": kelly, "mise": r.get("stake"),
            "bankroll": bankroll, "etat": _etat(r), "gain": _pnl(r),
            "p_cloture": _r(cl.get("p_fair")) if clv_ok else None, "clv": _r(cl.get("clv_odds")) if clv_ok else None,
            "cloture_min": round(cl["minutes_to_start"]) if clv_ok else None, "suspect": tracker.suspect(r)})
    return out


def daily(runs: list[dict], bets: list[dict], now: datetime, days: int = 10) -> list[dict]:
    """Par jour (UTC) : passages, plus long trou entre deux passages (panne si > 30 min), alertes, erreurs."""
    ts = []
    for r in runs:
        try:
            t = datetime.fromisoformat(r["at"].replace("Z", "+00:00"))
        except (KeyError, ValueError, AttributeError, TypeError):
            continue
        ts.append(t if t.tzinfo else t.replace(tzinfo=timezone.utc))
    ts.sort()
    picks: dict = {}
    for b in bets:
        d = (b.get("found_at") or "")[:10]
        picks[d] = picks.get(d, 0) + 1
    by: dict = {}
    for i, t in enumerate(ts):
        e = by.setdefault(t.date().isoformat(), {"passages": 0, "trou": 0.0})
        e["passages"] += 1
        if i:  # trou qui se termine ce jour-là
            e["trou"] = max(e["trou"], (t - ts[i - 1]).total_seconds() / 60)
    if ts:  # trou en cours (aucun passage depuis le dernier)
        e = by.setdefault(now.date().isoformat(), {"passages": 0, "trou": 0.0})
        e["trou"] = max(e["trou"], (now - ts[-1]).total_seconds() / 60)
    if ts:  # jours sans aucun passage (panne d'une journée entière) : listés aussi
        day = ts[0].date()
        while day <= now.date():
            by.setdefault(day.isoformat(), {"passages": 0, "trou": 1440.0})
            day += timedelta(days=1)
    out = [{"jour": d, "passages": v["passages"], "trou_max_min": round(v["trou"]), "alertes": picks.get(d, 0)}
           for d, v in sorted(by.items())]
    return [x for x in out if x["jour"] >= (now - timedelta(days=days)).date().isoformat()]


def _bankroll() -> float:
    try:
        return float(os.environ.get("BANKROLL") or 100)
    except ValueError:
        return 100.0


def build(root, meta: dict, obs: dict | None, now: datetime) -> dict:
    obs = obs or {}
    rows = store.read(root, tracker.BETS)
    alerts = []
    for r in rows:
        if r.get("status") != "open" or tracker.suspect(r):
            continue
        try:
            if datetime.fromisoformat(r["commence"].replace("Z", "+00:00")) <= now:
                continue
        except (KeyError, ValueError):
            continue
        alerts.append({"match": f"{r.get('home')} – {r.get('away')}", "pari": r.get("label") or r.get("selection"),
                       "book": r.get("book"), "cote": r.get("odds"), "juste": _r(r.get("fair_odds"), 2),
                       "ev": _r(r.get("ev")), "mise": r.get("stake"), "debut": r.get("commence"), "url": r.get("url"),
                       "ref": r.get("ref_kind")})
    alerts.sort(key=lambda a: a["debut"] or "")
    near = [{"match": f"{t.get('home')} – {t.get('away')}", "pari": t.get("label"), "book": t.get("book"),
             "cote": t.get("odds"), "juste": _r(t.get("fair_odds"), 2), "ev": _r(t.get("ev")), "debut": t.get("commence")}
            for t in (obs.get("top") or [])[:6]]
    books = []
    for bk, fams in (obs.get("by_book") or {}).items():
        n = sum(v.get("n", 0) for v in fams.values())
        if not n:
            continue
        best = max((v.get("max_ev") for v in fams.values() if v.get("max_ev") is not None), default=None)
        main = fams.get("1x2") or fams.get("ml") or max(fams.values(), key=lambda v: v.get("n", 0))
        books.append({"book": bk, "cotes": n, "ev_mediane": _r(main.get("median_ev")), "meilleure": _r(best)})
    books.sort(key=lambda b: -(b["meilleure"] if b["meilleure"] is not None else -9))
    st = tracker.stats(root)
    paper = [{"nom": x["name"], "paris": x["n"], "regles": x["settled"], "roi": _r(x["roi"]), "clv": _r(x["clv"]),
              "bankroll": round(x["bankroll"], 2)} for x in PP.summary(store.read(root, PP.FILE))]
    lag = [{"book": x["book"], "suivis": x["followed"], "pas_suivis": x["not_followed"], "mediane_min": x["median_min"],
            "en_15min": _r(x["within_15"], 3)} for x in LG.summary(store.read(root, "lag.jsonl"), now)]
    paused = sorted({r["source"] for r in store.read(root, "backoff.jsonl") if r.get("until", "") > now.isoformat()})
    return {
        "maj": now.astimezone(timezone.utc).isoformat(),
        "alertes": alerts[:8],
        "proches": near,
        "books": books[:8],
        "bilan": {"paris": st["bets_total"], "regles": st["bets_settled"], "roi": _r(st["roi"]["roi"]),
                  "gain": _r(st["roi"]["pnl"], 2), "mises": _r(st["roi"]["staked"], 2), "ecartes": st["bets_suspect"],
                  "clv": _r(st["clv"].get("mean")), "n_clv": st["clv"]["n"],
                  "clv_ic": [_r(x) for x in st["clv"]["ci95"]] if st["clv"].get("ci95") else None},
        "historique": history(rows, _bankroll()),
        "jours": daily(store.read(root, "runs.jsonl"), rows, now),
        "fictif": paper,
        "retard": lag[:6],
        "sante": {"cotes": obs.get("n"), "ev_pos": obs.get("n_ev_pos"), "matchs_ref": meta.get("ref_soon"),
                  "apparies": meta.get("pairs"),
                  "sources": {"PMU": meta.get("pmu_events"), "Betclic": meta.get("betclic_events"),
                              "Winamax": meta.get("winamax_events"), "NetBet": meta.get("netbet_pages"),
                              "Unibet": meta.get("unibet_events"), "coteur": meta.get("coteur_matchs")},
                  "en_pause": paused, "erreurs": [e[:90] for e in (meta.get("errors") or [])
                              if not (e.startswith("kambi") and "HTTP 404" in e)][:4]},  # 404 Kambi : sports vides, connus
    }
