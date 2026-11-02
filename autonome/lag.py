"""Retard des bookmakers sur la référence Polymarket : combien de minutes un book met à suivre un mouvement de marché.

Idée tirée de la recherche du 02/11/2026 (6 min à 1 h de retard selon un fournisseur de données, 28 matchs) : on le
mesure nous-mêmes, par book et famille de marché. Règles (10e revue adverse) :
- sources lues en direct seulement (PMU, Betclic, NetBet, Unibet, Winamax) : l'heure d'un instantané coteur ne dit pas
  quand la cote a changé ; une seule issue suivie par marché (domicile / plus / oui / favori / 1X) ;
- ancre = probabilité Polymarket et cote du book au dernier changement de la cote du book ; un changement de cote ne
  compte que s'il déplace la probabilité implicite d'au moins BOOK_MIN (1 point) ;
- mouvement = la référence s'écarte de l'ancre d'au moins THR (2 points) ; s'il se retourne au-delà de l'ancre, il
  redémarre dans l'autre sens ; s'il revient à moins de THR/2, il est abandonné (« reverted ») ;
- le book change dans le même sens -> « followed » avec délai [lag_min_lo ; lag_min] (borne basse = dernier relevé sans
  changement) ; dans le sens contraire -> « opposite » ; si référence et book bougent entre deux relevés -> « followed »
  avec délai ≤ un passage ;
- relevés espacés de plus de GAP_MIN (fin de job, pause, budget…) -> rien n'est déduit : ré-ancrage, « unobserved » ;
- coup d'envoi : « not_followed » seulement si la cote était encore observée dans les GAP_MIN avant ; sinon « unobserved ».
"""
from __future__ import annotations

from datetime import datetime, timedelta

THR = 0.02
BOOK_MIN = 0.01
GAP_MIN = 35
TRACK = {"home", "over", "yes", "fav", "1X"}


def _t(x: str) -> datetime:
    return datetime.fromisoformat(x.replace("Z", "+00:00"))


def _rec(st: dict, now: datetime, outcome: str, **kw) -> dict:
    return {"at": now.isoformat(), "book": st["book"], "sport": st["sport"], "family": st["family"],
            "src": st["src"], "outcome": outcome, "followed": outcome == "followed", **kw}


def _sign(x: float) -> int:
    return 1 if x > 0 else -1


def update(state: dict, comps: list[dict], now: datetime) -> list[dict]:
    """state : dict persistant (modifié sur place). comps : cotes comparées du passage. -> enregistrements terminés."""
    out, seen_now = [], set()
    for c in comps:
        if c.get("book_age_min") is not None or c.get("selection") not in TRACK or not c.get("odds") or not c.get("p_fair"):
            continue
        k = f"{c['book']}|direct|{c['event_id']}|{c['group']}|{c['selection']}"
        if k in seen_now:
            continue
        seen_now.add(k)
        p, o = float(c["p_fair"]), float(c["odds"])
        st = state.get(k)
        if st is None:
            state[k] = {"p": p, "o": o, "seen": now.isoformat(), "start": c["commence"], "mv": None,
                        "book": c["book"], "sport": c.get("ref_sport") or "?", "family": c["group"].split("@")[0],
                        "src": "direct"}
            continue
        prev_seen = _t(st["seen"])
        st["seen"] = now.isoformat()
        mv = st.get("mv")
        if (now - prev_seen).total_seconds() > GAP_MIN * 60:  # trou d'observation : rien n'est déduit
            if mv:
                out.append(_rec(st, now, "unobserved"))
            st.update(p=p, o=o, mv=None)
            continue
        d_book, dp = 1 / o - 1 / st["o"], p - st["p"]
        if abs(d_book) >= BOOK_MIN:
            if mv:
                if _sign(d_book) == mv["dir"]:
                    out.append(_rec(st, now, "followed", lag_min=round((now - _t(mv["t"])).total_seconds() / 60, 1),
                                    lag_min_lo=round(max(0.0, (prev_seen - _t(mv["t"])).total_seconds() / 60), 1),
                                    ref_move=round(mv["dp"], 4), book_move=round(d_book, 4)))
                else:
                    out.append(_rec(st, now, "opposite", ref_move=round(mv["dp"], 4), book_move=round(d_book, 4)))
            elif abs(dp) >= THR and _sign(d_book) == _sign(dp):  # les deux ont bougé entre deux relevés
                out.append(_rec(st, now, "followed", lag_min=round((now - prev_seen).total_seconds() / 60, 1),
                                lag_min_lo=0.0, same_pass=True, ref_move=round(dp, 4), book_move=round(d_book, 4)))
            st.update(p=p, o=o, mv=None)  # nouvelle ancre
            continue
        if mv is None:
            if abs(dp) >= THR:
                st["mv"] = {"t": now.isoformat(), "dir": _sign(dp), "dp": dp}
        elif abs(dp) >= THR and _sign(dp) != mv["dir"]:
            st["mv"] = {"t": now.isoformat(), "dir": _sign(dp), "dp": dp}  # retournement au-delà de l'ancre
        elif abs(dp) < THR / 2:
            out.append(_rec(st, now, "reverted", ref_move=round(mv["dp"], 4)))
            st["mv"] = None
    for k in list(state):  # coup d'envoi, ou cote disparue depuis longtemps
        st = state[k]
        try:
            start, last = _t(st["start"]), _t(st["seen"])
        except (KeyError, ValueError, AttributeError):
            del state[k]
            continue
        if start <= now or (now - last).total_seconds() > 6 * 3600:
            mv = st.get("mv")
            if mv:
                if start <= now and (start - last).total_seconds() <= GAP_MIN * 60:
                    out.append(_rec(st, now, "not_followed", waited_min=round((last - _t(mv["t"])).total_seconds() / 60, 1),
                                    ref_move=round(mv["dp"], 4)))
                else:
                    out.append(_rec(st, now, "unobserved"))
            del state[k]
    return out


def summary(records: list[dict], now: datetime, days: float = 7) -> list[dict]:
    """Par (book, source) : issues de chaque mouvement, délai médian / 3e quartile des suivis, part suivie en ≤ 15 min
    parmi les mouvements tranchés (suivis + non suivis + contraires)."""
    since = now - timedelta(days=days)
    by: dict = {}
    for r in records:
        try:
            if _t(r["at"]) < since:
                continue
        except (KeyError, ValueError, AttributeError):
            continue
        out = r.get("outcome") or ("followed" if r.get("followed") else "not_followed")
        by.setdefault((r.get("book"), r.get("src")), []).append((out, r.get("lag_min")))
    res = []
    for (bk, src), rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        cnt = {k: sum(1 for o, _ in rs if o == k) for k in ("followed", "not_followed", "opposite", "reverted", "unobserved")}
        lags = sorted(lag for o, lag in rs if o == "followed" and lag is not None)
        q = (lambda f: lags[min(len(lags) - 1, int(f * len(lags)))] if lags else None)
        decided = cnt["followed"] + cnt["not_followed"] + cnt["opposite"]
        res.append({"book": bk, "src": src, **cnt, "median_min": q(0.5), "p75_min": q(0.75),
                    "within_15": sum(x <= 15 for x in lags) / decided if decided else None})
    return res
