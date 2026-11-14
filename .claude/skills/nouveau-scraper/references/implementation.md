# Implémenter la classe

Fichier : `src/flatpulse/scrapers/sources/<slug>.py`, une classe `<Régie>Scraper`. Elle
ne contient que ce qui est propre au site : où sont les annonces, où est chaque champ.
Le reste est déjà écrit — débit, boucle, annonces invalides, canton manquant dans
`scrapers/base.py` ; formats suisses dans `common/utils.py`.

## Sommaire

- Squelette `CatalogueScraper`
- Squelette `FicheScraper`
- Lire du JSON avec parsel
- Champ par champ
- Ce que `utils.py` sait déjà lire
- Ce qui ne s'écrit pas dans une source

## Squelette — `CatalogueScraper`

`base_url` est le document unique. `listing_nodes` rend un nœud par annonce,
`parse_listing` en fait un `Listing`.

```python
"""Scraper for Régie Exemple, which exposes its whole catalogue as one JSON payload."""

from parsel import Selector

from flatpulse.common.models import Listing
from flatpulse.common.utils import (
    canton_code,
    parse_monthly_rent,
    parse_property_type,
    parse_rooms,
    parse_surface,
)
from flatpulse.scrapers.base import CatalogueScraper


class ExempleScraper(CatalogueScraper):
    """Scrape every rental listing of the Régie Exemple `biens` endpoint."""

    base_url = "https://www.regie-exemple.ch/api/biens?transaction=location"
    slug = "exemple"

    def listing_nodes(self, page: Selector) -> list[Selector]:
        """Return one JSON node per property of the payload."""
        return list(page.jmespath("biens[*]"))

    def parse_listing(self, node: Selector) -> Listing:
        """Extract the listing fields from a property node."""
        surface_m2 = parse_surface(self._text(node, "surface")) or None
        return Listing(
            external_id=self._text(node, "reference") or "",
            external_url=self._text(node, "url") or "",
            title=self._text(node, "titre") or "",
            property_type=parse_property_type(self._text(node, "type")),
            price_chf=parse_monthly_rent(self._text(node, "loyer"), surface_m2),
            nb_rooms=parse_rooms(self._text(node, "pieces")) or None,
            surface_m2=surface_m2,
            postal_code=self._text(node, "npa"),
            city=self._text(node, "localite"),
            canton=canton_code(self._text(node, "canton")),
            images=tuple(node.jmespath("photos[*]").getall()),
        )

    @staticmethod
    def _text(node: Selector, key: str) -> str | None:
        """Return the value at `key` as a string, or None when absent or empty."""
        value = node.jmespath(key).get()
        return str(value) if value not in (None, "") else None
```

## Squelette — `FicheScraper`

`base_url` est l'index. `fiche_urls` rend les URL des fiches, en passant par
`self._get()` ; `parse_fiche` reçoit la page d'une fiche et l'URL d'où elle vient.

```python
"""Scraper for Régie Exemple: the sitemap lists every fiche, each fiche is a listing."""

from urllib.parse import urljoin

import httpx
from parsel import Selector, SelectorList

from flatpulse.common.models import Listing
from flatpulse.common.utils import (
    parse_charges,
    parse_floor,
    parse_monthly_rent,
    parse_property_type,
    parse_rooms,
    parse_surface,
)
from flatpulse.scrapers.base import FicheScraper


class ExempleScraper(FicheScraper):
    """Scrape every rental fiche listed in Régie Exemple's sitemap."""

    base_url = "https://www.regie-exemple.ch/sitemap.xml"
    slug = "exemple"

    async def fiche_urls(self, client: httpx.AsyncClient) -> list[str]:
        """The rental fiches listed in the sitemap."""
        sitemap = Selector(text=(await self._get(client, self.base_url)).text)
        return sitemap.xpath(
            "//*[local-name()='loc'][contains(text(), '/louer/')]/text()"
        ).getall()

    def parse_fiche(self, node: Selector, url: str) -> Listing:
        """Extract the listing from a fiche page; `url`, from the sitemap, is its id."""
        surface_m2 = parse_surface(self._detail(node, "Surface"))
        rent = self._detail(node, "Loyer")
        price_chf = parse_monthly_rent(rent, surface_m2)
        charges_chf = parse_charges(self._detail(node, "Charges"), rent, price_chf)
        # The fiche shows the rent without charges: price_chf includes them.
        if price_chf is not None and charges_chf is not None:
            price_chf += charges_chf
        postal_code, _, city = (self._detail(node, "Localité") or "").partition(" ")
        return Listing(
            external_id=url,
            external_url=url,
            title=self._text(node.css("h1")) or "",
            property_type=parse_property_type(self._detail(node, "Type de bien")),
            price_chf=price_chf,
            charges_chf=charges_chf,
            nb_rooms=parse_rooms(self._detail(node, "Pièces")),
            surface_m2=surface_m2,
            floor=parse_floor(self._detail(node, "Etage")),
            address=self._detail(node, "Adresse"),
            postal_code=postal_code or None,
            city=city or None,
            description=self._text(node.css("div.description")),
            images=tuple(
                urljoin(url, src)
                for src in node.css("div.galerie img::attr(src)").getall()
            ),
        )

    def _detail(self, node: Selector, label: str) -> str | None:
        """Value of the details row whose header starts with `label`, None without one."""
        return self._text(
            node.xpath(
                "//th[starts-with(normalize-space(), $label)]/following-sibling::td[1]",
                label=label,
            )
        )

    @staticmethod
    def _text(nodes: SelectorList[Selector]) -> str | None:
        """Whitespace-normalised text of the first node, None when absent or empty."""
        return nodes.xpath("normalize-space()").get() or None
```

