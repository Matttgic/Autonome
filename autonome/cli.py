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


def _blocked(state, source, now) -> bool:
    """Source en pause (elle nous a renvoyé 403/429 récemment) : on respecte le refus, sans insister."""
    rows = store.read(state, "backoff.jsonl")
    until = max((r["until"] for r in rows if r["source"] == source), default="")
    return until > now.isoformat()


def _maybe_block(state, source, errors_before: int, errors: list, now, hours=6) -> None:
    new = errors[errors_before:]
    if any(("HTTP 403" in e or "HTTP 429" in e) for e in new):
        from datetime import timedelta
        store.append(state, "backoff.jsonl", [{"source": source, "at": now.isoformat(),
                                               "until": (now + timedelta(hours=hours)).isoformat()}])
        errors.append(f"{source} : accès refusé (403/429) -> pause de {hours} h, aucune insistance")


def cmd_live(a, cfg):
    """Sans clé : Polymarket (référence) vs NetBet (pages publiques). Clôture + règlement inclus."""
    from . import live
    from .sources import netbet as nb, polymarket as pm
    now = datetime.now(timezone.utc)
    lcfg = {**live.CFG, **cfg.get("live", {})}
    if os.environ.get("BANKROLL"):
        lcfg["bankroll"] = float(os.environ["BANKROLL"])
    errors = []
    try:
        ref, err = pm.fetch(cfg.get("polymarket_tags", pm.TAGS + pm.TAGS_2WAY))
        ref = [g for g in ref if isinstance(g.get("commence"), str) and g["commence"].endswith("Z")]
    except Exception as e:  # noqa: BLE001
        ref, err = [], [f"polymarket: {type(e).__name__}"]
    errors += err
    closed = live.update_closing(a.state, ref, now)

    def get_market(mid):
        try:
            r = pm.get(f"/markets?id={mid}&closed=true", pause=0.3) or pm.get(f"/markets?id={mid}", pause=0.3)
            return r[0] if r else None
        except pm.SourceError:
            return None
    settled = live.settle(a.state, get_market, now)

    def get_event(slug):
        try:
            r = pm.get(f"/events?slug={slug}", pause=0.3)
            return r[0] if r else None
        except pm.SourceError:
            return None
    from .boosts import settle as settle_boosts
    try:
        settled += settle_boosts(a.state, get_event, now)
    except Exception as e:  # noqa: BLE001
        errors.append(f"règlement boosts: {type(e).__name__}")
    # Paris « consensus » : résultat LiveScore (API publique sans clé), une requête par sport et par jour UTC,
    # seulement pour les jours où un pari attend son résultat (idée reprise de cotes-value).
    try:
        from . import consensus as CS0
        from .sources import livescore
        rows_s = store.read(a.state, tracker.BETS)
        results = []
        ls0 = len(errors)
        for sport, day in sorted(CS0.days_to_fetch(rows_s, now)) if not _blocked(a.state, "livescore", now) else []:
            try:
                results += livescore.fetch(sport, day)
            except livescore.SourceError as ex:
                errors.append(str(ex))
                if "HTTP 403" in str(ex) or "HTTP 429" in str(ex):
                    break  # refus : on n'insiste pas sur les autres jours
        _maybe_block(a.state, "livescore", ls0, errors, now)
        n_cons = CS0.settle(rows_s, results, now) if results else 0
        if n_cons:
            store.write_all(a.state, tracker.BETS, rows_s)
            settled += n_cons
    except Exception as e:  # noqa: BLE001
        errors.append(f"règlement consensus: {type(e).__name__}")
    # NetBet : pages de compétition -> événements dans la fenêtre -> pages d'événements (1 req / 5 s)
    soon = [g for g in ref if 0 < live._mins(g["commence"], now) <= lcfg["max_hours_to_start"] * 60]
    book_events, urls = [], []
    nb0 = len(errors)
    if soon and not _blocked(a.state, "netbet", now):
        for comp in cfg.get("netbet_competitions", nb.COMPETITIONS):
            try:
                urls += nb.event_urls(nb.fetch(comp))
            except nb.SourceError as e:
                errors.append(str(e))
                if "HTTP 403" in str(e) or "HTTP 429" in str(e):
                    break  # refus : on arrête immédiatement
        from .match import slug_hits
        wanted = [u for u in dict.fromkeys(urls) if any(slug_hits(u, g["home"], g["away"]) for g in soon)]
        for u in wanted[: lcfg.get("max_event_pages", 40)]:
            try:
                book_events += nb.parse_event_page(nb.fetch(u), u)
            except Exception as e:  # noqa: BLE001 - une page défectueuse ne doit jamais arrêter le run
                errors.append(f"netbet {u}: {type(e).__name__}")
    _maybe_block(a.state, "netbet", nb0, errors, now)
    # Unibet : une seule page publique lisible (1X2 des matchs mis en avant)
    from .sources import unibet as ub
    ub_events = []
    ub0 = len(errors)
    if soon and not _blocked(a.state, "unibet", now):
        for pg in cfg.get("unibet_pages", ub.PAGES):
            try:
                ub_events += ub.parse_page(ub.fetch(pg))
            except Exception as e:  # noqa: BLE001
                errors.append(f"unibet {pg}: {type(e).__name__}: {e}"[:160])
    # PMU (Kambi) : tous les sports (marché principal), puis tous les marchés des matchs appariés à Polymarket
    from .match import pair as _pair
    from .sources import kambi
    pmu_events, pmu_cov = [], {}
    try:
        pmu_main, err = kambi.fetch_main("pmusportsfr")
        errors += err
        for e in pmu_main:
            pmu_cov[e["sport"]] = pmu_cov.get(e["sport"], 0) + 1
        horizon = [e for e in pmu_main if 0 < live._mins(e["commence"], now) <= lcfg["max_hours_to_start"] * 60]
        matched = {id(b) for _, b, _ in _pair(soon, horizon, with_swap=True)}
        n_full = 0
        for e in horizon:
            if id(e) in matched and e["sport"] == "FOOTBALL" and n_full < lcfg.get("max_pmu_full", 40):
                try:
                    e = kambi.fetch_full("pmusportsfr", e)
                    n_full += 1
                except kambi.SourceError as ex:
                    errors.append(str(ex))
            pmu_events.append(e)
    except Exception as e:  # noqa: BLE001
        errors.append(f"pmu: {type(e).__name__}: {e}"[:160])
    _maybe_block(a.state, "unibet", ub0, errors, now)
    books = {"netbet_fr": book_events, "unibet_fr": ub_events, "pmu_fr": pmu_events}
    # coteur.com (instantané du workflow coteur) : Betclic, Unibet, Betsson, Olybet, Vbet, DAZN Bet, etc.
    from . import consensus as CS
    from .sources import coteur_odds
    try:
        ct_books, ct_matches, why = coteur_odds.load(Path(a.state, "coteur_odds.json"), now)
    except Exception as e:  # noqa: BLE001
        ct_books, ct_matches, why = {}, [], f"illisible ({type(e).__name__})"
    if why:
        errors.append(f"coteur : {why}")
    for bk, evs in ct_books.items():
        if books.get(bk):  # source directe plus fraîche (PMU via Kambi, NetBet) : prioritaire
            continue
        books[bk] = evs
    pairs, cands, allc = [], [], []
    diag = {**lcfg, "min_ev": -9, "min_ev_cons": -9, "diagnostic": True, "min_odds": 1.01, "max_odds": 100}
    for bk, evs in books.items():
        p_, c_ = live.scan(ref, evs, bk, now, lcfg)
        pairs += p_
        cands += c_
        allc += live.scan(ref, evs, bk, now, diag)[1]  # mesure : TOUTES les cotes comparables, même négatives
    # consensus : uniquement les matchs SANS référence Polymarket (sinon deux références pour un même match)
    from .match import pair as _pair2
    covered = {id(b) for _, b in _pair2(ref, ct_matches)}
    ct_matches = [m for m in ct_matches if id(m) not in covered]
    cons_diag = [x for m in ct_matches for x in CS.evaluate(m, now, lcfg["bankroll"],
                                                                {"min_ev": -9, "max_ev": 9, "max_dispersion": 9, "diagnostic": True})]
    cons_picks = [x for m in ct_matches for x in CS.evaluate(m, now, lcfg["bankroll"])]
    obs = live.summarize(allc, now)
    obs["consensus"] = {bk: live.summarize([c for c in cons_diag if c["book"] == bk], now)["by_family"]
                        for bk in sorted({c["book"] for c in cons_diag})}
    obs["consensus_top"] = [{k: c[k] for k in ("book", "sport", "home", "away", "label", "odds", "fair_odds", "ev")}
                            for c in sorted(cons_diag, key=lambda c: -c["ev"])[:8]]
    obs["by_book"] = {bk: live.summarize([c for c in allc if c["book"] == bk], now)["by_family"] for bk in books}
    obs["pairs_by_book"] = {bk: sum(1 for c in {(x["book"], x["event_id"]) for x in allc} if c[0] == bk) for bk in books}
    store.append(a.state, "observations.jsonl", [obs])
    rows = store.read(a.state, tracker.BETS)
    seen = {r["event_id"] for r in rows if r.get("ref_kind") == "polymarket"}
    today = now.date().isoformat()
    done_today = sum(1 for r in rows if r.get("found_at", "")[:10] == today and r.get("ref_kind") != "consensus-anj")
    cons_today = sum(1 for r in rows if r.get("found_at", "")[:10] == today and r.get("ref_kind") == "consensus-anj")
    best: dict = {}
    for c in cands:  # un seul pari par match : les marchés d'un même match sont corrélés
        if c["event_id"] not in seen and (c["event_id"] not in best or c["ev_cons"] > best[c["event_id"]]["ev_cons"]):
            best[c["event_id"]] = c
    cands = list(best.values())
    picks = engine.select_daily(cands, {"max_bets_per_day": lcfg["max_bets_per_day"]},
                                {r["bet_id"] for r in rows}, done_today)
    # Cotes boostées Winamax (coteur.com) évaluées contre Polymarket + modèle de score
    from . import boosts as BO
    from .sources import coteur
    boost_eval, boost_picks = [], []
    try:
        parsed = coteur.parse(coteur.fetch())
        seen_rows = store.read(a.state, "boosts_seen.jsonl")
        seen = {(r.get("event"), r.get("text")) for r in seen_rows}  # clé stable (indépendante de la cote)
        first = not seen_rows  # premier relevé = référence : on ne sait pas dater ces boosts
        cache: dict = {}
        boost_eval = [BO.evaluate(b, ref, cache, allow_team_legs=(not first and (b["event"], b["text"]) not in seen))
                      for b in parsed]
        store.append(a.state, "boosts_seen.jsonl",
                     [{"id": b["id"], "first_seen": now.isoformat(), "event": b["event"], "text": b["text"],
                       "odds": b["odds"]} for b in parsed if (b["event"], b["text"]) not in seen])
    except Exception as e:  # noqa: BLE001
        errors.append(f"boosts: {type(e).__name__}: {e}"[:160])
    known = {r["bet_id"] for r in rows}
    for e in boost_eval:
        b = BO.to_bet(e, now, lcfg["bankroll"], lcfg["kelly_mult"], lcfg["stake_cap_pct"])
        open_ev = {r["event_id"] for r in rows if r["status"] == "open"} | {x["event_id"] for x in boost_picks}
        if b and b["bet_id"] not in known and b["event_id"] not in open_ev:  # un boost par match (corrélés)
            boost_picks.append(b)
    picks += boost_picks
    open_ev = {r["event_id"] for r in rows if r["status"] == "open"}
    for c in sorted(cons_picks, key=lambda c: -c["ev_cons"]):  # quota séparé, après les paris Polymarket
        if cons_today >= lcfg.get("max_consensus_per_day", 3):
            break
        if c["bet_id"] not in known and c["event_id"] not in open_ev:
            picks.append(c)
            open_ev.add(c["event_id"])
            cons_today += 1
    tracker.record_bets(a.state, picks)
    rows2 = store.read(a.state, tracker.BETS)
    if CS.closing(rows2, ct_matches, now):
        store.write_all(a.state, tracker.BETS, rows2)
    obs["boosts"] = {"lus": len(boost_eval), "evaluables": sum(e["evaluable"] for e in boost_eval),
                     "value": len(boost_picks),
                     "top": [{k: e.get(k) for k in ("event", "text", "odds", "fair_odds", "ev", "ev_cons", "commence")}
                             for e in sorted((x for x in boost_eval if x["evaluable"]), key=lambda x: -x["ev"])[:15]]}
    store.write_all(a.state, "observations.jsonl", store.read(a.state, "observations.jsonl")[:-1] + [obs])
    meta = {"at": now.isoformat(), "mode": "live", "ref_games": len(ref), "ref_soon": len(soon),
            "netbet_pages": len(book_events), "unibet_events": len(ub_events), "pmu_events": len(pmu_events),
            "pmu_par_sport": pmu_cov, "coteur_matchs": len(ct_matches),
            "coteur_books": {k: len(v) for k, v in ct_books.items()}, "pairs": len(pairs), "candidates": len(cands), "picked": len(picks),
            "closing_updates": closed, "settled": settled, "boosts_lus": len(boost_eval),
            "boosts_evaluables": sum(e["evaluable"] for e in boost_eval), "boosts_value": len(boost_picks),
            "errors": errors}
    store.append(a.state, "runs.jsonl", [meta])
    print(json.dumps(meta, ensure_ascii=False))
    if picks:
        body = "@" + os.environ.get("GITHUB_REPOSITORY_OWNER", "") + " nouveaux paris :\n\n" + \
            "\n".join(notify.md_bet(b) for b in picks)
        print(notify.github_issue(f"Paris du {now:%d/%m/%Y}", body))
        print(notify.send(f"{len(picks)} value bet(s)", notify.message(picks), a.link))
    print(notify.github_dashboard(dashboard_md(a.state, meta, obs) + "\n\n" + fair_table_md(
        [g for g in ref if 0 < live._mins(g["commence"], now) <= 72 * 60])))
    if (errors and not ref) or (soon and not book_events and not ub_events and not pmu_events):
        print(notify.github_issue_once(f"Panne source {now:%d/%m/%Y}",
                                       "Sources en erreur (une alerte par jour) :\n- " + "\n- ".join(errors[:20] or ["NetBet : aucune page lue"])))
        return 2 if not ref else 0
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
        rows.append(f"| {jour} {t:%d/%m %H:%M} | {notify.md(g['home'])} – {notify.md(g['away'])} | {o(m, '1x2', 'home')} | {o(m, '1x2', 'draw')} | "
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
             f"matchs appariés (NetBet+Unibet+PMU) {meta['pairs']} · PMU {meta.get('pmu_events', 0)} matchs lus · candidats {meta['candidates']} · erreurs {len(meta['errors'])}",
             "", "## Mesure de l'avantage", f"- Paris : {st['bets_total']} (ouverts {st['bets_open']}, réglés {st['bets_settled']})",
             f"- **CLV moyenne : {pct(clv.get('mean'))}** (n={clv['n']}, IC95 % "
             f"{(f'{ci[0]:+.2%} à {ci[1]:+.2%}') if ci else 'n/a'}) — {st['clv_coverage']}",
             f"- EV attendue moyenne : {pct(st['ev_expected'].get('mean'))}",
             f"- ROI réel : {pct(roi['roi'])} sur {roi['n']} paris réglés (mises {roi['staked']:.1f} €, gain {roi['pnl']:+.1f} €)",
             f"- {st['note']}", "", "## Derniers paris", "| Match | Pari | Cote | EV | CLV | Résultat |", "|---|---|---|---|---|---|"]
    for r in rows:
        res = (r.get("result") or {}).get("won")
        lines.append(f"| {notify.md(r['home'])}–{notify.md(r['away'])} | {notify.md(r.get('label', r['selection']))} | {r['odds']:.2f} | {r['ev']:+.1%} | "
                     f"{pct(r['close']['clv_odds']) if r.get('close') else '—'} | "
                     f"{'✅' if res is True else '❌' if res is False else ('remboursé' if r['status'] == 'settled' else '…')} |")
    stale = [r for r in store.read(root, tracker.BETS) if r.get("status") == "open" and r.get("commence")
             and (datetime.now(timezone.utc) - datetime.fromisoformat(r["commence"].replace("Z", "+00:00"))).total_seconds() > 86400]
    if stale:
        lines += ["", f"## À régler à la main ({len(stale)} paris commencés depuis plus de 24 h sans résultat automatique)",
                  "| Match | Pari | Book | Début (UTC) |", "|---|---|---|---|"]
        lines += [f"| {notify.md(r['home'])}–{notify.md(r['away'])} | {notify.md(r.get('label', r['selection']))} | "
                  f"{notify.md(r.get('book', ''))} | {r['commence'][:16]} |" for r in stale[-20:]]
    if obs and obs.get("n"):
        lines += ["", f"## Bookmakers face à la cote juste (dernier passage : {obs['n']} cotes comparées, "
                      f"{obs['n_ev_pos']} à EV > 0)", "| Book · famille | n | EV médiane | meilleure EV |", "|---|---|---|---|"]
        for bk, fams in (obs.get("by_book") or {"tous": obs["by_family"]}).items():
            for k, v in fams.items():
                lines.append(f"| {bk} · {k} | {v['n']} | {v['median_ev']:+.1%} | {v['max_ev']:+.1%} |")
        t = obs["top"][0] if obs["top"] else {"home": "?", "away": "?", "label": "—", "odds": 0, "fair_odds": 0, "ev": 0}
        lines.append(f"\nMeilleure cote vue : {notify.md(t['home'])}–{notify.md(t['away'])}, {notify.md(t['label'])} @ {t['odds']} "
                     f"({t.get('book', '?')}) "
                     f"(juste {t['fair_odds']:.2f}, EV {t['ev']:+.1%}). Seuil d'alerte : EV ≥ +3 % et EV prudente > 0.")
    cs = (obs or {}).get("consensus")
    if cs:
        lines += ["", "## Bookmakers face au consensus ANJ (matchs sans Polymarket, via coteur.com)",
                  "| Book · marché | n | EV médiane | meilleure EV |", "|---|---|---|---|"]
        for bk, fams in cs.items():
            for k, v in fams.items():
                lines.append(f"| {bk} · {k} | {v['n']} | {v['median_ev']:+.1%} | {v['max_ev']:+.1%} |")
    bo = (obs or {}).get("boosts")
    if bo:
        lines += ["", f"## Cotes boostées Winamax (via coteur.com) : {bo['lus']} lues, {bo['evaluables']} évaluables "
                      f"(matchs cotés sur Polymarket, libellés reconnus), {bo['value']} au-dessus du seuil (EV ≥ 5 % et EV prudente ≥ 0)",
                  "| Match | Boost | Cote | Cote juste | EV | EV prudente |", "|---|---|---|---|---|---|"]
        for t in bo["top"]:
            lines.append(f"| {notify.md(t['event'])} | {notify.md(t['text'])} | {t['odds']:.2f} | {t['fair_odds']:.2f} | "
                         f"{t['ev']:+.1%} | {t['ev_cons']:+.1%} |")
        if not bo["top"]:
            lines.append("| — | aucun boost actuel ne porte sur un match coté par Polymarket avec un libellé reconnu | | | | |")
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
