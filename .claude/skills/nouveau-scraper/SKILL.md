---
name: nouveau-scraper
description: Mettre en place une nouvelle régie immobilière dans FlatPulse, de bout en bout — reconnaissance du site et entrée du spike, story, fixtures de cas réels, tests rouges, classe de scraper, audit en direct, enregistrement de la source et documentation. À utiliser dès qu'il est question d'ajouter une régie ou une source (Rosset, Bory, Moser Vernet, Bernard Nicod, Bordier…), d'implémenter une story de scraper, de savoir si le site d'une régie est scrapable, ou de réparer un scraper dont la régie a changé le site — même si le mot « scraper » n'est pas prononcé.
argument-hint: <régie ou slug>
---

# Mettre en place une nouvelle régie

Une régie = une classe dans `scrapers/sources/`, sa fixture de cas réels, son test, son
entrée dans `docs/spike-agencies.md` et sa ligne dans l'audit en direct. Rien d'existant
n'est modifié, sauf les endroits où une source s'enregistre (Open/Closed).

Le travail suit toujours le même fil. Chaque étape produit quelque chose dont la
suivante a besoin : la sauter, c'est coder sur une supposition.

| # | Étape | Ce qui en sort | À lire |
|---|---|---|---|
| 0 | Situer la régie | Ce qui manque : spike, story, forme | — |
| 1 | Reconnaître le site | Entrée complète dans `docs/spike-agencies.md` | `references/reconnaissance.md` |
| 2 | Choisir la forme | `CatalogueScraper` ou `FicheScraper`, ou un arrêt | ci-dessous |
| 3 | Avoir une story | Issue GitHub avec critères et tests | `references/story.md` |
| 4 | Figer les fixtures | Cas nommés dans `tests/fixtures/` | `references/fixtures.md` |
| 5 | Écrire les tests, rouges | `tests/unit/test_<slug>.py` | `references/tests.md` |
| 6 | Implémenter | `src/flatpulse/scrapers/sources/<slug>.py` | `references/implementation.md` |
| 7 | Enregistrer et auditer en direct | Source dans l'audit, seuils, run consigné | `references/audit-live.md` |
| 8 | Documenter, vérifier, clore | Docs à jour, un commit, issue fermée | ci-dessous |

Lire la fiche de référence d'une étape au moment d'y entrer, pas toutes d'avance.

## 0. Situer la régie

Trois lectures, avant tout :

1. **Son entrée dans `docs/spike-agencies.md`** : sa ligne du tableau de tête, puis sa
   section, titrée du nom de la régie suivi de son slug. Son statut décide de la suite :
   - *écartée* ou *à trancher* : il n'y a pas de scraper à écrire. Le dire, avec la
     raison du spike. Une régie à trancher demande d'abord une reconnaissance (étape 1) ;
     une régie écartée ne se rouvre que si l'utilisateur le demande.
   - *pas d'entrée*, ou une entrée avec « à mesurer », « à confirmer », un mapping de
     trois lignes : étape 1.
   - entrée complète : vérifier sa date. Un site change ; deux requêtes de
     `scripts/recon.py` disent si l'accès décrit répond encore.
2. **Sa story GitHub.** Chercher dans les issues par le nom de la régie. Elle porte les
   critères d'acceptation et la spec des tests ; rien ne se code sans elle (étape 3 si
   elle manque).
3. **`docs/architecture.md` §5.1, §6.1 et §11** : le contrat des scrapers, les pièges
   transverses, les écarts connus entre stories, spike et code.

Quand la story et le spike se contredisent sur la régie, **le spike gagne** : il est
mesuré sur le site réel. Signaler l'écart, ne pas coder au hasard.

## 1. Reconnaître le site

Seulement si l'entrée du spike manque ou a des trous. `scripts/recon.py` fait le premier
passage poliment (robots.txt, débit, poids, JSON embarqué, pagination fantôme) ;
`references/reconnaissance.md` dit quoi chercher ensuite et donne le gabarit de l'entrée.

