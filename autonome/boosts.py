"""Évaluation des cotes boostées (Winamax via coteur.com) contre la cote juste Polymarket + modèle de score.

Chaque boost est traduit, par gabarits explicites, en une conjonction de « jambes » portant sur le score final
de matchs Polymarket. Tout libellé non reconnu (buteurs, joueurs, mi-temps, autres sports…) est déclaré
« non évaluable » : on ne devine jamais.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from . import scoremodel as SM
from . import value as V
from .match import pair, sim

PRED = {
    "win": lambda s, a: lambda i, j: (i > j) if s == "home" else (j > i),
    "draw": lambda s, a: lambda i, j: i == j,
    "win_over": lambda s, a: lambda i, j: ((i > j) if s == "home" else (j > i)) and i + j > a["x"],
    "win_under": lambda s, a: lambda i, j: ((i > j) if s == "home" else (j > i)) and i + j < a["x"],
    "win_btts": lambda s, a: lambda i, j: ((i > j) if s == "home" else (j > i)) and i > 0 and j > 0,
    "win_nil": lambda s, a: lambda i, j: (i > j and j == 0) if s == "home" else (j > i and i == 0),
    "margin": lambda s, a: lambda i, j: ((i - j) if s == "home" else (j - i)) >= a["n"],
    "team_goals": lambda s, a: lambda i, j: (i if s == "home" else j) >= a["n"],
    "btts": lambda s, a: lambda i, j: i > 0 and j > 0,
    "btts_no": lambda s, a: lambda i, j: i == 0 or j == 0,
    "over": lambda s, a: lambda i, j: i + j > a["x"],
    "under": lambda s, a: lambda i, j: i + j < a["x"],
    "dc_win_or_draw": lambda s, a: lambda i, j: (i >= j) if s == "home" else (j >= i),
}


def _n(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace("’", "'").split())


def _num(x: str) -> float:
    return float(x.replace(",", "."))


T = r"(?P<t>[\w .'&/-]+?)"
SINGLE = [  # (regex sur le texte normalisé, prédicat, extraction d'arguments)
    (rf"^{T} gagne et plus de (?P<x>\d+[.,]5) buts( dans le match)?$", "win_over", lambda m: {"x": _num(m["x"])}),
    (rf"^{T} gagne et moins de (?P<x>\d+[.,]5) buts( dans le match)?$", "win_under", lambda m: {"x": _num(m["x"])}),
    (rf"^{T} gagne et les (deux|2) equipes marquent$", "win_btts", lambda m: {}),
    (rf"^{T} gagne sans encaisser de but$", "win_nil", lambda m: {}),
    (rf"^{T} gagne par au moins (?P<n>\d+) buts d'ecart$", "margin", lambda m: {"n": int(m["n"])}),
    (rf"^{T} marque au moins (?P<n>\d+) buts?( dans le match)?$", "team_goals", lambda m: {"n": int(m["n"])}),
    (rf"^{T} gagne( le match)?$", "win", lambda m: {}),
    (rf"^{T} ne perd pas$", "dc_win_or_draw", lambda m: {}),
    (r"^les (deux|2) equipes marquent( dans le match)?$", "btts", lambda m: {}),
    (r"^plus de (?P<x>\d+[.,]5) buts( dans le match)?$", "over", lambda m: {"x": _num(m["x"])}),
    (r"^moins de (?P<x>\d+[.,]5) buts( dans le match)?$", "under", lambda m: {"x": _num(m["x"])}),
    (r"^match nul$", "draw", lambda m: {}),
]


_NOT_TEAM = re.compile(r"\b(et|ou|buteur|buteurs|marque|marquent|but|buts|premier|1er|passe|decisive|tir|carton|"
                       r"penalty|corner|mi-temps|joueur|ni|avec|sans|plus|moins)\b|\d")


def _is_team_name(t: str) -> bool:
    """Un sujet de gabarit doit être un nom d'équipe seul (≤ 5 mots, aucun mot de pari ou de joueur)."""
    t = _n(t)
    return bool(t) and len(t.split()) <= 5 and not _NOT_TEAM.search(t) and "." not in t


