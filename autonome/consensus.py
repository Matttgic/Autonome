"""Référence « consensus ANJ » pour les matchs sans marché Polymarket (sports de niche, petits championnats).

Proba juste = moyenne des probabilités dé-viguées (Shin) de chaque bookmaker ayant le marché complet, en excluant le
bookmaker évalué (leave-one-out). Une cote nettement au-dessus de cette cote juste signale une erreur ou un retard de
mise à jour. Référence plus faible que Polymarket : seuils plus hauts et suivi CLV séparé (ref_kind « consensus »).
"""
from __future__ import annotations

from datetime import datetime

from . import value as V
from .devig import shin

# Paris réglés/clôturés comme le consensus : le consensus lui-même et les stratégies fictives de paper.py.
KINDS = {"consensus-anj", "paper-valeur4", "paper-temoin"}

CFG = {"min_books": 6, "min_groups": 5, "min_ev": 0.07, "max_ev": 0.4, "min_odds": 1.3, "max_odds": 6.0,
       "min_minutes_to_start": 20, "max_hours_to_start": 48, "max_dispersion": 0.04,
       "max_book_age_min": 60}  # remplacé par live.CFG au passage live (une seule valeur de réglage)


def evaluate(match: dict, now: datetime, bankroll: float, cfg=None) -> list[dict]:
    c = {**CFG, **(cfg or {})}
    start = datetime.fromisoformat(match["commence"].replace("Z", "+00:00"))
    mins = (start - now).total_seconds() / 60
    if not c["min_minutes_to_start"] <= mins <= c["max_hours_to_start"] * 60:
        return []
    if not c.get("diagnostic"):
        from .live import book_age_limit
        age = match.get("snapshot_age_min")
        if age is None or age > book_age_limit(mins, c["max_book_age_min"]):
            return []  # instantané trop vieux (ou d'âge inconnu) : mesuré, jamais proposé
    out = []
    for mk in ("1x2", "ml"):
        names = ["home", "draw", "away"] if mk == "1x2" else ["home", "away"]
        full = {bk: o[mk] for bk, o in match["books"].items() if mk in o and all(n in o[mk] for n in names)}
        if len(full) - 1 < c["min_books"]:  # au moins min_books AUTRES bookmakers
            continue
        fair = {bk: dict(zip(names, shin([o[n] for n in names]))) for bk, o in full.items()}
        for bk, o in full.items():
            # books aux cotes identiques (même fournisseur) = une seule voix
            groups: dict = {}
            for b in fair:
                if b != bk:
                    groups.setdefault(tuple(round(full[b][n], 2) for n in names), fair[b])
            others = list(groups.values())
            if len(others) < c["min_groups"]:
                continue
            for n in names:
                ps = [f[n] for f in others]
                p = sum(ps) / len(ps)
                disp = max(ps) - min(ps)
                odds = o[n]
                if disp > c["max_dispersion"] or not c["min_odds"] <= odds <= c["max_odds"]:
                    continue  # bookmakers en désaccord : consensus peu fiable
                ev = V.ev(p, odds)
                if not c["min_ev"] <= ev <= c["max_ev"]:
                    continue
                p_cons = p - disp / 2
                stake = V.stake(p_cons, odds, bankroll)
                if stake <= 0 and not c.get("diagnostic"):
                    continue
                label = {"home": match["home"], "away": match["away"], "draw": "Nul"}[n]
                out.append({"bet_id": f"cons|{match['renc']}|{mk}|{n}|{bk}", "event_id": f"cons|{match['renc']}",
                            "book_event": match["renc"], "sport": match["sport"], "commence": match["commence"],
                            "home": match["home"], "away": match["away"], "group": mk, "selection": n,
                            "label": f"{'1N2' if mk == '1x2' else 'Vainqueur'} : {label}", "book": bk,
                            "url": match["url"], "odds": odds, "ref_kind": "consensus-anj",
                            "ref_books": sorted(b for b in fair if b != bk), "ref_overround": 0.0,
                            "devig_method": f"Shin, moyenne de {len(others)} bookmakers ANJ (hors {bk})",
                            "p_fair": p, "p_cons": p_cons, "p_hi": p + disp / 2, "spread": disp,
                            "fair_odds": 1 / p, "ev": ev, "ev_cons": V.ev(p_cons, odds), "legs": [],
                            "stake": stake, "found_at": now.isoformat(), "coteur_renc": match["renc"]})
    return out


