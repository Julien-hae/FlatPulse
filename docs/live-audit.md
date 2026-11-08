# Audit en direct des sources — suivi des runs

Résultats de `tests/integration/test_live_sources.py` (#119), run par run, le plus récent
en tête. L'audit interroge le vrai site de chaque régie : il montre ce que les scrapers
extraient **réellement** de toute l'offre, là où les fixtures ne montrent que des cas
choisis. Commande et fonctionnement : `docs/architecture.md` §8.

Pour ajouter un run : copier la section du dernier, remplacer les tableaux par ceux du
log (`Live supply distribution`, `Live fill-rate report`), et lister ce qui a changé.
Un trou de remplissage est d'abord **vérifié sur le site** : soit la donnée est publiée
et le scraper la manque (→ issue), soit la régie ne la publie pas (→ noté ici et dans
`docs/spike-agencies.md`, sans issue).

---

## Run du 08.11.2026, 12:12 UTC (#131 complet)

- Code : branche #131, correctif « CHF 0.- » compris
- Durée : 4 523 s
- Résultat : **vert** — `test_live_catalogue_is_not_empty` et `test_live_fill_rates` ;
  **0 annonce ignorée**
- Volume : **1 365 annonces** — Naef 959, Comptoir 363, Burger 43 ; 637 à Genève
  (Naef 387, Comptoir 207, Burger 43)
- Canton inconnu : 0 sur les trois sources

### Ce qui a changé depuis le run de 10:47

- **Naef et Burger** : répartition et taux identiques au run de 10:47.
- **Comptoir** : 279533 n'est plus ignoré ; il sort sans prix, d'où `parking`
  `price_chf` 73/75 (97.3 %) au lieu de 73/74. Le catalogue passe de 369 fiches
  (368 + 1 ignorée) à 363 : −6 appartements (−3 GE, −3 VS), +1 parking GE. C'est
  probablement le roulement de l'offre (des fiches disparaissent vite, cf.
  `docs/spike-agencies.md`), non vérifié.

### Comptoir — répartition et taux de remplissage

| Type | GE | VD | VS | Total |
|---|---:|---:|---:|---:|
| apartment | 19 | 17 | 47 | 83 |
| commercial | 115 | 25 | 35 | 175 |
| house | 3 | 4 | 1 | 8 |
| parking | 50 | 9 | 16 | 75 |
| storage | 20 |  | 2 | 22 |

| Type | n | `price_chf` | `surface_m2` | `nb_rooms` | `postal_code` | `images` |
|---|---:|---:|---:|---:|---:|---:|
| apartment | 83 | 100 % | 62.7 % | 100 % | 0 % | 95.2 % |
| commercial | 175 | 96 % | 97.1 % | 12.6 % | 0 % | 98.3 % |
| house | 8 | 100 % | 50 % | 87.5 % | 0 % | 100 % |
| parking | 75 | 97.3 % | 0 % | 0 % | 0 % | 45.3 % |
| storage | 22 | 81.8 % | 81.8 % | 4.5 % | 0 % | 77.3 % |

### Reste ouvert

Les taux bas listés au run de 09:08 (surface des appartements Comptoir, prix et pièces
des maisons Naef, images des parkings), non investigués. Comptoir `postal_code` reste à
0 % : non publié par la régie.

---

## Run du 08.11.2026, 10:47 UTC (après #131)

- Code : branche #131, avant le correctif « CHF 0.- » ci-dessous
- Durée : 4 522 s
- Résultat : **1 échec** — `test_live_catalogue_is_not_empty` : 1 annonce Comptoir
  ignorée (au lieu de 5) ; `test_live_fill_rates` vert
- Volume : **1 370 annonces** — Naef 959, Comptoir 368 (+ 1 ignorée), Burger 43 ;
  639 à Genève (Naef 387, Comptoir 209, Burger 43)
- **Canton inconnu : 0** sur les trois sources (240 Naef et 43 Burger au run précédent)

### Ce qui a changé depuis le run de 09:08

| Source | Avant | Après |
|---|---|---|
| burger | canton inconnu 43/43, `postal_code` 0 %, 1 type inconnu | 43 GE, `postal_code` 100 %, 5 parkings (la « Place couverte » comprise) |
| naef | canton inconnu 240/959 | 0 ; le NPA donne notamment 11+5+4 annonces jurassiennes (JU) qui n'apparaissaient pas |
| comptoir | 5 parkings ignorés (titre vide) | 4 récupérés, titrés « Parking » ; le 5ᵉ (279533) tombe sur `price_chf must be positive: 0` |

### Constat vérifié sur le site

| Source | Constat | Cause | Suite |
|---|---|---|---|
| comptoir | 279533 (parking à Satigny) ignoré, `price_chf must be positive: 0` | La fiche affiche `CHF 0.- / mois` en en-tête comme en `Loyer` : pas de prix publié | #131 : `parse_monthly_rent` rend `None` pour un loyer nul, toutes sources |