def _split_teams(s: str) -> list[str]:
    return [re.sub(r"^(le|la|les|l') ", "", x.strip()) for x in re.split(r",| et ", s) if x.strip()]


def _multi(text: str):
    """Combinés multi-matchs → [(équipe ou match, prédicat, args)] ; None si non reconnu."""
    m = re.match(r"^(?P<ts>.+?) gagnent chacun leur match( \(respectivement.*\))?$", text)
    if m:
        return [(t, "win", {}) for t in _split_teams(m["ts"])]
    m = re.match(r"^(?P<ts>.+?) gagnent chacun par au moins (?P<n>\d+) buts d'ecart( \(respectivement.*\))?$", text)
    if m:
        return [(t, "margin", {"n": int(m["n"])}) for t in _split_teams(m["ts"])]
    m = re.match(r"^(?P<ts>.+?) marquent chacun au moins (?P<n>\d+) buts?( \(respectivement.*\))?$", text)
    if m:
        return [(t, "team_goals", {"n": int(m["n"])}) for t in _split_teams(m["ts"])]
    m = re.match(r"^plus de (?P<x>\d+[.,]5) buts lors de chacun des matchs suivants ?: (?P<ms>.+)$", text)
    if m:
        games = [g.strip() for g in re.split(r",| et ", m["ms"]) if " - " in g]
        return [(g, "over_game", {"x": _num(m["x"])}) for g in games] or None
    return None


def _game_for_team(team: str, games: list[dict]):
    """Prochain match de l'équipe (un boost porte sur le prochain match). Ambiguïté entre équipes = refus."""
    hits = []
    for g in games:
        sh, sa = sim(team, g["home"]), sim(team, g["away"])
        if max(sh, sa) >= 0.85:
            hits.append((max(sh, sa), g, "home" if sh >= sa else "away", g["home"] if sh >= sa else g["away"]))
    if not hits:
        return None
    best = max(h[0] for h in hits)
    top = [h for h in hits if h[0] >= best - 0.05]
    if len({h[3] for h in top}) > 1:
        return None  # deux équipes différentes ressemblent au nom : on refuse
    h = min(top, key=lambda h: h[1]["commence"])
    return h[1], h[2]


def _game_for_label(label: str, games: list[dict], start_hint=None):
    if " - " not in label:
        return None
    h, a = [x.strip() for x in label.split(" - ", 1)]
    for g in games:
        if min(sim(h, g["home"]), sim(a, g["away"])) >= 0.6 and \
                sim(h, g["home"]) + sim(a, g["away"]) > sim(h, g["away"]) + sim(a, g["home"]) + 0.5:
            return g
    return None


def _opponents(text: str) -> list[str] | None:
    m = re.search(r"\(respectivement contre (?P<o>.+?)\)$", text)
    return [re.sub(r"^(le|la|les|l') ", "", x.strip()) for x in re.split(r",| et ", m["o"]) if x.strip()] if m else None


