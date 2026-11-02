"""Résumé compact pour la page mobile (site/index.html) : site.json sur la branche data, réécrit à chaque passage.

La page (GitHub Pages, publiée une seule fois) lit ce fichier sur raw.githubusercontent.com : elle est à jour à chaque
passage sans redéploiement. Quatre onglets tenant chacun sur un écran : Alertes, Marché, Bilan, Santé.
Aucune donnée inventée : ce qui manque est absent (null) et la page l'affiche comme tel.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import lag as LG, paper as PP, store, tracker


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def build(root, meta: dict, obs: dict | None, now: datetime) -> dict:
    obs = obs or {}
    rows = store.read(root, tracker.BETS)
    alerts = []
    for r in rows:
        if r.get("status") != "open":
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
                  "clv": _r(st["clv"].get("mean")), "n_clv": st["clv"]["n"]},
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
