"""Notifications : ntfy.sh (sans compte) et Telegram. Secrets via variables d'environnement."""
from __future__ import annotations

import json
import os
import urllib.request


def fmt_bet(b: dict) -> str:
    return (f"{b['home'] or '?'} - {b['away'] or '?'}\n{b['group']} : {b['selection']} @ {b['odds']:.2f} ({b['book']})\n"
            f"cote juste {b['fair_odds']:.2f} (p={b['p_fair']:.1%}, réf {'+'.join(b['ref_books'][:2])}, "
            f"marge réf {b['ref_overround']:.1%}, dé-vig {b['devig_method']})\n"
            f"EV {b['ev']:+.1%} · mise {b['stake']:.1f} € · avant {b['commence'][11:16]} UTC ({b['commence'][:10]})")


def message(bets: list[dict]) -> str:
    if not bets:
        return "NO BET aujourd'hui : aucune cote ne dépasse les seuils."
    return "\n\n".join(fmt_bet(b) for b in bets)


def send(title: str, body: str, click: str | None = None) -> dict:
    sent = {}
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        h = {"Title": title.encode("utf-8").decode("latin-1", "ignore"), "Tags": "moneybag"}
        if click:
            h["Click"] = click
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), headers=h)
        sent["ntfy"] = _fire(req)
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        data = json.dumps({"chat_id": chat, "text": f"{title}\n\n{body}"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data,
                                     headers={"Content-Type": "application/json"})
        sent["telegram"] = _fire(req)
    if not sent:
        sent["none"] = "aucun canal configuré (NTFY_TOPIC ou TELEGRAM_*)"
    return sent


def _fire(req) -> str:
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return f"ok {r.status}"
    except Exception as e:  # noqa: BLE001 - ne jamais exposer l'URL (secret)
        return f"échec {type(e).__name__}"