Le correctif ne change rien chez Naef : 43 annonces sans prix sur le payload du
08.11.2026 avant comme après.

### Répartition de l'offre (source × type × canton)

| Source | Type | GE | VD | VS | NE | FR | BE | JU | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| burger | apartment | 28 |  |  |  |  |  |  | 28 |
| burger | commercial | 5 |  |  |  |  |  |  | 5 |
| burger | house | 2 |  |  |  |  |  |  | 2 |
| burger | parking | 5 |  |  |  |  |  |  | 5 |
| burger | storage | 3 |  |  |  |  |  |  | 3 |
| comptoir | apartment | 22 | 17 | 50 |  |  |  |  | 89 |
| comptoir | commercial | 115 | 25 | 35 |  |  |  |  | 175 |
| comptoir | house | 3 | 4 | 1 |  |  |  |  | 8 |
| comptoir | parking | 49 | 9 | 16 |  |  |  |  | 74 |
| comptoir | storage | 20 |  | 2 |  |  |  |  | 22 |
| naef | apartment | 79 | 63 | 11 | 146 | 8 | 5 | 11 | 323 |
| naef | commercial | 103 | 94 | 4 | 26 | 7 | 1 | 5 | 240 |
| naef | house | 2 | 9 | 9 | 1 |  |  |  | 21 |
| naef | parking | 203 | 124 | 1 | 37 | 5 | 1 | 4 | 375 |

### Taux de remplissage (source × type)

| Source | Type | n | `price_chf` | `surface_m2` | `nb_rooms` | `postal_code` | `images` |
|---|---|---:|---:|---:|---:|---:|---:|
| burger | apartment | 28 | 100 % | 92.9 % | 96.4 % | 100 % | 89.3 % |
| burger | commercial | 5 | 100 % | 100 % | 0 % | 100 % | 100 % |
| burger | house | 2 | 100 % | 0 % | 100 % | 100 % | 100 % |
| burger | parking | 5 | 100 % | 0 % | 0 % | 100 % | 0 % |
| burger | storage | 3 | 66.7 % | 33.3 % | 0 % | 100 % | 0 % |
| comptoir | apartment | 89 | 100 % | 59.6 % | 100 % | 0 % | 95.5 % |
| comptoir | commercial | 175 | 96 % | 97.1 % | 12.6 % | 0 % | 98.3 % |
| comptoir | house | 8 | 100 % | 50 % | 87.5 % | 0 % | 100 % |
| comptoir | parking | 74 | 98.6 % | 0 % | 0 % | 0 % | 44.6 % |
| comptoir | storage | 22 | 81.8 % | 81.8 % | 4.5 % | 0 % | 77.3 % |
| naef | apartment | 323 | 97.8 % | 75.9 % | 98.8 % | 100 % | 100 % |
| naef | commercial | 240 | 88.3 % | 85.4 % | 13.3 % | 100 % | 100 % |
| naef | house | 21 | 66.7 % | 95.2 % | 71.4 % | 100 % | 100 % |
| naef | parking | 375 | 99.7 % | 1.1 % | 0 % | 100 % | 100 % |

Les taux bas non investigués du run précédent restent ouverts, inchangés.

### Attendu au prochain run

- 0 annonce ignorée : 279533 sort avec `price_chf = None` (vérifié sur la fiche du
  08.11.2026, devenue la fixture `tests/fixtures/comptoir/279533.html`)
- comptoir `postal_code` toujours à 0 % (non publié)

---

## Run du 08.11.2026, 09:08 UTC

- Code : branche #119 (commit `bc648c9` + modifications non commitées de #119)
- Durée : 4 523 s (≈ 75 min, dont l'essentiel pour Comptoir : 16 pages + une fiche par
  annonce au Crawl-delay de 10 s)
- Résultat : **1 échec** — `test_live_catalogue_is_not_empty` (5 annonces Comptoir
  ignorées) ; `test_live_fill_rates` vert (rapport informatif, sans seuil)
- Volume : **1 366 annonces** — Naef 959, Comptoir 364 (+ 5 ignorées), Burger 43

### Répartition de l'offre (source × type × canton)

