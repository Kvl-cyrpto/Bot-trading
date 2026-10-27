# Test de l'IA (hors echantillon)

Periode testee : 29/10/2024 au 26/10/2026. Paires : ADA-EUR, BTC-EUR, DOGE-EUR, ETH-EUR, LINK-EUR, LTC-EUR, SOL-EUR, XRP-EUR.
Chaque jour, l'IA ne voit que le passe et predit le mouvement des 24 prochaines heures.

Correlation entre prediction et realite : +0.089 (0 = aucune, 0,05 = faible, 0,1 = bonne)

Mouvement moyen sur 24 h, tous moments confondus : +0.06 %

## Que gagne-t-on en suivant les signaux ? (moyenne par signal)

| Groupe | Signaux | Gain brut | Net frais 1 % | Net frais 0,5 % |
|---|---|---|---|---|
| Bas 5 % (signal de vente) | 6980 | +0.34 % | -0.66 % | -0.16 % |
| Bas 20 % | 27937 | -0.09 % | -1.09 % | -0.59 % |
| Milieu 60 % | 83735 | -0.09 % (mouvement) | - | - |
| Haut 20 % | 27920 | +0.46 % | -0.54 % | -0.04 % |
| Haut 5 % (signal d'achat) | 6980 | +1.08 % | +0.08 % | +0.58 % |

## Stabilite dans le temps (signaux d'achat 5 % + de vente 5 %, frais 1 %)

| Periode | Signaux | Net moyen par signal |
|---|---|---|
| P1 | 6958 | +0.10 % |
| P2 | 3240 | -0.97 % |
| P3 | 1935 | +0.15 % |
| P4 | 1827 | -1.03 % |

Attention : les signaux voisins se chevauchent (deux signaux a 1 h d'ecart couvrent presque le meme mouvement), donc le nombre de vrais trades independants est bien plus petit que la colonne Signaux.

## Verdict automatique

Pas d'avantage net apres frais de 1 % de facon stable. Dans cet etat, l'IA ne vaut pas la peine d'etre branchee.
