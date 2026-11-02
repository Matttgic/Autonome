"""Suppression de la marge (dé-vig). Fonctions pures, sans dépendance.

Toutes les fonctions prennent une liste de cotes décimales (toutes les issues
d'un même marché, exhaustives et exclusives) et renvoient les probabilités justes.
"""
from __future__ import annotations

from math import sqrt


def implied(odds: list[float]) -> list[float]:
    if not odds or any(o is None or o <= 1.0 for o in odds):
        raise ValueError(f"cotes invalides: {odds}")
    return [1.0 / o for o in odds]


def overround(odds: list[float]) -> float:
    """Marge du bookmaker = somme(1/cote) - 1."""
    return sum(implied(odds)) - 1.0


def multiplicative(odds: list[float]) -> list[float]:
    q = implied(odds)
    s = sum(q)
    return [x / s for x in q]


def power(odds: list[float]) -> list[float]:
    """p_i = q_i**k avec k tel que somme(p_i)=1 (k>=1 si marge>0)."""
    q = implied(odds)
    if abs(sum(q) - 1.0) < 1e-12:
        return q
    lo, hi = 0.5, 20.0
    for _ in range(200):
        k = (lo + hi) / 2
        s = sum(x ** k for x in q)
        if s > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    return [x ** k for x in q]


def shin(odds: list[float]) -> list[float]:
    """Méthode de Shin (modèle de parieurs informés, proportion z)."""
    q = implied(odds)
    s = sum(q)
    if abs(s - 1.0) < 1e-12:
        return q

    def probs(z: float) -> list[float]:
        return [(sqrt(z * z + 4 * (1 - z) * x * x / s) - z) / (2 * (1 - z)) for x in q]

    lo, hi = 0.0, 0.4
    for _ in range(200):
        z = (lo + hi) / 2
        if sum(probs(z)) > 1.0:
            lo = z
        else:
            hi = z
    p = probs((lo + hi) / 2)
    t = sum(p)
    return [x / t for x in p]


METHODS = {"multiplicative": multiplicative, "power": power, "shin": shin}


def fair_probs(odds: list[float], method: str = "shin") -> list[float]:
    return METHODS[method](odds)
