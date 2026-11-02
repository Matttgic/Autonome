# Autonome — règles du projet
Outil perso de value betting (bookmakers ANJ uniquement, 0 €, détection seulement, jamais de pari auto).
- Tests : `python -m unittest discover -s tests -t .` (doit passer avant tout merge dans main).
- Exécution : `ODDS_API_KEY=... python -m autonome scan|close|settle|stats|report --state state`.
- Stdlib Python uniquement. Secrets en variables d'env (ODDS_API_KEY, NTFY_TOPIC, TELEGRAM_*), jamais dans le code/logs/URLs.
- Jamais d'invention de cotes/résultats : donnée absente = signalée absente. Fixtures de test = format seulement.
- État (paris, CLV) sur la branche git `data` (dossier state/), pas sur main.
- Reprendre : lire PROGRESS.md puis docs/FAISABILITE.md.
## Erreurs à ne plus faire
- Sandbox : l'IP du cloud est bloquée par Cloudflare (Smarkets 403) ; les sondes d'endpoints non officiels de bookmakers depuis la session ont été refusées par le classifieur d'autorisation → ne pas les relancer sans règle de permission explicite de l'utilisateur.
- `python -m unittest discover` exige `tests/__init__.py` et `-t .`.