Un index paginé lit ses pages une à une dans `fiche_urls`, toujours par `self._get()`
(voir `ComptoirScraper.fiche_urls` et `nb_pages`). La boucle sur les fiches, elle, est
dans `FicheScraper.fetch_listings` : une fiche qui ne se télécharge pas y est loguée et
sautée, l'index en échec remonte.

Lire un tableau **par libellé** (`_detail`) plutôt que par position : une ligne de plus
ou de moins sur une fiche ne décale rien, et une ligne absente donne `None`.

## Lire du JSON avec parsel

`Selector(text=…)` reconnaît le JSON : `CatalogueScraper` passe donc un payload JSON
tel quel à `listing_nodes`, et `.jmespath()` s'y promène. Pas de `json.loads` dans une
source.

```python
page.jmespath("props[*]")  # un nœud par annonce
node.jmespath("imgs[*] || imgs.*").getall()  # liste OU objet indexé (Naef)
node.jmespath("medias.nodes[*].path").getall()  # listes imbriquées
```

JSON embarqué dans une page HTML (`__NEXT_DATA__`, `drupal-settings-json`) :

```python
state = Selector(text=page.css("script#__NEXT_DATA__::text").get(""), type="json")
nodes = state.jmespath("props.pageProps.listings.edges[*].node")
```

Fragment HTML dans une clé JSON (Bernard Nicod) : `Selector(text=page.jmespath("html").get(""))`,
puis des sélecteurs CSS dans le fragment.

## Champ par champ

`Listing` (`common/models.py`) valide à la construction et lève `ValueError` en nommant
le champ et l'URL. `HttpScraper._build_or_skip` logue alors l'annonce et passe à la
suivante. Une annonce incomplète sort donc avec des `None` ; une annonce **fausse** (URL
relative, prix à 0, texte vide) est rejetée, et c'est le comportement voulu : elle se
verra dans l'audit en direct.