| Source | Type | GE | VD | VS | NE | FR | BE | inconnu | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| burger | apartment |  |  |  |  |  |  | 28 | 28 |
| burger | commercial |  |  |  |  |  |  | 5 | 5 |
| burger | house |  |  |  |  |  |  | 2 | 2 |
| burger | parking |  |  |  |  |  |  | 4 | 4 |
| burger | storage |  |  |  |  |  |  | 3 | 3 |
| burger | *inconnu* |  |  |  |  |  |  | 1 | 1 |
| comptoir | apartment | 22 | 17 | 49 |  |  |  |  | 88 |
| comptoir | commercial | 116 | 25 | 35 |  |  |  |  | 176 |
| comptoir | house | 3 | 4 | 1 |  |  |  |  | 8 |
| comptoir | parking | 46 | 8 | 16 |  |  |  |  | 70 |
| comptoir | storage | 20 |  | 2 |  |  |  |  | 22 |
| naef | apartment | 68 | 53 | 5 | 62 | 5 | 5 | 125 | 323 |
| naef | commercial | 97 | 79 | 4 | 12 | 5 | 1 | 42 | 240 |
| naef | house | 1 | 6 | 6 |  |  |  | 8 | 21 |
| naef | parking | 172 | 108 | 1 | 25 | 3 | 1 | 65 | 375 |

### Taux de remplissage (source × type)

| Source | Type | n | `price_chf` | `surface_m2` | `nb_rooms` | `postal_code` | `images` |
|---|---|---:|---:|---:|---:|---:|---:|
| burger | apartment | 28 | 100 % | 92.9 % | 96.4 % | 0 % | 89.3 % |
| burger | commercial | 5 | 100 % | 100 % | 0 % | 0 % | 100 % |
| burger | house | 2 | 100 % | 0 % | 100 % | 0 % | 100 % |
| burger | parking | 4 | 100 % | 0 % | 0 % | 0 % | 0 % |
| burger | storage | 3 | 66.7 % | 33.3 % | 0 % | 0 % | 0 % |
| burger | *inconnu* | 1 | 100 % | 0 % | 0 % | 0 % | 0 % |
| comptoir | apartment | 88 | 100 % | 59.1 % | 100 % | 0 % | 95.5 % |
| comptoir | commercial | 176 | 96 % | 97.2 % | 12.5 % | 0 % | 98.3 % |
| comptoir | house | 8 | 100 % | 50 % | 87.5 % | 0 % | 100 % |
| comptoir | parking | 70 | 98.6 % | 0 % | 0 % | 0 % | 44.3 % |
| comptoir | storage | 22 | 81.8 % | 81.8 % | 4.5 % | 0 % | 77.3 % |
| naef | apartment | 323 | 97.8 % | 75.9 % | 98.8 % | 100 % | 100 % |
| naef | commercial | 240 | 88.3 % | 85.4 % | 13.3 % | 100 % | 100 % |
| naef | house | 21 | 66.7 % | 95.2 % | 71.4 % | 100 % | 100 % |
| naef | parking | 375 | 99.7 % | 1.1 % | 0 % | 100 % | 100 % |

### Constats vérifiés sur le site

| Source | Constat | Cause | Suite |
|---|---|---|---|
| comptoir | 5 parkings ignorés, `title cannot be empty` (921110, 901969, 895145, 455280, 279533) | Fiches publiées avec un `<h1>` vide ; le reste du tableau « Détails » est complet | #131 : titre = `Type de bien` |
| burger | 1 annonce de type inconnu | Libellé « Place couverte », absent du mapping | #131 : → `PARKING` |
| burger | `postal_code` 0 %, canton inconnu 43/43 | NPA affiché (`1205 Genève`) mais jeté par le scraper ; aucun canton sur la fiche | #131 : NPA lu, canton déduit du NPA |
| naef | canton inconnu 240/959 | `adresse_canton` vide dans le payload ; `npa` toujours là | #131 : canton déduit du NPA (et de la localité si le NPA est partagé) |
| comptoir | `postal_code` 0 % | **Non publié** : adresse « rue, ville » sans NPA, seulement `data-lat`/`data-lng` | Aucune (géocodage inverse hors périmètre) |

### Taux bas, non investigués

Pas d'issue tant qu'ils ne sont pas vérifiés sur le site :

- `surface_m2` et `nb_rooms` des parkings, `nb_rooms` des commerces et dépôts : le plus
  souvent sans objet pour ces types.
- comptoir `apartment` `surface_m2` 59.1 % (36 sur 88 sans surface) : la ligne
  « Surface » manque-t-elle sur la fiche, ou porte-t-elle un autre libellé ?
- naef `house` `price_chf` 66.7 % et `nb_rooms` 71.4 % : probablement des loyers sur
  demande (`loyer_sur_demande`), à confirmer.
- comptoir `parking` `images` 44.3 %, burger `parking` et `storage` 0 % : fiches sans
  photo ?

### Attendu au prochain run (après #131)

Vérifié hors ligne le 08.11.2026 sur les pages relevées ce jour-là :

- comptoir : 0 annonce ignorée ; les parkings sans `h1` titrés « Parking » (921110, 901969)
- burger : « Place couverte » → `parking` ; `postal_code` et canton renseignés
- naef : canton connu sur 959/959 annonces du payload, 0 contradiction avec
  `adresse_canton` là où il est rempli
- comptoir : `postal_code` toujours à 0 % (attendu)
