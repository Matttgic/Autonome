#!/usr/bin/env python3
"""Affiche des pages publiques dans un navigateur sans écran (Playwright) et enregistre :
- le HTML rendu (après exécution du JavaScript de la page, comme pour un visiteur) ;
- la liste des requêtes réseau JSON faites par la page (URL, statut, début de la réponse).
Aucun contournement : si un site renvoie 403/captcha, c'est noté et on passe. 1 page / 5 s.
Usage : python tools/render.py dossier_sortie url1 url2 ...
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def main(out, urls):
    Path(out).mkdir(parents=True, exist_ok=True)
    index = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(locale="fr-FR", timezone_id="Europe/Paris")
        for u in urls:
            page = ctx.new_page()
            xhr = []

            def on_resp(r, xhr=xhr):
                ct = r.headers.get("content-type", "")
                kind = r.request.resource_type
                if ("json" in ct or kind in ("xhr", "fetch")) and len(xhr) < 120:
                    try:
                        body = r.text()[:200_000]
                    except Exception:  # noqa: BLE001
                        body = ""
                    xhr.append({"url": r.url, "status": r.status, "type": kind, "ct": ct, "len": len(body), "body": body})
            page.on("response", on_resp)
            name = re.sub(r"[^A-Za-z0-9._-]", "_", u.replace("https://", ""))[:120]
            try:
                resp = page.goto(u, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(8000)
                st = resp.status if resp else None
                Path(out, name + ".html").write_text(page.content())
            except Exception as e:  # noqa: BLE001
                st = f"erreur {type(e).__name__}"
            Path(out, name + ".xhr.json").write_text(json.dumps(xhr, ensure_ascii=False))
            index.append(f"{u} {st} xhr_json={len(xhr)}")
            print(index[-1], flush=True)
            page.close()
            time.sleep(5)
        b.close()
    Path(out, "index.txt").write_text("\n".join(index) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
