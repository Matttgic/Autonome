"""Fiche de cotes justes pour les matchs à venir (source : fixtures.csv de football-data.co.uk).

Les books ANJ ne sont PAS dans ce fichier : la fiche donne, par issue, la cote juste (référence sharp dé-viguée,
méthode la plus exigeante des 3) et la « cote minimale » à exiger chez un book ANJ = cote juste × (1 + EV min).
La comparaison avec Winamax/Betclic/... est faite par l'utilisateur, à la main, dans son navigateur.

Limite mesurée (docs/RECHERCHE.md §5-6) : la fiche n'est utile que près de l'heure du relevé. Jouer plus tard
contre une référence périmée a donné une CLV d'environ -5 % (sélection adverse) sur 2019/20-2025/26.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from .devig import METHODS, overround
from .engine import groups, parse_ts
from .sources.footballdata import PARIS

DEFAULT = {
    "min_ev": 0.03,
    "ref_order": ["pinnacle", "betfair_ex_eu"],
    # marge max de la référence : au-delà le marché est illiquide (BFE « avant » : p95 de marge 17-52 %)
    "max_ref_overround": {"pinnacle": 0.08, "betfair_ex_eu": 0.015},
}


def _names(ev: dict, group: str, sel: dict) -> list[str] | None:
    want = [ev["home"], "Draw", ev["away"]] if group == "h2h" else ["Over", "Under"]
    return want if sorted(want) == sorted(sel) else None


def build(events: list[dict], now: datetime, cfg: dict | None = None) -> dict:
    cfg = {**DEFAULT, **(cfg or {})}
    rows, no_ref = [], 0
    for ev in events:
        if parse_ts(ev["commence"]) <= now:
            continue
        for group in ("h2h", "totals@2.5"):
            ref = None
            for k in cfg["ref_order"]:
                sel = groups(ev["books"].get(k, {})).get(group)
                names = _names(ev, group, sel) if sel else None
                if names:
                    odds = [sel[n] for n in names]
                    ov = overround(odds)
                    if ov <= cfg["max_ref_overround"].get(k, 0.08):
                        ref = (k, names, odds, ov)
                        break
            if not ref:
                no_ref += 1
                continue
            k, names, odds, ov = ref
            per = {m: fn(odds) for m, fn in METHODS.items()}
            avg = groups(ev["books"].get("market_avg", {})).get(group) or {}
            sels = []
            for i, n in enumerate(names):
                fair = max(1.0 / per[m][i] for m in per)  # la plus exigeante = EV la plus prudente
                sels.append({"name": n, "fair": round(fair, 3), "min_odds": round(fair * (1 + cfg["min_ev"]), 2),
                             "market_avg": avg.get(n)})
            rows.append({"event_id": ev["id"], "league": ev.get("league", ev["sport"]), "commence": ev["commence"],
                         "home": ev["home"], "away": ev["away"], "group": group, "ref": k,
                         "ref_overround": round(ov, 4), "selections": sels})
    rows.sort(key=lambda r: (r["commence"], r["league"], r["home"], r["group"]))
    return {"generated_at": now.isoformat(), "min_ev": cfg["min_ev"], "rows": rows, "markets_without_ref": no_ref}


def _paris(iso: str | None) -> str:
    if not iso:
        return "inconnue"
    t = parse_ts(iso).astimezone(PARIS)
    return ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"][t.weekday()] + t.strftime(" %d/%m %H:%M")


LABEL = {"Draw": "Nul", "Over": "+2,5 buts", "Under": "-2,5 buts"}


def render(sheet: dict, snapshot: datetime | None) -> str:
    snap = snapshot.astimezone(timezone.utc).isoformat() if snapshot else None
    cards = []
    for r in sheet["rows"]:
        cells = "".join(
            f"<tr><td>{html.escape(LABEL.get(s['name'], s['name']))}</td><td>{s['fair']:.2f}</td>"
            f"<td><b>{s['min_odds']:.2f}</b></td><td>{'%.2f' % s['market_avg'] if s['market_avg'] else '—'}</td></tr>"
            for s in r["selections"])
        cards.append(
            f"<div class=c><b>{html.escape(r['home'])} – {html.escape(r['away'])}</b><br><small>"
            f"{html.escape(r['league'])} · {_paris(r['commence'])} (Paris) · "
            f"{'1N2' if r['group'] == 'h2h' else '+/-2,5 buts'} · réf {html.escape(r['ref'])} "
            f"(marge {r['ref_overround']:.1%})</small><table><tr><th>Issue<th>Cote juste<th>Cote mini ANJ"
            f"<th>Moy. marché</tr>{cells}</table></div>")
    body = "".join(cards) or "<p>Aucun match à venir avec une référence fiable dans le fichier.</p>"
    return f"""<!doctype html><html lang=fr><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Cotes justes</title><style>:root{{--bg:#0f1115;--fg:#e8e8e8;--card:#1a1d24;--mut:#9aa}}
@media (prefers-color-scheme: light){{:root{{--bg:#fafafa;--fg:#111;--card:#fff;--mut:#555}}}}
body{{font:16px system-ui;margin:0 auto;max-width:640px;padding:12px 16px;background:var(--bg);color:var(--fg)}}
.c{{background:var(--card);border-radius:10px;padding:12px;margin:10px 0}}small{{color:var(--mut)}}
table{{width:100%;font-size:14px;border-collapse:collapse}}td,th{{text-align:left;padding:2px 4px}}
.w{{border-left:4px solid #d9a400;padding-left:8px}}</style>
<h1>Cotes justes</h1>
<p class=w>Relevé des cotes : <b>{_paris(snap)}</b> (Paris) — source football-data.co.uk.
Aucun bookmaker ANJ dans la source : compare toi-même dans l'appli/le site du book.
Ne joue que si la cote ANJ ≥ « cote mini » (EV ≥ {sheet['min_ev']:.0%}), <b>et seulement peu après le relevé</b> :
sur 2019-2026, jouer plus tard contre une référence périmée a donné une CLV d'environ −5 %.
Ce n'est pas une garantie de gain ; détection seulement.</p>
<p><small>{len(sheet['rows'])} marchés · {sheet['markets_without_ref']} marchés sans référence fiable (ignorés) ·
généré {_paris(sheet['generated_at'])}</small></p>{body}</html>"""
