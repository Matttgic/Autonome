# Pistes d'avantage : hypothèse → test → résultat → décision
Aucune piste n'est encore validée sur données réelles : l'historique n'existe pas (pas de clé, pas de données). Aucun chiffre de rentabilité n'est avancé.

| # | Piste | Hypothèse | Test | État | Décision |
|---|---|---|---|---|---|
| 1 | Value vs Pinnacle dé-viguée | Les cotes FR dépassent parfois la cote juste Pinnacle | Mesure : CLV moyenne + IC95 % sur ≥200 paris recommandés (tracker intégré) | Dé-vig/EV/Kelly vérifiés à la main ; suivi CLV corrigé après revue adverse (clôture ≤90 min seulement, couverture affichée) mais non éprouvé ; **0 donnée réelle** | Garder ; verdict statistique après collecte |
| 2 | Dé-vig conservateur (min de 3 méthodes) | Évite de surestimer l'EV sur favoris/outsiders | Tests : Shin/puissance donnent moins à l'outsider que la méthode proportionnelle | Implémentée | Garder à titre prudent (propriété algébrique testée ; taux de faux positifs NON mesuré) |
| 3 | Référence exchange / consensus si Pinnacle absent | Compléter la couverture | Seuils d'EV plus hauts (3 %/5 %), ≥5 books | Implémentée | Garder, à évaluer par CLV séparée par type de référence |
| 4 | Filtre de fraîcheur | Cotes périmées = faux positifs (ou vraies opportunités ?) | Âges max configurables | Implémentée | Mesurer l'impact sur la CLV |
| 5 | Surebets entre books FR | Écarts inter-books > marge | Somme 1/meilleure cote < 1 | Non implémentée | À faire si les données montrent des cas |
| 6 | Cotes boostées / promos | Cote boostée vs cote juste du marché d'origine | Nécessite scraping des promos | Non testée (source non accessible légalement/simplement) | Reportée |
| 7 | Marchés secondaires (totals, buteurs) | Moins efficients | `markets=h2h,totals` coûte 2× les crédits | Totals supportés dans le moteur, désactivés pour budget | Activer si plus de crédits |
| 8 | Backtest | — | Impossible sans historique de cotes de clôture (The Odds API historique = payant) | Non faisable à 0 € | Remplacé par suivi forward (CLV réelle) |
