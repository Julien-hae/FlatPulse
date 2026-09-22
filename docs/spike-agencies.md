# SPIKE — Accès aux annonces des 13 régies

> Généré depuis `notebooks/spike-agences.ipynb` le 22.09.2026 07:29 UTC.
> Aucune régie ne nécessite Playwright.

Les volumes sont des **fiches distinctes**, pagination suivie et dédupliquée — pas des
cartes d'une page. La colonne Genève ne compte que le canton, quand la source permet de
le distinguer.

| Régie | Statut | Accès | Pagination | Fiches | Genève | Scraper | Vérifié |
|---|---|---|---|---|---|---|---|
| Naef Immobilier | MVP phase 1 | `GET naef.ch/wp-admin/admin-ajax.php?action=get_all_props&type=Location` | aucune — tout le parc en un GET | 355 | 58 | **HttpScraper (JSON)** | HTTP 200 |
| Agence Immobilière Rodolphe Burger SA | MVP phase 1 | `GET burger-sa.ch/fr/louer?page=N` | ?page=N, 6 annonces par page | 32 | 32 | **HttpScraper** | HTTP 200 |
| Comptoir Immobilier | MVP phase 1 | `GET comptoir-immo.ch/location/{appartement,maison}/Genève/?page=N` | ?page=N, 24 par page — tri antichronologique par défaut | 29 | 29 | **HttpScraper** | HTTP 200 |
| Rosset & Cie | candidate phase 2 | `GET rosset.ch/api/properties?page=N` | ?page=N, 24 par page, totalPages dans la réponse | 165 | 105 | **HttpScraper (JSON)** | HTTP 200 |
| Bory & Cie | candidate phase 2 | `GET bory.ch/louer → script#__NEXT_DATA__` | connexion GraphQL Relay : pageInfo.endCursor, 20 sur 28 | 20 | — | **HttpScraper (JSON)** | HTTP 200 |
| Moser Vernet & Cie | candidate phase 2 | `GET moservernet.ch/louer/` | aucune — 152 cartes, catalogue entier en une page | 150 | — | **HttpScraper** | HTTP 200 |
| Bernard Nicod | candidate phase 2 | `GET bernard-nicod.ch/api/search-projects-list` | dans la réponse JSON | 17 | — | **HttpScraper (JSON enveloppant du HTML)** | HTTP 200 |
| Bordier & Schmidhauser | candidate phase 2 | `GET bordier-schmidhauser.ch/location/` | à confirmer | 46 | — | **HttpScraper** | HTTP 200 |
| Zimmo | catalogue | `GET zimmo.ch/rent.html?search-state-ge=on` | à confirmer | 1 | — | **HttpScraper** | HTTP 200 |
| Gerofinance-Régie du Rhône | catalogue | `GET gerofinance.ch/p3157-alouer.html?type[]=…` | à confirmer | 11 | — | **HttpScraper** | HTTP 200 |
| Pilet & Renaud | à trancher | `endpoint AJAX assemblé en JavaScript — non identifié` | — | — | — | **à trancher** | non vérifiable |
| CPEG | à trancher | `iframe → immobilier.cpeg.ch (Blazor + portail_api)` | — | — | — | **à trancher** | non vérifiable |
| Grange & Cie | écarté | `—` | — | — | — | **écarté** | non vérifiable |

# MVP — phase 1

## Naef Immobilier (`naef`)

