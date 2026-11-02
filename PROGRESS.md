# PROGRESS
## Fait (session 1, 2026-11-02)
- Moteur : dé-vig (proportionnel, puissance, Shin), EV conservative, Kelly 1/4 plafonné 2 %, CLV, IC95 %, ROI (`autonome/`).
- Source : adaptateur The Odds API (officiel) ; pipeline scan/close/settle/stats/report ; alertes ntfy + Telegram ; page mobile HTML.
- GitHub Actions : `ci.yml` (tests) et `run.yml` (cron 2 scans/jour, 3 clôtures, 1 règlement ; état sur branche `data`).
- 24 tests (cas calculés à la main) : `python -m unittest discover -s tests -t .`
- Docs : FAISABILITE.md, RECHERCHE.md.
## En cours / prochaine étape
1. L'utilisateur crée les secrets (ci-dessous) → premier run réel via Actions > run > Run workflow (mode scan).
2. Vérifier les clés de bookmakers réellement renvoyées par l'API (liste `fr_books` à ajuster selon `/v4/sports/{sport}/odds` réel).
3. Après ~2 semaines : lire `python -m autonome stats` ; conclure sur la CLV.
4. Sous-agent « briseur » indépendant avant livraison finale (non fait).
5. Explorer endpoints directs des books / PulseScore si permission donnée.
## À configurer par l'utilisateur
- `ODDS_API_KEY` (clé gratuite sur the-odds-api.com), `NTFY_TOPIC` (sujet aléatoire long ; app ntfy Android), variable `BANKROLL`. Optionnel : `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Pages : Réglages > Pages > Source « GitHub Actions ».
## Décisions
- Python stdlib seul (0 dépendance, démarrage rapide sur Actions). Raison : gratuité, robustesse.
- État sur branche `data` (pas de bruit sur main). Min des 3 méthodes de dé-vig (prudence).
- ntfy en priorité sur Telegram : aucun compte à créer.
## Skills installés / délégation
- Aucun skill externe installé (aucun nécessaire pour le noyau ; skills perso `calculs-cotes`, `value-bets-pulsescore` lus pour aligner méthode/seuils).
- Aucune délégation sous-agent jusqu'ici (tâches courtes, contexte partagé).
## Limites connues
Plan gratuit 500 crédits/mois ; CLV approximative ; settlement via scores = score final API (prolongations des coupes non gérées) ; aucune donnée réelle testée.
