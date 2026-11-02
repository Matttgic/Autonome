"""Retard des bookmakers sur la référence Polymarket : combien de minutes un book met à suivre un mouvement de marché.

Idée tirée de la recherche du 02/11/2026 (les books « mous » suivent le marché avec 6 min à 1 h de retard selon un
fournisseur de données, sur 28 matchs) : on le mesure nous-mêmes, par book, sport et famille de marché.

Pour chaque cote comparée (book, match, marché, issue) :
- ancre = probabilité Polymarket au moment du dernier changement de la cote du book ;
- la référence s'écarte de l'ancre d'au moins THR (2 points) -> mouvement, chronomètre lancé ;
- la cote du book change ensuite dans le même sens (sa probabilité implicite bouge comme la référence) -> délai
  enregistré (« suivi ») ; sens contraire ou référence revenue -> mouvement abandonné ;
- coup d'envoi atteint sans réaction -> « pas suivi » (durée d'attente enregistrée).
La résolution est celle des passages (quelques minutes) ; pour un book lu via l'instantané coteur, l'heure du changement
est celle de l'instantané (marqué src=coteur, moins précis). Aucune donnée inventée : rien n'est déduit entre deux relevés.
"""
from __future__ import annotations

from datetime import datetime, timedelta

THR = 0.02


def _t(x: str) -> datetime:
    return datetime.fromisoformat(x)


def update(state: dict, comps: list[dict], now: datetime) -> list[dict]:
    """state : dict persistant (modifié sur place). comps : cotes comparées du passage (live.compare en diagnostic).
    -> enregistrements terminés (suivi ou pas suivi)."""
    out = []
    seen = set()
    for c in comps:
        if not c.get("odds") or not c.get("p_fair"):
            continue
        k = f"{c['book']}|{c['event_id']}|{c['group']}|{c['selection']}"
        if k in seen:
            continue
        seen.add(k)
        age = c.get("book_age_min")
        t_book = now - timedelta(minutes=age) if age is not None else now
        p, o = float(c["p_fair"]), float(c["odds"])
        st = state.get(k)
        base = {"book": c["book"], "sport": c.get("ref_sport") or "?", "family": c["group"].split("@")[0],
                "src": "coteur" if age is not None else "direct"}
        if st is None:
            state[k] = {"p": p, "o": o, "to": t_book.isoformat(), "start": c["commence"], "mv": None, **base}
            continue
        mv = st.get("mv")
        if abs(o - st["o"]) >= 0.01 and t_book > _t(st["to"]):  # la cote du book a changé depuis le dernier relevé
            d_book = 1 / o - 1 / st["o"]
            if mv and t_book > _t(mv["t"]) and (d_book > 0) == (mv["dir"] > 0):
                out.append({**base, "at": now.isoformat(), "followed": True,
                            "lag_min": round((t_book - _t(mv["t"])).total_seconds() / 60, 1),
                            "ref_move": round(mv["dp"], 4), "book_move": round(d_book, 4)})
            st.update(p=p, o=o, to=t_book.isoformat(), mv=None)  # nouvelle ancre
            continue
        dp = p - st["p"]
        if mv is None and abs(dp) >= THR:
            st["mv"] = {"t": now.isoformat(), "dir": 1 if dp > 0 else -1, "dp": dp}
        elif mv is not None and abs(dp) < THR / 2:
            st["mv"] = None  # la référence est revenue : pas un mouvement durable
    # coup d'envoi : mouvements jamais suivis, puis nettoyage
    for k in list(state):
        st = state[k]
        try:
            started = _t(st["start"].replace("Z", "+00:00")) <= now
        except (KeyError, ValueError, AttributeError):
            started = True
        if started:
            mv = st.get("mv")
            if mv:
                out.append({**{x: st.get(x) for x in ("book", "sport", "family", "src")}, "at": now.isoformat(),
                            "followed": False, "lag_min": None, "ref_move": round(mv["dp"], 4),
                            "waited_min": round((now - _t(mv["t"])).total_seconds() / 60, 1)})
            del state[k]
    return out


def summary(records: list[dict], now: datetime, days: float = 7) -> list[dict]:
    """Par book : mouvements suivis / non suivis, délai médian et 3e quartile, part suivie en 15 min."""
    since = now - timedelta(days=days)
    by: dict = {}
    for r in records:
        try:
            if _t(r["at"]) < since:
                continue
        except (KeyError, ValueError):
            continue
        by.setdefault(r.get("book"), []).append(r)
    out = []
    for bk, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        lags = sorted(r["lag_min"] for r in rs if r.get("followed"))
        n_no = sum(1 for r in rs if not r.get("followed"))
        q = (lambda f: lags[min(len(lags) - 1, int(f * len(lags)))] if lags else None)
        out.append({"book": bk, "followed": len(lags), "not_followed": n_no, "median_min": q(0.5), "p75_min": q(0.75),
                    "within_15": (sum(x <= 15 for x in lags) / (len(lags) + n_no)) if (lags or n_no) else None,
                    "src": sorted({r.get("src") for r in rs})})
    return out