- Accès : `GET naef.ch/wp-admin/admin-ajax.php?action=get_all_props&type=Location`
- Rendu : JS-rendered — la page de listings ne contient aucune annonce
- Pagination : aucune — tout le parc en un GET
- Scraper : **HttpScraper (JSON)**
- Débit : pas de Crawl-delay · poll 90-120s (leur cache tourne à 180s)
- Volume : 355 fiches distinctes, dont 58 dans le canton de Genève — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/naef_location.json` (JSON)

### Clés du payload JSON

| Champ normalisé | Clé source |
|---|---|
| `external_id` | `no_dossier` |
| `external_url` | `link` |
| `description` | `intitule_plaquette` |
| `price_chf` | `loyer_mensuel_brut` |
| `nb_rooms` | `nb_pieces` |
| `surface_m2` | `surface_habitable` |
| `city` | `adresse_localite` |
| `canton` | `adresse_canton` |
| `postal_code` | `npa` |
| `images` | `imgs` |

### Pièges

- L'URL /page-N/ renvoie le même shell vide : ne jamais paginer par URL.
- /wp-json/naef/v1/api/properties-data répond 401 Invalid licence key — fausse piste.
- loyer_sur_demande == 'oui' → price_chf = None, surtout pas 0.
- imgs arrive en liste OU en objet indexé.
- adresse_canton est le nom complet → utils.canton_code pour le VARCHAR(2).
- Pas de rue dans le payload : slug du link ou fiche détail.

## Agence Immobilière Rodolphe Burger SA (`burger`)

- Accès : `GET burger-sa.ch/fr/louer?page=N`
- Rendu : HTML statique
- Pagination : ?page=N, 6 annonces par page
- Scraper : **HttpScraper**
- Débit : pas de Crawl-delay · 6 pages à 90s = 4 req/min
- Canal de repli : sitemap.php — 32 fiches /fr/louer/ en 5 Ko, lastmod à jour, URLs nues
- Volume : 32 fiches distinctes, dont 32 dans le canton de Genève — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/burger_listing.html` (HTML)

### Sélecteurs CSS

| Champ | Sélecteur |
|---|---|
| conteneur | `div.bien-item` |
| lien | `div.bien-item a::attr(href)` |
| image | `div.bien-item img::attr(src)` |
| ville | `div.bien-item h2::text` |
| adresse | `div.bien-item h3::text` |
| prix / pièces / surface | `par motif sur le texte de la carte (Tailwind)` |

### Pièges

- Trois formats de prix : CHF 3'500.— / mois, CHF 2'320.- + charges, Dès CHF 2'320.- + charges. Tiret cadratin autant que tiret simple.
- Charges sur une ligne commençant par « + » : écarter les lignes contenant « charges » casserait le format « Dès … + charges ».
- Surface absente, en fourchette (de 85 M2 à 100 M2) ou préfixée (ENV. 60 M2).
- Le slug peut mentir (35-pieces affiché 3.0 pièces) : faire foi au texte.
- external_id = URL complète : deux fiches partagent le préfixe …mont-bla.
- Le listing mélange logements, commerces et parkings : filtrer.

## Comptoir Immobilier (`comptoir`)

- Accès : `GET comptoir-immo.ch/location/{appartement,maison}/Genève/?page=N`
- Rendu : HTML statique, filtrage par le chemin de l'URL
- Pagination : ?page=N, 24 par page — tri antichronologique par défaut
- Scraper : **HttpScraper**
- Débit : Crawl-delay: 10 → rate_limit_rpm = 6
- Canal de repli : GET /?post_type=property_for_rent&feed=rss2 — 24 items, pubDate réelles. Le sitemap property_for_rent-*.xml est périmé (lastmod 2025-11)
- Volume : 29 fiches distinctes, dont 29 dans le canton de Genève — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/comptoir_listing.html` (HTML)

### Sélecteurs CSS

| Champ | Sélecteur |
|---|---|
| conteneur | `article.teaser--property_for_rent` |
| lien | `article.teaser--property_for_rent a::attr(href)` |
| image | `article.teaser--property_for_rent img::attr(src)` |
| prix / pièces / surface / localité | `par motif sur le texte de la carte` |

### Pièges

- propertyId (Apimo) absent des annonces sans photo : external_id = chemin de la fiche.
- Le titre contredit parfois la métadonnée : la ligne de métadonnées fait foi.
- Surface tantôt collée à la métadonnée, tantôt sur sa propre ligne.
- Prix sur demande → price_chf = None.
- Canton écrit canton-de-geneve dans les fiches, Genève dans les filtres.
- Les liens SEO contextuels vivent dans la même grille que les cartes.

# Candidates — phase 2

## Rosset & Cie (`rosset`)

- Accès : `GET rosset.ch/api/properties?page=N`
- Rendu : Next.js — API REST publique, sans authentification
- Pagination : ?page=N, 24 par page, totalPages dans la réponse
- Scraper : **HttpScraper (JSON)**
- Débit : à mesurer
- Canal de repli : HTML de /louer
- Volume : 165 fiches distinctes, dont 105 dans le canton de Genève (la source en déclare 165) — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/rosset_properties.json` (JSON)