def closing(rows: list[dict], matches: list[dict], now: datetime) -> int:
    """Clôture des paris « consensus » : consensus recalculé sur l'instantané coteur le plus récent."""
    by = {m["renc"]: m for m in matches}
    n = 0
    for r in rows:
        if r.get("status") != "open" or r.get("ref_kind") not in KINDS or r.get("coteur_renc") not in by:
            continue
        m = by[r["coteur_renc"]]
        mins = (datetime.fromisoformat(m["commence"].replace("Z", "+00:00")) - now).total_seconds() / 60
        if mins <= 0:
            continue
        names = ["home", "draw", "away"] if r["group"] == "1x2" else ["home", "away"]
        fair = [dict(zip(names, shin([o[r["group"]][x] for x in names]))) for bk, o in m["books"].items()
                if bk != r["book"] and r["group"] in o and all(x in o[r["group"]] for x in names)]
        if len(fair) < CFG["min_books"]:
            continue
        p = sum(f[r["selection"]] for f in fair) / len(fair)
        r["close"] = {"book": "consensus-anj", "p_fair": p, "seen_at": now.isoformat(), "minutes_to_start": mins,
                      "ref_age_min": m.get("snapshot_age_min"), **V.clv(r["odds"], p),
                      "note": "clôture = même méthode de consensus : CLV indicative seulement"}
        n += 1
    return n


def _when(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def days_to_fetch(rows: list[dict], now: datetime, after_h: float = 3.0, max_days: int = 14) -> set[tuple[str, str]]:
    """(sport, AAAAMMJJ UTC) à lire pour régler les paris « consensus » ouverts commencés depuis after_h heures."""
    from datetime import timedelta
    from .sources.livescore import SLUG
    need = set()
    for r in rows:
        if r.get("status") != "open" or r.get("ref_kind") not in KINDS or r.get("sport") not in SLUG:
            continue
        try:
            start = _when(r["commence"])
        except (KeyError, ValueError, AttributeError):
            continue
        if timedelta(hours=after_h) <= now - start <= timedelta(days=max_days):
            for d in (start - timedelta(minutes=30), start, start + timedelta(minutes=30)):
                need.add((r["sport"], d.strftime("%Y%m%d")))
    return need


def settle(rows: list[dict], results: list[dict], now: datetime, after_h: float = 3.0,
           max_dt_min: float = 20, min_sim: float = 0.6) -> int:
    """Règle les paris « consensus » (1N2 foot/basket, vainqueur basket/tennis) sur un résultat LiveScore apparié
    sans ambiguïté : même sport, même heure (±max_dt_min), les deux noms ressemblants. Deux candidats possibles,
    un sens douteux ou un statut non final => le pari reste ouvert (jamais deviné)."""
    from .match import markers, sim
    from .sources.livescore import outcome
    n = 0
    for r in rows:
        if r.get("status") != "open" or r.get("ref_kind") not in KINDS:
            continue
        try:
            start = _when(r["commence"])
        except (KeyError, ValueError, AttributeError):
            continue
        if (now - start).total_seconds() < after_h * 3600:
            continue
        two_way = r.get("group") == "ml"
        bet_marks = markers(r["home"]) | markers(r["away"])
        bet_doubles = "/" in r["home"] + r["away"]
        found = []
        for res in results:
            if res.get("sport") != r.get("sport") or abs((_when(res["commence"]) - start).total_seconds()) > max_dt_min * 60:
                continue
            res_marks = {x for n in res["homes"] + res["aways"] for x in markers(n)}
            if res_marks != bet_marks or (res.get("special") and not bet_marks) or res.get("doubles", False) != bet_doubles:
                continue  # féminines/jeunes/réserves ou double au tennis : jamais pris pour le pari
            sh = max(sim(r["home"], x) for x in res["homes"])
            sa = max(sim(r["away"], x) for x in res["aways"])
            xh = max(sim(r["home"], x) for x in res["aways"])
            xa = max(sim(r["away"], x) for x in res["homes"])
            swap = two_way and xh + xa > sh + sa
            if swap:
                sh, sa, xh, xa = xh, xa, sh, sa
            if sh + sa < xh + xa + 0.5:
                continue  # sens ambigu
            if min(sh, sa) >= min_sim or (max(sh, sa) >= 0.95 and min(sh, sa) >= 0.35):
                found.append((res, swap))
        if len({f[0]["id"] or id(f[0]) for f in found}) != 1:
            continue  # aucun ou plusieurs matchs possibles (même reporté) : à régler à la main
        res, swap = found[0]
        win = outcome(res, r.get("group"))
        if win is None:
            continue
        if swap:
            win = {"home": "away", "away": "home"}.get(win, win)
        score = res["regular"] if r.get("group") == "1x2" else res["final"]
        if swap:
            score = (score[1], score[0])
        r["status"] = "settled"
        r["result"] = {"won": r["selection"] == win, "payout": 1.0 if r["selection"] == win else 0.0,
                       "source": f"LiveScore {res['id']} ({res['status']})",
                       "score": f"{score[0]}-{score[1]}", "match": f"{res['homes'][0]} - {res['aways'][0]}",
                       "note": ("score du temps réglementaire" if r.get("group") == "1x2" else
                                "sets gagnés" if r.get("sport") == "TENNIS" else "prolongation incluse")}
        n += 1
    return n