def translate(boost: dict, games: list[dict], allow_team_legs: bool = True):
    """→ (jambes [(jeu, prédicat, côté, args)], raison si non évaluable)."""
    text = _n(boost["text"])
    single = _game_for_label(boost["event"], games)
    if single:
        for rx, pred, ex in SINGLE:
            m = re.match(rx, text)
            if not m:
                continue
            side = None
            if "t" in m.groupdict() and m["t"]:
                if not _is_team_name(m["t"]):
                    return None, f"sujet « {m['t']} » n'est pas un simple nom d'équipe (joueur, combinaison…)"
                sh, sa = sim(m["t"], single["home"]), sim(m["t"], single["away"])
                if max(sh, sa) < 0.8 or abs(sh - sa) < 0.2:
                    return None, f"équipe « {m['t']} » non reconnue dans {single['home']} – {single['away']}"
                side = "home" if sh > sa else "away"
            return [(single, pred, side, ex(m))], None
        return None, "libellé non pris en charge (joueur, mi-temps, autre)"
    legs_txt = _multi(text)
    if not legs_txt:
        return None, "match non coté sur Polymarket ou libellé non pris en charge"
    opp = _opponents(text)
    team_legs = [x for x in legs_txt if x[1] != "over_game"]
    if team_legs and opp is None and not allow_team_legs:
        return None, "combiné désigné par équipes, boost non daté (déjà présent au relevé de référence)"
    if opp is not None and len(opp) != len(team_legs):
        return None, "adversaires « respectivement » incohérents"
    legs = []
    k = 0
    for who, pred, args in legs_txt:
        if pred == "over_game":
            g = _game_for_label(who, games)
            if not g:
                return None, f"match « {who} » introuvable"
            legs.append((g, "over", None, args))
        else:
            if not _is_team_name(who):
                return None, f"« {who} » n'est pas un simple nom d'équipe"
            r = _game_for_team(who, games)
            if not r:
                return None, f"équipe « {who} » introuvable ou ambiguë"
            if opp is not None:
                other = r[0]["away"] if r[1] == "home" else r[0]["home"]
                if sim(opp[k], other) < 0.8:
                    return None, f"adversaire attendu « {opp[k]} », prochain match contre « {other} » : boost périmé"
                k += 1
            legs.append((r[0], pred, r[1], args))
    if len({id(g) for g, *_ in legs}) != len(legs):
        return None, "deux jambes sur le même match (corrélées) : non évalué"
    return legs, None


def evaluate(boost: dict, games: list[dict], cache: dict, max_fit_err: float = 0.02, model_margin: float = 0.01,
             allow_team_legs: bool = True):
    legs, why = translate(boost, games, allow_team_legs)
    if not legs:
        return {**boost, "evaluable": False, "why": why}
    p, worst_err, parts = 1.0, 0.0, []
    for g, pred, side, args in legs:
        if g["key"] not in cache:
            cache[g["key"]] = SM.fit(g["markets"])
        f = cache[g["key"]]
        if not f or f["max_err"] > max_fit_err:
            return {**boost, "evaluable": False, "why": f"calage du modèle insuffisant ({g['home']} – {g['away']})"}
        q = SM.prob(f["grid"], PRED[pred](side, args))
        p *= q
        worst_err = max(worst_err, f["max_err"])
        parts.append({"game": g["key"], "match": f"{g['home']} – {g['away']}", "commence": g["commence"],
                      "pred": pred, "side": side, "args": args, "p": q,
                      "lambda": [round(f["lh"], 3), round(f["la"], 3), round(f["rho"], 3)], "fit_err": f["max_err"]})
    # borne prudente : chaque jambe perd (erreur de calage + marge modèle) en probabilité absolue
    p_cons = 1.0
    for x in parts:
        p_cons *= max(0.0, x["p"] - (x["fit_err"] + model_margin))
    return {**boost, "evaluable": True, "p_fair": p, "p_cons": p_cons, "fair_odds": 1 / p if p > 0 else None,
            "ev": V.ev(p, boost["odds"]), "ev_cons": V.ev(p_cons, boost["odds"]), "legs": parts,
            "commence": min(x["commence"] for x in parts)}


CFG = {"min_ev": 0.05, "min_ev_cons": 0.0, "min_minutes_to_start": 20}


