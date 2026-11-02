# Recherche : hypothèse → test → résultat → décision

## A. Backtest football-data.co.uk (session 2, 2026-11-02) — chiffres réels
Données : archives publiques `https://football-data.co.uk/mmz4281/{saison}/data.zip`, 22 divisions, 2012/13 → 2026/27
(15 requêtes HTTP 200, 1 / 4 s, ≈ 11 Mo, cache local `.cache/` non versionné). Reproduire :
`python tools/backtest_fd.py` (télécharge si absent) ou `--offline`. Cotes « avant » = relevé du vendredi après-midi
(week-end) / mardi (milieu de semaine) ; « clôture » = colonnes `*C*`. Aucun book ANJ dans ces fichiers.

### Synthèse (ce que disent les chiffres)
1. **Pinnacle clôture dé-viguée est bien calibrée** (test 2019/20-2025/26, 48 594 matchs) : écart p annoncée / fréquence
   observée ≤ 1,5 pt dans toutes les tranches (ex. 0,2-0,3 : 0,2588 vs 0,2572 ± 0,0036). Léger biais outsider (<10 % :
   0,0697 vs 0,0618 ± 0,0074).
2. **Méthode de dé-vig : différences négligeables.** Log-loss test PS clôture : power 0,99850 < shin 0,99852 <
   multiplicative 0,99877. Power retenue (meilleure sur train 2012-2019). Le moteur garde le min des 3 (prudence).
3. **Comparaison simultanée = avantage mesurable mais rare.** Réf PS « avant » → Bet365 au même relevé, seuil 3 % choisi
   sur 2019-2022 : test 2022/23-2025/26 = **378 paris sur 26 151 matchs (~95/saison, 22 ligues), CLV-EV +2,37 %
   [IC95 +1,38 ; +3,35]**, ROI réel −2,8 % [−19,9 ; +14,3] (non significatif : trop peu de paris).
