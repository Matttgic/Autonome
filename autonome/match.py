"""Appariement des matchs entre sources (noms d'équipes différents) : heure + similarité des noms."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

_STOP = {"fc", "sc", "ac", "as", "cf", "afc", "ogc", "rc", "sv", "fk", "sk", "cd", "ud", "sd", "club", "de", "la",
         "le", "les", "du", "stade", "olympique", "sporting", "calcio", "hotspur", "albion", "and", "the",
         "1901", "29", "04", "05", "09", "1899", "1846", "1907", "us", "ss", "ssc", "vfb", "vfl", "tsg", "bsc", "rcd",
         "alsace", "football", "cp", "fsv", "ca", "sl"}
_WEAK = {"paris", "united", "city", "town", "saint", "st", "sankt", "san", "santa", "county", "rovers", "wanderers"}
_ALIAS = {"psg": "paris saint germain", "paris sg": "paris saint germain", "om": "marseille", "ol": "lyonnais lyon",
          "man utd": "manchester united", "man united": "manchester united", "man city": "manchester city",
          "spurs": "tottenham", "wolves": "wolverhampton wanderers", "nottm forest": "nottingham forest",
          "inter": "internazionale inter", "bayern": "bayern munchen munich", "gladbach": "monchengladbach",
          "lyon": "lyonnais lyon", "atletico madrid": "atletico madrid atleti", "brest": "brestois brest"}


# Noms français des books -> noms internationaux (jeton par jeton)
_TOK = {"corogne": "coruna", "majorque": "mallorca", "cadix": "cadiz", "seville": "sevilla", "saragosse": "zaragoza",
        "munich": "munchen", "cologne": "koln", "monchengladbach": "monchengladbach", "naples": "napoli",
        "rome": "roma", "milano": "milan", "inter": "internazionale", "turin": "torino", "florence": "fiorentina", "genes": "genoa",
        "lisbonne": "lisbon", "porto": "porto", "londres": "london", "brugge": "brugge", "bruges": "brugge",
        "glasgow": "glasgow", "prague": "praha", "belgrade": "beograd", "athenes": "athens", "eindhoven": "eindhoven",
        "francfort": "frankfurt", "hambourg": "hamburger", "brest": "brest", "vigo": "vigo", "pampelune": "osasuna",
        "betis": "betis", "atletico": "atletico", "copenhague": "kobenhavn", "varsovie": "warszawa"}


def norm(name: str) -> set[str]:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s).strip()
    s = _ALIAS.get(s, s)
    s = " ".join(_TOK.get(t, t) for t in s.split())
    toks = {t for t in s.split() if t not in _STOP}
    return toks or set(s.split())


def sim(a: str, b: str) -> float:
    ta, tb = norm(a), norm(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    jac = len(inter) / len(ta | tb)
    # inclusion (« Brest » ⊂ « Brestois Brest ») seulement si un jeton fort est commun et qu'il n'y a pas de
    # jetons propres des deux côtés (« Manchester City » vs « Manchester United »).
    cont = 0.9 if (inter - _WEAK) and not (ta - tb and tb - ta) else 0.0
    seq = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    pref = max((SequenceMatcher(None, x, y).ratio() for x in ta - _WEAK for y in tb - _WEAK), default=0)
    pref = 0.85 * pref if pref >= 0.8 and len(ta) == 1 and len(tb) == 1 else 0.0
    return max(jac, cont, seq if seq >= 0.75 else 0.0, pref)


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def pair(ref_games: list[dict], book_events: list[dict], max_dt_min: float = 20, min_sim: float = 0.6,
         with_swap: bool = False) -> list[tuple]:
    """Paires (ref, book) uniques : même heure (±max_dt_min) et deux équipes ressemblantes, dans le même sens.
    Sports à deux issues (ref['two_way']) : le sens inverse est accepté (« A vs. B » = « B - A ») ; avec
    with_swap=True on renvoie (ref, book, inversé)."""
    cands = []
    for i, r in enumerate(ref_games):
        for j, b in enumerate(book_events):
            if abs(_ts(r["commence"]) - _ts(b["commence"])) > max_dt_min * 60:
                continue
            sh, sa = sim(r["home"], b["home"]), sim(r["away"], b["away"])
            xh, xa = sim(r["home"], b["away"]), sim(r["away"], b["home"])
            swap = False
            if r.get("two_way") and xh + xa > sh + sa:
                sh, sa, xh, xa, swap = xh, xa, sh, sa, True
            if sh + sa < xh + xa + 0.5:  # sens ambigu (derby « Inter – AC Milan ») : refusé plutôt que risquer l'inversion
                continue
            if min(sh, sa) >= min_sim or (max(sh, sa) >= 0.95 and min(sh, sa) >= 0.35):
                cands.append((sh + sa, i, j, swap))
    cands.sort(reverse=True)
    used_r, used_b, out = set(), set(), []
    for _, i, j, swap in cands:
        if i not in used_r and j not in used_b:
            used_r.add(i)
            used_b.add(j)
            out.append((ref_games[i], book_events[j], swap) if with_swap else (ref_games[i], book_events[j]))
    return out


def slug_hits(url: str, home: str, away: str, thr: float = 0.75) -> bool:
    """L'URL « /evenement/123-rennes-lille » évoque-t-elle les deux équipes ? (pré-filtre avant téléchargement)"""
    toks = url.rsplit("/", 1)[-1].split("-", 1)[-1].split("-")

    def hit(name):
        return any(SequenceMatcher(None, t, x).ratio() >= thr for t in norm(name) - _WEAK for x in toks if len(x) > 2) \
            or bool(norm(name) & set(toks))
    return hit(home) and hit(away)
