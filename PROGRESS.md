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
3. Conclure sur la CLV seulement à 200+ paris avec clôture ≤90 min (couverture affichée par `stats`).
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
## Session 1 (suite) — décision « pas d'API »
- L'utilisateur ne veut pas d'API/clé. Sondes cloud : Winamax 403, Betclic injoignable, endpoints internes refusés par le classifieur → pas de contournement.
- Décision : collecte depuis le téléphone (Termux, IP résidentielle). Étape 1 : `tools/probe.py` (résumé à coller dans le chat) ; étape 2 (session suivante) : écrire les parseurs sur données RÉELLES, jamais sur des formats supposés.
- Sous-agent briseur lancé (Sonnet) ; corriger ses défauts avant livraison.
- Revue adverse (17 défauts) : corrigés (t de Student, clôture/CLV, couverture, ref sans horodatage/marge<0.5 %, lignes .25/entières, limite/jour, crash par événement, alerte avant rendu, workflow état/injection/deploy). Régressions : tests/test_regress.py. Non corrigé : IC du ROI pondéré par mises (renommé return_per_bet), correction de tests séquentiels.

## Session 2 (2026-11-02) — voie sans API ni installation
- Fait : football-data.co.uk accessible (fixtures.csv + 15 archives saisonnières HTTP 200). Backtest réel
  `tools/backtest_fd.py` → docs/RECHERCHE.md (calibration PS, log-loss dé-vig, CLV/ROI séparés dans le temps).
- Fait : `autonome/sources/footballdata.py` (adaptateur CSV → format interne), `autonome/fairsheet.py` +
  `python -m autonome fair` (fiche cotes justes / cote mini ANJ), `autonome/backtest.py` (fonctions pures).
- Fait : workflows `fair.yml` (planifié ven./mar., Pages) et `probe.yml` (manuel, résumé dans le run).
  `run.yml` (The Odds API) : planification retirée = désactivé par défaut (code conservé).
- Tests : 44 (13 nouveaux dans tests/test_sources.py, sans réseau).
- Résultats clés : comparaison simultanée PS→Bet365 CLV +2,4 % [1,4 ; 3,4] mais ~95 paris/saison ; référence
  périmée (pari tardif) CLV −5,5 % ; Pinnacle absent des fichiers 2026/27 ; books ANJ absents (marge non mesurée).
## Prochaine étape
1. Propriétaire : Réglages > Pages > Source « GitHub Actions » ; lancer Actions > probe, puis Actions > fair.
2. Lire le résumé de probe : si l'API publique Smarkets répond 200 depuis GitHub → adaptateur Smarkets
   (référence exchange fraîche toutes les heures) ; sinon la fiche CSV reste la seule voie, à faible valeur.
3. Ne pas annoncer de rentabilité : aucune mesure sur des cotes ANJ réelles n'existe.
