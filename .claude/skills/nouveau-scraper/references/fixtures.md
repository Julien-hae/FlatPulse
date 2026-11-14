# Figer les fixtures

Un test de scraper tape sur une fixture figée, jamais sur le réseau. La fixture n'est
pas une copie du catalogue : ce sont **des cas nommés**, chacun une annonce réelle et
non retouchée, choisie parce qu'elle porte un piège (architecture §8).

## Quels cas choisir

Parcourir le catalogue réel avec la section « Pièges » du spike sous les yeux, et retenir
une annonce par ligne de cette liste que la source présente :

- un appartement genevois **complet** — le cas nominal, comparé champ par champ ;
- un **prix sur demande** (et un loyer affiché à zéro si la source en publie) ;
- un bien de chaque **type** publié : parking, commerce (bureau, arcade), dépôt, maison ;
- une annonce **hors de Genève** (elle doit sortir, avec son canton) ;
- une annonce dont le **canton n'est pas écrit**, s'il se déduit du NPA ;
- un **loyer non mensuel** (`/ an`, `/ m² / an`) et un loyer au m² sans surface ;
- une **valeur absente** que la source écrit à sa façon (`0`, `0.0 pièces`, champ vide) ;
- deux annonces que l'**identifiant** doit distinguer (même préfixe d'URL, même chemin) ;
- chaque autre piège du spike : fourchette de surface, titre vide, images en liste ou
  en objet, libellé de type inconnu de `utils.py`…

Dix à quinze cas suffisent en général. Un cas que le catalogue du jour ne présente pas
ne s'invente pas dans la fixture : il se fabrique **dans le test**, en modifiant en
mémoire un cas réel (voir `references/tests.md`).

Pour un index (sitemap, catalogue), garder aussi **une entrée hors périmètre** (une
vente) : elle prouve que le scraper ne la demande pas.

## Où ranger, selon la forme

| Forme | Fichiers | Contenu |
|---|---|---|
| `CatalogueScraper`, JSON | `tests/fixtures/<slug>_cases.json` | L'enveloppe du payload, avec les seuls objets retenus, inchangés |
| `CatalogueScraper`, HTML | `tests/fixtures/<slug>_cases.html` | Les blocs d'annonce retenus, extraits tels quels, dans un document minimal |
| `FicheScraper` | `tests/fixtures/<slug>_sitemap.xml` ou `<slug>_cases.html` | L'index réduit aux entrées des fiches retenues (+ l'entrée hors périmètre) |
| | `tests/fixtures/<slug>/<id>.html` | Une fiche par fichier, nommée par ce qui permet au test de la servir depuis son URL |

`fixture_name` de la classe de test est l'index (ou le catalogue). Chaque fichier reste
**sous 100 Ko**.

Le dossier `tests/fixtures/` garde des captures du spike du 22.09.2026
(`rosset_properties.json`, `bory_next_data.json`, `*_listing.html`…). Ce sont des
instantanés de catalogue, pas des cas choisis, et le site a pu changer depuis : repartir
d'un relevé du jour. Si l'ancienne capture ne sert plus à aucun test, le signaler à
l'utilisateur plutôt que de la supprimer d'office.

## Relever

Toujours au débit du spike, une requête à la fois.

**JSON.** Un seul GET du payload, enregistré hors du dépôt (dossier temporaire), puis
on ne garde que les objets choisis, sans toucher à leur contenu :

```python
import json
from pathlib import Path

payload = json.loads(Path("/tmp/regie.json").read_text(encoding="utf-8"))
wanted = {"261036.6001", "CP.19643"}
payload["props"] = [prop for prop in payload["props"] if prop["no_dossier"] in wanted]
Path("tests/fixtures/<slug>_cases.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
)
```

L'enveloppe (clé de liste, compteurs, pagination) reste : le scraper la lit. Les objets
gardent toutes leurs clés, même celles que le scraper ignore aujourd'hui.

