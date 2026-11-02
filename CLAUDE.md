# Autonome — règles du projet
Outil perso de value betting (bookmakers ANJ uniquement, 0 €, détection seulement, jamais de pari auto).
- Tests : `python -m unittest discover -s tests -t .` (doit passer avant tout merge dans main).
- Exécution sans clé (voie par défaut) : `python -m autonome fair [--csv fichier|URL] --out site` (football-data.co.uk).
- Backtest : `python tools/backtest_fd.py [--offline]` (cache `.cache/`, jamais versionné).
- The Odds API (refusée par le propriétaire, désactivée par défaut) : `ODDS_API_KEY=... python -m autonome scan|close|settle|stats|report --state state`.
- Stdlib Python uniquement. Secrets en variables d'env (ODDS_API_KEY, NTFY_TOPIC, TELEGRAM_*), jamais dans le code/logs/URLs.
- Jamais d'invention de cotes/résultats : donnée absente = signalée absente. Fixtures de test = format seulement.
- État (paris, CLV) sur la branche git `data` (dossier state/), pas sur main.
- Reprendre : lire PROGRESS.md puis docs/FAISABILITE.md.
## Erreurs à ne plus faire
- Sandbox : l'IP du cloud est bloquée par Cloudflare (Smarkets 403) ; les sondes d'endpoints non officiels de bookmakers depuis la session ont été refusées par le classifieur d'autorisation → ne pas les relancer sans règle de permission explicite de l'utilisateur.
- `python -m unittest discover` exige `tests/__init__.py` et `-t .`.
- football-data.co.uk : `www.` redirige (302) vers `football-data.co.uk` ; plus de Pinnacle en 2026/27 (utiliser BFE, filtrer la marge, illiquide en divisions mineures).
- Backtest : les dé-vig power/shin de devig.py (200 itérations) sont trop lents sur 100k matchs → utiliser `backtest.fair` (cache + 64 itérations, résultat identique à 1e-12).
- Ne jamais comparer une cote ANJ « plus tard » à une référence périmée : CLV mesurée ≈ −5 %.
