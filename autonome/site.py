"""Résumé compact pour la page mobile (site/index.html) : site.json sur la branche data, réécrit à chaque passage.

La page (GitHub Pages, publiée une seule fois) lit ce fichier sur raw.githubusercontent.com : elle est à jour à chaque
passage sans redéploiement. Quatre onglets tenant chacun sur un écran : Alertes, Marché, Bilan, Santé.
Aucune donnée inventée : ce qui manque est absent (null) et la page l'affiche comme tel.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import lag as LG, paper as PP, store, tracker
from .tracker import suspect


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def _pnl(r):
    res = r.get("result") or {}
    if r.get("status") != "settled" or "won" not in res:
        return None
    if res["won"] is None:
        return 0.0
    return round(r["stake"] * (r["odds"] - 1), 2) if res["won"] else -float(r["stake"])


def _etat(r, now: datetime | None = None):
    if r.get("status") != "settled":
        return "à régler" if now and tracker.a_regler(r, now) else "en cours"
    res = r.get("result") or {}
    if "won" not in res:
        return "inconnu"
    won = res["won"]
    return "remboursé" if won is None else "gagné" if won else "perdu"


BOOK_FR = {"pmu_fr": "PMU", "betclic_fr": "Betclic", "winamax_fr": "Winamax", "unibet_fr": "Unibet", "netbet_fr": "NetBet",
           "betsson_fr": "Betsson", "olybet_fr": "Olybet", "vbet_fr": "Vbet", "daznbet_fr": "DAZN Bet", "genybet_fr": "Genybet",
           "feelingbet_fr": "Feelingbet", "parionssport_fr": "Parions Sport", "zebet_fr": "ZEbet", "pokerstars_fr": "PokerStars",
           "barrierebet_fr": "Barrière"}
WHY_SUSPECT = {"marche_fige_50_50": "Écarté après coup : le marché Polymarket était figé à 50/50, ce qui annonce en général "
                                    "un forfait ou une annulation, pas une vraie chance sur deux.",
               "ev_trop_grande": "Écarté après coup : un écart de plus de 30 % est presque toujours une erreur de la "
                                 "référence, pas une vraie value."}


def _n(x, d=2):
    return f"{x:.{d}f}".replace(".", ",").replace("-", "−")


def _pc(x, sign=False, d=1):
    return ("+" if sign and x > 0 else "") + _n(x * 100, d) + " %"


def pourquoi(r: dict) -> str | None:
    """Résumé en 2-3 phrases simples : pourquoi ce pari, et ce qu'il a donné. Uniquement les chiffres enregistrés."""
    p, o, ev = r.get("p_fair"), r.get("odds"), r.get("ev")
    if p is None or not o or ev is None:
        return None
    kind = str(r.get("group", "")).split("@")[0]
    lab = r.get("label") or str(r.get("selection") or "")
    pick = lab.split(" : ", 1)[1] if " : " in lab else lab
    if kind in ("1x2", "ml") and pick.lower() in ("nul", "draw"):
        evt = "le match se termine sur un nul"
    elif kind in ("1x2", "ml") and pick:
        evt = f"{pick} gagne"
    else:
        evt = f"« {lab} » passe"
    src = ("Les autres bookmakers français, une fois leur marge retirée," if r.get("ref_kind") == "consensus-anj"
           else "Sur Polymarket, les parieurs")
    que = "qu'" if evt[:1].lower() in "aeiouyhàâéèêîôû" and not evt.startswith("«") else "que "
    out = [f"{src} donnent {_pc(p)} de chances {que}{evt} : la cote juste est donc {_n(1 / p)}."]
    sus = suspect(r)
    if sus:
        out.append(WHY_SUSPECT.get(sus, "Écarté après coup : référence douteuse."))
        return " ".join(out)
    book = BOOK_FR.get(r.get("book"), r.get("book") or "Le bookmaker")
    s2 = f"{book} paie {_n(o)}, plus que ce que ça vaut : sur le long terme, ce genre de pari rapporte {_pc(ev, True)} de la mise"
    s2 += " en moyenne." if (r.get("ev_cons") or 0) > 0 else " en moyenne, mais l'avantage est fragile."
    out.append(s2)
    res, cl = r.get("result") or {}, r.get("close") or {}
    clv_ok = cl.get("clv_odds") is not None and (cl.get("minutes_to_start") or 1e9) <= tracker.CLOSE_MAX_MIN
    if r.get("status") == "settled" and "won" in res:
        g = _pnl(r)
        s3 = ("Mise rendue." if res["won"] is None else f"Gagné, {'+' if g > 0 else ''}{_n(g)} €." if res["won"]
              else f"Perdu, {_n(g)} €.")
        if clv_ok and cl.get("p_fair"):
            fin = _n(1 / cl["p_fair"])
            s3 += (f" Au coup d'envoi, la cote juste était de {fin} : les {_n(o)} pris valaient mieux que le marché final, "
                   f"bon signe." if cl["clv_odds"] > 0 else
                   f" Au coup d'envoi, la cote juste était de {fin}, au-dessus des {_n(o)} pris : ce n'était finalement "
                   f"pas une value, le gain tient de la chance.")
        out.append(s3)
    elif ev >= 0.10:
        out.append("L'écart est grand : vérifie qu'aucune info (blessure, composition) ne l'explique avant de jouer.")
    elif r.get("stake"):
        out.append(f"Mise conseillée {_n(r['stake'])} €, volontairement petite : même un bon pari perd souvent.")
    return " ".join(out)