### Clés du payload JSON

| Champ normalisé | Clé source |
|---|---|
| `external_id` | `id` |
| `external_url` | `href` |
| `price_chf` | `priceRaw` |
| `nb_rooms` | `roomsRaw` |
| `surface_m2` | `surface` |
| `city` | `city` |
| `canton` | `canton` |
| `address` | `address` |
| `images` | `images` |
| `disponibilité` | `availabilityDate` |

### Pièges

- Les filtres transaction/type/category sont ignorés : la réponse ne bouge pas.
- L'API mélange location et vente, et tous les cantons : filtrer côté scraper.

## Bory & Cie (`bory`)

- Accès : `GET bory.ch/louer → script#__NEXT_DATA__`
- Rendu : Next.js — état React Query hydraté dans la page
- Pagination : connexion GraphQL Relay : pageInfo.endCursor, 20 sur 28
- Scraper : **HttpScraper (JSON)**
- Débit : à mesurer
- Canal de repli : /_next/data/<buildId>/fr/louer — le buildId change à chaque déploiement
- Volume : 20 fiches distinctes (la source en déclare 28) — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/bory_next_data.json` (JSON)

### Clés du payload JSON

| Champ normalisé | Clé source |
|---|---|
| `external_id` | `slug` |
| `title` | `name` |
| `price_chf` | `net_rent` |
| `nb_rooms` | `number_rooms` |
| `surface_m2` | `living_area_square_meter` |
| `city` | `address_town` |
| `street` | `address_street` |
| `street_number` | `address_street_number` |
| `postal_code` | `address_npa` |
| `floor` | `floor_number` |
| `images` | `medias.nodes[].path` |

### Pièges

- Connexion Relay : les annonces sont sous edges[].node, pas dans une liste plate.
- counter.amount = 28 alors que la page n'en porte que 20 : curseur obligatoire.
- rent_displayed = false signale un loyer sur demande.
- Seule source à donner floor_number et l'adresse décomposée.
- Backend WordPress headless + GraphQL (edit.bory.ch).

## Moser Vernet & Cie (`moservernet`)

- Accès : `GET moservernet.ch/louer/`
- Rendu : WordPress + Quorum, HTML statique
- Pagination : aucune — 152 cartes, catalogue entier en une page
- Scraper : **HttpScraper**
- Débit : page de 2,9 Mo : privilégier le GET conditionnel (ETag / If-None-Match)
- Canal de repli : wp-content/moser-vernet-sitemap.xml
- Volume : 150 fiches distinctes — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/moservernet_listing.html` (HTML)

### Sélecteurs CSS

| Champ | Sélecteur |
|---|---|
| conteneur | `div.property-card` |
| lien | `div.property-card a::attr(href)` |
| image | `div.property-card img::attr(src)` |

### Pièges

- /louer/tous/tous/tous/ renvoie 500 tout en servant le contenu : utiliser /louer/.
- ?page=2 renvoie les mêmes 152 cartes : la pagination n'existe pas.
- 2,9 Mo par poll = ~2,8 Go/jour à 90s sans GET conditionnel.

## Bernard Nicod (`bernard-nicod`)

- Accès : `GET bernard-nicod.ch/api/search-projects-list`
- Rendu : Drupal — page vide, JSON {html, visible, total}
- Pagination : dans la réponse JSON
- Scraper : **HttpScraper (JSON enveloppant du HTML)**
- Débit : à mesurer
- Canal de repli : /api/search-projects-markers — {id, lat, lng}, utile en phase 3
- Volume : 17 fiches distinctes (la source en déclare 17) — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/bernard_nicod_list.json` (JSON)

### Clés du payload JSON

| Champ normalisé | Clé source |
|---|---|
| `fragment` | `html` |
| `total` | `total` |
| `visible` | `visible` |

### Pièges

- La charge utile est un fragment HTML dans une clé JSON : parsel reste nécessaire.
- Les paramètres de filtre sont ignorés : on récupère tout le catalogue.
- Les 1597 CHF de la page sont dans drupal-settings-json, pas dans le DOM.
- Le conteneur de carte reste à identifier DANS le fragment html de la réponse.

## Bordier & Schmidhauser (`bordier`)

- Accès : `GET bordier-schmidhauser.ch/location/`
- Rendu : WordPress + plugin RealForce, HTML statique
- Pagination : à confirmer
- Scraper : **HttpScraper**
- Débit : Cloudflare sans challenge : requêtes normales
- Canal de repli : sitemap_index.xml
- Volume : 46 fiches distinctes — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/bordier_listing.html` (HTML)

