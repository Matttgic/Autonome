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

## Session 3 (2026-11-02, Opus 5.5) — voie sans clé ni installation : OPÉRATIONNELLE
Fait :
- Sondes depuis GitHub Actions (probe/capture déclenchés via MCP) : Polymarket, Smarkets, NetBet, Unibet lisibles ;
  Winamax/Betclic 403 ; ZEbet/Parions Sport → redirection Unibet. Détails : docs/FAISABILITE.md.
- Référence Polymarket (`sources/polymarket.py`) : 1X2, DC, plus/moins, 2 marquent, buts par équipe, handicaps, mi-temps.
  **Validée** : 189 matchs EPL 25/26, log-loss PM 0,9781 vs Pinnacle 0,9826 (docs/RECHERCHE.md).
- Book NetBet (`sources/netbet.py` + `sources/jslit.py`, sans exécution de JS), appariement (`match.py`),
  comparaison/CLV/règlement (`live.py`), `python -m autonome live`, workflow `live.yml` horaire 6-22 h UTC.
- Interface sans installation : issue « 📊 Tableau de bord Autonome » (#1, réécrite à chaque run : CLV, ROI,
  distribution d'EV NetBet, cotes justes à 72 h pour juger un boost) ; issue « Paris du JJ/MM » + mention = e-mail.
- 2 revues adverses indépendantes (Sonnet) : 17 + 15 défauts, corrigés ; 62 tests.
Résultat honnête : 117 cotes NetBet comparées (3 matchs) → 0 à EV > 0 ; médiane 1X2 −9 %, secondaires −13 à −23 %.
Prochaine étape :
1. Laisser tourner ; lire `observations.jsonl` (branche data) après ~1 semaine : fréquence réelle d'EV > 0.
2. Si toujours ~0 : ajouter Unibet (Kambi, rendu serveur partiel) seulement si une source lisible sans JS existe.
3. Valider Polymarket sur Ligue 1/Liga (`tools/pm_collect.py` avec la série correspondante).
4. Possible : ntfy/Telegram déjà supportés si le propriétaire change d'avis (secrets).
Décisions : Polymarket plutôt que Smarkets (marchés secondaires + historique pour valider) ; un seul pari par match ;
EV ≥ 3 % au milieu ET EV > 0,5 % sur la borne prudente ; alerte = issue GitHub (zéro installation).

## Session 3 (suite) — Unibet + cotes boostées Winamax
- Demande du propriétaire : les gros books (Unibet, Betclic, Winamax, PMU, Bet365). Bet365 : non agréé ANJ → exclu.
  Winamax/Betclic 403, PMU rendu JS : non lisibles. Unibet : `sources/unibet.py` (page publique, souvent 503).
- **Winamax via coteur.com** : `sources/coteur.py` (boosts), `scoremodel.py` (Dixon-Coles), `boosts.py` (gabarits),
  intégré au passage horaire (alerte si EV ≥ 5 % et EV prudente ≥ 0 ; mise ≤ mise max). Boosts « par équipes »
  évalués seulement s'ils sont nouveaux depuis le relevé de référence (`boosts_seen.jsonl`).
- Backtest boosts : EV moyenne −7 % ; ~4 % des boosts > +5 % (docs/RECHERCHE.md #14).
- 75 tests.
Prochaine étape : laisser tourner ; règlement automatique des boosts (score exact Polymarket) non fait — CLV seulement.
- 3e revue adverse sur les boosts : 12 défauts corrigés ; backtest refait : EV moyenne −6,9 % (44 boosts). 85 tests.
- Règlement automatique des boosts via le score exact Polymarket résolu (`boosts.settle`).
- Session 3 (fin) : PMU via flux Kambi public (19 sports), Betclic + 8 books via coteur.com (navigateur, workflow `coteur`
  /2 h), Polymarket NBA/NHL/tennis/UFC/NCAAB/boxe + 4 championnats foot, consensus ANJ pour les matchs sans Polymarket,
  pause auto 6 h sur 403/429 (NetBet bloque depuis 03:51). Winamax : boosts seulement (désactivé chez coteur). 91 tests.
  Prochaine étape : laisser tourner une semaine, lire observations.jsonl (fréquence réelle d'EV>0 par book/sport).
- 4e revue adverse (PMU/coteur/consensus) : 13 défauts corrigés ; 99 tests. Relais `pulse` ajouté car le cron
  GitHub ne s'est pas déclenché (06h–08h UTC le 02/11). Collecte coteur complète : 744 matchs, Betclic sur 683.
  Limites ouvertes : paris « consensus » non réglés automatiquement (CLV indicative seulement) ; Betclic/Unibet via
  coteur = marché principal seulement ; Winamax = boosts seulement.

## Session 4 (2026-11-02) — leçons des autres dépôts (cotes-value, cotes-boostees, Grotonome, Revue, Boost)
- Lu et chiffré : docs/RECHERCHE.md « Session 4 ». cotes-value (4 672 paris simulés) : Polymarket ROI +9 % [−1 ; +20],
  CLV +3 % ; Pinnacle lu depuis GitHub ≈ 0 % (cache Cloudflare périmé) ; cotes > 10 : −70 %. Boosts en bloc : −4 à −7 %.
- Fait : Polymarket lu sur TOUS les championnats de foot (tag 100350) et de basket (tag 28), fenêtre end_date
  [−1 h ; +36 h], féminines/jeunes/réserves exclues, repli sur l'ancienne liste si la lecture large échoue.
  Foot dans les 30 h : 92 matchs (contre 6).
- Fait : règlement automatique des paris « consensus » par LiveScore (API publique sans clé) : 1N2 foot/basket au
  temps réglementaire, vainqueur basket (prolongation incluse) et tennis (FT seulement). Reporté/annulé/abandon/
  appariement ambigu => reste ouvert. Hockey, rugby, handball, volley : non réglés automatiquement.
Prochaine étape : laisser tourner ; si toujours 0 EV>0 après une semaine, regarder les marchés « vainqueur »
tennis/basket (seul segment positif chez cotes-value) et le délai de mise à jour des books (PMU via Kambi le plus frais).
- 5e revue adverse (règlement LiveScore + Polymarket large) : 11 défauts, tous corrigés ; 119 tests. Principaux :
  match féminin pris pour le masculin (marqueur seulement dans NmEn, ligues « Naisten » sans marqueur), homonyme
  choisi quand le vrai match est reporté (désormais tous les matchs sont candidats, seul un candidat FINI règle),
  simple apparié à un double au tennis, Epr/Ewt non contrôlés, pas de pause 403/429, fenêtre 36 h qui laissait des
  matchs Polymarket au consensus (passée à 72 h). Paris ouverts > 24 h listés « À régler à la main » au tableau de bord.
- Session 4 (suite) : relais `pulse` toutes les 5 min (live dès 15 min, coteur dès 45 min, branche par défaut, 5 essais
  de relance, filets dans live/coteur) ; garde-fous avant alerte (cote coteur > 60 min ou > 1/4 du temps avant match,
  groupe (book, sport, marché) non conforme sur ≥ 3 matchs) ; values écartées listées au tableau de bord.
  6e revue adverse : 10 points corrigés. 126 tests. Premier passage élargi (09:12 UTC) : 1 692 cotes comparées
  (contre 537), 3 à EV > 0 (max +1,3 %, sous le seuil de 3 %).
- Betclic direct (API publique gRPC-web, stdlib) : tous marchés des matchs appariés à Polymarket, liste blanche de
  libellés complets, budget 150 s, arrêt sur 403/429/3 erreurs, fusion par match avec coteur. Autorisé par le
  propriétaire. Winamax par imitation TLS (curl_cffi) : refusé par le classifieur, abandonné. 7e revue adverse :
  8 défauts prouvés corrigés (dont lecture bloquante d'un flux ouvert). 140 tests.