| Champ | Règle | Avec |
|---|---|---|
| `external_id` | Requis. Ce qui distingue deux annonces et ne change pas d'un poll à l'autre : numéro de dossier, sinon l'URL complète. Jamais une URL tronquée de sa query string. | — |
| `external_url` | Requis, `http(s)://`, **telle que publiée** (le lien canonique s'il y en a un). Relative → `urljoin`. | `urllib.parse.urljoin` |
| `title` | Requis. Un repli se décide par régie et se note au spike (Naef : désignation du type ; Comptoir : type si `<h1>` vide). Pas de repli générique : un titre absent du gabarit doit faire échouer l'annonce. | — |
| `property_type` | Libellé français → `parse_property_type`. Code propre à la source → dictionnaire dans le module, WARNING avec l'identifiant sur un code inconnu (voir `naef.py`). | `parse_property_type` |
| `price_chf` | Loyer **mensuel, charges comprises**, en centimes. Passer le texte brut du loyer et la surface. Loyer affiché hors charges : ajouter `charges_chf`. | `parse_monthly_rent` |
| `charges_chf` | Part des charges dans `price_chf`. `None` sans loyer mensuel connu. | `parse_charges` |
| `nb_rooms` | `or None` si la source écrit `0` pour « inconnu ». | `parse_rooms` |
| `surface_m2` | Idem. Fourchette : borne basse. | `parse_surface` |
| `floor` | 0 = rez, négatif = sous-sol. | `parse_floor` |
| `address` | Rue et numéro seulement, sans NPA ni ville. | — |
| `postal_code` | Chaîne de 4 chiffres, telle que publiée. Non publié → `None`. | — |
| `city` | La localité telle qu'écrite. | — |
| `canton` | Nom complet → `canton_code`. Code à deux lettres → tel quel. **Absent → laisser `None`** : `HttpScraper` le déduit du NPA et de la ville. | `canton_code` |
| `description` | Texte normalisé, `None` si vide. | `normalize-space()` |
| `images` | `tuple` d'URL absolues, dans l'ordre de la page. Aucune → `()`. | `urljoin` |

Trois réflexes qui évitent la plupart des annonces rejetées :

- un texte optionnel vide est `None`, donc `… or None` après chaque extraction ;
- un nombre à `0` est une absence, donc `… or None` aussi quand la source écrit des zéros ;
- `price_chf` et `charges_chf` se calculent avant le `Listing(...)`, parce que le second
  dépend du premier.

## Ce que `utils.py` sait déjà lire

| Fonction | Entrée → sortie |
|---|---|
| `parse_swiss_price(text)` | `CHF 1'850.–` → `185000` ; apostrophe droite ou typographique, espace, centimes ; rien de lisible → `None`. Brique de base : pour un loyer, préférer la suivante. |
| `parse_monthly_rent(text, surface_m2)` | Loyer ramené au mois : `/ an`, `par année`, `p.a.`, `pro Jahr` ÷ 12 ; `/ m²` × surface, `None` sans surface ; `CHF 0.-` et « sur demande » → `None`. |
| `parse_charges(text, rent, price_chf)` | Charges en centimes, `None` si le loyer est inconnu, annuel ou au m² (les charges n'ont pas d'unité affichée), ou si elles valent 0. |
| `is_monthly_rent(text)` | Le texte du loyer est-il mensuel ? |
| `parse_rooms(text)` | `3½`, `3.5`, `4 pièces`, `2 Zimmer` → `float` ; `Studio` → `1.0`. |
| `parse_surface(text)` | `68 m²`, `68 m2`, `118.5` → `float`. |
| `parse_floor(text)` | `2ème étage` → 2, `rez`, `rdc` → 0, `1er sous-sol` → -1, `7ème`, `-1` seuls → 7, -1. |
| `parse_property_type(text)` | Premier mot du libellé : Appartement, Studio, Maison, Place ouverte/couverte, Garage individuel, Parking, Atelier, Arcade, Bureau, Commerce, Dépôt. Inconnu → `None` + WARNING. |
| `canton_code(name)` | `Genève` → `GE`. Inconnu → `None` + WARNING. |

Un format ou un libellé que la régie écrit et qu'aucune fonction ne lit : **étendre
`utils.py`**, test d'abord dans `tests/unit/test_utils.py`. C'est la seule modification
de l'existant qu'une story de scraper s'autorise, parce que la prochaine régie écrira
le même format. Une regex de prix, de pièces ou de surface dans un module de source est
un défaut, même courte.

Une grammaire propre à **une** régie (les lignes de caractéristiques de Burger) reste
dans son module ; ce qu'elle ne reconnaît pas est logué et ignoré, jamais deviné.

## Ce qui ne s'écrit pas dans une source

- **Un filtre.** Ni par type, ni par canton, ni par prix. La source remonte tout ce que
  son accès publie en location et l'étiquette. Ne pas typer une annonce d'après un
  paramètre d'URL : les sites les ignorent souvent.
- **La déduction du canton.** Elle est dans `HttpScraper`, pour toutes les sources.
- **Une requête hors de `self._get()`**, une pause (`sleep`), un client `httpx` à soi :
  le débit de la source est tenu par le `RateLimiter`, requête par requête.
- **`fetch_listings`, `run`, `_get`, `_build_or_skip`.** Si la régie ne tient pas dans
  `listing_nodes`/`parse_listing` ou `fiche_urls`/`parse_fiche`, voir l'étape 2 du skill.
- **Un `try/except` autour du parsing** pour « ne pas planter » : la base saute déjà
  l'annonce fautive, en la loguant. L'avaler dans la source la cache à l'audit.
- **Une valeur par défaut** là où la source ne dit rien : c'est `None`.
- `print()`, `TODO`, `beautifulsoup4`, un `Any` ou un `# type: ignore` sans raison écrite.

Docstring sur le module, la classe et chaque méthode publique, en anglais comme le
reste du code ; signatures typées (`mypy --strict` tourne sur `src/`).
