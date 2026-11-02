#!/usr/bin/env python3
"""Transforme la sortie JSON de probe.py en tableau Markdown (journal GitHub Actions / résumé du run).

Usage : python tools/probe.py tools/probe_urls.txt | python tools/probe_summary.py
Verdicts : lisible (HTTP 200 avec contenu), bloqué (401/403/429 : noté, jamais contourné), erreur (autre).
"""
import json
import sys


def verdict(r: dict) -> str:
    if r.get("error"):
        return f"erreur réseau ({r['error']})"
    st = r.get("status")
    if st in (401, 403, 429):
        return f"bloqué (HTTP {st})"
    if st == 200 and r.get("bytes", 0) > 0:
        return "lisible"
    return f"autre (HTTP {st})"


def table(rows: list[dict]) -> str:
    out = ["| URL | verdict | octets | type | JSON embarqué | mots « cote/odds » | titre | URL finale |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['url']} | {verdict(r)} | {r.get('bytes', '—')} | {r.get('type', '—')} | "
                   f"{r.get('json_state', '—')} | {r.get('has_odds_words', '—')} | "
                   f"{(r.get('title') or '—').replace('|', '/')} | {r.get('final_url', '—')} |")
    return "\n".join(out)


if __name__ == "__main__":
    print(table(json.load(sys.stdin)))