def history(rows: list[dict], bankroll: float, limit: int = 60, now: datetime | None = None) -> list[dict]:
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
            "bankroll": bankroll, "etat": _etat(r, now), "gain": _pnl(r),
            "p_cloture": _r(cl.get("p_fair")) if clv_ok else None, "clv": _r(cl.get("clv_odds")) if clv_ok else None,
            "cloture_min": round(cl["minutes_to_start"]) if clv_ok else None, "suspect": tracker.suspect(r),
            "pourquoi": pourquoi(r)})
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


def repeated(runs: list[dict], last: int = 50, min_n: int = 3) -> dict:
    """Erreurs revenues sur au moins `min_n` des `last` derniers passages (une fois par passage), y compris les 404
    PMU masqués de la liste du dernier passage : une source qui échoue en boucle se voit sur la page."""
    tail = [r for r in runs if isinstance(r, dict)][-last:]
    c = Counter(e for r in tail for e in set(x for x in (r.get("errors") or []) if isinstance(x, str)))
    top = [{"erreur": e[:90], "passages": n} for e, n in c.most_common() if n >= min_n]
    return {"sur": len(tail), "n": len(top), "top": top[:5]}


# Page d'entrée « Aujourd'hui » (vague 2, approuvée le 09/11/2026) : schéma commun aux 3 dépôts (aujourdhui.json chez
# cotes-value et cotes-boostees ; ici un bloc de site.json). Verdict = gabarit rempli avec les chiffres calculés.
SITE_URL = "https://matttgic.github.io/Autonome/"
N_REQUIS = 460  # docs/PROTOCOLE.md P3 : paris avec clôture pour juger une CLV à 1 % près (borne basse, une stratégie)


def _sante(meta: dict, paused: list[str], now: datetime) -> dict:
    """ok / degrade / panne d'après le dernier passage (l'âge du passage est jugé par la page, à la lecture)."""
    pmu, ct = meta.get("pmu_events") or 0, sum(1 for v in (meta.get("coteur_books") or {}).values() if v)
    if not meta.get("ref_games"):
        etat, msg = "panne", "référence Polymarket non lue au dernier passage : aucune détection possible"
    elif not pmu or not ct:
        etat = "degrade"
        msg = " et ".join(x for x, ok in (("PMU", pmu), ("coteur.com", ct)) if not ok) + " non lu(s) au dernier passage"
    else:
        etat, msg = "ok", f"PMU : {pmu} matchs lus ; coteur.com : {ct} bookmakers lus"
    if paused:
        msg += f" ; en pause : {', '.join(paused)}"
    return {"etat": etat, "message": msg[:200], "derniere_collecte": meta.get("at") or now.isoformat()}


