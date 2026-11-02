"""Page web mobile statique (publiable via GitHub Pages)."""
from __future__ import annotations

import html

from . import store
from .tracker import BETS, stats


def _pct(x):
    return "—" if x is None else f"{x:+.2%}"


def render(root, today_bets: list[dict]) -> str:
    st = stats(root)
    clv = st["clv"]
    ci = clv.get("ci95")
    rows = "".join(
        f"<div class=c><b>{html.escape(b['home'] or '?')} – {html.escape(b['away'] or '?')}</b><br>"
        f"{html.escape(b['group'])} · <b>{html.escape(b['selection'])}</b> @ <b>{b['odds']:.2f}</b> "
        f"({html.escape(b['book'])})<br>EV {b['ev']:+.1%} · mise {b['stake']:.1f} € · cote juste {b['fair_odds']:.2f}"
        f"<br><small>p={b['p_fair']:.2%} · réf {html.escape('+'.join(b['ref_books'][:2]))} "
        f"(marge {b['ref_overround']:.1%}, {html.escape(b['devig_method'])}) · avant {html.escape(b['commence'])}</small></div>"
        for b in today_bets) or "<p>NO BET</p>"
    hist = store.read(root, BETS)[-30:][::-1]
    hrows = "".join(
        f"<tr><td>{html.escape((r['home'] or '?')[:14])}–{html.escape((r['away'] or '?')[:14])}</td><td>{html.escape(r['selection'])}</td>"
        f"<td>{r['odds']:.2f}</td><td>{_pct(r['close']['clv_odds']) if r.get('close') else '—'}</td>"
        f"<td>{html.escape(str((r.get('result') or {}).get('won', '—')))}</td></tr>" for r in hist)
    return f"""<!doctype html><html lang=fr><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Autonome</title><style>body{{font:16px system-ui;margin:0 auto;max-width:640px;padding:12px;background:#0f1115;color:#e8e8e8}}
.c{{background:#1a1d24;border-radius:10px;padding:12px;margin:10px 0}}small{{color:#9aa}}table{{width:100%;font-size:13px}}</style>
<h1>Autonome</h1><h2>Paris du jour</h2>{rows}
<h2>Performance</h2><div class=c>Paris : {st['bets_total']} (réglés {st['bets_settled']})<br>
CLV moyenne : {_pct(clv.get('mean'))} (n={clv['n']}, IC95 % {('%+.2f%% à %+.2f%%' % (ci[0]*100, ci[1]*100)) if ci else 'n/a'})<br>
EV attendue moyenne : {_pct(st['ev_expected'].get('mean'))}<br>ROI : {_pct(st['roi']['roi'])} (n={st['roi']['n']})<br>
<small>{html.escape(st['note'])}</small></div>
<h2>Historique</h2><table><tr><th>Match<th>Sél.<th>Cote<th>CLV<th>Gagné</tr>{hrows}</table></html>"""
