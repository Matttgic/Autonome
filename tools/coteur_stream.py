#!/usr/bin/env python3
"""Collecte coteur.com dans un vrai navigateur (Playwright) : pages publiques « cotes-<sport> » (aujourd'hui, demain,
pages 1..N). Pour chaque match affiché : identifiant, sport, compétition, heure, équipes (DOM) et cotes de chaque
bookmaker ANJ reçues par le flux temps réel de la page (messages socket.io « cotes »).
Aucun contournement : pages publiques en HTTP 200, une page à la fois, pause entre pages.
Usage : python tools/coteur_stream.py sortie.json [sport ...]
"""
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

SPORTS = ["foot", "tennis", "basket", "hockey", "volley", "rugby", "baseball", "mma", "boxe", "snooker",
          "tennis-de-table", "cyclisme", "golf"]   # handball, football-americain, flechettes, esport : 404 chez coteur
MAX_PAGES = {"foot": 40}
MSG = re.compile(r'42(\["cotes",.*?\])(?=\d+:42\[|$)', re.S)


def parse_msgs(text, sink):
    for m in MSG.finditer(text):
        try:
            msg = json.loads(m.group(1))
            c = msg[1]
            sink.setdefault(str(c["rencId"]), {})[f"{c['cote']['typename']}|{c['cote'].get('special', '')}"] = [
                {"book": v["bookId"], "odds": v.get("current"), "upd": v.get("lastUpdate"), "off": v.get("disable")}
                for v in c["cote"].get("values", [])]
        except Exception:  # noqa: BLE001
            continue


META = """() => [...document.querySelectorAll('.match-row')].map(r => {
  const a = r.querySelector('a[href^="/cote/"]'); const o = r.querySelector('[data-eventname]');
  const sp = r.querySelectorAll('.small span');
  return {href: a ? a.getAttribute('href') : null, name: o ? o.dataset.eventname : null,
          ts: o ? o.dataset.eventdate : null, compet: sp.length ? sp[0].textContent.trim() : null};
})"""


def main(out, sports):
    res = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "matches": {}, "pages": []}
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(locale="fr-FR", timezone_id="Europe/Paris")
        ctx.route(re.compile(r".*\.(png|jpe?g|gif|webp|svg|woff2?|ttf)(\?.*)?$|.*(googlesyndication|doubleclick|"
                             r"gambling-affiliation|google-analytics|googletagmanager).*"), lambda r: r.abort())
        for sp in sports:
            for pg in range(1, MAX_PAGES.get(sp, 15) + 1):
                url = f"https://www.coteur.com/cotes-{sp}?page={pg}"
                odds = {}
                page = ctx.new_page()
                page.on("response", lambda r, odds=odds: parse_msgs(r.text(), odds)
                        if "socket.io" in r.url and r.request.method == "GET" else None)
                page.on("websocket", lambda ws, odds=odds: ws.on("framereceived", lambda f: parse_msgs(
                    f if isinstance(f, str) else "", odds)))
                try:
                    st = page.goto(url, wait_until="domcontentloaded", timeout=40000)
                    page.wait_for_timeout(6000)
                    meta = page.evaluate(META)
                except Exception as e:  # noqa: BLE001
                    res["pages"].append(f"{url} erreur {type(e).__name__}")
                    page.close()
                    break
                page.close()
                n_new = 0
                for m in meta:
                    rid = re.search(r"-(\d{5,9})$", m.get("href") or "")
                    if not rid:
                        continue
                    rid = rid.group(1)
                    if rid not in res["matches"]:
                        n_new += 1
                    res["matches"][rid] = {"sport": sp, **m, "odds": odds.get(rid, res["matches"].get(rid, {}).get("odds", {}))}
                res["pages"].append(f"{url} {st.status if st else '?'} matchs={len(meta)} nouveaux={n_new} cotes={len(odds)}")
                print(res["pages"][-1], flush=True)
                if not meta or n_new == 0 or (st and st.status >= 400):
                    break
                time.sleep(2)
        b.close()
    json.dump(res, open(out, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:] or SPORTS)
