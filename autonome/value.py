"""EV, Kelly, CLV et statistiques. Fonctions pures."""
from __future__ import annotations

from math import sqrt

from .devig import METHODS


def ev(p_fair: float, odds: float) -> float:
    """Espérance par unité misée."""
    return p_fair * odds - 1.0


def conservative_ev(ref_odds: list[float], idx: int, book_odds: float) -> dict:
    """EV de la sélection idx selon chaque méthode de dé-vig ; retient le minimum.

    Le minimum protège contre le choix de méthode (favori/outsider).
    """
    per = {}
    for name, fn in METHODS.items():
        p = fn(ref_odds)[idx]
        per[name] = {"p": p, "ev": ev(p, book_odds)}
    worst = min(per, key=lambda m: per[m]["ev"])
    return {"per_method": per, "method": worst, "p_fair": per[worst]["p"], "ev": per[worst]["ev"]}


def kelly_fraction(p_fair: float, odds: float) -> float:
    if odds <= 1.0:
        return 0.0
    return max(0.0, (p_fair * odds - 1.0) / (odds - 1.0))


def stake(p_fair: float, odds: float, bankroll: float, kelly_mult: float = 0.25,
          cap_pct: float = 0.02, min_stake: float = 1.0, rounding: float = 0.5) -> float:
    """Mise Kelly fractionnée, plafonnée, arrondie. 0 si sous la mise minimale."""
    raw = bankroll * min(kelly_fraction(p_fair, odds) * kelly_mult, cap_pct)
    s = round(raw / rounding) * rounding
    return s if s >= min_stake else 0.0


def clv(taken_odds: float, close_fair_p: float) -> dict:
    """CLV : cote prise contre cote juste de clôture (sharp, sans marge)."""
    close_odds = 1.0 / close_fair_p
    return {"close_fair_odds": close_odds, "clv_odds": taken_odds / close_odds - 1.0,
            "ev_vs_close": close_fair_p * taken_odds - 1.0}


_T975 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36, 8: 2.31, 9: 2.26,
         10: 2.23, 15: 2.13, 20: 2.09, 25: 2.06, 30: 2.04}


_T975.update({40: 2.021, 60: 2.000, 120: 1.980})


def _t(df: int) -> float:
    """t(0.975, df) : on prend la plus grande clé <= df (t plus grand = IC plus large, conservateur)."""
    ks = [k for k in sorted(_T975) if k <= df]
    return _T975[ks[-1]] if ks else _T975[1]


def mean_ci(xs: list[float]) -> dict:
    """Moyenne et IC95 % (loi de Student). IC None si n<2."""
    n = len(xs)
    if n == 0:
        return {"n": 0, "mean": None, "ci95": None}
    m = sum(xs) / n
    if n < 2:
        return {"n": n, "mean": m, "ci95": None}
    sd = sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    h = _t(n - 1) * sd / sqrt(n)
    return {"n": n, "mean": m, "sd": sd, "ci95": (m - h, m + h)}


def roi(bets: list[dict]) -> dict:
    """ROI sur paris réglés : bets = [{stake, odds, won(bool|None)}] ; won=None (push/void) = remboursé."""
    st = pnl = 0.0
    per_unit = []
    for b in bets:
        if b.get("won") is None:
            continue
        p = b["stake"] * (b["odds"] - 1) if b["won"] else -b["stake"]
        st += b["stake"]
        pnl += p
        per_unit.append(p / b["stake"])
    out = {"n": len(per_unit), "staked": st, "pnl": pnl, "roi": (pnl / st) if st else None}
    out["return_per_bet"] = mean_ci(per_unit)  # moyenne par pari, pas le ROI pondéré par les mises
    return out
