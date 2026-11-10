# SPIKE — Accès aux annonces des 13 régies

> Généré depuis `notebooks/spike-agences.ipynb` le 22.09.2026 07:29 UTC.
> Naef : volumes et mapping actualisés au 30.10.2026 (#116).
> Naef, Burger, Comptoir : localisation, titres et types revus après l'audit en direct
> du 08.11.2026 (#131, résultats dans `docs/live-audit.md`).
> Aucune régie ne nécessite Playwright.

Les volumes sont des **fiches distinctes**, pagination suivie et dédupliquée — pas des
cartes d'une page. La colonne Genève ne compte que le canton, quand la source permet de
le distinguer.

\* Zimmo : la mesure du 22.09.2026 07:29 UTC (1 fiche) est invalidée par un bug de
dédoublonnage (toutes les fiches partagent le même chemin, seule `?ref=` les distingue —
corrigé dans le notebook, `count.keep_query`) et un sélecteur `conteneur` erroné qui ne
matchait rien sur le site réel (corrigé également). La fixture, elle, contient bien 4
fiches distinctes. À recalculer au prochain passage du notebook.

| Régie | Statut | Accès | Pagination | Fiches | Genève | Scraper | Vérifié |
|---|---|---|---|---|---|---|---|
| Naef Immobilier | MVP phase 1 | `GET naef.ch/wp-admin/admin-ajax.php?action=get_all_props&type=Location` | aucune — tout le parc en un GET | 963 | — | **HttpScraper (JSON)** | HTTP 200 |
| Agence Immobilière Rodolphe Burger SA | MVP phase 1 | `GET www.burger-sa.ch/sitemap.php` + fiches | aucune — sitemap complet, `lastmod` par fiche | 27 | 27 | **HttpScraper** | HTTP 200 |
| Comptoir Immobilier | MVP phase 1 | `GET comptoir-immo.ch/location/{appartement,maison}/Genève/?page=N` | ?page=N, 24 par page — tri antichronologique par défaut | 29 | 29 | **HttpScraper** | HTTP 200 |
| Rosset & Cie | candidate phase 2 | `GET rosset.ch/api/properties?page=N` | ?page=N, 24 par page, totalPages dans la réponse | 165 | 105 | **HttpScraper (JSON)** | HTTP 200 |
| Bory & Cie | candidate phase 2 | `GET bory.ch/louer → script#__NEXT_DATA__` | connexion GraphQL Relay : pageInfo.endCursor, 20 sur 28 | 20 | — | **HttpScraper (JSON)** | HTTP 200 |
| Moser Vernet & Cie | candidate phase 2 | `GET moservernet.ch/louer/` | aucune — 152 cartes, catalogue entier en une page | 150 | — | **HttpScraper** | HTTP 200 |
| Bernard Nicod | candidate phase 2 | `GET bernard-nicod.ch/api/search-projects-list` | dans la réponse JSON | 17 | — | **HttpScraper (JSON enveloppant du HTML)** | HTTP 200 |
| Bordier & Schmidhauser | candidate phase 2 | `GET bordier-schmidhauser.ch/location/` | à confirmer | 46 | — | **HttpScraper** | HTTP 200 |
| Zimmo | catalogue | `GET zimmo.ch/rent.html?search-state-ge=on` | à confirmer | ≥4* | — | **HttpScraper** | HTTP 200 |
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
- Volume : 963 annonces — relevé le 30.10.2026 (#116) : 309 appartements (`APP`),
  389 parkings (`PARC`), 244 commerces (`LCO`) et 21 maisons (`MAI`).
- Périmètre : **toute l'offre**, parkings et commerces compris, tous cantons
  confondus. Le scraper étiquette les annonces sans les filtrer ; le filtrage vient en aval.
- Localisation : NPA disponible sur les 963 annonces ; canton renseigné sur 726,
  vide sur 237. Le nombre d'annonces genevoises n'est pas établi pour ce relevé.
  Au 08.11.2026 : 959 annonces, `adresse_canton` vide sur 240 ; le canton est déduit du
  NPA (#131), connu alors sur les 959 (387 GE).
- Fixture : `tests/fixtures/naef_cases.json` (JSON) — 15 props des catalogues des 30.10, 03.11 et 08.11.2026, une par piège

### Clés du payload JSON

| Champ normalisé | Clé source |
|---|---|
| `external_id` | `no_dossier` |
| `external_url` | `link` |
| `title` | `intitule_plaquette`, sinon `type_designation_fr` |
| `price_chf` | `loyer_mensuel_brut` |
| `charges_chf` | `loyer_mensuel_brut − loyer_mensuel_net`, en centimes si brut > net ; sinon `None` |
| `property_type` | `type_code` : `APP` → `APARTMENT`, `MAI` → `HOUSE`, `PARC` → `PARKING`, `LCO` → `COMMERCIAL` |
| `nb_rooms` | `nb_pieces` |
| `surface_m2` | `surface_habitable` |
| `city` | `adresse_localite` |
| `canton` | `adresse_canton` (nom complet → abréviation via `utils.canton_code`) ; vide → déduit de `npa` et `adresse_localite` par `HttpScraper` (`CantonLookup`, #133) |
| `postal_code` | `npa` |
| `images` | `imgs` (liste ou valeurs d'un objet indexé, dans l'ordre du payload) |

### Pièges

- L'URL /page-N/ renvoie le même shell vide : ne jamais paginer par URL.
- /wp-json/naef/v1/api/properties-data répond 401 Invalid licence key — fausse piste.
- loyer_sur_demande == 'oui' → price_chf = None, surtout pas 0.
- `surface_habitable` contient un nombre nu (`"119"`, `"118.5"`) : accepté par
  `parse_surface`, contrairement à `nan`, `inf` et à la notation scientifique.
- `surface_habitable == 0` signifie une surface absente → `surface_m2 = None`,
  quel que soit le type de bien (parking, commerce ou dépôt notamment).
- imgs arrive en liste OU en objet indexé : `imgs[*] || imgs.*` avec
  `jmespath(...).getall()` extrait les URL dans l'ordre du payload (sans trier les
  clés). Une valeur absente ou vide donne un tuple vide.
- adresse_canton est le nom complet → utils.canton_code pour le VARCHAR(2).
- adresse_canton vide sur un quart des annonces (240/959 le 08.11.2026 : Renens VD,
  La Chaux-de-Fonds, Delémont, Versoix…) : le canton vient du NPA. 1290 est partagé
  entre Versoix (GE) et Chavannes-des-Bois (VD) : la localité tranche.
- Pas de rue dans le payload : slug du link ou fiche détail.

## Agence Immobilière Rodolphe Burger SA (`burger`)

- Accès : `GET www.burger-sa.ch/sitemap.php` (liste des fiches) puis `GET /fr/louer/<slug>` (une fiche = une annonce)
- Rendu : HTML statique ; le listing `/fr/louer` se charge en scroll infini (`infiniteScroll` sur `a.pagination__next`, lien jamais retiré, même sur les pages vides)
- Pagination : aucune côté scraper — le sitemap liste toutes les fiches avec leur `lastmod`
- Scraper : **HttpScraper** (sitemap XML + fiche HTML) : chaque poll lit le sitemap puis parse chaque fiche
- Débit : pas de Crawl-delay · 4 req/min mesurés au spike ; un poll = sitemap + une requête par fiche (28 le 21.10.2026), à étaler par le `RateLimiter` (architecture §11)
- Pas d'API ni de flux : ni RSS, ni JSON-LD ; les `api/…` du JS servent au formulaire de candidature
- Volume : 27 fiches /fr/louer/ au sitemap, identiques aux 27 du scroll, toutes dans le canton de Genève — relevé le 21.10.2026 ; 43 fiches au 08.11.2026
- Fixtures : `tests/fixtures/burger_sitemap.xml` (11 entrées `/fr/louer/` et une vente, sitemaps des 30.10 et 08.11.2026) et les 11 fiches correspondantes dans `tests/fixtures/burger/` (contact anonymisé) ; `burger_listing.html` (listing, spike du 22.09)

### Sélecteurs CSS (fiche détail)

| Champ | Sélecteur |
|---|---|
| URL / id | l'URL `<loc>` du sitemap, passée à `parse_fiche` |
| titre | `h1::text` |
| description | `div.prose` (texte) |
| loyer net | `//div[text()='Loyer']/following-sibling::div/text()` |
| charges | `//div[text()='Charges']/following-sibling::div/text()` ; affichées sans unité, donc ajoutées au loyer seulement s'il est mensuel (`price_chf`), et conservées dans `charges_chf` ; loyer annuel, au m² ou sur demande → `charges_chf = None` |
| étage | dans `h1` : « N(er\|e\|ème) étage » = N, « rez-de-chaussée » / « rdc » = 0, « N(er\|e) sous-sol » = -N ; autres cas = `None` |
| bloc de détails | `div.space-y-4.mt-6` — unique, absent des cartes « Ces biens pourraient vous intéresser » |
| rue / NPA ville | dans ce bloc, `div.text-base::text` (deux lignes séparées par `<br>`) : `address` = la rue ; la ligne `1205 Genève` donne `postal_code` et `city` |
| canton | absent de la fiche : déduit de `postal_code` et `city` par `HttpScraper` (`CantonLookup`, #133) |
| type / pièces / surface | dans ce bloc, chaque `div.text-sm` lu en entier contre sa grammaire : `<Type>[ <n> pièces]`, puis `[ENV. \| de ]<n> m2[ à <n> m2]` ; une ligne hors grammaire est loguée et ignorée |
| images | `div.swiper-slide img::attr(data-src)`, relatives à `https://www.burger-sa.ch/` |

### Pièges

- Trois formats de prix : CHF 3'500.— / mois, CHF 2'320.- + charges, Dès CHF 2'320.- + charges. Tiret cadratin autant que tiret simple.
- Les charges sont affichées séparément du loyer net : CHF 2'330.— + CHF 270.— donne `price_chf=260000`, `charges_chf=27000`. Sans loyer connu, ou avec un loyer à l'année ou au m² (CHF 24.— de charges pour CHF 260.— / m2 / année, unité inconnue), `charges_chf = None`.
- Loyers non mensuels sur les commerces (3 fiches sur 42 le 30.10.2026) : CHF 24'000.— / année (arcade), CHF 260.— / m2 / année (bureaux de 214 m²). `parse_monthly_rent` les ramène au mois : ÷ 12, et × surface pour un prix au m² ; sans surface, un prix au m² donne None, jamais un faux loyer.
- Surface absente, en fourchette (de 85 M2 à 100 M2) ou préfixée (ENV. 60 M2).
- Le slug peut mentir (35-pieces affiché 3.0 pièces) : faire foi au texte.
- external_id = URL complète : deux fiches partagent le préfixe …mont-bla.
- Hôte canonique www.burger-sa.ch (celui du sitemap et du `link rel=canonical`).
- Type de bien = première ligne des caractéristiques : Appartement, Studio, Maison ; Place ouverte, Place couverte (vue le 08.11.2026), Bureau, Arcade, Garage individuel, Dépôt, Commerce. Non filtré par le scraper.
- Le canton n'est écrit nulle part sur la fiche : seul le NPA le donne.
- « 0.0 pièces » affiché quand le nombre est inconnu : c'est `None`.
- Le 21.10.2026, une fiche sur six enchaînées a coupé la connexion sans réponse (`RemoteProtocolError`), puis répondu normalement : raison de plus pour espacer les requêtes ; une fiche en échec est loguée et ignorée, sans faire tomber le poll.

## Comptoir Immobilier (`comptoir`)

- Accès : `GET comptoir-immo.ch/location/?page=N` (toute l'offre, tous types et cantons), puis `GET` de chaque fiche détail
- Rendu : HTML statique
- Pagination : ?page=N, 24 par page — tri antichronologique par défaut
- Scraper : **HttpScraper** — la carte ne sert qu'à trouver l'URL de la fiche, tout le reste vient de la fiche
- Débit : Crawl-delay: 10 → rate_limit_rpm = 6, attendu avant **chaque** requête (catalogue et fiches) : un poll complet dure ≈ 1 h (16 pages + 375 fiches au 04.11.2026)
- Canal de repli : GET /?post_type=property_for_rent&feed=rss2 — 24 items, pubDate réelles. Le sitemap property_for_rent-*.xml est périmé (lastmod 2025-11)
- Volume : 375 biens en location au 04.11.2026 (Genève, Vaud, Valais)
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/comptoir_cases.html` — 10 cartes du catalogue, une par piège ; `tests/fixtures/comptoir/<slug>.html` — leurs 10 fiches des 04.11 et 08.11.2026, plus `279533.html`, fiche seule sans carte, lue directement par `parse_listing` (contact anonymisé ; scripts, styles, SVG et srcset retirés)

### Sélecteurs de la fiche

Le tableau « Détails » se lit **par libellé** : la valeur est la cellule qui suit le
`<th>` (`//th[starts-with(normalize-space(), 'Surface')]/following-sibling::td[1]`).
Une ligne absente → `None`.

| Champ | Lecture |
|---|---|
| lien de la fiche (catalogue) | `article.teaser--property_for_rent a:has(h2)::attr(href)` |
| `external_url` | `link[rel=canonical]::attr(href)` ; `external_id` = son dernier segment |
| `title` | `h1` ; `h1` présent mais vide → `Type de bien` (`Parking`) ; pas de `h1` du tout → fiche rejetée (refonte à voir dans l'audit) |
| `city`, `canton` | `h1 + h2` : `Yvorne, Vaud` → `Yvorne`, `canton_code("Vaud")` |
| `postal_code` | **non publié** → `None` |
| `price_chf` | `h1 ~ .heading-3` (`CHF 3'070.- / mois charges comprises`) → `parse_monthly_rent` |
| `property_type` | `Type de bien` → `parse_property_type` (`Dépôt, Entrepôt` → STORAGE) |
| `address` | `Adresse` (`Route de Lausanne 24 A, Yvorne`), avant la virgule |
| `charges_chf` | `Charges`, seulement si `Loyer` est mensuel |
| `nb_rooms` | `Pièces` (`5.5`) |
| `surface_m2` | `Surface habitable` ou `Surface utile` (`165 m²`) |
| `floor` | `Etage` (`7ème`, `1er`, `-1`, `Rez-de-chaussée`) |
| `description` | `div.rich-text` |
| `images` | `[data-gallery] img::attr(src)` — URL du proxy `external-images/?url=…`, telle quelle |

### Pièges

- propertyId (Apimo) absent des annonces sans photo : external_id = chemin de la fiche.
- Des fiches sont publiées **sans titre** : `<h1>` vide, `<title>` réduit à
  `- Comptoir Immobilier`, et le slug de l'URL devient le numéro de la fiche
  (`…/geneve-geneve/921110/`). 5 parkings le 08.11.2026 ; le reste du tableau est complet.
  Le titre devient alors le `Type de bien`. Seul un `<h1>` **vide** est rattrapé : une
  fiche sans `<h1>` reste rejetée, pour qu'une refonte du gabarit se voie dans l'audit.
- Aucun NPA sur la fiche : l'adresse est « rue, ville » et la carte n'a que
  `data-lat` / `data-lng`. `postal_code` reste `None` ; le canton vient de l'en-tête.
- Le titre contredit parfois la métadonnée : le tableau « Détails » fait foi (« duplex en attique », `Etage` : `2ème`).
- La carte n'affiche pas toujours la surface alors que la fiche la donne (`cabinet-bureau-remettre-au-centre-de-sion` : rien sur la carte, `Surface utile` 120 m² sur la fiche) : sans elle, un loyer au m² serait perdu.
- Le libellé de surface varie : `Surface habitable` (logements), `Surface utile` (bureaux, arcades).
- Prix sur demande → price_chf = None.
- Loyer affiché `CHF 0.- / mois` (parking 279533 à Satigny, 08.11.2026) : pas de prix
  publié → `price_chf = None`, jamais 0. Ces fiches ont aussi un tableau avec une ligne
  `Téléphone` en plus de `Votre contact` : les deux sont anonymisés dans les fixtures.
- Loyers non mensuels (30.10.2026) : CHF 18'720.- / an (3 cartes sur 374) et CHF 600.- / m² / an (104 cartes, surtout des bureaux). `parse_monthly_rent` divise par 12 et multiplie par la surface de la fiche ; sans surface, None.
- `Charges` n'a pas d'unité : annuelles quand le loyer est `/ an` (`CHF 6'720.-` à Monthey), au m² quand il est `/ m² / an`. Elles ne sont gardées que sur un loyer mensuel connu (`CHF 0.- / mois` → ni prix, ni charges) ; le prix de l'en-tête est déjà charges comprises.
- Les fiches disparaissent vite : 2 des 7 cartes du 30.10.2026 renvoyaient « Page Not Found » le 04.11.2026.
- Le HTML ferme les `<th>` par `</td>` : parsel (lxml) le répare, la lecture par libellé fonctionne.
- Canton écrit canton-de-geneve dans les URL, Genève dans l'en-tête de la fiche.
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
- L'API mélange location et vente, et tous les cantons : tout remonter et étiqueter (`listing_type`, `canton`), ne rien écarter.

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
- ⚠️ Volume : 1 fiches distinctes — relevé le 22.09.2026 07:29 UTC, **invalidé** (voir note
  en tête de document) ; la fixture en contient 4 distinctes
- Flux : +0 depuis 22.09.2026 07:25
- Fixture : `tests/fixtures/zimmo_listing.html` (HTML)

### Sélecteurs CSS

| Champ | Sélecteur |
|---|---|
| conteneur | `div.cell.block.item` |
| lien | `div.cell.block.item a.title::attr(href)` |
| image | `div.cell.block.item div.flickity-carousel-cell-block img::attr(src)` |

### Pièges

- /api/v1/map/ existe dans le code mais répond 404 en GET.
- Pas de `div.objects-list` dans le HTML réel : le conteneur est `div.cell.block.item` —
  un bare `div.item` attrape aussi les cellules d'icônes (surface, prix…) qui portent la
  même classe.
- Toutes les fiches partagent le même chemin `fiche-location.html` : seule la query
  string `?ref=…` les distingue. Le dédoublonnage générique (qui tronque la query
  string) réduisait le volume mesuré à 1 fiche au lieu de 4 — `count.keep_query=True`
  corrige ça pour cette source.

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