def verdict(st: dict) -> str:
    """Une ligne, chiffres calculés seulement (CLV par pari = par match : un seul pari par match)."""
    clv, n = st["clv"], st["clv"]["n"]
    roi = st["roi"]
    if not n:
        return f"Autonome : aucun pari avec clôture mesurée pour l'instant (0 / {N_REQUIS} nécessaires)."
    ci = clv.get("ci95")
    ic = f" (IC 95 % {_pc(ci[0], True)} à {_pc(ci[1], True)})" if ci else ""
    out = f"Autonome : CLV moyenne {_pc(clv['mean'], True)}{ic} sur {n} paris"
    if roi.get("n"):
        out += f", ROI {_pc(roi['roi'], True)} sur {roi['n']} réglés"
    if n < N_REQUIS:
        return out + f" ; {n} / {N_REQUIS} nécessaires : trop tôt pour conclure."
    return out + (" : avantage démontré (borne basse de l'IC > 0)." if ci and ci[0] > 0
                  else " : pas d'avantage démontré.")


def aujourdhui(meta: dict, alerts: list[dict], st: dict, paused: list[str], now: datetime) -> dict:
    return {"depot": "Autonome", "url": SITE_URL, "genere_le": now.astimezone(timezone.utc).isoformat(),
            "sante": _sante(meta, paused, now),
            "a_jouer": [{"match": a["match"], "debut": a["debut"], "bookmaker": BOOK_FR.get(a["book"], a["book"]),
                         "pari": a["pari"], "cote": a["cote"], "cote_juste": a["juste"], "ev": a["ev"],
                         "lien": a["url"] if str(a.get("url") or "").startswith("https://") else None}
                        for a in alerts[:5]],
            "verdict": verdict(st)}


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
    st = tracker.stats(root, now)
    paper = [{"nom": x["name"], "paris": x["n"], "regles": x["settled"], "roi": _r(x["roi"]), "clv": _r(x["clv"]),
              "bankroll": round(x["bankroll"], 2)} for x in PP.summary(store.read(root, PP.FILE))]
    lag = [{"book": x["book"], "suivis": x["followed"], "pas_suivis": x["not_followed"], "mediane_min": x["median_min"],
            "en_15min": _r(x["within_15"], 3)} for x in LG.summary(store.read(root, "lag.jsonl"), now)]
    paused = sorted({r["source"] for r in store.read(root, "backoff.jsonl") if r.get("until", "") > now.isoformat()})
    runs = store.read(root, "runs.jsonl")
    return {
        "maj": now.astimezone(timezone.utc).isoformat(),
        "aujourdhui": aujourdhui(meta, alerts, st, paused, now),
        "alertes": alerts[:8],
        "proches": near,
        "books": books[:8],
        "bilan": {"paris": st["bets_total"], "regles": st["bets_settled"], "a_regler": st["bets_a_regler"],
                  "n_requis": N_REQUIS,
                  "roi": _r(st["roi"]["roi"]),
                  "gain": _r(st["roi"]["pnl"], 2), "mises": _r(st["roi"]["staked"], 2), "ecartes": st["bets_suspect"],
                  "clv": _r(st["clv"].get("mean")), "n_clv": st["clv"]["n"],
                  "clv_ic": [_r(x) for x in st["clv"]["ci95"]] if st["clv"].get("ci95") else None},
        "historique": history(rows, _bankroll(), now=now),
        "jours": daily(runs, rows, now),
        "fictif": paper,
        "retard": lag[:6],
        "sante": {"cotes": obs.get("n"), "ev_pos": obs.get("n_ev_pos"), "matchs_ref": meta.get("ref_soon"),
                  "apparies": meta.get("pairs"),
                  "sources": {"PMU": meta.get("pmu_events"), "Betclic": meta.get("betclic_events"),
                              "Winamax": meta.get("winamax_events"), "NetBet": meta.get("netbet_pages"),
                              "Unibet": meta.get("unibet_events"), "coteur": meta.get("coteur_matchs")},
                  "en_pause": paused, "pmu_groupes_en_pause": meta.get("pmu_groupes_en_pause"),
                  "erreurs_repetees": repeated(runs),
                  "erreurs": [e[:90] for e in (meta.get("errors") or [])
                              if not (e.startswith("kambi") and "HTTP 404" in e)][:4]},  # 404 Kambi : sports vides, connus
    }