**Fiches HTML.** Une par appel, en laissant passer l'intervalle du débit entre deux :

```bash
python .claude/skills/nouveau-scraper/scripts/trim_fixture.py \
    "https://www.regie.ch/louer/carouge-appartement-3-pieces" \
    tests/fixtures/<slug>/carouge-appartement-3-pieces.html
```

Le script retire ce qu'aucun scraper ne lit (scripts, styles, SVG, `srcset`) mais garde
les scripts de données (`application/json`, `application/ld+json`, `__NEXT_DATA__`),
remplace les e-mails par `gerance@example.com`, écrit en tête d'où et quand la page a
été relevée, et annonce le poids. Il refuse d'écraser une fixture existante. Une page
déjà enregistrée se passe en fichier, avec `--url` et `--date`.

Encore trop lourde : retirer à la main ce que le scraper ne lit pas (menus, pied de
page, formulaires, « ces biens pourraient vous intéresser »). Jamais un morceau de
l'annonce — et relancer les tests après chaque coupe, un sélecteur dépend parfois d'un
voisin.

**Index.** Recopier telles quelles les entrées (`<url>` du sitemap, cartes du
catalogue) des fiches retenues dans un document minimal, avec un commentaire qui dit
d'où elles viennent et de quand. Sans pagination, sauf si la pagination est un cas.

## Anonymiser le contact, pas l'annonce

Les fiches nomment un gérant, son téléphone, son e-mail : ce sont des données de
personnes, elles ne se committent pas.

- e-mail → `gerance@example.com` (fait par le script) ;
- nom → `Contact anonymisé` ;
- téléphone → retiré ou remplacé par un numéro manifestement faux.

Le script liste les téléphones qu'il repère ; relire quand même le bloc contact. Tout le
reste de l'annonce (titre, adresse du bien, prix, texte) est publié par la régie et
reste tel quel : c'est ce que le test vérifie.

## Deux vérifications avant d'écrire les tests

**URLs valides.** Une annonce dont l'URL est cassée — gabarit non rempli comme
`/location/%property_canton%/…` — n'est pas un cas de test : `Listing` l'accepte (elle
commence par `https://`), et le test graverait une URL que personne ne peut ouvrir. La
retirer de la fixture, noter le phénomène dans « Pièges ».

**NPA connus de l'extrait swisstopo.** Les tests de scrapers déduisent le canton avec
`tests.helpers.CANTON_LOOKUP`, construit sur `tests/fixtures/swisstopo_localities.csv`,
qui ne contient que les NPA des fixtures existantes. Un NPA nouveau y est inconnu : le
canton sort `None` avec un WARNING `Unknown postal code`, et le test échoue sans que le
scraper soit en cause. Ajouter les lignes de l'annuaire officiel pour chaque NPA
nouveau :

```python
import io
import zipfile

import httpx

from flatpulse.postal_code_table import SWISSTOPO_LOCALITIES_URL

wanted = {"1227", "1211"}
response = httpx.get(SWISSTOPO_LOCALITIES_URL, timeout=30, follow_redirects=True)
with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
    [name] = [item for item in archive.namelist() if item.endswith(".csv")]
    for line in archive.read(name).decode("utf-8-sig").splitlines():
        if line.split(";")[1] in wanted:
            print(line)
```

Copier **toutes** les lignes d'un NPA, inchangées, à leur place dans l'ordre des NPA.
Toutes, parce qu'un NPA peut couvrir plusieurs localités et deux cantons (1290 : Versoix
GE, Chavannes-des-Bois VD) : n'en copier qu'une ferait croire au lookup de test que le
code n'a qu'un canton, à l'inverse de la production.

## Écrire où est la fixture

La ligne « Fixture : » de l'entrée du spike dit le fichier, le nombre de cas, les dates
des relevés et ce qui a été retiré ou anonymisé. La docstring de la classe de test le
redit en une phrase.