La reconnaissance est un travail à part entière : son résultat se committe seul
(`docs(spike): …`), avant le scraper, parce que la story s'écrit à partir de lui.

## 2. Choisir la forme

`scrapers/base.py` offre deux formes, et une source prend l'une des deux :

| Le site publie… | Forme | La régie implémente | Requêtes par poll |
|---|---|---|---|
| un seul document portant toutes les annonces, avec tous leurs champs (payload JSON, page unique) | `CatalogueScraper` | `listing_nodes(page)`, `parse_listing(node)` | 1 |
| un index (sitemap, catalogue paginé) qui nomme des fiches, chaque fiche étant une annonce | `FicheScraper` | `fiche_urls(client)`, `parse_fiche(node, url)` | index + 1 par fiche |

Les cartes d'un catalogue HTML portent rarement tous les champs (adresse, description,
charges) : si la fiche en sait plus que la carte, c'est un `FicheScraper`, la carte ne
servant qu'à trouver l'URL (Comptoir).

Calculer tout de suite la durée d'un poll : `requêtes × 60 / rate_limit_rpm`. Au-delà
des 3 minutes visées pour une alerte, l'écrire dans la story et dans le spike — c'est
connu pour Burger et Comptoir (architecture §11.9 et §11.10), ça ne bloque pas le
scraper, mais ça ne se découvre pas en production.

### Quand la régie n'entre dans aucune forme : s'arrêter et le dire

Ces cas ne se règlent pas dans la classe de la régie. Chacun demande sa propre story
sur le socle, à faire **avant** le scraper ; le rôle du skill est de le constater tôt
et de le signaler à l'utilisateur avec ce que le spike a montré.

- **Catalogue paginé dont chaque page porte plusieurs annonces complètes** (API
  `?page=N`, curseur) : ni l'une ni l'autre forme. Ne pas surcharger `fetch_listings`
  ni détourner `FicheScraper` : c'est une troisième forme, à poser dans `base.py` avec
  ses tests dans `tests/unit/test_scrapers.py`.
- **Requête autre qu'un GET simple** (POST, en-têtes, `If-None-Match` sur une page
  lourde) : `HttpScraper._get()` ne sait faire qu'un GET nu. L'étendre est une story
  du socle, pas un `client.get()` glissé dans la source, qui échapperait au limiteur.
- **Champ que `Listing` n'a pas** (location ou vente, disponibilité…) : modèle, schéma
  SQL et tests bougent ensemble, dans leur story.
- **Protection anti-robot, connexion, navigateur nécessaire** : on ne contourne pas.
  La régie passe à « écartée » ou « à trancher » dans le spike.

## 3. Avoir une story

Pas de story pour la régie : en rédiger une au format de la maison à partir du spike,
la montrer, et ne créer l'issue qu'avec l'accord de l'utilisateur
(`references/story.md`). Avec une story : la lire en entier, tests compris.

## 4. Figer les fixtures

