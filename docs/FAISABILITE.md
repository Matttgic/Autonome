# Faisabilité des données (verdict honnête, 2026-11-02)

## Ce qui a été réellement testé depuis la session cloud
| Source | Résultat mesuré | Verdict |
|---|---|---|
| Polymarket Gamma API (publique) | HTTP 200 | Joignable ; marchés de prédiction, couverture sportive FR/ANJ nulle → pas de comparaison directe, utile seulement comme signal annexe |
| Smarkets API publique | HTTP 403 (page Cloudflare) | Bloquée depuis l'IP cloud ; à retester depuis GitHub Actions |
| The Odds API (officielle) | HTTP 401 « clé manquante » = service joignable | **Voie retenue** : clé gratuite (500 crédits/mois), couverture annoncée par le fournisseur (Pinnacle, exchanges, certains books FR) — **non vérifiée**, aucune clé de bookmaker réellement observée ; refusée par l'utilisateur (pas d'API) |
| Telegram / ntfy | Telegram répond 302 (ne prouve pas l'envoi) ; ntfy non testé | OK pour alertes |

## Non testé (honnêteté)
Les endpoints non officiels des sites de bookmakers (API publiques utilisées par les apps Winamax/Betclic/Unibet-Kambi/PMU/Parions Sport, API invitée de Pinnacle) : la sonde a été **refusée par le contrôle d'autorisation de la session** (« attaque tierce »). Je ne l'ai donc pas relancée ni contournée. Aucune affirmation sur leur disponibilité n'est faite ici. Si tu veux que j'explore cette piste, il faut ajouter une règle de permission Bash pour `curl` vers ces hôtes (Paramètres Claude Code → permissions) ; sinon elle reste fermée. Tu as aussi un skill perso « PulseScore » (flux 30+ books dont Pinnacle) : si tu possèdes une clé, la donner en secret `PULSESCORE_API_KEY` permettrait un 2e adaptateur ; couverture Winamax/Betclic non vérifiée.

## Limite structurelle du plan gratuit (chiffrée)
500 crédits/mois ≈ 16/jour. 1 crédit = 1 sport × 1 marché × 1 région. Avec `h2h`/`eu` : ~16 appels/jour, soit 4-5 ligues couvertes 2×/jour + quelques relevés de clôture. Conséquences :
- Beaucoup de matchs/marchés secondaires ne sont pas couverts ; pas de surveillance continue → on rate les cotes périmées éphémères (quelques minutes).
- Les cotes de clôture (CLV) ne sont relevées qu'aux moments planifiés : CLV approximative (bruitée), pas la vraie clôture.
- Le plan est un point de départ, pas une machine à gagner : l'avantage réel dépend de l'habileté à saisir des cotes avant leur correction, ce qu'un relevé 2-3×/jour ne garantit pas.

## Décision
Moteur indépendant de la source (format interne unique) + adaptateur The Odds API maintenant. Autres adaptateurs ajoutables sans toucher au moteur. Panne de source : le scan échoue proprement, notifie (ntfy/Telegram), n'invente aucune cote.

## Session 2 (2026-11-02) — voie « sans API ni installation »
| Source | Mesure depuis la session cloud | Verdict |
|---|---|---|
| football-data.co.uk `fixtures.csv` | HTTP 200 (après redirection 302 www → sans www), 55 479 octets, 196 matchs, `Last-Modified: Fri, 30 Oct 2026 09:33:33 GMT` | **Accessible**. Matchs à venir des 22 ligues ; 1X2, +/-2,5, handicap ; books UK + Betfair Exchange + moyenne/max ; **pas de Pinnacle en 2026/27, aucun book ANJ** |
| football-data.co.uk archives `mmz4281/{saison}/data.zip` | 15/15 HTTP 200 (2012/13 → 2026/27), ≈ 11 Mo | **Accessible** → backtest réel (docs/RECHERCHE.md) |
| football-data.co.uk `new_league_fixtures.csv`, `new/BRA.csv` | HTTP 200 | Accessible (ligues hors Europe ; non exploité) |
| tennis-data.co.uk | HTTP 403 | Bloqué depuis la session (noté, pas contourné) ; à mesurer via probe GitHub |
Rythme : 1 requête / 4 s, User-Agent `autonome/0.2 (outil perso de recherche…)`.

Ce qui tourne sans rien installer : `.github/workflows/fair.yml` (ven. 10:17/17:17 UTC, mar. 14:17 UTC) télécharge
`fixtures.csv` (1 requête), publie `fair.html` sur GitHub Pages (lisible dans le navigateur du téléphone) ;
`.github/workflows/probe.yml` (manuel) mesure depuis les IP GitHub ce qui est lisible (football-data, tennis-data,
Smarkets, Polymarket, pages publiques des books ANJ) et écrit un tableau dans le résumé du run.
Limite mesurée : la fiche est relevée 1-3 jours avant les matchs ; jouer plus tard contre ce relevé = CLV ≈ −5 %
(RECHERCHE §A.4). Les cotes ANJ restent à comparer à la main.
