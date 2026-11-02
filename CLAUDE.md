# Autonome — règles du projet
Outil perso de value betting (bookmakers ANJ uniquement, 0 €, détection seulement, jamais de pari auto).
Le propriétaire refuse toute clé d'API/compte et toute installation sur son téléphone : tout tourne sur GitHub Actions.
- Tests : `python -m unittest discover -s tests -t .` (doit passer avant tout merge dans main).
- **Voie principale** : `python -m autonome live --state state` (workflow `live.yml`, horaire) =
  référence Polymarket (API publique Gamma, milieu bid/ask) vs cotes publiques NetBet (état Nuxt lu sans exécution).
  Alertes : issue GitHub « Paris du JJ/MM » (e-mail au propriétaire) ; issue « Tableau de bord » réécrite à chaque run.
- Diagnostic réseau depuis GitHub : workflows `probe.yml` (tableau des accès) et `capture.yml` (pages publiques
  enregistrées sur la branche `captures`, à analyser localement). Lancement : MCP `actions_run_trigger`.
- Voies secondaires : `python -m autonome fair` (CSV football-data.co.uk) ; backtest `python tools/backtest_fd.py`.
- The Odds API (refusée, désactivée) : `ODDS_API_KEY=... python -m autonome scan|close|settle`.
- Stdlib Python uniquement. Secrets en variables d'env, jamais dans le code/logs/URLs.
- Jamais d'invention de cotes/résultats : donnée absente = signalée absente. Fixtures de test = format seulement.
- État (paris, CLV, observations) sur la branche git `data`, pas sur main.
- Reprendre : lire PROGRESS.md puis docs/FAISABILITE.md et docs/RECHERCHE.md.
## Erreurs à ne plus faire
- Depuis la session cloud : sondes d'endpoints internes de bookmakers et exécution de JS de pages tierces
  (node/vm) refusées par le classifieur → passer par les pages publiques via Actions et un analyseur sans exécution.
- Winamax et Betclic : 403 depuis GitHub aussi (protection anti-bot) → ne pas contourner.
- ZEbet et Parions Sport redirigent vers unibet.fr (observé le 2026-11-02 depuis GitHub).
- `python -m unittest discover` exige `tests/__init__.py` et `-t .`.
- football-data.co.uk : plus de Pinnacle en 2026/27 ; ne jamais comparer une cote ANJ à une référence périmée (CLV ≈ −5 %).
- Appariement d'équipes : « Paris FC » ≠ « Paris SG », « Man City » ≠ « Man Utd » : garder les tests de match.py.
- Pas de `sleep` en chaîne dans Bash : utiliser une boucle until en arrière-plan.