Des cas réels, non retouchés, un par piège du spike, chaque fichier sous 100 Ko :
`references/fixtures.md` (quels cas choisir, où les ranger selon la forme, comment
alléger et anonymiser avec `scripts/trim_fixture.py`, et le piège des NPA absents de
l'extrait swisstopo).

## 5. Écrire les tests, rouges

`references/tests.md` donne le squelette par forme et la liste des cas attendus. Les
contrats hérités de `ScraperContractMixin` ne suffisent pas : ils passent sur un scraper
qui ne remplit aucun champ. Chaque cas compare des **valeurs exactes**.

Lancer et lire l'échec avant d'implémenter : rouge parce que le comportement manque,
pas à cause d'un `ImportError` ou d'une fixture introuvable.

## 6. Implémenter

`references/implementation.md` : squelette par forme, règle champ par champ, inventaire
de `common/utils.py`. L'essentiel tient en cinq phrases :

- Le parsing suisse existe déjà dans `utils.py`. Un format qu'il ne lit pas s'ajoute
  là, avec son test dans `tests/unit/test_utils.py`, jamais dans la source.
- Montants en centimes, loyer **mensuel charges comprises**. Absent → `None`, jamais
  `0` ni `""` : `Listing` refuse les deux, et c'est voulu.
- Tout remonter, tout étiqueter (`property_type`, `canton`, `postal_code`), ne rien
  écarter. Le canton absent n'est pas déduit dans la source : `HttpScraper` le fait.
- Chaque requête passe par `self._get(client, url)`. C'est ce qui tient le débit.
- Ne redéfinir ni `fetch_listings`, ni `run`, ni `_get`, ni `_build_or_skip`.

Puis :

```bash
python -m unittest tests.unit.test_<slug> -v
python -m unittest discover tests/
ruff format . && ruff check .
mypy src/
```

## 7. Enregistrer et auditer en direct

Les fixtures montrent des cas choisis ; seul le site montre toute l'offre.
`references/audit-live.md` : où la source s'enregistre, comment lancer
`scripts/audit_source.py` sur elle seule, lire le résultat, poser ses seuils
`MIN_FILL_RATE` et consigner le run dans `docs/live-audit.md`.

Chaque annonce ignorée et chaque libellé inconnu que l'audit remonte est un cas qui
manquait : il entre dans la fixture, avec son test rouge, puis se corrige.

Si l'audit ne peut pas tourner (réseau fermé vers la régie), le dire tel quel dans le
résumé. Des seuils inventés sont pires que pas de seuils.

## 8. Documenter, vérifier, clore

Mettre à jour, dans le même commit que le code :

- `docs/spike-agencies.md` : la section de la régie (accès tel qu'implémenté, ligne
  « Fixture », tableau des clés ou sélecteurs **réellement lus**, pièges rencontrés en
  route) et sa ligne du tableau de tête (statut, forme, volume).
- `docs/architecture.md` §6 : la ligne du tableau des sources.
- `docs/live-audit.md` : le run de l'étape 7.
- `README.md`, « État du projet » : le nombre et le nom des régies en service.
- `docs/architecture.md` §11 si un écart entre story, spike et code est apparu.

Puis la vérification du câblage, qui regarde ce qu'aucun test ne voit (source non
enregistrée, fixture trop lourde, requête hors limiteur, débit encore « à mesurer ») :

```bash
python .claude/skills/nouveau-scraper/scripts/check_scraper.py <slug>
```

Un ✘ se corrige ; un ⚠ se dit dans le résumé. Ensuite la Definition of Done (#81) :
suite verte, `ruff` et `mypy` propres, aucun `print()`, `TODO`, `FIXME` ni `pass`
temporaire, docstrings et types sur tout ce qui est public.

**Un commit atomique** pour la story, en anglais, au format du dépôt :
`feat(scraping): implement NaefScraper with JSON payload parsing`. Si le travail passe
par une PR, son titre suit la même convention (la CI le vérifie) et son corps ferme
l'issue (`Closes #N`). L'issue se ferme avec un résumé : ce qui est extrait, ce qui ne
l'est pas et pourquoi, la durée d'un poll, les ⚠ restants.

Ce qui déborde de la story (un format ajouté à `utils.py` mis à part) ne s'ajoute pas
au diff : le signaler, proposer une story.

## Quand une régie déjà en service casse

Même fil, plus court : la source a changé, pas le projet.

1. Reproduire sur le site (`scripts/recon.py`, une fiche) et dire ce qui a changé.
2. Figer le cas nouveau **à côté** des anciens : une fixture garde l'histoire des
   formats rencontrés, on n'écrase pas un cas qui passe.
3. Test rouge sur ce cas, correction, suite verte.
4. Mettre à jour « Pièges » et les sélecteurs dans `docs/spike-agencies.md`, relancer
   `scripts/audit_source.py`, consigner le run.

Commit : `fix(scraping): …`. Un test né d'un bug va dans `tests/unit/`, comme les autres.
