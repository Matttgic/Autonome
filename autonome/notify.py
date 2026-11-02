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


# --- GitHub Issues : alerte sans rien installer (GitHub envoie un e-mail au propriétaire mentionné) ---
def _gh(method: str, path: str, payload: dict | None = None):
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}", method=method,
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json", "User-Agent": "autonome"})
    opener = urllib.request.build_opener(_NoRedirect)  # le jeton ne suit jamais une redirection
    with opener.open(req, timeout=20) as r:
        return json.load(r)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def github_issue(title: str, body: str, label: str = "paris") -> str:
    """Crée l'issue du jour, ou y ajoute un commentaire si elle existe déjà. Renvoie un statut lisible."""
    try:
        issues = _gh("GET", f"/issues?state=open&labels={label}&per_page=30") or []
        same = [i for i in issues if i.get("title") == title]
        if same:
            _gh("POST", f"/issues/{same[0]['number']}/comments", {"body": body})
            return f"commentaire #{same[0]['number']}"
        r = _gh("POST", "/issues", {"title": title, "body": body, "labels": [label]})
        return f"issue #{r['number']}" if r else "pas de GITHUB_TOKEN"
    except Exception as e:  # noqa: BLE001
        return f"échec {type(e).__name__}"


def github_issue_once(title: str, body: str, label: str = "panne") -> str:
    try:
        issues = _gh("GET", f"/issues?state=all&labels={label}&per_page=30") or []
        if any(i.get("title") == title for i in issues):
            return "déjà signalé aujourd'hui"
        r = _gh("POST", "/issues", {"title": title, "body": body, "labels": [label]})
        return f"issue #{r['number']}" if r else "pas de GITHUB_TOKEN"
    except Exception as e:  # noqa: BLE001
        return f"échec {type(e).__name__}"


def md(s) -> str:
    """Échappe un texte venant d'une source externe (noms d'équipes) pour Markdown GitHub."""
    s = str(s if s is not None else "?")
    for ch in "\\`*_[]<>|#@!":
        s = s.replace(ch, "\\" + ch)
    return s.replace("\n", " ")[:80]


def github_dashboard(body: str, title: str = "📊 Tableau de bord Autonome") -> str:
    """Issue épinglable unique, dont le corps est réécrit à chaque exécution (aucune notification)."""
    try:
        issues = _gh("GET", "/issues?state=open&labels=tableau&per_page=10") or []
        same = [i for i in issues if i.get("title") == title]
        if same:
            _gh("PATCH", f"/issues/{same[0]['number']}", {"body": body})
            return f"tableau #{same[0]['number']}"
        r = _gh("POST", "/issues", {"title": title, "body": body, "labels": ["tableau"]})
        return f"tableau #{r['number']}" if r else "pas de GITHUB_TOKEN"
    except Exception as e:  # noqa: BLE001
        return f"échec {type(e).__name__}"


def md_bet(b: dict) -> str:
    """Un pari en Markdown, avec tout le détail vérifiable."""
    when = b["commence"][:16].replace("T", " ")
    url = b.get("url") or ""
    if b.get("ref_kind") == "polymarket-modele":
        legs = "\n".join(f"  - {md(x['match'])} : {x['pred']} {x.get('side') or ''} {x.get('args') or ''} → p = {x['p']:.2%} "
                         f"(λ dom/ext/ρ = {x['lambda']}, erreur de calage {x['fit_err']:.2%})" for x in b.get("boost_legs", []))
        return (f"### ⚡ {md(b['label'])}\n"
                f"**Cote boostée {b['odds']:.2f}** chez **{b['book']}** (mise max {b.get('max_stake') or '?'} €)\n"
                f"- Mise conseillée : **{b['stake']:.1f} €** (¼ Kelly sur la proba prudente, plafonnée par la mise max)\n"
                f"- EV : **{b['ev']:+.1%}** ; EV prudente {b['ev_cons']:+.1%} (chaque jambe diminuée de l'erreur de calage + 1 pt)\n"
                f"- Cote juste {b['fair_odds']:.2f} (p = {b['p_fair']:.2%}) : modèle de score Dixon-Coles calé sur les marchés "
                f"Polymarket (1X2, plus/moins, 2 marquent, buts par équipe), jambes indépendantes multipliées :\n{legs}\n"
                f"- Heure limite : premier coup d'envoi {when} UTC\n")
    if b.get("ref_kind") == "consensus-anj":
        return (f"### {md(b['home'])} – {md(b['away'])}  ·  {when} UTC ({md(b.get('sport'))})\n"
                f"**{md(b['label'])}** @ **{b['odds']:.2f}** chez **{b['book']}** — {url}\n"
                f"- Mise conseillée : **{b['stake']:.1f} €** (¼ Kelly sur la proba prudente, plafond 2 %)\n"
                f"- EV : **{b['ev']:+.1%}** contre le consensus, {b['ev_cons']:+.1%} en prudent\n"
                f"- Cote juste {b['fair_odds']:.2f} (p = {b['p_fair']:.2%}) = {md(b['devig_method'])} ; "
                f"écart entre bookmakers {b['spread']:.1%}. Référence plus faible que Polymarket (pas de marché sharp)\n"
                f"- Heure limite : coup d'envoi {when} UTC (vérifie que la cote est toujours ≥ {b['odds']:.2f})\n")
    return (f"### {md(b['home'])} – {md(b['away'])}  ·  {when} UTC\n"
            f"**{md(b['label'])}** @ **{b['odds']:.2f}** chez **{b['book']}** {('— ' + url) if url else ''}\n"
            f"- Mise conseillée : **{b['stake']:.1f} €** (¼ Kelly sur la proba prudente, plafond 2 %)\n"
            f"- EV : **{b['ev']:+.1%}** au milieu, {b['ev_cons']:+.1%} en prudent\n"
            f"- Référence Polymarket : proba juste {b['p_fair']:.2%} (cote juste {b['fair_odds']:.2f}), "
            f"fourchette bid/ask {b['p_cons']:.2%} – {b['p_hi']:.2%} ; marge retirée : aucune (milieu d'un carnet "
            f"d'ordres){' ; 1X2 normalisé par la somme des milieux' if b['group'] in ('1x2', 'ht1x2', 'dc') else ''}\n"
            f"- Heure limite : coup d'envoi {when} UTC (vérifie que la cote est toujours ≥ {b['odds']:.2f})\n")
