"""coteur.com (comparateur public) : page /cotes-boostees = cotes boostées Winamax (logo bookid 33 vérifié le
2026-11-02), mise max, libellé du match et du pari. Lisible depuis GitHub (HTTP 200), aucune connexion.
La page complète pèse ~16 Mo (archives) ; les cartes les plus récentes sont en tête : on n'en lit que le début.
"""
from __future__ import annotations

import hashlib
import html as H
import http.client
import re
import time
import urllib.error
import urllib.request

URL = "https://www.coteur.com/cotes-boostees"
UA = "autonome/0.4 (outil perso; 1 requete par heure)"
BOOKIDS = {"33": "winamax"}


class SourceError(RuntimeError):
    pass


def fetch(max_bytes: int = 2_500_000, timeout: int = 40) -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept-Language": "fr-FR"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(max_bytes).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise SourceError(f"coteur: HTTP {e.code}") from None
    except (OSError, http.client.HTTPException) as e:
        raise SourceError(f"coteur: {type(e).__name__}") from None
    finally:
        time.sleep(2)


def _txt(s: str) -> str:
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def parse(page: str, limit: int = 400) -> list[dict]:
    out = []
    for c in page.split('<div class="custom-card p-0 overflow-hidden')[1:limit + 1]:
        try:
            book = re.search(r"logo/bookid/(\d+)\.webp", c)
            ev = re.search(r'text-truncate"[^>]*>(.*?)</span>', c, re.S)
            ti = re.search(r'card-title[^>]*>(.*?)</h5>', c, re.S)
            od = re.search(r'display-6[^>]*>\s*([\d.,]+)\s*<', c)
            mx = re.search(r"Max:\s*([\d.,]+)\s*€", c)
            if not (book and ev and ti and od):
                continue
            label = re.sub(r"^Cote Boostée\s*:\s*", "", _txt(ev.group(1)))
            text, odds = _txt(ti.group(1)), float(od.group(1).replace(",", "."))
            bid = hashlib.sha1(f"{book.group(1)}|{label}|{text}|{odds}".encode()).hexdigest()[:12]
            out.append({"id": f"boost|{bid}", "book": BOOKIDS.get(book.group(1), f"book{book.group(1)}"),
                        "event": label, "text": text, "odds": odds,
                        "max_stake": float(mx.group(1).replace(",", ".")) if mx else None})
        except (ValueError, AttributeError):
            continue
    return out
