# Protocole d'évaluation (Autonome)

Commun aux trois dépôts du propriétaire (cotes-value, cotes-boostees, Autonome), adapté ici. Source : débat du
statisticien, supervision du 09/11/2026. But : savoir honnêtement si une règle gagne, sans se raconter d'histoire.

## P0. Pré-enregistrement
Avant une période d'évaluation, un fichier `docs/prereg/AAAA-MM-JJ.md` commité fixe : la règle de sélection (version
`tracker.VERSION_REGLES` et commit), la métrique principale, N, la règle d'arrêt, la liste des stratégies évaluées.
Chaque pari porte `version_regles` depuis le 09/11/2026 (les paris antérieurs n'en ont pas). Les données d'avant le gel
servent à explorer ; elles ne valident rien.

## P1. Unité = le match
Intervalles de confiance et p-valeurs par match (bootstrap ou erreur-type robuste par match). Autonome ne propose déjà
qu'un pari par match (`cli.cmd_live`, marchés d'un même match corrélés) : pour les vrais paris, IC par pari = IC par
match. Les stratégies fictives (`paper.py`) peuvent en avoir plusieurs : à regrouper par match avant tout IC.

## P2. Métrique principale
- **CLV** = cote prise × probabilité juste de clôture − 1, référence Polymarket (milieu achat/vente).
  Aujourd'hui : clôture = dernier milieu vu avant le coup d'envoi, retenue si ≤ 90 min avant (`tracker.CLOSE_MAX_MIN`).
  Cible du protocole : ≤ 10 min (sensibilité à 30 min) et couverture ≥ 80 % (affichée par `tracker.stats`).
- Paris « consensus ANJ » : CLV indicative seulement (référence = autres books), jamais mélangée à la CLV Polymarket.
- Secondaires : ROI à mise plate, taux de gain contre attendu. Jamais un ROI en vert sans son IC et son n.

## P3. Taille d'échantillon
n = ((z₁₋α + z₁₋β)·σ/δ)², σ mesuré sur les données d'exploration. Ordres de grandeur (débat du 09/11) : CLV, δ = 1 %,
σ ≈ 0,09-0,10 par match, puissance 80 % : ~460-660 matchs pour une stratégie, ~650-900 pour trois. ROI, δ = 3 % : ~8 100
paris (contrôle de non-contradiction seulement). Au rythme d'Autonome (17 paris en 7 jours au 09/11), N est loin :
afficher « n = x / N », ne rien conclure avant (la page dit « il manque environ … paris réglés »).

## P4. Règle d'arrêt
Un seul regard final à N fixé d'avance. Regard intermédiaire seulement pour arrêter une règle nocive (borne haute de l'IC
de CLV < 0 après ≥ 200 matchs). Aucun arrêt pour « succès » avant N.

## P5. Tests multiples
Une stratégie primaire par période (α = 5 % unilatéral) ; au plus 3 additionnelles pré-enregistrées (Holm) ; tout le
reste est exploratoire (BH, q = 10 %), étiqueté « exploratoire », jamais « recommandé ». « Valeur 4 % » et les Témoins de
`paper.py` sont exploratoires tant qu'aucun pré-enregistrement ne les désigne.

## P6. « Recommandée »
Les trois à la fois, hors échantillon : (i) CLV > 0 avec p < α corrigé à N ; (ii) borne basse de l'IC du ROI > −5 points ;
(iii) signe positif sur les deux moitiés de la période. Déclassement automatique dès que (ii) échoue.

## P7. Hygiène des données (déjà appliquée)
Exclus du principal et comptés à part : références suspectes (`tracker.suspect` : EV > 30 %, Polymarket figé à 50/50),
paris « à régler » (ouverts > 48 h après le début, hors ROI), paris fictifs non réglés (`paper.abandon`). La part exclue
est publiée (bilan : « écartés », « à régler »).

## P8. Affichage honnête
Toujours : n, IC 95 % par match, date de gel, étiquette « exploration » / « hors échantillon », CLV et ROI côte à côte.
Vert réservé à « critère P6 rempli » ; sous 30 paris réglés, un ROI est affiché sans couleur (« trop peu »).
