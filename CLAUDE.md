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
  Alertes : page https://matttgic.github.io/Autonome/ (site/index.html lit site.json sur data). Onglet d'entrée
  « Aujourd'hui » (approuvé le 09/11) : paris à jouer et voyants des 3 outils, schéma commun `aujourdhui.json` (bloc
  `aujourdhui` de site.json ici ; cotes-value/aujourdhui.json sur Pages, cotes-boostees sur `donnees`), 8 s max par
  source, source absente = « pas encore publié », jamais bloquant. PAS d'e-mail (demande du
  propriétaire) : issues « Paris du… »/« Panne… » coupées (variable ALERT_ISSUES=1 pour réactiver) ; issue « Tableau de bord » réécrite.
- Ordonnancement : le cron GitHub se déclenche trop peu pour compter dessus (21 départs programmés de live en 7 jours, au
  lieu de 119, mesuré au 09/11) → `live.yml` boucle ~50 min (un passage dès que le précédent finit, état sauvegardé après chacun)
  et met lui-même le live suivant en file en fin de job ; `pulse` (contrôle 2 min) et le filet de `coteur` relancent live
  si aucun ne tourne ou si son dernier départ a plus de 60 min (décision sur l'âge, jamais sur « un pulse est en cours » :
  un pulse mort peut rester affiché « en cours » des heures) ; coteur dès 45 min (filet de live après 90) ; jamais de
  relance si un live attend déjà (GitHub n'en garde qu'un en file par groupe). Arrêt : variable PULSE=off. Intervalles minimaux par source (NetBet 15, Unibet 10, Betclic 6,
  Winamax 30, boosts coteur 30 min ; cache de travail Actions `cache/`). La branche par défaut est `ccr-0a28d713-rav38k`
  (= main ; garder `main` alignée par avance rapide après chaque fusion).
- Diagnostic réseau depuis GitHub : workflows `probe.yml` (tableau des accès) et `capture.yml` (pages publiques
  enregistrées sur la branche `captures`, à analyser localement). Lancement : MCP `actions_run_trigger`.
- Recherche : backtest `python tools/backtest_fd.py` (football-data.co.uk, reproductibilité). Voies The Odds API et fiche « fair » supprimées (clé refusée ; plus de Pinnacle en 2026/27).
- Stdlib Python uniquement. Secrets en variables d'env, jamais dans le code/logs/URLs.
- Jamais d'invention de cotes/résultats : donnée absente = signalée absente. Fixtures de test = format seulement.
- État (paris, CLV, observations) sur la branche git `data`, pas sur main. `store` : lecture tolérante (ligne illisible
  ignorée, copiée dans `quarantaine.jsonl`), écritures atomiques, UTF-8. Rotation en fin de passage (`cli.housekeeping`) :
  observations 30 j, runs 14 j, lag 30 j, fichier chaud ≤ 16 Mo ; le reste dans `archives/<nom>-AAAA-MM.jsonl.gz` (jamais
  supprimé). `ci.yml` refuse un fichier d'état > 20 Mo. Pari ouvert > 48 h après le début = « à régler » (hors ROI,
  compté à part) sauf match signalé reporté. Chaque nouveau pari porte `version_regles` (date) : l'incrémenter
  (`tracker.VERSION_REGLES`) à tout changement de détection ou de collecte.
- Évaluation : docs/PROTOCOLE.md (unité = match, n / N requis, aucune conclusion avant N).
- Reprendre : lire PROGRESS.md puis docs/FAISABILITE.md et docs/RECHERCHE.md.
- Autres dépôts du propriétaire (cotes-value surtout) : chiffres et idées déjà repris dans docs/RECHERCHE.md « Session 4 ».
- Mesures en fictif sans alerte : `paper.py` (« Valeur 4 % », Témoins) ; `lag.py` (retard des books sur Polymarket).
## Erreurs à ne plus faire
- Depuis la session cloud : sondes d'endpoints internes de bookmakers et exécution de JS de pages tierces
  (node/vm) refusées par le classifieur → passer par les pages publiques via Actions et un analyseur sans exécution.
- Winamax et Betclic : 403 depuis GitHub (anti-bot). Le propriétaire a autorisé le contournement le 02/11/2026 :
  Betclic lu par son API publique gRPC-web (`sources/betclic.py`, urllib, en-têtes Origin/Referer betclic.fr, aucune empreinte TLS imitée).
  Imiter l'empreinte TLS de Chrome (curl_cffi, Winamax socket) est REFUSÉ par le classifieur de la session cloud :
  ne pas réessayer. Winamax : page publique tentée par requête ordinaire (`sources/winamax.py`, 403 le plus souvent
  → pause 6 h) ; SportyTrader 403 depuis GitHub, matchendirect sans cotes, OddsPapi = compte (02/11/2026).
- ZEbet et Parions Sport redirigent vers unibet.fr (observé le 2026-11-02 depuis GitHub).
- `python -m unittest discover` exige `tests/__init__.py` et `-t .`.
- football-data.co.uk : plus de Pinnacle en 2026/27 ; ne jamais comparer une cote ANJ à une référence périmée (CLV ≈ −5 %).
- Appariement d'équipes : « Paris FC » ≠ « Paris SG », « Man City » ≠ « Man Utd » : garder les tests de match.py.
- Pas de `sleep` en chaîne dans Bash : utiliser une boucle until en arrière-plan.
- Une source qui répond 403/429 est mise en pause 6 h (backoff.jsonl) : ne jamais insister (NetBet a fini par bloquer).
- Winamax : cotes « désactivées » chez coteur depuis le 29/10 → seulement les boosts. Bet365 : non ANJ, exclu.
- Toujours une revue adverse indépendante (sous-agent sans contexte) sur tout nouveau code de cotes : 4 revues ont
  trouvé 57 défauts dont plusieurs faux positifs (joueur+équipe, réserves/féminines, Venus/Serena, foot vs handball).
- Polymarket tennis : un match non joué (forfait) est réglé 50/50 et le marché reste figé à 0,49/0,50 → ce n'est
  pas une value (`tracker.suspect`, 6 fausses alertes sur 15 avant le 08/11). EV > 30 % = erreur de référence.
- Résultats LiveScore : le marqueur féminin n'est parfois que dans NmEn (« Arsenal W ») ou dans le nom de ligue
  (« Naisten… ») ; un match reporté doit rester candidat (sinon son homonyme est pris) ; doubles ≠ simples au tennis.
- `str.splitlines()` coupe aussi sur U+2028/U+0085 (possibles dans un nom venu d'une page tierce) : JSONL = `split("\n")`.
- Kambi (PMU) 404 sur `betoffer/group/<id>` = sport sans offre avant match, pas une panne (pause 1 h après 3 de suite).
- Cotes > 5 : chez cotes-value, la cote juste Pinnacle y est ≈ 2 fois trop optimiste (ROI −70 % au-delà de 10) ; ne
  jamais conclure sur ces cotes sans le vérifier ici.
- Code repris d'un autre dépôt du propriétaire : en-tête « Copié de <dépôt>/<chemin> @ <commit> le <date> — écarts : … ».
- Ne jamais supprimer de données historiques : archiver (gz).
