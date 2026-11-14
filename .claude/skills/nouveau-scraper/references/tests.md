# Écrire les tests, rouges

Fichier : `tests/unit/test_<slug>.py`. `unittest` uniquement, tout mocké, aucune I/O
hors lecture de fixture. Les squelettes ci-dessous sont ceux de Naef (catalogue) et de
Burger (fiches), ramenés à une régie fictive `exemple` : remplacer le nom, garder la
structure.

## Sommaire

- Ce que le mixin apporte, et ce qu'il n'apporte pas
- Squelette — `CatalogueScraper`
- Squelette — `FicheScraper`
- Les cas à écrire
- Rouge, pour la bonne raison

## Ce que le mixin apporte, et ce qu'il n'apporte pas

Hériter de `ScraperContractMixin` (`tests/contract/test_scraper_contract.py`) fait
tourner cinq contrats sur la fixture : elle produit au moins une annonce, le retour est
une `list` de `Listing`, les annonces sont immuables et hashables, `fingerprint` est un
SHA-256 hex de 64 caractères, deux lectures donnent les mêmes fingerprints.

Ces contrats restent verts sur un scraper qui ne remplit que les trois champs requis.
Ce qui prouve le scraper, ce sont les cas nommés : `assert_listing(external_id, {…})`
retrouve une annonce de la fixture par son identifiant et compare les champs donnés à
des valeurs écrites en dur.

## Squelette — `CatalogueScraper`

```python
"""Unit tests for the Régie Exemple scraper."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from parsel import Selector

from flatpulse.common.models import PropertyType
from flatpulse.scrapers.rate_limiter import RateLimiter
from flatpulse.scrapers.sources.exemple import ExempleScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import CANTON_LOOKUP, response_from_fixture


class TestExempleScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and named cases of ExempleScraper.

    `exemple_cases.json` holds three properties of the catalogue of 14.11.2026,
    unchanged, one per trap of docs/spike-agencies.md.
    """

    scraper_class = ExempleScraper
    fixture_name = "exemple_cases.json"

    def new_scraper(self) -> ExempleScraper:
        """A fresh ExempleScraper, typed as such: some cases call its parse_listing."""
        return ExempleScraper(
            rate_limiter=AsyncMock(spec=RateLimiter), canton_lookup=CANTON_LOOKUP
        )

    async def test_exemple_full_apartment(self) -> None:
        """A complete Geneva apartment comes out field by field."""
        await self.assert_listing(
            "A-1001",
            {
                "external_url": "https://www.regie-exemple.ch/louer/A-1001",
                "title": "Appartement de 3½ pièces aux Eaux-Vives",
                "property_type": PropertyType.APARTMENT,
                "price_chf": 185000,
                "nb_rooms": 3.5,
                "surface_m2": 68.0,
                "postal_code": "1207",
                "city": "Genève",
                "canton": "GE",
                "images": ("https://www.regie-exemple.ch/img/A-1001-1.jpg",),
            },
        )

    async def test_exemple_price_on_request_is_none(self) -> None:
        """« Prix sur demande » gives no price, never 0; zeros are absent values."""
        await self.assert_listing(
            "A-1002",
            {
                "property_type": PropertyType.COMMERCIAL,
                "price_chf": None,
                "nb_rooms": None,
                "surface_m2": None,
            },
        )

    async def test_exemple_canton_from_postal_code_when_empty(self) -> None:
        """A Vaud parking is kept; its empty canton is read from the postal code."""
        await self.assert_listing(
            "P-2001",
            {"property_type": PropertyType.PARKING, "price_chf": 18000, "canton": "VD"},
        )

    def test_exemple_missing_required_field_is_a_value_error(self) -> None:
        """No id, URL or title is an invalid listing (ValueError), not a crash."""
        payload = json.loads(response_from_fixture(self.fixture_name).text)
        for key in ("reference", "url", "titre"):
            node = Selector(text=json.dumps({**payload["biens"][0], key: None}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.new_scraper().parse_listing(node)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    async def test_exemple_invalid_listing_is_skipped(
        self, mock_get: AsyncMock
    ) -> None:
        """A property Listing rejects is logged and skipped; the others come out."""
        payload = json.loads(response_from_fixture(self.fixture_name).text)
        payload["biens"][0]["url"] = "/louer/relative"
        mock_get.return_value = MagicMock(text=json.dumps(payload))

        with self.assertLogs("flatpulse.scrapers.base", "WARNING") as captured:
            listings = await self.new_scraper().fetch_listings()

        self.assertEqual(len(listings), len(payload["biens"]) - 1)
        [warning] = captured.output
        self.assertIn("external_url", warning)
```