### Sélecteurs CSS

| Champ | Sélecteur |
|---|---|
| conteneur | `div.realforce_catalog-list__item` |
| prix | `div.realforce_catalog-list__price::text` |
| titre | `div.realforce_catalog-list__head::text` |
| texte | `div.realforce_catalog-list__text::text` |
| lien | `a.realforce_object__img-link::attr(href)` |
| image | `div.realforce_catalog-list__figure img::attr(src)` |

### Pièges

- Aucune route REST immobilière sur les 562 de /wp-json/.
- Aucun lien de pagination dans le HTML : convention à identifier.

# Catalogue — non retenues pour l'instant

## Zimmo (`zimmo`)

- Accès : `GET zimmo.ch/rent.html?search-state-ge=on`
- Rendu : HTML statique, un seul script externe
- Pagination : à confirmer
- Scraper : **HttpScraper**
- Débit : à mesurer
- Volume : 1 fiches distinctes — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/zimmo_listing.html` (HTML)

### Sélecteurs CSS

| Champ | Sélecteur |
|---|---|
| conteneur | `div.objects-list div.item` |
| lien | `div.objects-list div.item a::attr(href)` |
| image | `div.objects-list div.item img::attr(src)` |

### Pièges

- /api/v1/map/ existe dans le code mais répond 404 en GET.
- div.item seul attrape autre chose que des annonces : ancrer sur div.objects-list.

## Gerofinance-Régie du Rhône (`gerofinance`)

- Accès : `GET gerofinance.ch/p3157-alouer.html?type[]=…`
- Rendu : CMS propriétaire PHP, HTML statique
- Pagination : à confirmer
- Scraper : **HttpScraper**
- Débit : à mesurer
- Volume : 11 fiches distinctes — relevé le 22.09.2026 07:29 UTC
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/gerofinance_listing.html` (HTML)

### Sélecteurs CSS

| Champ | Sélecteur |
|---|---|
| conteneur | `article.bien-article` |
| prix | `article.bien-article h6.article-price::text` |
| infos | `article.bien-article div.article-price-bien_img_informations::text` |
| lien | `article.bien-article a::attr(href)` |
| image | `article.bien-article img::attr(src)` |

### Pièges

- Endpoints AJAX .php présents mais getMapBienInfo.php répond 400 en GET.
- Volume faible : à mettre en regard du coût d'un scraper.

# À trancher

## Pilet & Renaud (`pilet-renaud`)

- Accès : `endpoint AJAX assemblé en JavaScript — non identifié`
- Rendu : JS — filtres passés en base64 dans le fragment d'URL
- Pagination : —
- Scraper : **à trancher**

### Pièges

- Le fragment décode transaction=rent&type=APPARTEMENT&room_min=… : ce sont les clés attendues par l'endpoint.
- base64 apparaît 10 fois dans les scripts, ajaxUrl 3 fois, mais le chemin est assemblé dynamiquement.

## CPEG (`cpeg`)

- Accès : `iframe → immobilier.cpeg.ch (Blazor + portail_api)`
- Rendu : cpeg.ch ne contient aucune annonce
- Pagination : —
- Scraper : **à trancher**
- Débit : Crawl-delay: 10

### Pièges

- Scraper cpeg.ch ne donnera jamais rien : tout est dans l'iframe.
- Gros bailleur genevois : l'API du portail vaut la passe supplémentaire.

# Écartées

## Grange & Cie (`grange`)

- Accès : `—`
- Rendu : 403 Cloudflare, y compris sur robots.txt
- Pagination : —
- Scraper : **écarté**

### Pièges

- Challenge sur empreinte TLS : ni les en-têtes Chrome complets ni HTTP/2 ne passent.
- Contourner coûterait curl-impersonate ou un navigateur, pour une seule régie.
