"""CLI : python -m autonome {scan|close|settle|report|stats}."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import engine, notify, oddsapi, report, store, tracker


def load_cfg(path="config.json") -> dict:
    cfg = json.loads(Path(path).read_text())
    eng = {**engine.DEFAULT_CFG, **cfg.get("engine", {})}
    if os.environ.get("BANKROLL"):
        eng["bankroll"] = float(os.environ["BANKROLL"])
    cfg["engine"] = eng
    return cfg


def active_sports(cl: oddsapi.Client, wanted: list[str]) -> list[str]:
    try:
        act = {s["key"] for s in cl.sports() if s.get("active")}
        return [s for s in wanted if s in act]
    except oddsapi.OddsApiError as e:
        print(f"[warn] liste des sports indisponible ({e}); on tente la liste complète", file=sys.stderr)
        return wanted


def budget_ok(cl, cfg, spent, per_run) -> bool:
    if spent >= per_run:
        return False
    return cl.remaining is None or cl.remaining > cfg["credits_reserve"]


def cmd_scan(a, cfg):
    cl = oddsapi.Client()
    now = datetime.now(timezone.utc)
    cands, spent, errors = [], 0, []
    ncost = len(cfg["markets"].split(",")) * len(cfg["regions"].split(","))
    for sport in active_sports(cl, cfg["sports_priority"]):
        if not budget_ok(cl, cfg, spent, cfg["credits_per_scan"]):
            break
        try:
            events = [oddsapi.normalize(e) for e in cl.odds(sport, cfg["markets"], cfg["regions"])]
        except oddsapi.OddsApiError as e:
            errors.append(f"{sport}: {e}")
            continue
        spent += ncost
        for ev in events:
            try:
                cands += engine.find_value(ev, cfg["engine"], now)
                tracker.update_closing(a.state, ev, cfg["engine"], now)
            except Exception as e:  # noqa: BLE001 - un événement corrompu ne doit pas tuer le scan
                errors.append(f"{sport}/{ev.get('id')}: {type(e).__name__}")
    already = {r["bet_id"] for r in store.read(a.state, tracker.BETS)}
    # un pari déjà recommandé sur (match, marché) n'est pas re-recommandé, même chez un autre book
    seen = {(r["event_id"], r["group"]) for r in store.read(a.state, tracker.BETS)}
    cands = [c for c in cands if (c["event_id"], c["group"]) not in seen]
    today = now.date().isoformat()
    done_today = sum(1 for r in store.read(a.state, tracker.BETS) if r.get("found_at", "")[:10] == today)
    picks = engine.select_daily(cands, cfg["engine"], already, done_today)
    tracker.record_bets(a.state, picks)
    meta = {"at": now.isoformat(), "credits_spent": spent, "credits_remaining": cl.remaining,
            "candidates": len(cands), "picked": len(picks), "errors": errors}
    store.append(a.state, "runs.jsonl", [meta])
    print(json.dumps(meta, ensure_ascii=False))
    if picks or a.notify_empty:  # notifier AVANT le rendu : une panne de page ne doit pas perdre l'alerte
        print(notify.send(f"{len(picks)} value bet(s)" if picks else "NO BET", notify.message(picks), a.link))
    try:
        Path(a.out).mkdir(exist_ok=True)
        Path(a.out, "index.html").write_text(report.render(a.state, picks))
    except Exception as e:  # noqa: BLE001
        errors.append(f"rapport: {type(e).__name__}")
    if errors:
        notify.send("Autonome : erreurs partielles" if spent else "Autonome : source en panne", "; ".join(errors)[:500])
    return 2 if (errors and spent == 0 and not picks) else 0


def cmd_close(a, cfg):
    """Rafraîchit la clôture sharp des matchs avec paris ouverts qui démarrent bientôt."""
    cl = oddsapi.Client()
    now = datetime.now(timezone.utc)
    soon = {}
    for r in store.read(a.state, tracker.BETS):
        if r["status"] == "open":
            mins = (engine.parse_ts(r["commence"]) - now).total_seconds() / 60
            if 0 < mins <= a.within_min:
                soon[r["sport"]] = True
    spent = 0
    for sport in soon:
        if not budget_ok(cl, cfg, spent, cfg["credits_per_close"]):
            break
        try:
            for e in cl.odds(sport, cfg["markets"], cfg["regions"]):
                tracker.update_closing(a.state, oddsapi.normalize(e), cfg["engine"], now)
            spent += len(cfg["markets"].split(","))
        except oddsapi.OddsApiError as e:
            print(f"[warn] {sport}: {e}", file=sys.stderr)
    print(json.dumps({"close_sports": list(soon), "credits_spent": spent, "remaining": cl.remaining}))
    return 0


def cmd_settle(a, cfg):
    cl = oddsapi.Client()
    now = datetime.now(timezone.utc)
    sports = {r["sport"] for r in store.read(a.state, tracker.BETS)
              if r["status"] == "open" and engine.parse_ts(r["commence"]) < now}
    spent = n = 0
    for sport in sports:
        if not budget_ok(cl, cfg, spent, cfg["credits_per_settle"]):
            break
        try:
            for ev in cl.scores(sport, 3):
                res = oddsapi.result_of(ev)
                if res:
                    n += tracker.settle(a.state, ev["id"], res)
            spent += 2
        except oddsapi.OddsApiError as e:
            print(f"[warn] {sport}: {e}", file=sys.stderr)
    print(json.dumps({"settled": n, "credits_spent": spent, "remaining": cl.remaining}))
    return 0


def cmd_stats(a, cfg):
    print(json.dumps(tracker.stats(a.state), indent=1, ensure_ascii=False, default=str))
    return 0


def cmd_report(a, cfg):
    Path(a.out).mkdir(exist_ok=True)
    Path(a.out, "index.html").write_text(report.render(a.state, []))
    return 0


def cmd_fair(a, cfg):
    """Fiche de cotes justes depuis fixtures.csv (football-data.co.uk) : sans clé, sans compte."""
    from . import fairsheet
    from .sources import footballdata as fd
    src = a.csv or fd.FIXTURES_URL
    try:
        if src.startswith("https://"):
            data, snap = fd.fetch(src)
        else:
            data, snap = Path(src).read_bytes(), None  # fichier local : date du relevé inconnue (signalée)
    except (fd.SourceError, OSError) as e:
        print(f"[erreur] source indisponible : {e}", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    sheet = fairsheet.build(fd.load_fixtures(data, snap), now, cfg.get("fair"))
    sheet["snapshot"] = snap.isoformat() if snap else None
    Path(a.out).mkdir(parents=True, exist_ok=True)
    Path(a.out, "fair.html").write_text(fairsheet.render(sheet, snap))
    Path(a.out, "fair.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=1))
    print(json.dumps({"snapshot": sheet["snapshot"], "markets": len(sheet["rows"]),
                      "markets_without_ref": sheet["markets_without_ref"]}, ensure_ascii=False))
    return 0


def cmd_live(a, cfg):
    """Sans clé : Polymarket (référence) vs NetBet (pages publiques). Clôture + règlement inclus."""
    from . import live
    from .sources import netbet as nb, polymarket as pm
    now = datetime.now(timezone.utc)
    lcfg = {**live.CFG, **cfg.get("live", {})}
    if os.environ.get("BANKROLL"):
        lcfg["bankroll"] = float(os.environ["BANKROLL"])
    errors = []
    ref, err = pm.fetch(cfg.get("polymarket_tags", pm.TAGS))
    errors += err
    closed = live.update_closing(a.state, ref, now)

    def get_market(mid):
        try:
            r = pm.get(f"/markets?id={mid}", pause=0.3)
            return r[0] if r else None
        except pm.SourceError:
            return None
    settled = live.settle(a.state, get_market, now)
    # NetBet : pages de compétition -> événements dans la fenêtre -> pages d'événements (1 req / 5 s)
    soon = [g for g in ref if 0 < live._mins(g["commence"], now) <= lcfg["max_hours_to_start"] * 60]
    book_events, urls = [], []
    if soon:
        for comp in cfg.get("netbet_competitions", nb.COMPETITIONS):
            try:
                urls += nb.event_urls(nb.fetch(comp))
            except nb.SourceError as e:
                errors.append(str(e))
        from .match import slug_hits
        wanted = [u for u in dict.fromkeys(urls) if any(slug_hits(u, g["home"], g["away"]) for g in soon)]
        for u in wanted[: lcfg.get("max_event_pages", 40)]:
            try:
                book_events += nb.parse_event_page(nb.fetch(u), u)
            except nb.SourceError as e:
                errors.append(str(e))
    pairs, cands = live.scan(ref, book_events, "netbet_fr", now, lcfg)
    # Mesure de recherche : TOUTES les cotes comparables (même négatives), agrégées par famille de marché.
    _, allc = live.scan(ref, book_events, "netbet_fr", now,
                        {**lcfg, "min_ev": -9, "min_ev_cons": -9, "diagnostic": True, "min_odds": 1.01, "max_odds": 100})
    obs = live.summarize(allc, now)
    store.append(a.state, "observations.jsonl", [obs])
    rows = store.read(a.state, tracker.BETS)
    seen = {(r["event_id"], r["group"]) for r in rows}
    today = now.date().isoformat()
    done_today = sum(1 for r in rows if r.get("found_at", "")[:10] == today)
    cands = [c for c in cands if (c["event_id"], c["group"]) not in seen]
    picks = engine.select_daily(cands, {"max_bets_per_day": lcfg["max_bets_per_day"]},
                                {r["bet_id"] for r in rows}, done_today)
    tracker.record_bets(a.state, picks)
    meta = {"at": now.isoformat(), "mode": "live", "ref_games": len(ref), "ref_soon": len(soon),
            "netbet_pages": len(book_events), "pairs": len(pairs), "candidates": len(cands), "picked": len(picks),
            "closing_updates": closed, "settled": settled, "errors": errors}
    store.append(a.state, "runs.jsonl", [meta])
    print(json.dumps(meta, ensure_ascii=False))
    if picks:
        body = "@" + os.environ.get("GITHUB_REPOSITORY_OWNER", "") + " nouveaux paris :\n\n" + \
            "\n".join(notify.md_bet(b) for b in picks)
        print(notify.github_issue(f"Paris du {now:%d/%m/%Y}", body))
        print(notify.send(f"{len(picks)} value bet(s)", notify.message(picks), a.link))
    print(notify.github_dashboard(dashboard_md(a.state, meta, obs) + "\n\n" + fair_table_md(
        [g for g in ref if 0 < live._mins(g["commence"], now) <= 72 * 60])))
    if errors and not ref:
        print(notify.github_issue(f"Panne source {now:%d/%m/%Y}", "Sources en erreur :\n- " + "\n- ".join(errors[:20])))
        return 2
    return 0


def fair_table_md(games, limit=40) -> str:
    """Cotes justes (sans marge) des prochains matchs : pour juger soi-même une cote boostée d'un book ANJ."""
    def o(m, k, sel):
        leg = (m.get(k) or {}).get(sel)
        return f"{1 / leg['p']:.2f}" if leg and leg["p"] > 0 else "—"
    rows = ["## Cotes justes Polymarket (sans marge) — un boost n'est intéressant que s'il dépasse ces cotes",
            "| Heure (Paris) | Match | 1 | N | 2 | +2,5 | −2,5 | 2 marquent |", "|---|---|---|---|---|---|---|---|"]
    from zoneinfo import ZoneInfo
    for g in sorted(games, key=lambda g: g["commence"])[:limit]:
        m = g["markets"]
        t = datetime.fromisoformat(g["commence"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Paris"))
        jour = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"][t.weekday()]
        rows.append(f"| {jour} {t:%d/%m %H:%M} | {g['home']} – {g['away']} | {o(m, '1x2', 'home')} | {o(m, '1x2', 'draw')} | "
                    f"{o(m, '1x2', 'away')} | {o(m, 'ou@2.5', 'over')} | {o(m, 'ou@2.5', 'under')} | {o(m, 'btts', 'yes')} |")
    if len(rows) == 3:
        rows.append("| — | aucun match liquide dans les 72 h | | | | | | |")
    return "\n".join(rows)


def dashboard_md(root, meta, obs=None) -> str:
    st = tracker.stats(root)
    clv, roi = st["clv"], st["roi"]
    ci = clv.get("ci95")
    pct = lambda x: "—" if x is None else f"{x:+.2%}"  # noqa: E731
    rows = store.read(root, tracker.BETS)[-15:][::-1]
    lines = [f"Dernière exécution : {meta['at'][:16]} UTC · matchs de référence {meta['ref_games']} · "
             f"appariés NetBet {meta['pairs']} · candidats {meta['candidates']} · erreurs {len(meta['errors'])}",
             "", "## Mesure de l'avantage", f"- Paris : {st['bets_total']} (ouverts {st['bets_open']}, réglés {st['bets_settled']})",
             f"- **CLV moyenne : {pct(clv.get('mean'))}** (n={clv['n']}, IC95 % "
             f"{(f'{ci[0]:+.2%} à {ci[1]:+.2%}') if ci else 'n/a'}) — {st['clv_coverage']}",
             f"- EV attendue moyenne : {pct(st['ev_expected'].get('mean'))}",
             f"- ROI réel : {pct(roi['roi'])} sur {roi['n']} paris réglés (mises {roi['staked']:.1f} €, gain {roi['pnl']:+.1f} €)",
             f"- {st['note']}", "", "## Derniers paris", "| Match | Pari | Cote | EV | CLV | Résultat |", "|---|---|---|---|---|---|"]
    for r in rows:
        res = (r.get("result") or {}).get("won")
        lines.append(f"| {r['home']}–{r['away']} | {r.get('label', r['selection'])} | {r['odds']:.2f} | {r['ev']:+.1%} | "
                     f"{pct(r['close']['clv_odds']) if r.get('close') else '—'} | "
                     f"{'✅' if res is True else '❌' if res is False else ('remboursé' if r['status'] == 'settled' else '…')} |")
    if obs and obs.get("n"):
        lines += ["", f"## Marché NetBet face à la cote juste (dernier passage : {obs['n']} cotes comparées, "
                      f"{obs['n_ev_pos']} à EV > 0)", "| Famille | n | EV médiane | meilleure EV |", "|---|---|---|---|"]
        for k, v in obs["by_family"].items():
            lines.append(f"| {k} | {v['n']} | {v['median_ev']:+.1%} | {v['max_ev']:+.1%} |")
        t = obs["top"][0]
        lines.append(f"\nMeilleure cote vue : {t['home']}–{t['away']}, {t['label']} @ {t['odds']} "
                     f"(juste {t['fair_odds']:.2f}, EV {t['ev']:+.1%}). Seuil d'alerte : EV ≥ +3 % et EV prudente > 0.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="autonome")
    ap.add_argument("cmd", choices=["scan", "close", "settle", "stats", "report", "fair", "live"])
    ap.add_argument("--state", default="state")
    ap.add_argument("--out", default="site")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--within-min", type=int, default=240)
    ap.add_argument("--link", default=None)
    ap.add_argument("--notify-empty", action="store_true")
    ap.add_argument("--csv", default=None, help="fair : chemin local ou URL https de fixtures.csv")
    a = ap.parse_args(argv)
    return {"scan": cmd_scan, "close": cmd_close, "settle": cmd_settle, "stats": cmd_stats,
            "report": cmd_report, "fair": cmd_fair, "live": cmd_live}[a.cmd](a, load_cfg(a.config))


if __name__ == "__main__":
    sys.exit(main())
