# Autonome — règles du projet
Outil perso de value betting (bookmakers ANJ uniquement, 0 €, détection seulement, jamais de pari auto).
Le propriétaire refuse toute clé d'API/compte et toute installation sur son téléphone : tout tourne sur GitHub Actions.
- Tests : `python -m unittest discover -s tests -t .` (doit passer avant tout merge dans main).
- **Voie principale** : `python -m autonome live --state state` (workflow `live.yml`, horaire) =
  référence Polymarket (API publique Gamma, milieu bid/ask ; foot et basket tous championnats via tags
  100350/28, + NBA/NHL/tennis/UFC/NCAAB/boxe) vs cotes :
  PMU (flux public Kambi), NetBet (état Nuxt lu sans exécution), Unibet (page publique), Betclic/Unibet/Betsson/
  Olybet/Vbet/DAZN… via l'instantané coteur.com (`coteur_odds.json`, workflow `coteur` = navigateur Playwright).
  Matchs sans Polymarket : référence « consensus ANJ » (leave-one-out, clones fusionnés). Boosts Winamax via coteur.
  Règlement : résolution Polymarket ; paris « consensus » via LiveScore (API publique, `sources/livescore.py`).
  Alertes : issue GitHub « Paris du JJ/MM » (e-mail au propriétaire) ; issue « Tableau de bord » réécrite à chaque run.
- Ordonnancement : le cron GitHub ne s'est pas déclenché sur ce dépôt → workflow `pulse` (relais auto-relancé,
  contrôle toutes les 5 min : live dès 15 min, coteur dès 45 min ; filets dans live/coteur ; arrêt : variable PULSE=off). La branche par défaut est `ccr-0a28d713-rav38k` (= main).
- Diagnostic réseau depuis GitHub : workflows `probe.yml` (tableau des accès) et `capture.yml` (pages publiques
  enregistrées sur la branche `captures`, à analyser localement). Lancement : MCP `actions_run_trigger`.
- Voies secondaires : `python -m autonome fair` (CSV football-data.co.uk) ; backtest `python tools/backtest_fd.py`.
- The Odds API (refusée, désactivée) : `ODDS_API_KEY=... python -m autonome scan|close|settle`.
- Stdlib Python uniquement. Secrets en variables d'env, jamais dans le code/logs/URLs.
- Jamais d'invention de cotes/résultats : donnée absente = signalée absente. Fixtures de test = format seulement.
- État (paris, CLV, observations) sur la branche git `data`, pas sur main.
- Reprendre : lire PROGRESS.md puis docs/FAISABILITE.md et docs/RECHERCHE.md.
- Autres dépôts du propriétaire (cotes-value surtout) : chiffres et idées déjà repris dans docs/RECHERCHE.md « Session 4 ».
## Erreurs à ne plus faire
- Depuis la session cloud : sondes d'endpoints internes de bookmakers et exécution de JS de pages tierces
  (node/vm) refusées par le classifieur → passer par les pages publiques via Actions et un analyseur sans exécution.
- Winamax et Betclic : 403 depuis GitHub (anti-bot). Le propriétaire a autorisé le contournement le 02/11/2026 :
  Betclic lu par son API publique gRPC-web (`sources/betclic.py`, requête ordinaire, sans imitation de navigateur).
  Imiter l'empreinte TLS de Chrome (curl_cffi, Winamax socket) est REFUSÉ par le classifieur de la session cloud :
  ne pas réessayer ; Winamax reste limité aux boosts via coteur.
- ZEbet et Parions Sport redirigent vers unibet.fr (observé le 2026-11-02 depuis GitHub).
- `python -m unittest discover` exige `tests/__init__.py` et `-t .`.
- football-data.co.uk : plus de Pinnacle en 2026/27 ; ne jamais comparer une cote ANJ à une référence périmée (CLV ≈ −5 %).
- Appariement d'équipes : « Paris FC » ≠ « Paris SG », « Man City » ≠ « Man Utd » : garder les tests de match.py.
- Pas de `sleep` en chaîne dans Bash : utiliser une boucle until en arrière-plan.
- Une source qui répond 403/429 est mise en pause 6 h (backoff.jsonl) : ne jamais insister (NetBet a fini par bloquer).
- Winamax : cotes « désactivées » chez coteur depuis le 29/10 → seulement les boosts. Bet365 : non ANJ, exclu.
- Toujours une revue adverse indépendante (sous-agent sans contexte) sur tout nouveau code de cotes : 4 revues ont
  trouvé 57 défauts dont plusieurs faux positifs (joueur+équipe, réserves/féminines, Venus/Serena, foot vs handball).
- Résultats LiveScore : le marqueur féminin n'est parfois que dans NmEn (« Arsenal W ») ou dans le nom de ligue
  (« Naisten… ») ; un match reporté doit rester candidat (sinon son homonyme est pris) ; doubles ≠ simples au tennis.
