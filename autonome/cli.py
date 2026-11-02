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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="autonome")
    ap.add_argument("cmd", choices=["scan", "close", "settle", "stats", "report", "fair"])
    ap.add_argument("--state", default="state")
    ap.add_argument("--out", default="site")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--within-min", type=int, default=240)
    ap.add_argument("--link", default=None)
    ap.add_argument("--notify-empty", action="store_true")
    ap.add_argument("--csv", default=None, help="fair : chemin local ou URL https de fixtures.csv")
    a = ap.parse_args(argv)
    return {"scan": cmd_scan, "close": cmd_close, "settle": cmd_settle, "stats": cmd_stats,
            "report": cmd_report, "fair": cmd_fair}[a.cmd](a, load_cfg(a.config))


if __name__ == "__main__":
    sys.exit(main())
