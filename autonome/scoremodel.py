"""Modèle de score Dixon-Coles calé sur les probabilités justes d'un match (Polymarket).

Sert à évaluer des paris composés (gagne ET plus de 2,5 buts, gagne sans encaisser, combinés…) qu'aucun marché
ne cote directement. Le calage est vérifié : on rapporte l'erreur maximale sur les marchés utilisés ; au-delà
du seuil, le match est déclaré non évaluable (jamais de cote inventée).
"""
from __future__ import annotations

from math import exp, factorial

N = 11  # scores 0..10


def _pois(l: float) -> list[float]:
    return [exp(-l) * l ** k / factorial(k) for k in range(N)]


def grid(lh: float, la: float, rho: float = 0.0) -> list[list[float]]:
    ph, pa = _pois(lh), _pois(la)
    g = [[ph[i] * pa[j] for j in range(N)] for i in range(N)]
    # correction Dixon-Coles des petits scores
    g[0][0] *= 1 - lh * la * rho
    g[0][1] *= 1 + lh * rho
    g[1][0] *= 1 + la * rho
    g[1][1] *= 1 - rho
    s = sum(map(sum, g))
    return [[x / s for x in row] for row in g]


def prob(g, pred) -> float:
    return sum(g[i][j] for i in range(N) for j in range(N) if pred(i, j))


def _targets(markets: dict) -> list[tuple]:
    """(prédicat sur le score final, proba juste) à partir des marchés de référence disponibles."""
    t = []
    m = markets.get("1x2")
    if m:
        t += [(lambda i, j: i > j, m["home"]["p"]), (lambda i, j: i == j, m["draw"]["p"]),
              (lambda i, j: i < j, m["away"]["p"])]
    for k, v in markets.items():
        kind, *r = k.split("@")
        if kind == "ou" and float(r[0]) <= 4.5:
            x = float(r[0])
            t.append((lambda i, j, x=x: i + j > x, v["over"]["p"]))
        elif kind == "team_ou" and float(r[1]) <= 2.5:
            x, side = float(r[1]), r[0]
            t.append(((lambda i, j, x=x: i > x) if side == "home" else (lambda i, j, x=x: j > x), v["over"]["p"]))
        elif kind == "btts":
            t.append((lambda i, j: i > 0 and j > 0, v["yes"]["p"]))
    return t


def fit(markets: dict) -> dict | None:
    """Calage (λ dom, λ ext, ρ) par moindres carrés ; None si moins de 4 contraintes."""
    t = _targets(markets)
    if len(t) < 4 or "1x2" not in markets:
        return None

    def err(lh, la, rho):
        g = grid(lh, la, rho)
        return sum((prob(g, f) - p) ** 2 for f, p in t)

    best = None
    for lh in [x / 10 for x in range(2, 41, 2)]:
        for la in [x / 10 for x in range(2, 41, 2)]:
            e = err(lh, la, 0.0)
            if best is None or e < best[0]:
                best = (e, lh, la, 0.0)
    _, lh, la, rho = best
    step = 0.1
    for _ in range(40):  # descente par coordonnées
        improved = False
        for d in ((step, 0, 0), (-step, 0, 0), (0, step, 0), (0, -step, 0), (0, 0, step / 2), (0, 0, -step / 2)):
            c = (max(0.05, lh + d[0]), max(0.05, la + d[1]), min(0.3, max(-0.3, rho + d[2])))
            e = err(*c)
            if e < best[0] - 1e-12:
                best, (lh, la, rho), improved = (e, *c), c, True
        if not improved:
            step /= 2
            if step < 0.002:
                break
    g = grid(lh, la, rho)
    maxerr = max(abs(prob(g, f) - p) for f, p in t)
    return {"lh": lh, "la": la, "rho": rho, "n_targets": len(t), "max_err": maxerr, "grid": g}