Le mixin sert la fixture à l'unique GET : rien à surcharger d'autre que `new_scraper`,
et seulement parce que des cas appellent `parse_listing` directement (mypy doit savoir
que c'est un `ExempleScraper`).

## Squelette — `FicheScraper`

Plusieurs requêtes, donc un `fake_get` qui sert l'index puis chaque fiche depuis son
URL, et `fetch_from_fixture` surchargé pour l'utiliser.

```python
"""Unit tests for the Régie Exemple scraper."""

import re
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

from parsel import Selector

from flatpulse.common.models import Listing, PropertyType
from flatpulse.scrapers.rate_limiter import RateLimiter
from flatpulse.scrapers.sources.exemple import ExempleScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import CANTON_LOOKUP, response_from_fixture

LOUER = "https://www.regie-exemple.ch/louer/"
APARTMENT = LOUER + "carouge-appartement-3-pieces"
STORAGE = LOUER + "geneve-depot-plainpalais"


def fake_get(url: str) -> MagicMock:
    """Serve the frozen sitemap, and the frozen fiche of each of its entries."""
    if url == ExempleScraper.base_url:
        return response_from_fixture("exemple_sitemap.xml")
    return response_from_fixture(f"exemple/{url.removeprefix(LOUER)}.html")


class TestExempleScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and named cases of ExempleScraper.

    `exemple_sitemap.xml` keeps two `/louer/` entries and one sale fiche from the
    sitemap of 14.11.2026; `exemple/` holds the two rental fiches, contact anonymised.
    """

    scraper_class = ExempleScraper
    fixture_name = "exemple_sitemap.xml"

    def new_scraper(self) -> ExempleScraper:
        """A fresh ExempleScraper, typed as such: some cases call its parse_fiche."""
        return ExempleScraper(
            rate_limiter=AsyncMock(spec=RateLimiter), canton_lookup=CANTON_LOOKUP
        )

    async def fetch_from_fixture(self) -> list[Listing]:
        """Serve the sitemap, then its rental fiches."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = fake_get
            return await self.new_scraper().fetch_listings()

    async def test_exemple_apartment_fiche(self) -> None:
        """A complete Geneva apartment fiche comes out field by field."""
        await self.assert_listing(
            APARTMENT,
            {
                "external_url": APARTMENT,
                "title": "Appartement de 3 pièces au 2ème étage",
                "property_type": PropertyType.APARTMENT,
                "price_chf": 260000,
                "charges_chf": 27000,
                "nb_rooms": 3.0,
                "surface_m2": 59.0,
                "floor": 2,
                "address": "Rue de Contamines 36",
                "postal_code": "1206",
                "city": "Genève",
                "canton": "GE",
                "description": "Bel appartement traversant.",
                "images": (
                    "https://www.regie-exemple.ch/img/1.jpg",
                    "https://www.regie-exemple.ch/img/2.jpg",
                ),
            },
        )

    async def test_exemple_price_on_request_is_none(self) -> None:
        """« Loyer sur demande » gives no price, never 0, and no charges either."""
        await self.assert_listing(
            STORAGE,
            {
                "property_type": PropertyType.STORAGE,
                "price_chf": None,
                "charges_chf": None,
                "nb_rooms": None,
                "surface_m2": None,
                "images": (),
            },
        )

    def test_exemple_fiche_without_title_is_a_value_error(self) -> None:
        """A missing <h1> is an invalid listing (ValueError), not an AttributeError."""
        html = fake_get(APARTMENT).text
        page = Selector(text=re.sub(r"<h1[^>]*>.*?</h1>", "", html, flags=re.S))

        with self.assertRaisesRegex(ValueError, "title"):
            self.new_scraper().parse_fiche(page, APARTMENT)

    async def test_exemple_only_rental_fiches_are_fetched(self) -> None:
        """The sale fiche of the sitemap is never requested."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = fake_get
            await self.new_scraper().fetch_listings()

        requested = [request.args[0] for request in mock_get.call_args_list]
        self.assertEqual(requested, [ExempleScraper.base_url, APARTMENT, STORAGE])

    async def test_exemple_acquires_before_each_request(self) -> None:
        """A token is awaited before the sitemap GET and before each fiche GET."""
        limiter = AsyncMock(spec=RateLimiter)
        scraper = ExempleScraper(rate_limiter=limiter, canton_lookup=CANTON_LOOKUP)
        manager = Mock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = fake_get
            manager.attach_mock(limiter.acquire, "acquire")
            manager.attach_mock(mock_get, "get")
            await scraper.fetch_listings()

        expected = []
        for url in (ExempleScraper.base_url, APARTMENT, STORAGE):
            expected.extend([call.acquire("exemple"), call.get(url)])
        self.assertEqual(manager.mock_calls, expected)
```

`test_…_acquires_before_each_request` est le seul test qui voit une requête de
`fiche_urls` partir sans passer par `_get()` : il compte pour toute source dont l'index
fait ses propres requêtes (sitemap, pages d'un catalogue). Pour un index paginé, vérifier
de même que chaque page est demandée, dans l'ordre (`test_comptoir_acquires_before_each_page`).

La boucle des fiches elle-même (fiche en échec de téléchargement sautée, index en échec
remonté) est testée une fois dans `tests/unit/test_scrapers.py` : inutile de la retester
par régie.

## Les cas à écrire

Un test par cas de la fixture, plus ceux de la story. À minima :

| Cas | Ce qui est comparé | Ce que ça attrape |
|---|---|---|
| Appartement genevois complet | Tous les champs que la source publie | Un sélecteur ou une clé qui dérive |
| Prix sur demande | `price_chf is None` (et `charges_chf is None`) | Le `0` qui traverse les filtres de prix |
| Chaque type de bien | `property_type` exact | Un libellé absent de `utils.py` |
| Annonce hors Genève | `canton` | Un filtre glissé dans le scraper |
| Canton non écrit | `postal_code`, `canton` déduit | Un NPA mal lu |
| Loyer `/ an`, `/ m² / an` | `price_chf` mensuel, `charges_chf is None` | Un loyer annuel pris pour mensuel |
| Valeur absente écrite `0` | `nb_rooms is None`, `surface_m2 is None` | Le `0` que `Listing` refuse |
| Deux annonces voisines | Deux `external_id` distincts | Une dédup qui en perd une |
| Champ requis manquant | `ValueError` de `parse_*` | Un `AttributeError` sur `None` |
| Annonce invalide dans le lot | Les autres sortent, WARNING | Une annonce qui fait tomber le poll |
| Index : entrée hors périmètre | URLs demandées | Des requêtes pour rien chez la régie |
| Chaque piège du spike | La valeur attendue | Le piège |

Règles d'écriture, qui sont celles de l'architecture §8 :

- **Des valeurs, pas des propriétés.** `price_chf == 185000`, pas « un `int` ou `None` »,
  qui reste vert quand le champ n'est jamais rempli.
- **Seulement des valeurs justes.** `assert_listing` ne compare que les champs donnés.
  Calculer la valeur attendue depuis ce que montre le site, à la main ; ne jamais y
  recopier ce que le scraper sort.
- **Jamais le nombre d'annonces du catalogue.** `len(result) == 374` décrit un jour, pas
  le code. Le nombre d'objets *de la fixture* peut se comparer (`len(payload["biens"])`).
- **Un cas que le catalogue n'offre pas se fabrique dans le test**, à partir d'un cas
  réel modifié en mémoire, jamais dans la fixture :

  ```python
  html = fake_get(APARTMENT).text.replace("CHF 2'330.— / mois", "Loyer sur demande")
  listing = self.new_scraper().parse_fiche(Selector(text=html), APARTMENT)
  ```

- Nom : `test_<slug>_<ce_qui_est_vrai>`, docstring d'une phrase qui dit le fait, pas le
  mécanisme. Exemples genevois.
- Un format que `utils.py` ne lit pas encore : son test s'écrit d'abord dans
  `tests/unit/test_utils.py`, rouge, puis `utils.py` s'étend.

## Rouge, pour la bonne raison

Créer d'abord `src/flatpulse/scrapers/sources/<slug>.py` avec la classe, `slug`,
`base_url` et ses deux méthodes qui lèvent `NotImplementedError`. Puis :

```bash
python -m unittest tests.unit.test_<slug> -v
```

Chaque test doit échouer sur le comportement absent (`NotImplementedError`, puis des
écarts de valeurs à mesure que l'implémentation avance). Un `ImportError`, un
`FileNotFoundError` sur la fixture ou un `Aucune annonce '…' dans …` causé par un
identifiant mal recopié ne sont pas du rouge utile : les corriger avant d'implémenter.
Un test vert dès l'écriture ne teste rien de nouveau : le relire.
