#!/usr/bin/env python3
"""Sonde de faisabilité à lancer sur le téléphone (Termux : pkg install python).

Lit quelques pages publiques de cotes, 1 requête toutes les 4 s, avec un User-Agent honnête.
N'envoie aucun identifiant, ne contourne aucune protection : si un site répond 403/captcha,
on le note simplement comme « bloqué ». Écrit un résumé compact à coller dans le chat.
Usage : python probe.py [urls.txt]   (une URL par ligne ; sinon liste par défaut)
"""
import json, sys, time, urllib.request, urllib.error

DEFAULT = [
    "https://www.winamax.fr/paris-sportifs/sports/1",
    "https://www.betclic.fr/football-s1",
    "https://www.unibet.fr/sport/football",
    "https://www.zebet.fr/paris-football",
    "https://www.pmu.fr/sport/",
    "https://www.enligne.parionssport.fdj.fr/paris-football",
    "https://www.netbet.fr/football",
    "https://www.pinnacle.com/fr/soccer/matchups/",
]


def probe(url):
    req = urllib.request.Request(url, headers={"User-Agent": "autonome-probe/0.1 (usage personnel)",
                                               "Accept-Language": "fr-FR"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read(400_000)
            txt = body.decode("utf-8", "replace")
            return {"url": url, "status": r.status, "type": r.headers.get("content-type"), "bytes": len(body),
                    "ms": int((time.time() - t) * 1000), "json_state": "__PRELOADED_STATE__" in txt or "application/json" in txt,
                    "has_odds_words": sum(w in txt.lower() for w in ("cote", "odds", "1.", "pari")),
                    "head": " ".join(txt[:200].split())}
    except urllib.error.HTTPError as e:
        return {"url": url, "status": e.code, "blocked": e.code in (401, 403, 429)}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "error": type(e).__name__}


if __name__ == "__main__":
    urls = [l.strip() for l in open(sys.argv[1])] if len(sys.argv) > 1 else DEFAULT
    out = []
    for u in filter(None, urls):
        out.append(probe(u)); time.sleep(4)
    print(json.dumps(out, ensure_ascii=False, indent=1))
