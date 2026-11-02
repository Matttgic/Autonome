# Faisabilité des données (verdict honnête, 2026-11-02)

## Ce qui a été réellement testé depuis la session cloud
| Source | Résultat mesuré | Verdict |
|---|---|---|
| Polymarket Gamma API (publique) | HTTP 200 | Joignable ; marchés de prédiction, couverture sportive FR/ANJ nulle → pas de comparaison directe, utile seulement comme signal annexe |
| Smarkets API publique | HTTP 403 (page Cloudflare) | Bloquée depuis l'IP cloud ; à retester depuis GitHub Actions |
| The Odds API (officielle) | HTTP 401 « clé manquante » = service joignable | **Voie retenue** : clé gratuite (500 crédits/mois), région `eu` = Pinnacle + exchanges + books FR (Winamax, Betclic, Unibet FR…), cotes décimales, un seul format |
| Telegram / ntfy | Telegram joignable (302) ; ntfy non testé (sans secret) | OK pour alertes |

## Non testé (honnêteté)
Les endpoints non officiels des sites de bookmakers (API publiques utilisées par les apps Winamax/Betclic/Unibet-Kambi/PMU/Parions Sport, API invitée de Pinnacle) : la sonde a été **refusée par le contrôle d'autorisation de la session** (« attaque tierce »). Je ne l'ai donc pas relancée ni contournée. Aucune affirmation sur leur disponibilité n'est faite ici. Si tu veux que j'explore cette piste, il faut ajouter une règle de permission Bash pour `curl` vers ces hôtes (Paramètres Claude Code → permissions) ; sinon elle reste fermée. Tu as aussi un skill perso « PulseScore » (flux 30+ books dont Pinnacle) : si tu possèdes une clé, la donner en secret `PULSESCORE_API_KEY` permettrait un 2e adaptateur ; couverture Winamax/Betclic non vérifiée.

## Limite structurelle du plan gratuit (chiffrée)
500 crédits/mois ≈ 16/jour. 1 crédit = 1 sport × 1 marché × 1 région. Avec `h2h`/`eu` : ~16 appels/jour, soit 4-5 ligues couvertes 2×/jour + quelques relevés de clôture. Conséquences :
- Beaucoup de matchs/marchés secondaires ne sont pas couverts ; pas de surveillance continue → on rate les cotes périmées éphémères (quelques minutes).
- Les cotes de clôture (CLV) ne sont relevées qu'aux moments planifiés : CLV approximative (bruitée), pas la vraie clôture.
- Le plan est un point de départ, pas une machine à gagner : l'avantage réel dépend de l'habileté à saisir des cotes avant leur correction, ce qu'un relevé 2-3×/jour ne garantit pas.

## Décision
Moteur indépendant de la source (format interne unique) + adaptateur The Odds API maintenant. Autres adaptateurs ajoutables sans toucher au moteur. Panne de source : le scan échoue proprement, notifie (ntfy/Telegram), n'invente aucune cote.