4. **Référence périmée = perdant.** Même réf PS « avant », mais pari pris à la cote Bet365 de clôture (on joue plus tard
   que le relevé) : test **CLV-EV −5,46 % [−5,68 ; −5,23], ROI −7,0 % [−13,1 ; −0,9]** sur 2 639 paris, quel que soit le
   seuil (sélection adverse : la cote « trop haute » l'est parce que le marché a bougé). C'est LA limite d'une fiche
   de cotes justes non rafraîchie.
5. **Saison 2026/27 : Pinnacle a disparu des fichiers** (0 cote PS sur 2 027 matchs ; 2 931/7 647 en 2025/26). Reste
   Betfair Exchange (BFE) : à la clôture excellent (log-loss 1,00051 vs PS 0,99914, marge 0,9 %), mais « avant » souvent
   illiquide (marge médiane 2 %, p95 17-52 %, en 2025/26 : 58-93 % des matchs à marge > 5 % en National League et Écosse D2-D4). Sur les
   marchés liquides (marge BFE ≤ 1,5 %, n = 4 573) BFE « avant » ≈ PS « avant » (log-loss 0,98104 vs 0,98097),
   mais la stratégie BFE → Bet365 n'y produit presque aucun pari (33 en test) et une CLV nulle (+0,09 %).
6. **+/-2,5 buts** (PS → Bet365, même relevé) : CLV-EV +4,6 % à seuil 2 % mais seulement 159 paris en 7 saisons.
7. **Marché moyen** : la cote moyenne dépasse rarement la cote juste PS (78 cas en 4 saisons) → un book « moyen » n'offre
   presque jamais de value ; seuls les écarts ponctuels d'un book précis comptent.

### Books ANJ : non mesuré (franchise)
Aucun des fichiers ne contient Winamax, Betclic, Unibet FR, PMU, ParionsSport, etc. Leur marge par match **n'est pas
mesurée**. Fait réglementaire vérifié : plafond légal du TRJ moyen des paris sportifs en ligne = 85 % (loi 2010-476
art. 13-II, décret 2020-1349 art. 27 ; l'ANJ a sanctionné 9 opérateurs pour dépassement en 2022). C'est une moyenne sur
toute l'activité (combinés compris), pas une marge 1N2 ; elle indique seulement que les books ANJ ne peuvent pas être
structurellement plus généreux que la concurrence. Meilleure approximation honnête : Bet365 (marge moyenne 6,9 %) et
la moyenne du marché (6,5-6,7 %) ; un book ANJ à marge plus élevée offrira encore moins souvent une cote ≥ cote juste.

### Décision
- Construit : adaptateur `autonome/sources/footballdata.py` + `python -m autonome fair` → page `fair.html`
  (cote juste + « cote mini ANJ » = juste × 1,03) publiée par `.github/workflows/fair.yml` (ven./mar.).
  Valeur réelle limitée par le point 4 : utile seulement si l'utilisateur compare **peu après** le relevé, et rare.
- Le vrai levier reste une référence sharp **fraîche** (relevée en même temps que la cote ANJ). Candidat sans clé :
  API publique Smarkets (403 depuis la session ; à mesurer via `.github/workflows/probe.yml`).

## B. Tableaux complets générés par `tools/backtest_fd.py`
### 1. Couverture (matchs avec cotes non vides)

| Saison | matchs | PS avant | PS clôture | BFE avant | BFE clôture | B365 clôture |
|---|---|---|---|---|---|---|
| 12/13 | 7744 | 7577 | 7341 | 0 | 0 | 0 |
| 13/14 | 7810 | 7608 | 7423 | 0 | 0 | 0 |
| 14/15 | 7876 | 7745 | 7453 | 0 | 0 | 0 |
| 15/16 | 7810 | 7660 | 7434 | 0 | 0 | 0 |
| 16/17 | 7810 | 7680 | 7785 | 0 | 0 | 0 |
| 17/18 | 7810 | 7650 | 7775 | 0 | 0 | 0 |
| 18/19 | 7690 | 7548 | 7666 | 0 | 0 | 0 |
| 19/20 | 6904 | 6836 | 6893 | 0 | 0 | 6897 |
| 20/21 | 7648 | 7590 | 7635 | 0 | 0 | 7622 |
| 21/22 | 7822 | 7813 | 7821 | 0 | 0 | 7822 |
| 22/23 | 7830 | 7789 | 7800 | 0 | 0 | 7800 |
| 23/24 | 7800 | 7779 | 7800 | 0 | 0 | 7800 |
| 24/25 | 7681 | 7670 | 7681 | 7632 | 7680 | 7681 |
| 25/26 | 7647 | 2931 | 2964 | 7132 | 7206 | 7647 |
| 26/27 | 2027 | 0 | 0 | 2000 | 2025 | 2027 |

### 2. Méthodes de dé-vig (Pinnacle), séparation temporelle

Choix sur 2012/13-2018/19, vérification sur 2019/20-2025/26 (log-loss : plus bas = mieux).

| Source | Méthode | log-loss train (n) | log-loss test (n) | Brier test |
|---|---|---|---|---|
| PSC | multiplicative | 1.00151 (52876) | 0.99877 (48594) | 0.59692 |
| PSC | power | 1.00133 (52876) | 0.99850 (48594) | 0.59678 |
| PSC | shin | 1.00137 (52876) | 0.99852 (48594) | 0.59680 |
| PS | multiplicative | 1.00609 (53467) | 1.00229 (48408) | 0.59928 |
| PS | power | 1.00593 (53467) | 1.00195 (48408) | 0.59911 |
| PS | shin | 1.00597 (53467) | 1.00201 (48408) | 0.59914 |

Méthode retenue (meilleure sur train, PS clôture) : **power**.

### 3. Qualité comparée des références (échantillon commun 2024/25-2025/26, méthode power)

Échantillon commun : n = 10513 matchs.

| Source | log-loss | Brier | marge moyenne |
|---|---|---|---|
| PSC | 0.99914 | 0.59733 | +3.91 % |
| PS | 1.00162 | 0.59916 | +5.02 % |
| BFEC | 1.00051 | 0.59754 | +0.91 % |
| BFE | 1.04881 | 0.61597 | +8.13 % |
| B365C | 0.99997 | 0.59773 | +6.93 % |
| B365 | 1.00249 | 0.59950 | +6.89 % |
| AvgC | 0.99876 | 0.59707 | +6.47 % |
| Avg | 1.00188 | 0.59931 | +6.74 % |

Dérive moyenne |p_clôture − p_avant| (toutes issues) : PS +1.92 %, BFE +3.26 %, BFE avant vs PS clôture +3.24 %.

### 4. Calibration de Pinnacle clôture dé-viguée (test 2019/20-2025/26)

| tranche p | n issues | p moyenne | fréquence observée ± 1,96·se |
|---|---|---|---|
| 0.0-0.1 | 4059 | 0.0697 | 0.0618 ± 0.0074 |
| 0.1-0.2 | 16843 | 0.1589 | 0.1610 ± 0.0056 |
| 0.2-0.3 | 55131 | 0.2588 | 0.2572 ± 0.0036 |
| 0.3-0.4 | 31445 | 0.3396 | 0.3399 ± 0.0052 |
| 0.4-0.5 | 17817 | 0.4459 | 0.4481 ± 0.0073 |
| 0.5-0.6 | 10683 | 0.5454 | 0.5397 ± 0.0095 |
| 0.6-0.7 | 5427 | 0.6445 | 0.6562 ± 0.0126 |
| 0.7-0.8 | 2867 | 0.7435 | 0.7586 ± 0.0157 |
| 0.8-0.9 | 1340 | 0.8415 | 0.8366 ± 0.0198 |
| 0.9-1.0 | 170 | 0.9221 | 0.9118 ± 0.0426 |

### 5. Value « avant clôture » chez des books grand public, mesurée contre la clôture Pinnacle

Mise plate 1 u, 1 pari max par match (meilleure EV), cotes 1,40-6,00, EV = pire des 3 dé-vig (comme le moteur). Seuil choisi sur 2019/20-2021/22 (meilleure CLV-EV avec n ≥ 300), résultat sur 2022/23-2025/26. CLV-EV = cote prise × p juste de clôture PS − 1 (proxy de l'EV réelle) ; ROI = résultat réel.


**1X2 réf PS avant → Bet365 avant**

| seuil | période | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |
|---|---|---|---|---|---|---|
| 0% | train | 2628 / 22182 | +2.17 % | +0.61 % [+0.24 ; +0.98] | -0.87 % [-7.09 ; +5.35] | 3.60 |
| 0% | **test** | 1808 / 26151 | +1.95 % | +0.90 % [+0.50 ; +1.29] | +6.60 % [-1.07 ; +14.27] | 3.61 |
| 2% | train | 1060 / 22182 | +4.15 % | +1.65 % [+1.01 ; +2.29] | +0.22 % [-9.81 ; +10.26] | 3.76 |
| 2% | **test** | 632 / 26151 | +3.99 % | +1.60 % [+0.87 ; +2.33] | -1.35 % [-14.41 ; +11.71] | 3.77 |
| 3% ← retenu | train | 669 / 22182 | +5.13 % | +2.11 % [+1.26 ; +2.97] | +5.63 % [-7.24 ; +18.50] | 3.81 |
| 3% ← retenu | **test** | 378 / 26151 | +5.03 % | +2.37 % [+1.38 ; +3.35] | -2.79 % [-19.91 ; +14.33] | 3.82 |
| 5% | train | 240 / 22182 | +7.49 % | +2.79 % [+1.01 ; +4.56] | +10.43 % [-11.96 ; +32.82] | 3.97 |
| 5% | **test** | 127 / 26151 | +7.40 % | +3.81 % [+1.83 ; +5.78] | -13.57 % [-42.34 ; +15.19] | 3.85 |
| 8% | train | 62 / 22182 | +11.61 % | +3.74 % [+0.36 ; +7.11] | -15.68 % [-57.10 ; +25.74] | 4.24 |
| 8% | **test** | 33 / 26151 | +11.29 % | +1.83 % [-3.17 ; +6.82] | -51.06 % [-93.09 ; -9.03] | 3.58 |

**1X2 réf PS avant → cote moyenne du marché**

| seuil | période | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |
|---|---|---|---|---|---|---|
| 0% | train | 35 / 22230 | +1.14 % | -2.71 % [-5.97 ; +0.54] | -9.63 % [-59.92 ; +40.66] | 3.15 |
| 0% | **test** | 77 / 26165 | +2.57 % | -2.26 % [-4.15 ; -0.37] | -4.58 % [-38.22 ; +29.05] | 3.10 |
| 2% | train | 3 / 22230 | +7.07 % | -3.47 % [-58.90 ; +51.96] | -100.00 % [-100.00 ; -100.00] | 3.34 |
| 2% | **test** | 23 / 26165 | +7.13 % | +2.00 % [-3.07 ; +7.07] | -4.74 % [-74.25 ; +64.77] | 2.98 |
| 3% | train | 2 / 22230 | +9.57 % | +3.44 % [-236.14 ; +243.01] | -100.00 % [-100.00 ; -100.00] | 3.58 |
| 3% | **test** | 16 / 26165 | +9.17 % | +2.77 % [-3.46 ; +9.00] | +23.00 % [-71.92 ; +117.92] | 2.93 |
| 5% | train | 1 / 22230 | +15.61 % | +22.29 % n/a | -100.00 % n/a | 5.00 |
| 5% | **test** | 11 / 26165 | +11.51 % | +2.41 % [-6.75 ; +11.57] | +78.91 % [-49.82 ; +207.64] | 2.94 |
| 8% | train | 1 / 22230 | +15.61 % | +22.29 % n/a | -100.00 % n/a | 5.00 |
| 8% | **test** | 6 / 26165 | +15.72 % | +4.12 % [-14.37 ; +22.60] | +153.17 % [-70.24 ; +376.57] | 3.35 |

**1X2 réf PS avant → meilleure cote du marché (borne haute, irréaliste)**

| seuil | période | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |
|---|---|---|---|---|---|---|
| 0% | train | 12266 / 22230 | +2.08 % | +1.60 % [+1.44 ; +1.75] | +0.39 % [-2.25 ; +3.03] | 3.19 |
| 0% | **test** | 8701 / 26165 | +1.99 % | +1.70 % [+1.54 ; +1.87] | +2.93 % [-0.33 ; +6.19] | 3.34 |
| 2% | train | 4865 / 22230 | +3.89 % | +2.75 % [+2.49 ; +3.00] | +1.27 % [-3.15 ; +5.68] | 3.43 |
| 2% | **test** | 3117 / 26165 | +4.02 % | +2.95 % [+2.64 ; +3.26] | +1.88 % [-3.76 ; +7.52] | 3.55 |
| 3% | train | 2905 / 22230 | +4.86 % | +3.21 % [+2.88 ; +3.55] | +1.12 % [-4.71 ; +6.95] | 3.53 |
| 3% | **test** | 1791 / 26165 | +5.18 % | +3.74 % [+3.30 ; +4.18] | +4.09 % [-3.53 ; +11.72] | 3.61 |
| 5% ← retenu | train | 977 / 22230 | +6.90 % | +3.93 % [+3.27 ; +4.60] | +5.79 % [-4.68 ; +16.27] | 3.62 |
| 5% ← retenu | **test** | 610 / 26165 | +7.80 % | +5.24 % [+4.27 ; +6.21] | +2.28 % [-10.90 ; +15.46] | 3.70 |
| 8% | train | 201 / 22230 | +10.15 % | +5.25 % [+3.38 ; +7.12] | +23.61 % [-1.63 ; +48.85] | 3.83 |
| 8% | **test** | 159 / 26165 | +12.69 % | +8.61 % [+5.81 ; +11.41] | +4.16 % [-21.92 ; +30.24] | 3.73 |

**1X2 réf PS avant → Bet365 à la clôture (pari tardif, référence périmée)**

| seuil | période | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |
|---|---|---|---|---|---|---|
| 0% | train | 9971 / 22205 | +6.62 % | -4.96 % [-5.05 ; -4.87] | -7.11 % [-10.12 ; -4.10] | 3.40 |
| 0% | **test** | 10626 / 26164 | +5.81 % | -5.24 % [-5.33 ; -5.15] | -6.25 % [-9.05 ; -3.45] | 3.24 |
| 2% | train | 7222 / 22205 | +8.78 % | -4.95 % [-5.06 ; -4.85] | -7.24 % [-10.87 ; -3.62] | 3.50 |
| 2% | **test** | 7491 / 26164 | +7.86 % | -5.39 % [-5.50 ; -5.28] | -8.15 % [-11.53 ; -4.77] | 3.34 |
| 3% | train | 6124 / 22205 | +9.91 % | -4.96 % [-5.08 ; -4.84] | -7.09 % [-11.08 ; -3.10] | 3.55 |
| 3% | **test** | 6311 / 26164 | +8.87 % | -5.41 % [-5.53 ; -5.29] | -8.20 % [-11.91 ; -4.48] | 3.38 |
| 5% | train | 4492 / 22205 | +12.08 % | -4.92 % [-5.06 ; -4.78] | -6.18 % [-10.97 ; -1.39] | 3.66 |
| 5% | **test** | 4413 / 26164 | +10.99 % | -5.47 % [-5.62 ; -5.31] | -8.25 % [-12.80 ; -3.70] | 3.49 |
| 8% ← retenu | train | 2858 / 22205 | +15.34 % | -4.73 % [-4.92 ; -4.54] | -4.38 % [-10.58 ; +1.82] | 3.80 |
| 8% ← retenu | **test** | 2639 / 26164 | +14.09 % | -5.46 % [-5.68 ; -5.23] | -6.96 % [-13.06 ; -0.86] | 3.64 |

**1X2 réf PS clôture → Bet365 clôture (comparaison simultanée à la clôture)**

| seuil | période | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |
|---|---|---|---|---|---|---|
| 0% | train | 2905 / 22323 | +2.12 % | +2.38 % [+2.30 ; +2.46] | +2.68 % [-3.38 ; +8.74] | 3.65 |
| 0% | **test** | 2068 / 26244 | +2.44 % | +2.73 % [+2.58 ; +2.89] | +0.27 % [-6.43 ; +6.97] | 3.43 |
| 2% | train | 1149 / 22323 | +4.09 % | +4.38 % [+4.25 ; +4.50] | +5.28 % [-4.79 ; +15.36] | 3.83 |
| 2% | **test** | 800 / 26244 | +5.03 % | +5.37 % [+5.05 ; +5.69] | -0.61 % [-11.40 ; +10.19] | 3.48 |
| 3% ← retenu | train | 710 / 22323 | +5.07 % | +5.37 % [+5.21 ; +5.54] | +3.12 % [-9.84 ; +16.07] | 3.93 |
| 3% ← retenu | **test** | 511 / 26244 | +6.48 % | +6.84 % [+6.38 ; +7.29] | -1.01 % [-14.58 ; +12.57] | 3.53 |
| 5% | train | 266 / 22323 | +7.13 % | +7.47 % [+7.19 ; +7.74] | +15.95 % [-6.28 ; +38.19] | 4.07 |
| 5% | **test** | 244 / 26244 | +9.41 % | +9.83 % [+9.04 ; +10.61] | -5.52 % [-24.71 ; +13.66] | 3.62 |
| 8% | train | 63 / 22323 | +10.33 % | +10.74 % [+10.17 ; +11.32] | -0.89 % [-46.30 ; +44.53] | 4.30 |
| 8% | **test** | 99 / 26244 | +14.16 % | +14.66 % [+13.18 ; +16.15] | -14.30 % [-43.84 ; +15.24] | 3.74 |

### 6. Configuration « live » réelle 2026/27 : référence Betfair Exchange (Pinnacle absent)

Réf = BFE avant (relevé ven./mar.), jugé contre PS clôture. Les cotes BFE « avant » sont souvent illiquides (marge médiane 2 %, p95 17-52 % selon la saison) : filtre sur la marge de la référence. Filtre et seuil choisis sur 2024/25, vérifiés sur 2025/26 (seul recouvrement BFE + PS).


**pari Bet365 au moment du relevé**

| marge réf max | seuil | période | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |
|---|---|---|---|---|---|---|---|
| 1.5% | 0% | train | 106 / 7629 | +1.44 % | +1.74 % [+0.50 ; +2.98] | +46.17 % [+11.46 ; +80.88] | 3.58 |
| 1.5% | 0% | **test** | 33 / 2918 | +1.09 % | +0.09 % [-1.41 ; +1.60] | -5.15 % [-67.06 ; +56.76] | 3.65 |
| 1.5% | 2% | train | 28 / 7629 | +2.99 % | +0.88 % [-2.31 ; +4.06] | +14.57 % [-52.60 ; +81.74] | 3.56 |
| 1.5% | 2% | **test** | 4 / 2918 | +3.56 % | -1.31 % [-1.58 ; -1.05] | -100.00 % [-100.00 ; -100.00] | 3.51 |
| 1.5% | 3% | train | 9 / 7629 | +4.22 % | +0.10 % [-7.38 ; +7.57] | -13.33 % [-145.81 ; +119.14] | 3.93 |
| 1.5% | 3% | **test** | 2 / 2918 | +4.52 % | -1.20 % [-1.40 ; -0.99] | -100.00 % [-100.00 ; -100.00] | 3.65 |
| 1.5% | 5% | train | 1 / 7629 | +6.12 % | -18.47 % n/a | -100.00 % n/a | 5.00 |
| 1.5% | 5% | **test** | 0 / 2918 | — | — | — | — |
| 3.0% | 0% | train | 186 / 7629 | +1.63 % | +0.51 % [-0.63 ; +1.64] | +30.41 % [+4.74 ; +56.08] | 3.58 |
| 3.0% | 0% | **test** | 55 / 2918 | +1.26 % | -0.51 % [-1.77 ; +0.76] | -10.73 % [-55.63 ; +34.17] | 3.60 |
| 3.0% | 2% | train | 52 / 7629 | +3.55 % | -0.47 % [-3.33 ; +2.39] | -5.42 % [-50.06 ; +39.21] | 3.64 |
| 3.0% | 2% | **test** | 12 / 2918 | +3.32 % | +0.10 % [-2.69 ; +2.89] | -40.83 % [-129.80 ; +48.13] | 3.54 |
| 3.0% | 3% | train | 20 / 7629 | +5.38 % | -3.78 % [-10.26 ; +2.71] | -61.00 % [-118.19 ; -3.81] | 3.87 |
| 3.0% | 3% | **test** | 5 / 2918 | +4.56 % | +2.48 % [-2.67 ; +7.63] | -28.00 % [-228.16 ; +172.16] | 3.54 |
| 3.0% | 5% | train | 7 / 7629 | +8.27 % | -14.69 % [-30.48 ; +1.10] | -100.00 % [-100.00 ; -100.00] | 4.05 |
| 3.0% | 5% | **test** | 1 / 2918 | +6.79 % | +3.24 % n/a | +260.00 % n/a | 3.60 |
| 8.0% | 0% | train | 377 / 7629 | +1.89 % | +0.05 % [-0.79 ; +0.89] | +14.98 % [-2.11 ; +32.08] | 3.51 |
| 8.0% | 0% | **test** | 94 / 2918 | +1.49 % | -1.39 % [-2.55 ; -0.23] | -7.93 % [-41.05 ; +25.20] | 3.52 |
| 8.0% | 2% | train | 131 / 7629 | +3.78 % | +0.35 % [-1.28 ; +1.99] | -21.66 % [-46.84 ; +3.53] | 3.56 |
| 8.0% | 2% | **test** | 28 / 2918 | +3.34 % | -1.44 % [-3.81 ; +0.93] | +11.96 % [-53.07 ; +77.00] | 3.50 |
| 8.0% | 3% | train | 66 / 7629 | +5.13 % | +0.54 % [-2.13 ; +3.20] | -35.68 % [-69.60 ; -1.76] | 3.68 |
| 8.0% | 3% | **test** | 11 / 2918 | +4.84 % | -3.18 % [-8.76 ; +2.40] | -8.18 % [-115.88 ; +99.52] | 3.44 |
| 8.0% | 5% | train | 21 / 7629 | +7.64 % | -3.63 % [-10.46 ; +3.20] | -49.05 % [-107.40 ; +9.30] | 3.79 |
| 8.0% | 5% | **test** | 4 / 2918 | +6.58 % | -6.83 % [-25.70 ; +12.03] | +55.00 % [-236.89 ; +346.89] | 3.23 |

**pari Bet365 à la clôture (joué plus tard)**

| marge réf max | seuil | période | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |
|---|---|---|---|---|---|---|---|
| 1.5% | 0% | train | 1284 / 7632 | +5.22 % | -5.56 % [-5.74 ; -5.38] | -0.65 % [-8.86 ; +7.56] | 3.14 |
| 1.5% | 0% | **test** | 529 / 2919 | +5.07 % | -2.20 % [-2.71 ; -1.69] | +4.79 % [-7.81 ; +17.38] | 3.04 |
| 1.5% | 2% | train | 865 / 7632 | +7.32 % | -5.78 % [-6.00 ; -5.56] | +3.18 % [-7.12 ; +13.48] | 3.23 |
| 1.5% | 2% | **test** | 358 / 2919 | +7.08 % | -1.50 % [-2.20 ; -0.80] | +6.37 % [-9.32 ; +22.06] | 3.13 |
| 1.5% | 3% | train | 706 / 7632 | +8.41 % | -5.82 % [-6.06 ; -5.58] | +5.13 % [-6.47 ; +16.73] | 3.27 |
| 1.5% | 3% | **test** | 305 / 2919 | +7.88 % | -1.27 % [-2.06 ; -0.47] | +6.72 % [-10.35 ; +23.79] | 3.16 |
| 1.5% | 5% | train | 481 / 7632 | +10.50 % | -5.89 % [-6.19 ; -5.59] | +2.30 % [-11.83 ; +16.43] | 3.32 |
| 1.5% | 5% | **test** | 199 / 2919 | +9.94 % | -0.83 % [-1.93 ; +0.28] | +5.26 % [-16.36 ; +26.87] | 3.26 |
| 3.0% | 0% | train | 1926 / 7632 | +5.50 % | -5.74 % [-5.89 ; -5.59] | -0.98 % [-7.63 ; +5.66] | 3.15 |
| 3.0% | 0% | **test** | 790 / 2919 | +5.46 % | -2.02 % [-2.47 ; -1.58] | +3.08 % [-7.28 ; +13.44] | 3.07 |
| 3.0% | 2% | train | 1304 / 7632 | +7.70 % | -5.96 % [-6.14 ; -5.78] | +0.27 % [-7.99 ; +8.54] | 3.24 |
| 3.0% | 2% | **test** | 552 / 2919 | +7.43 % | -1.38 % [-1.97 ; -0.79] | +1.56 % [-11.04 ; +14.15] | 3.15 |
| 3.0% | 3% | train | 1065 / 7632 | +8.87 % | -6.05 % [-6.26 ; -5.85] | +0.64 % [-8.61 ; +9.90] | 3.28 |
| 3.0% | 3% | **test** | 460 / 2919 | +8.42 % | -1.05 % [-1.73 ; -0.37] | +1.01 % [-12.86 ; +14.87] | 3.19 |
| 3.0% | 5% | train | 755 / 7632 | +10.90 % | -6.18 % [-6.43 ; -5.92] | -2.11 % [-13.18 ; +8.96] | 3.34 |
| 3.0% | 5% | **test** | 305 / 2919 | +10.65 % | -0.41 % [-1.35 ; +0.53] | -0.13 % [-17.63 ; +17.36] | 3.31 |
| 8.0% | 0% | train | 2711 / 7632 | +5.68 % | -5.95 % [-6.10 ; -5.81] | -3.95 % [-9.52 ; +1.62] | 3.18 |
| 8.0% | 0% | **test** | 1019 / 2919 | +5.57 % | -2.00 % [-2.41 ; -1.60] | -1.19 % [-10.31 ; +7.93] | 3.13 |
| 8.0% | 2% | train | 1871 / 7632 | +7.82 % | -6.20 % [-6.38 ; -6.03] | -3.72 % [-10.57 ; +3.12] | 3.27 |
| 8.0% | 2% | **test** | 712 / 2919 | +7.58 % | -1.25 % [-1.79 ; -0.71] | -2.01 % [-13.12 ; +9.10] | 3.20 |
| 8.0% | 3% | train | 1547 / 7632 | +8.93 % | -6.33 % [-6.52 ; -6.14] | -4.02 % [-11.62 ; +3.57] | 3.31 |
| 8.0% | 3% | **test** | 598 / 2919 | +8.55 % | -0.87 % [-1.48 ; -0.25] | -3.05 % [-15.19 ; +9.09] | 3.23 |
| 8.0% | 5% | train | 1095 / 7632 | +10.98 % | -6.54 % [-6.77 ; -6.31] | -7.86 % [-16.90 ; +1.18] | 3.39 |
| 8.0% | 5% | **test** | 408 / 2919 | +10.67 % | -0.21 % [-1.04 ; +0.62] | -2.51 % [-17.60 ; +12.57] | 3.33 |

Sous-échantillon liquide (marge BFE avant ≤ 1,5 %, n = 4573) : log-loss PS avant 0.98097, BFE avant 0.98104, PS clôture 0.97953.


### 7. +/-2,5 buts : réf PS avant → Bet365 avant, jugé contre PS clôture (2019/20-2025/26)

| seuil | paris / matchs | EV attendue | CLV-EV [IC95] | ROI réel [IC95] | cote moy. |
|---|---|---|---|---|---|
| 0% | 618 / 48228 | +1.89 % | +1.69 % [+1.12 ; +2.27] | -4.52 % [-12.87 ; +3.83] | 2.10 |
| 2% | 159 / 48228 | +5.26 % | +4.60 % [+3.34 ; +5.86] | +14.16 % [-4.40 ; +32.73] | 2.43 |
| 3% | 92 / 48228 | +7.28 % | +6.46 % [+4.69 ; +8.22] | +9.68 % [-17.05 ; +36.42] | 2.71 |
| 5% | 40 / 48228 | +11.94 % | +12.52 % [+9.92 ; +15.12] | -13.55 % [-61.79 ; +34.69] | 3.43 |
| 8% | 27 / 48228 | +14.67 % | +15.83 % [+13.12 ; +18.54] | -1.37 % [-65.03 ; +62.29] | 3.63 |

## C. Pistes (état)
| # | Piste | Test | État | Décision |
|---|---|---|---|---|
| 1 | Value vs Pinnacle dé-viguée (simultané) | §B.5 | CLV +2,4 % [1,4 ; 3,4], ~95 paris/saison sur 22 ligues | Valide si cotes simultanées ; FR non mesuré |
| 2 | Dé-vig conservateur (min de 3) | §B.2 | méthodes quasi équivalentes (Δ log-loss < 0,0003) | Garder (coût faible) |
| 3 | Référence exchange (BFE) | §B.3, §B.6 | clôture fiable ; « avant » illiquide | Filtre marge ≤ 1,5 % dans la fiche |
| 4 | Fiche de cotes justes périmée | §B.5 (pari tardif) | CLV −5,5 % | Avertissement explicite sur la page |
| 5 | Surebets entre books FR | — | non faisable sans cotes FR | Reportée |
| 6 | Cotes boostées | — | source non accessible | Reportée |
| 7 | +/-2,5 buts | §B.7 | CLV +4,6 %, 159 paris / 7 saisons | Inclus dans la fiche |
| 8 | The Odds API | — | refusée par le propriétaire | Code gardé, workflow `run` désactivé |
| 9 | tennis-data.co.uk | HTTP 403 depuis la session | bloqué | À mesurer via probe |
| 10 | Smarkets API publique | 403 (Cloudflare) depuis la session | inconnu depuis GitHub | probe.yml |

## Session 3 — mesures réelles NetBet (ANJ) contre Polymarket (2026-11-02)
Méthode : proba juste = milieu bid/ask Polymarket (1X2 normalisé par la somme des milieux) ; EV = p × cote NetBet − 1 ;
EV prudente = borne défavorable (bid pour « oui », 1 − ask pour « non »).

| # | Piste | Hypothèse | Test | Résultat chiffré | Décision |
|---|---|---|---|---|---|
| 9 | Value NetBet vs Polymarket (pré-match) | NetBet affiche parfois une cote > cote juste | 117 cotes comparables, 3 matchs (run live 02:18 UTC) | **0/117 à EV > 0**. Médiane EV : 1X2 −9,0 % ; handicaps −16 % ; 2 marquent −12,7 % ; double chance −17,9 % ; plus/moins −18,0 % ; mi-temps −19 à −20 % ; buts par équipe −23,4 %. Meilleure : −6,5 % | Garder la surveillance horaire (erreurs ponctuelles, cotes non mises à jour après une nouvelle) ; échantillon encore minuscule |
| 10 | Combi Boost NetBet | Le bonus des combinés compense la marge | Paliers lus dans la page : +4 % (4 sél.) … +25 % (10) … +75 % (20) ; seuil de rentabilité par sélection = (1+bonus)^(1/n) − 1 | Il faut au mieux EV ≥ −2,8 %/sélection (20 sél.) ; −2,2 % (10 sél.) ; les sélections réelles sont à −7 % ou pire | **Abandonnée** |
| 11 | Marchés secondaires mieux pricés | Moins surveillés donc plus d'erreurs | Même mesure | Au contraire : marge 2× plus forte que le 1X2 | Seuil inchangé ; rien de systématique |

Conclusion honnête à ce stade : la marge française (fiscalité sur les mises, plafond de retour joueur à 85 %) rend la
value systématique quasi inexistante sur NetBet. Les seules sources plausibles : (a) cotes figées après un mouvement de
marché (mesurées chaque heure dans `observations.jsonl`), (b) cotes boostées des books bloqués (Winamax, Betclic) —
non lisibles automatiquement ; à évaluer à la main avec la cote juste affichée.

## Session 3 — Polymarket est-il une référence « sharp » ? (validation réelle)
Données : 251 matchs de Premier League 2025/26 sur Polymarket (série 10188), prix CLOB (prices-history, pas de 5 min)
au dernier point ≥ 5 min avant le coup d'envoi ; 189 appariés à football-data E0 avec clôture Pinnacle (PSC*, dé-vig Shin).
Scripts : `tools/pm_collect.py`, `tools/pm_vs_pinnacle.py`.

| Mesure | Polymarket | Pinnacle clôture |
|---|---|---|
| Écart absolu moyen de proba | 0,63 point | — |
| Log-loss (1X2) | **0,97812** | 0,98262 |
| Brier | **0,58676** | 0,58935 |
| Δ log-loss PM − PS | −0,0045, IC95 [−0,0083 ; −0,0008] | |
Délai médian du dernier prix PM : 10 min avant le coup d'envoi ; somme médiane des 3 prix : 1,000.
Conclusion : sur la Premier League, Polymarket près du coup d'envoi est au moins aussi bien calibré que Pinnacle.
Limites : un seul championnat, matchs très liquides, prix de dernière transaction et non milieu de carnet ;
les championnats moins liquides (Ligue 1, Liga) ne sont pas validés — d'où les filtres écart ≤ 3 % et liquidité ≥ 2 000 $.

## Session 3 (suite) — Unibet et cotes boostées Winamax
| # | Piste | Hypothèse | Test | Résultat chiffré | Décision |
|---|---|---|---|---|---|
| 12 | Unibet 1X2 | Unibet mieux pricé que NetBet | Lorient–Brest, page publique | Unibet 2,30/3,00/3,00 ; NetBet 2,37/3,05/2,85 ; juste 2,58/3,37/3,16 → marge ≈ 10 % chez les deux | Adaptateur gardé (page souvent en 503 depuis GitHub) |
| 13 | « Mène de 2 buts ou gagne » (Unibet/NetBet) | Marché mal pricé | Modèle Poisson calé sur Polymarket : Lorient 2,43 juste vs NetBet 2,27 | EV −6,8 % | Pas d'avantage |
| 14 | **Cotes boostées Winamax** (coteur.com) | Les boosts dépassent la cote juste | `tools/boost_backtest.py` : 45 boosts « un match » foot reconnus (août–oct. 2026), cote juste = Dixon-Coles calé sur les prix Polymarket à T-60 min | **EV moyenne −6,9 % [−9,0 ; −4,8]**, médiane −6,3 % ; 6/44 > 0 ; 2/44 > +5 %. Réglés 39 : 9 gagnés pour 11,5 attendus ; ROI −31,5 % (bruit) — chiffres après la 3e revue (règles durcies) | Garder l'alerte : seuls ~4 % des boosts passent le filtre ; jamais de pari « parce que c'est boosté » |
| 15 | Modèle de score (Dixon-Coles) | Calé sur 1X2/plus-moins/BTTS/buts équipe | Comparé au marché « score exact » Polymarket non utilisé (Lorient–Brest) | Écart moyen 0,37 pt ; erreur de calage ≤ 1,6 pt sur 45 matchs | Validé pour combinaisons de score final |

Bug trouvé et corrigé pendant le backtest : le gabarit « X gagne » acceptait « Mbappé premier buteur et Real Madrid
gagne » → 8 faux boosts à EV +25 à +160 %. Le sujet doit désormais être un simple nom d'équipe (test de régression).

3e revue adverse (Sonnet, sans contexte) : 12 défauts sur les boosts (dont réserves/féminines assimilées à l'équipe
première, match oublié dans un combiné, « respectivement » non standard, calage sous-contraint) — tous corrigés,
tests de régression dans tests/test_boosts.py (85 tests au total).

## Session 3 (fin) — tous sports, PMU, Betclic, consensus ANJ
| # | Piste | Hypothèse | Test | Résultat chiffré | Décision |
|---|---|---|---|---|---|
| 16 | PMU vs Polymarket (foot, tous marchés) | PMU parfois au-dessus du juste | 162 cotes, 6 matchs (run 03:51) | 0 à EV > 0 ; médianes 1X2 −9,7 %, DC −10,7 %, BTTS −10,9 %, plus/moins −13,3 %, mi-temps −16 % ; meilleure −4,8 % | Surveillance horaire |
| 17 | **Sports de niche / petits championnats moins bien pricés** (hypothèse du propriétaire) | Les books font plus d'erreurs hors grands championnats | Consensus ANJ leave-one-out (Shin), 2 326 cotes de 10 books, 163 matchs foot (Liga MX, Géorgie, Pologne…), tennis ITF/WTA, basket | **0 cote au-dessus du consensus** ; meilleure 0,0 % ; EV médiane par book : PMU −10,1 %, Olybet −10,4 %, Betclic −11,0 %, Betsson −11,4 %, NetBet −11,6 %, Unibet −13,0 %, DAZN −16,0 %, Vbet −18,3 % | Hypothèse non confirmée sur cet échantillon (une nuit) ; mesure continue dans observations.jsonl |
| 18 | Polymarket comme référence hors foot | NBA/NHL/tennis/UFC liquides | Tags testés : NBA 28, NHL 59, tennis 46, NCAAB 35 matchs liquides ; e-sport, tennis de table, volley, fléchettes : 0 liquide | Référence sharp utilisable pour 4 sports US + tennis ; pas pour les sports de niche | Niche → consensus seulement |
Constat structurel : les bookmakers français sont très alignés (mêmes fournisseurs de cotes), marges 10–18 %. Les
« erreurs » exploitables sont rares et brèves ; l'outil les cherche chaque heure sur ~600 matchs et ~20 bookmakers.

### Mesure du 2026-11-02 08:33 UTC (premier passage complet : PMU + coteur + Polymarket tous sports)
537 cotes de 10 bookmakers ANJ comparées à la cote juste Polymarket : **0 à EV > 0** ; meilleure −0,9 % (PMU, tennis).
EV médiane par bookmaker et marché : Betclic 1X2 −8,5 % / vainqueur (tennis, basket) −6,6 % ; Betsson −7,8 % / −8,4 % ;
Olybet −8,4 % / −7,8 % ; PMU 1X2 −9,9 %, vainqueur −6,9 %, plus/moins −13,9 % ; NetBet 1X2 −9,2 %, secondaires −13 à −20 % ;
DAZN Bet −10,5 % / −14,0 % ; Vbet −16,7 % / −14,3 %. Consensus ANJ (matchs sans Polymarket) : meilleure −1,2 %.
Lecture : les marchés « vainqueur » de tennis/basket sont les plus proches du juste (−1 à −3 % pour les meilleures cotes) :
c'est là qu'un décalage ponctuel a le plus de chances de devenir positif.

## Session 4 — ce que les autres dépôts du propriétaire ont déjà mesuré (2026-11-02)
Lus : cotes-value (le plus avancé : 4 672 paris simulés depuis le 05/10, branche `donnees`), cotes-boostees (941 boosts
suivis), Grotonome (relevé ANJ vs Smarkets/Pinnacle, toutes les 6 min), Revue (audit de 44 dépôts publics), Boost
(tracker de boosts transfermarkt), Cotescope (console qui relit cotes-value). Chiffres recalculés ici depuis leurs
fichiers publics (`paris.json`, `BILAN.md`), pas recopiés de leurs README.

### cotes-value : quelle référence a rapporté ? (paris simulés 10 €, premières détections, réglés au 02/11 08:44 UTC)
Hors tranche X (cotes > 10) ; IC 95 % naïf (les paris d'un même match sur plusieurs books sont corrélés : IC trop étroit).

| Référence | Réglés | ROI | IC 95 % | CLV moy. |
|---|---:|---:|---|---:|
| Polymarket | 670 | +9,3 % | [−0,8 ; +19,5] | +3,0 % |
| Pinnacle (API guest, cache Cloudflare) | 2 248 | −0,5 % | [−5,0 ; +3,9] | +1,3 % |
| Consensus des références | 373 | +6,9 % | [−5,7 ; +19,5] | +2,9 % |
| Betfair (arrêté le 18/10) | 196 | +13,9 % | [−5,0 ; +32,9] | +4,7 % |
| Matchbook | 137 | +11,0 % | [−11,1 ; +33,2] | +2,9 % |
| Kalshi (abandonné) | 191 | −28,4 % | — | −2,0 % |

- Polymarket « vainqueur » (tennis, NBA…) : 145 paris, ROI +33,8 % [+14,5 ; +53,1], CLV +7,4 % : seul segment dont l'IC
  exclut 0, à confirmer (choisi après coup). Polymarket 1N2 foot : +14 % mais IC [−10 ; +38].
- Tranche X (cotes > 10) contre Pinnacle : 545 paris, ROI −70 % malgré une CLV « +7,9 % » : les grosses cotes et la
  CLV mesurée contre une référence en cache trompent. Autonome plafonne déjà à 5 (Polymarket) et 6 (consensus) : garder.
- Pinnacle lu depuis GitHub (runners américains) : prix servis par le cache Cloudflare jusqu'à 15 min, d'où un
  « réchauffeur » Supabase à Paris chez cotes-value (compte requis : exclu ici). Confirme le choix de Polymarket.
- Leur règlement automatique tient sur LiveScore (API publique sans clé), ESPN, Flashscore et la source NHL officielle.

### cotes-boostees : les boosts ne sont pas rentables en bloc
Témoin « tout miser » : 293 réglés, ROI −3,9 % (protocole gelé : −6,9 % sur 166) ; boosts à EV ≥ +5 % face à Pinnacle :
2 sur 941. Cohérent avec notre backtest (#14 : EV moyenne −6,9 %, ~4 % des boosts > +5 %). Ne pas investir davantage
dans les boosts ; leurs modèles K/L/M (+14 à +43 %) sont exploratoires et choisis après lecture des résultats.

### Grotonome et Revue
- Grotonome : Smarkets (API publique, 60 req/min, milieu ≤ 10 pts d'écart) et Pinnacle guest servent de référence ;
  Betclic relayé par SportyTrader (horloge recalée, cote « figée » écartée). Aucune piste déclarée rentable.
- Revue : règle de décision à ≥ 300 paris pré-match à cote observée, ROI ET CLV positifs (IC 95 %). Leçon reprise :
  distinguer CLV contre la référence et ROI ; un résultat absent reste « non mesurable ».

### Repris dans Autonome (session 4)
1. **Polymarket tous championnats** (idée cotes-value : lecture par étiquette « soccer » 100350 et « basket » 28,
   bornée par la date de fin) : foot dans les 30 h = 92 matchs contre 6 avec l'ancienne liste de 11 championnats
   (02/11 09 h UTC). Contre l'instantané coteur de 08:33 : 90 matchs appariés, 1 348 cotes comparables, **0 à EV > 0**
   (médiane −12,7 % en 1N2 foot). Plus de chances de trouver un décalage ; aucune promesse.
2. **Règlement des paris « consensus » via LiveScore** (avant : jamais réglés, CLV seule). Contrôle sur la vraie
   journée du 01/11 (832 matchs finis) : 19 paris fictifs sur 28 réglés sur le bon match, 9 laissés ouverts (noms trop
   vagues), aucun mauvais appariement.
Non repris : Winamax/Betclic directs (proxy français + empreinte Chrome chez cotes-boostees = contournement exclu),
Pinnacle (cache périmé depuis GitHub), Supabase/Bright Data (comptes).

### Session 4 (suite) — obstacles d'Autonome et solutions trouvées ailleurs
| Obstacle | Constat | Solution reprise |
|---|---|---|
| Cadence | 3 passages `live` entre 03:51 et 08:33 UTC ; le relais relançait `live` sur `main` (ancien code) | `pulse` toutes les 5 min : `live` dès 15 min, `coteur` dès 60 min, branche par défaut (cotes-value 5 min, Grotonome 6 min) |
| Cotes de book vieilles | instantané coteur jusqu'à 3 h contre une référence Polymarket fraîche = fausses values | pas d'alerte si cote > 45 min (Revue : ≤ 5 min ; Cotescope : ≤ 2-15 min) |
| Marché mal traduit | aucun contrôle global par (book, marché) | groupe non conforme (EV médiane hors [−25 % ; −1 %] ou < 5 mesures) bloqué (cotes-value `controle.py`) |
| Couverture Polymarket | 6 matchs de foot à 30 h | tous championnats foot/basket (cotes-value) |
| Paris consensus non réglés | — | LiveScore (cotes-value) |
Recherche web (02/11) : aucune étude sérieuse ; un blog de fournisseur (OddsPapi, 28 matchs) mesure un retard médian des books
« mous » sur Pinnacle de ~6 min (1xBet) à ~1 h (Bet365) : la valeur se trouve dans ce retard, d'où la cadence.
Écartés (contournement ou compte) : Winamax socket et NetBet/Unibet/OlyBet via `curl_cffi` « impersonate=chrome »
(cotes-value), proxy français Bright Data (cotes-boostees), réchauffeur Pinnacle Supabase. Betclic gRPC-web public
(`offering.begmedia.com`, cotes-value, sans empreinte) : à décider par le propriétaire (CLAUDE.md : ne pas contourner le 403).
