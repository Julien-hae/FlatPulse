# Reconnaître le site d'une régie

But : remplir l'entrée de la régie dans `docs/spike-agencies.md` avec des faits
**observés sur le site**, datés. Tout ce qui suit dans le skill (forme, fixtures, tests,
débit) se lit dans cette entrée.

## Se conduire chez la régie

Un ban, c'est une source perdue, et le projet tient à scraper proprement.

- Peu de requêtes, espacées. `scripts/recon.py` attend 10 s entre deux (le plus long
  Crawl-delay du parc), ou le Crawl-delay du site s'il est plus long. Garder ce rythme
  pour toute requête faite à la main.
- `robots.txt` fait foi : une URL interdite ne se demande pas. Un `robots.txt` refusé
  (401, 403) arrête la reconnaissance.
- On ne contourne rien : ni challenge Cloudflare, ni empreinte TLS, ni connexion. Le
  précédent est Grange, écartée pour cette raison.
- Pas de navigateur headless dans le scraper (aucune régie n'en a eu besoin,
  architecture §11.4). Un navigateur peut servir à **regarder** quelles requêtes la page
  fait ; le scraper, lui, lira l'endpoint trouvé.
- Même User-Agent que les scrapers (celui d'`httpx`) : on observe ce qu'ils verront.

## Premier passage

```bash
python .claude/skills/nouveau-scraper/scripts/recon.py \
    "https://www.regie.ch/louer" "https://www.regie.ch/louer?page=2"
```

Une requête sur `robots.txt`, puis une par URL. Donner la page 2 supposée avec la
page 1 : le script dit si elle apporte autre chose (voir « Pagination »). `--conditional`
redemande chaque page avec ses validateurs pour savoir si un `304` est servi.

Le rapport donne : Crawl-delay et sitemaps, statut, temps de réponse, poids, `ETag` /
`Last-Modified`, puis où sont les annonces — listes d'objets d'un JSON avec leurs clés,
JSON embarqué (`__NEXT_DATA__`, `drupal-settings-json`), JSON-LD, flux RSS, blocs
répétés portant un lien et un prix, liens de pagination.

## Trouver le meilleur accès

Par ordre de préférence, parce que chaque cran coûte des requêtes et de la fragilité :

1. **Un endpoint JSON qui rend tout le parc** (Naef) : un GET par poll, des champs typés.
2. **Un état hydraté dans la page** (`script#__NEXT_DATA__`, Bory) : du JSON, sans
   endpoint à deviner — mais vérifier qu'il porte tout le catalogue et pas la première
   page seulement (le compteur déclaré contre le nombre d'objets).
3. **Une API JSON paginée** (Rosset).
4. **Un sitemap complet qui nomme les fiches** (Burger) : pas de pagination à suivre.
5. **Le catalogue HTML**, paginé ou non, puis les fiches si les cartes ne suffisent pas
   (Comptoir).

Quand le rapport dit « aucun prix dans le DOM », les annonces arrivent par JavaScript.
Chercher dans l'ordre : le JSON embarqué que le rapport liste, les `fetch(`, `ajaxUrl`
ou `/api/` des scripts de la page, `/wp-json/` sur un WordPress, puis l'onglet réseau
d'un navigateur. Noter les fausses pistes dans « Pièges » : elles coûteront au suivant
(Naef : `/wp-json/naef/v1/…` répond 401).

Noter aussi un **canal de repli** s'il y en a un (flux RSS, sitemap, HTML de la liste).

## Ce que l'entrée doit établir

**Pagination.** Ne jamais la supposer. `?page=2` peut rendre les mêmes cartes (Moser
Vernet), `/page-2/` un shell vide (Naef), et un lien « suivant » ne jamais disparaître
(Burger). Vérifier trois choses : la page 2 diffère de la page 1, où s'arrête la suite
(nombre de pages annoncé, page vide, curseur nul), et que le total compté égale le total
que la source déclare.

**Identifiant.** Ce qui distingue deux annonces et ne bouge pas d'un poll à l'autre : un
numéro de dossier, sinon l'URL complète. Regarder deux fiches voisines : si elles
partagent le chemin et ne diffèrent que par la query string (Zimmo, `?ref=`), ou
partagent un préfixe de slug (Burger), le dire — une dédup qui tronque fait disparaître
des annonces.

**Champs.** Pour chaque champ de `Listing` (`common/models.py`), où il se lit : clé JSON
ou sélecteur, avec un exemple de valeur brute. Écrire aussi ce que la régie **ne publie
pas** (« `postal_code` : non publié ») : c'est un `None` légitime, pas un oubli, et
l'audit en direct s'y référera.

**Périmètre de ce que rend l'accès.** Location et vente mélangées ? Tous cantons ?
Parkings et commerces ? Les paramètres de filtre de l'URL sont-ils vraiment appliqués
(Rosset et Bernard Nicod les ignorent) ? Le scraper remontera tout et étiquettera ; il
faut savoir ce que « tout » contient.

**Formats.** Relever tels quels les prix (mensuel, `/ an`, `/ m² / an`, « sur demande »,
`CHF 0.-`, charges à part ou comprises), les pièces (`3½`, `3.5`, `0.0`), les surfaces
(fourchette, « env. »), les étages, les libellés de type de bien. Chaque format qui
surprend est un piège, donc un cas de fixture.

**Volume.** Le nombre de fiches **distinctes**, pagination suivie et dédupliquée, pas
les cartes d'une page — et la date du relevé. Le nombre d'annonces genevoises si la
source permet de le dire. Un volume faible se met en regard du coût d'un scraper : c'est
une information pour l'utilisateur, à donner avant de coder.

**Poids.** Le poids d'un poll, multiplié par sa fréquence. Une page lourde relue toutes
les 90 s pèse des Go par jour (Moser Vernet : 2,9 Mo) : dire si un GET conditionnel est
honoré (`--conditional`).

## Mesurer le débit

Le `rate_limit_rpm` d'une source est une valeur **constatée**, jamais choisie :

- `robots.txt` donne un Crawl-delay : `rate_limit_rpm = 60 / Crawl-delay`, arrondi en
  dessous (Comptoir : 10 s → 6).
- Pas de Crawl-delay : le débit retenu est celui auquel la reconnaissance a réellement
  lu le site sans erreur ni coupure, pas plus. Écrire l'échantillon (« 6 req/min tenus
  sur 12 fiches le JJ.MM.AAAA ») et qu'il reste à confirmer au premier audit complet.
  Une coupure de connexion ou un 429 pendant la reconnaissance est un signal : baisser,
  et le noter dans « Pièges » (Burger : une fiche sur six a coupé la connexion).

Pour un `CatalogueScraper`, noter aussi la fraîcheur côté serveur si elle se voit
(`cache-control`, Naef : cache de 180 s) : inutile de poller plus vite que le cache.

## Conclure

- **Scrapable** : écrire l'entrée, proposer la forme (étape 2 du skill).
- **À trancher** : l'accès n'est pas identifié. Écrire ce qui a été essayé.
- **Écartée** : anti-robot, connexion requise, ou volume qui ne vaut pas un scraper.
  C'est à l'utilisateur de trancher sur le volume ; donner les chiffres.

## Écrire l'entrée

Dans `docs/spike-agencies.md`, sous le titre de son statut, au format des entrées
voisines :

```markdown
## Nom de la régie (`slug`)

- Accès : `GET www.regie.ch/chemin` (ce que rend la requête)
- Rendu : HTML statique | JSON | état hydraté — et le CMS s'il se reconnaît
- Pagination : aucune — tout le parc en un GET | ?page=N, 24 par page, dernière page annoncée par …
- Scraper : **CatalogueScraper** | **FicheScraper** (index : …, puis une fiche par annonce)
- Débit : Crawl-delay: 10 → rate_limit_rpm = 6 | pas de Crawl-delay · 6 req/min tenus sur 12 requêtes le JJ.MM.AAAA, à confirmer au premier audit
- Canal de repli : …
- Volume : 165 fiches distinctes, dont 105 dans le canton de Genève — relevé le JJ.MM.AAAA
- Fixture : (à l'étape 4)

### Clés du payload JSON

| Champ normalisé | Clé source |
|---|---|
| `external_id` | `id` |
| `price_chf` | `price` (`CHF 1’850/mois (+ CHF 175 charges)`) |
| `postal_code` | **non publié** |

### Pièges

- Un fait observé par ligne, avec sa date et son exemple.
```

Le tableau s'intitule « Sélecteurs CSS » pour une source HTML. Le `slug` est court, en
minuscules, sans accent ; il deviendra le nom du module, du test et de la fixture.

Ajouter ou mettre à jour la ligne de la régie dans le tableau de tête du spike et dans
celui de `docs/architecture.md` §6, puis dater le relevé dans l'en-tête du spike.

Commit : `docs(spike): record the <régie> access, pace and field mapping`.
