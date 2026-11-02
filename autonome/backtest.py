"""Outils de backtest (fonctions pures) : log-loss, Brier, calibration, dérive des lignes, simulation de value.

Format d'un enregistrement : {"season": "2425", "div": "E0", "res": index de l'issue gagnante,
"odds": {"PS": [h, d, a], "PSC": [...], "B365": [...], ...}}. Une clé absente = donnée absente (jamais imputée).
"""
from __future__ import annotations

from functools import lru_cache
from math import log, sqrt

from .devig import METHODS, overround
from .value import mean_ci

EPS = 1e-12


def _power_fast(q: list[float]) -> list[float]:
    """Même équation que devig.power (bisection sur k), 64 itérations : précision ~1e-17, 3x plus rapide."""
    if abs(sum(q) - 1.0) < 1e-12:
        return q
    lo, hi = 0.5, 20.0
    for _ in range(64):
        k = (lo + hi) / 2
        if sum(x ** k for x in q) > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    return [x ** k for x in q]


def _shin_fast(q: list[float]) -> list[float]:
    """Même équation que devig.shin, 64 itérations de bisection sur z."""
    s = sum(q)
    if abs(s - 1.0) < 1e-12:
        return q
    q2 = [x * x / s for x in q]

    def probs(z):
        return [(sqrt(z * z + 4 * (1 - z) * x) - z) / (2 * (1 - z)) for x in q2]

    lo, hi = 0.0, 0.4
    for _ in range(64):
        z = (lo + hi) / 2
        if sum(probs(z)) > 1.0:
            lo = z
        else:
            hi = z
    p = probs((lo + hi) / 2)
    t = sum(p)
    return [x / t for x in p]


@lru_cache(maxsize=2_000_000)
def _fair_cached(odds: tuple[float, ...], method: str) -> tuple[float, ...]:
    if method == "multiplicative":
        return tuple(METHODS[method](list(odds)))
    q = [1.0 / o for o in odds]
    return tuple(_power_fast(q) if method == "power" else _shin_fast(q))


def fair(odds: list[float], method: str) -> list[float]:
    return list(_fair_cached(tuple(odds), method))


def logloss(probs: list[list[float]], outcomes: list[int]) -> float:
    return sum(-log(max(p[o], EPS)) for p, o in zip(probs, outcomes)) / len(outcomes)


def brier(probs: list[list[float]], outcomes: list[int]) -> float:
    return sum(sum((x - (i == o)) ** 2 for i, x in enumerate(p)) for p, o in zip(probs, outcomes)) / len(outcomes)


def usable(records: list[dict], *keys: str) -> list[dict]:
    """Enregistrements où toutes les cotes demandées et le résultat existent (échantillon commun)."""
    return [r for r in records if r.get("res") is not None and all(r["odds"].get(k) for k in keys)]


def score_source(records: list[dict], key: str, method: str) -> dict:
    """Log-loss / Brier de la probabilité dé-viguée d'une source (sur les enregistrements fournis)."""
    rs = usable(records, key)
    if not rs:
        return {"n": 0, "logloss": None, "brier": None}
    ps = [fair(r["odds"][key], method) for r in rs]
    ys = [r["res"] for r in rs]
    return {"n": len(rs), "logloss": logloss(ps, ys), "brier": brier(ps, ys)}


def calibration(records: list[dict], key: str, method: str, edges: list[float]) -> list[dict]:
    """Probabilité moyenne annoncée vs fréquence observée, par tranche de probabilité (toutes issues confondues)."""
    bins = [{"lo": lo, "hi": hi, "n": 0, "sp": 0.0, "hits": 0} for lo, hi in zip(edges, edges[1:])]
    for r in usable(records, key):
        for i, p in enumerate(fair(r["odds"][key], method)):
            for b in bins:
                if b["lo"] <= p < b["hi"] or (b["hi"] == edges[-1] and p == edges[-1]):
                    b["n"] += 1
                    b["sp"] += p
                    b["hits"] += r["res"] == i
                    break
    out = []
    for b in bins:
        if b["n"]:
            f = b["hits"] / b["n"]
            out.append({"lo": b["lo"], "hi": b["hi"], "n": b["n"], "mean_p": b["sp"] / b["n"], "freq": f,
                        "se": (f * (1 - f) / b["n"]) ** 0.5})
    return out


def margin(records: list[dict], key: str) -> dict:
    return mean_ci([overround(r["odds"][key]) for r in records if r["odds"].get(key)])


def drift(records: list[dict], pre: str, close: str, method: str) -> dict:
    """|p_clôture - p_avant| moyen (toutes issues) : coût d'une référence relevée trop tôt."""
    d = []
    for r in records:
        a, b = r["odds"].get(pre), r["odds"].get(close)
        if a and b and len(a) == len(b):
            d += [abs(x - y) for x, y in zip(fair(a, method), fair(b, method))]
    return mean_ci(d)


def _ev(fair_odds: list[float], i: int, o: float, method: str) -> float:
    if method == "min":  # conservateur, comme le moteur : pire EV des 3 méthodes
        return min(fair(fair_odds, m)[i] * o - 1 for m in METHODS)
    return fair(fair_odds, method)[i] * o - 1


def simulate(records: list[dict], fair_key: str, bet_key: str, close_key: str, thr: float,
             method: str = "min", close_method: str = "shin", min_odds: float = 1.0, max_odds: float = 1e9,
             max_ref_overround: float = 1e9) -> dict:
    """Mise plate de 1 sur la meilleure issue (EV >= thr) par match.

    EV attendue : contre fair_key ; CLV-EV : contre close_key dé-viguée (proxy de l'EV réelle) ; ROI : résultat réel.
    max_ref_overround : ignore les matchs dont la référence a une marge supérieure (marché illiquide).
    """
    ev_l, clv_l, pnl_l, odds_l = [], [], [], []
    for r in usable(records, fair_key, bet_key, close_key):
        f, b = r["odds"][fair_key], r["odds"][bet_key]
        if len(f) != len(b) or overround(f) > max_ref_overround:
            continue
        cands = [(_ev(f, i, o, method), i) for i, o in enumerate(b) if min_odds <= o <= max_odds]
        cands = [c for c in cands if c[0] >= thr]
        if not cands:
            continue
        e, i = max(cands)
        o = b[i]
        pc = fair(r["odds"][close_key], close_method)[i]
        ev_l.append(e)
        clv_l.append(pc * o - 1)
        pnl_l.append((o - 1) if r["res"] == i else -1.0)
        odds_l.append(o)
    return {"n": len(pnl_l), "matches": len(usable(records, fair_key, bet_key, close_key)),
            "ev_expected": mean_ci(ev_l)["mean"], "clv_ev": mean_ci(clv_l), "roi": mean_ci(pnl_l),
            "avg_odds": (sum(odds_l) / len(odds_l)) if odds_l else None}