def to_bet(e: dict, now: datetime, bankroll: float, kelly_mult=0.25, cap_pct=0.02) -> dict | None:
    """Boost évalué -> pari enregistrable (même schéma que live.compare), ou None s'il ne passe pas les seuils."""
    if not e.get("evaluable") or e["ev"] < CFG["min_ev"] or e["ev_cons"] < CFG["min_ev_cons"]:
        return None
    start = datetime.fromisoformat(e["commence"].replace("Z", "+00:00"))
    if (start - now).total_seconds() < CFG["min_minutes_to_start"] * 60:
        return None
    stake = V.stake(e["p_cons"], e["odds"], bankroll, kelly_mult, cap_pct)
    if e.get("max_stake"):
        stake = min(stake, e["max_stake"])
    if stake <= 0:
        return None
    first = e["legs"][0]
    home, _, away = first["match"].partition(" – ")
    return {"bet_id": e["id"], "event_id": f"{first['game']}|boost", "book_event": e["id"], "sport": "boost",
            "commence": e["commence"], "home": home, "away": away, "group": "boost", "selection": e["text"],
            "label": f"Cote boostée {e['book'].capitalize()} : {e['text']}", "book": e["book"], "url": None,
            "odds": e["odds"], "ref_kind": "polymarket-modele", "ref_books": ["polymarket"], "ref_overround": 0.0,
            "devig_method": "Dixon-Coles calé sur Polymarket", "p_fair": e["p_fair"], "p_cons": e["p_cons"],
            "p_hi": e["p_fair"], "spread": None, "fair_odds": e["fair_odds"], "ev": e["ev"], "ev_cons": e["ev_cons"],
            "legs": [], "boost_legs": e["legs"], "max_stake": e.get("max_stake"), "stake": stake,
            "found_at": now.isoformat()}


def reprice(legs: list[dict], games: list[dict], cache: dict) -> float | None:
    """Recalcule la proba d'un boost avec les marchés actuels (clôture). None si une jambe n'est plus cotée."""
    by = {g["key"]: g for g in games}
    p = 1.0
    for x in legs:
        g = by.get(x["game"])
        if not g:
            return None
        if g["key"] not in cache:
            cache[g["key"]] = SM.fit(g["markets"])
        f = cache[g["key"]]
        if not f or f["max_err"] > 0.03:
            return None
        p *= SM.prob(f["grid"], PRED[x["pred"]](x["side"], x["args"]))
    return p


def final_score(exact_event: dict | None):
    """Score final lu dans le marché « score exact » Polymarket résolu : (dom, ext), 'autre', 'annulé' ou None."""
    if not exact_event:
        return None
    ms = exact_event.get("markets") or []
    for m in ms:
        try:
            p = [float(x) for x in __import__("json").loads(m.get("outcomePrices") or "[]")]
        except ValueError:
            continue
        if not m.get("closed") or len(p) != 2:
            continue
        if p[0] == 1.0:
            r = re.search(r" (\d+) - (\d+) ", f" {m.get('groupItemTitle') or ''} ")
            return (int(r.group(1)), int(r.group(2))) if r else "autre"
        if p[0] == 0.5:
            return "annulé"
    return None


def settle(root, get_event, now: datetime, delay_h: float = 3.0) -> int:
    """Règle les boosts : chaque jambe évaluée sur le score final ; une jambe annulée => pari annulé."""
    from . import store
    from .tracker import BETS
    rows, n = store.read(root, BETS), 0
    for r in rows:
        if r["status"] != "open" or r.get("ref_kind") != "polymarket-modele":
            continue
        legs = r.get("boost_legs") or []
        if not legs or any((now - datetime.fromisoformat(x["commence"].replace("Z", "+00:00"))).total_seconds()
                           < delay_h * 3600 for x in legs):
            continue
        outcomes = []
        for x in legs:
            sc = final_score(get_event(x["game"].split("|", 1)[-1] + "-exact-score"))
            if sc is None or sc == "autre":
                break
            outcomes.append(None if sc == "annulé" else PRED[x["pred"]](x["side"], x["args"])(*sc))
        if len(outcomes) != len(legs):
            continue
        won = None if None in outcomes else all(outcomes)
        r["status"], r["result"] = "settled", {"won": won, "source": "score exact Polymarket"}
        n += 1
    store.write_all(root, BETS, rows)
    return n
