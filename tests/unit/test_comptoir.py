"""Unit tests for the Comptoir Immobilier scraper."""

import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import httpx
from parsel import Selector

from flatpulse.common.models import Listing, PropertyType
from flatpulse.scrapers.rate_limiter import RateLimiter
from flatpulse.scrapers.sources.comptoir import ComptoirScraper
from tests.contract.test_scraper_contract import ScraperContractMixin
from tests.helpers import CANTON_LOOKUP, response_from_fixture

YVORNE = (
    "magnifique-duplex-de-5-5-pices-en-attique-denviron-165m2-dans-un-petit-"
    "immeuble-avec-ascenseur-lavenue-de-lausanne-24-situ-sur-la-commune-dyvorne-"
    "10-minutes-pieds-du-centre-ville-dai"
)
GENEVA = "a-louer-appartement-de-4-pices-au-7me-tage"
SATIGNY = (
    "https://comptoir-immo.ch/location/place-de-parc/canton-de-geneve/satigny/279533/"
)


def fake_get(url: str) -> MagicMock:
    """Serve the frozen catalogue, and the frozen fiche of each of its cards."""
    if url.startswith(ComptoirScraper.base_url + "?page="):
        return response_from_fixture("comptoir_cases.html")
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return response_from_fixture(f"comptoir/{slug}.html")


CATALOGUE_PAGE = f"{ComptoirScraper.base_url}?page=1"
SECOND_PAGE = f"{ComptoirScraper.base_url}?page=2"
# The ten cards of the frozen catalogue, by the URL of their fiche.
CARDS = {
    card.css("a:has(h2)::attr(href)").get(""): card.get()
    for card in Selector(text=response_from_fixture("comptoir_cases.html").text).css(
        "article.teaser--property_for_rent"
    )
}


def card_url(slug: str) -> str:
    """URL of the frozen card whose fiche is `slug`."""
    return next(url for url in CARDS if url.endswith(f"/{slug}/"))


class FakeComptoir:
    """comptoir-immo.ch as a test changes it between two polls of one scraper.

    `cards` is the catalogue, newest first, served `per_page` cards at a time;
    `fiches` holds the pages that differ from the frozen ones; a fiche held as an
    exception fails to download.
    """

    def __init__(self, per_page: int = len(CARDS)) -> None:
        """Start as the frozen catalogue, on a single page unless told otherwise."""
        self.cards = dict(CARDS)
        self.per_page = per_page
        self.fiches: dict[str, str | Exception] = {}

    def page(self, number: int) -> str:
        """Catalogue page `number`: its cards, then the link to the last page."""
        cards = list(self.cards.values())
        last = max(1, -(-len(cards) // self.per_page))
        start = (number - 1) * self.per_page
        return "".join(cards[start : start + self.per_page]) + (
            f'<a class="page-number page-numbers">{last}</a>'
        )

    def get(self, url: str) -> MagicMock:
        """Serve the catalogue as it stands, else the fiche at `url`."""
        if url.startswith(ComptoirScraper.base_url + "?page="):
            return MagicMock(text=self.page(int(url.rpartition("=")[2])))
        fiche = self.fiches.get(url)
        if isinstance(fiche, Exception):
            raise fiche
        return fake_get(url) if fiche is None else MagicMock(text=fiche)

    async def poll(self, scraper: ComptoirScraper) -> tuple[list[Listing], list[str]]:
        """One poll of `scraper` on this site: its listings, and the URLs it requested."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = self.get
            listings = await scraper.fetch_listings()
        return listings, [request.args[0] for request in mock_get.await_args_list]


class TestComptoirScraper(ScraperContractMixin, unittest.IsolatedAsyncioTestCase):
    """Contract tests and named cases of ComptoirScraper.

    `comptoir_cases.html` holds ten catalogue cards without pagination;
    `comptoir/` holds their ten fiches of 04.11.2026 and 08.11.2026, contact
    anonymised.
    """

    scraper_class = ComptoirScraper
    fixture_name = "comptoir_cases.html"

    def new_scraper(self) -> ComptoirScraper:
        """A fresh ComptoirScraper, typed as such: some cases call its parse_fiche."""
        return ComptoirScraper(
            rate_limiter=AsyncMock(spec=RateLimiter), canton_lookup=CANTON_LOOKUP
        )

    async def fetch_from_fixture(self) -> list[Listing]:
        """Serve the catalogue, then its fiches, without waiting the crawl-delay."""
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.side_effect = fake_get
            return await self.new_scraper().fetch_listings()

    async def test_comptoir_details_table(self) -> None:
        """A Geneva apartment comes out of its « Détails » table, field by field."""
        await self.assert_listing(
            GENEVA,
            {
                "title": "A louer, appartement de 4 pièces au 7ème étage",
                "property_type": PropertyType.APARTMENT,
                "price_chf": 276700,
                "charges_chf": 21700,
                "nb_rooms": 4.0,
                "surface_m2": 79.0,
                "floor": 7,
                "address": "Quai Charles-Page 49",
                "city": "Genève",
                "canton": "GE",
            },
        )

    async def test_comptoir_other_canton_is_kept(self) -> None:
        """A Vaud duplex is kept; its floor comes from the table, not the title."""
        await self.assert_listing(
            YVORNE,
            {
                # The site's typographic apostrophes, kept as scraped
                "title": "Magnifique duplex de 5.5 pièces en attique d’environ 165m2 "  # noqa: RUF001
                "dans un petit immeuble avec ascenseur, à l’Avenue de Lausanne 24. "  # noqa: RUF001
                "Situé sur la commune d’Yvorne à 10 minutes à pieds du centre ville d’Ai",  # noqa: RUF001
                "price_chf": 307000,
                "nb_rooms": 5.5,
                "surface_m2": 165.0,
                "floor": 2,
                "address": "Route de Lausanne 24 A",
                "city": "Yvorne",
                "canton": "VD",
            },
        )

    async def test_comptoir_description_and_images(self) -> None:
        """The fiche gives the full description and every photo of its gallery."""
        listing = next(
            item
            for item in await self.fetch_from_fixture()
            if item.external_id == YVORNE
        )

        assert listing.description is not None
        self.assertTrue(listing.description.startswith("Magnifique duplex de 5.5"))
        self.assertTrue(listing.description.endswith("Cuisine équipée, WC séparé."))
        self.assertEqual(len(listing.images), 13)
        self.assertEqual(
            listing.images[0],
            "https://comptoir-immo.ch/external-images/?url=https%3A%2F%2Fmedia.apimo.pro"
            "%2Fcache%2F802522d3f833ead4be77ef2784873b0f_5e7471171f_1024-original.jpg"
            "&propertyId=1006865&preset=fullwidth",
        )

    async def test_comptoir_without_surface(self) -> None:
        """A fiche without a surface row, nor photos, keeps its rooms."""
        await self.assert_listing(
            "appartement-avec-balcon-situ-dans-environnement-verdoyant-proche-de-"
            "toutes-les-commodits",
            {"surface_m2": None, "nb_rooms": 5.0, "images": (), "city": "Carouge"},
        )

    async def test_comptoir_parking(self) -> None:
        """A parking has a rent, no rooms, and lies on the ground floor."""
        await self.assert_listing(
            "emplacement-de-parking-dans-un-parking-scuris-cet-place-est-louer-"
            "uniquement-des-personnes-extrieures-au-plq-amandolier",
            {
                "property_type": PropertyType.PARKING,
                "price_chf": 26000,
                "nb_rooms": None,
                "floor": 0,
            },
        )

    async def test_comptoir_untitled_fiche_takes_property_type(self) -> None:
        """A parking published with an empty <h1> is titled by its « Type de bien »."""
        await self.assert_listing(
            "901969",
            {
                "title": "Parking",
                "property_type": PropertyType.PARKING,
                "price_chf": 20000,
                "floor": -2,
                "address": "Rue du Fort-Barreau 15",
                "city": "Genève",
                "canton": "GE",
                "postal_code": None,
            },
        )

    def test_comptoir_zero_rent_is_none(self) -> None:
        """« CHF 0.- / mois » is no price, never 0: the untitled Satigny parking.

        `comptoir/279533.html` is a fiche without its catalogue card, parsed alone.
        """
        fiche = Selector(text=response_from_fixture("comptoir/279533.html").text)

        listing = self.new_scraper().parse_fiche(fiche, SATIGNY)

        self.assertEqual(listing.external_url, SATIGNY)
        self.assertEqual(listing.title, "Parking")
        self.assertIsNone(listing.price_chf)
        self.assertEqual(listing.city, "Satigny")
        self.assertEqual(listing.canton, "GE")

    def test_comptoir_no_charges_without_rent(self) -> None:
        """Charges belong to a rent: « CHF 0.- / mois » is no rent, so no charges."""
        html = response_from_fixture("comptoir/279533.html").text.replace(
            "</table>",
            "<tr><th>Charges</th><td>CHF 150.-</td></tr></table>",
            1,
        )

        listing = self.new_scraper().parse_fiche(Selector(text=html), SATIGNY)

        self.assertIsNone(listing.price_chf)
        self.assertIsNone(listing.charges_chf)

    async def test_comptoir_fiche_without_h1_is_skipped(self) -> None:
        """Only an empty <h1> falls back on the type: no <h1> at all means a redesign.

        Titling such fiches by their type would hide it from the live audit (#119),
        which counts the listings skipped as invalid.
        """
        expected = len(await self.fetch_from_fixture()) - 1

        def get(url: str) -> MagicMock:
            response = fake_get(url)
            if GENEVA in url:
                response.text = response.text.replace("<h1", "<h3")
            return response

        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            self.assertLogs("flatpulse.scrapers.base", "WARNING") as logs,
        ):
            mock_get.side_effect = get
            listings = await self.new_scraper().fetch_listings()

        self.assertEqual(len(listings), expected)
        self.assertIn("title", logs.output[0])

    async def test_comptoir_rent_per_square_meter(self) -> None:
        """« CHF 600.- / m² / an » on 117 m² is a monthly rent of CHF 5'850.-."""
        await self.assert_listing(
            "belles-surfaces-administratives-dans-un-immeuble-de-haut-standing-dans-le-"
            "quartier-des-banques",
            {
                "property_type": PropertyType.COMMERCIAL,
                "price_chf": 585000,
                "charges_chf": None,
                "surface_m2": 117.0,
                "floor": 1,
            },
        )

    async def test_comptoir_surface_only_on_fiche(self) -> None:
        """The card shows no surface; the fiche's « Surface utile » prices the m²."""
        await self.assert_listing(
            "cabinet-bureau-remettre-au-centre-de-sion",
            {"surface_m2": 120.0, "price_chf": 308000, "charges_chf": None},
        )

    async def test_comptoir_yearly_rent(self) -> None:
        """« CHF 18'720.- / an » is a monthly rent; yearly charges are not added."""
        await self.assert_listing(
            "bureau-louer-au-centre-de-monthey",
            {"price_chf": 156000, "charges_chf": None, "floor": 0, "canton": "VS"},
        )

    async def test_comptoir_price_on_request_is_none(self) -> None:
        """« Prix sur demande » gives no price, never 0."""
        await self.assert_listing(
            "surface-administrative-dexception-au-coeur-de-genve",
            {"price_chf": None, "surface_m2": 1061.0},
        )

    async def test_comptoir_storage_without_surface(self) -> None:
        """A basement dépôt priced per m² without a surface has no price, never 0."""
        await self.assert_listing(
            "a-louer-dpot-scuris-plainpalais",
            {
                "property_type": PropertyType.STORAGE,
                "price_chf": None,
                "surface_m2": None,
                "floor": -1,
            },
        )

    async def test_comptoir_failing_fiche_is_skipped(self) -> None:
        """A fiche that fails to download is logged; the other fiches come out."""
        expected = len(await self.fetch_from_fixture()) - 1

        def get(url: str) -> MagicMock:
            if GENEVA in url:
                raise httpx.RemoteProtocolError("Server disconnected")
            return fake_get(url)

        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            self.assertLogs("flatpulse.scrapers.base", "WARNING"),
        ):
            mock_get.side_effect = get
            listings = await self.new_scraper().fetch_listings()

        self.assertEqual(len(listings), expected)

    async def test_comptoir_invalid_fiche_is_skipped(self) -> None:
        """A fiche that cannot be parsed is logged and skipped; the others come out."""
        expected = len(await self.fetch_from_fixture()) - 1

        def get(url: str) -> MagicMock:
            response = fake_get(url)
            if GENEVA in url:
                # No canonical link, no URL: Listing rejects the fiche.
                response.text = response.text.replace('rel="canonical"', 'rel="x"')
            return response

        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            self.assertLogs("flatpulse.scrapers.base", "WARNING"),
        ):
            mock_get.side_effect = get
            listings = await self.new_scraper().fetch_listings()

        self.assertEqual(len(listings), expected)

    async def test_comptoir_acquires_before_each_page(self) -> None:
        """Each catalogue page acquires a token immediately before its GET."""
        rate_limiter = AsyncMock(spec=RateLimiter)
        scraper = ComptoirScraper(
            rate_limiter=rate_limiter, canton_lookup=CANTON_LOOKUP
        )
        manager = Mock()
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.return_value = httpx.Response(
                200,
                request=httpx.Request("GET", ComptoirScraper.base_url),
                text=(
                    '<a class="page-number page-numbers">1</a>'
                    '<a class="page-number page-numbers">3</a>'
                ),
            )
            manager.attach_mock(rate_limiter.acquire, "acquire")
            manager.attach_mock(mock_get, "get")
            await scraper.fetch_listings()

        self.assertEqual(
            manager.mock_calls,
            [
                call.acquire("comptoir"),
                call.get(f"{ComptoirScraper.base_url}?page=1"),
                call.acquire("comptoir"),
                call.get(f"{ComptoirScraper.base_url}?page=2"),
                call.acquire("comptoir"),
                call.get(f"{ComptoirScraper.base_url}?page=3"),
            ],
        )


class TestComptoirFicheCache(unittest.IsolatedAsyncioTestCase):
    """An established poll downloads only the fiches whose card is new or changed (#120)."""

    def setUp(self) -> None:
        """One scraper for the polls of a test: the cache lives in it."""
        self.site = FakeComptoir()
        self.now = 0.0
        self.scraper = ComptoirScraper(
            rate_limiter=AsyncMock(spec=RateLimiter),
            canton_lookup=CANTON_LOOKUP,
            clock=lambda: self.now,
        )

    async def test_comptoir_unchanged_card_reuses_fiche(self) -> None:
        """A second poll on the same catalogue reads its pages, and not one fiche."""
        first, _ = await self.site.poll(self.scraper)

        second, requested = await self.site.poll(self.scraper)

        self.assertEqual(requested, [CATALOGUE_PAGE])
        self.assertEqual(second, first)
        self.assertEqual(len(first), len(CARDS))

    async def test_comptoir_changed_card_refetches_its_fiche(self) -> None:
        """A rent lowered on a card is read again from its fiche, and from it alone."""
        url = card_url(YVORNE)
        first, _ = await self.site.poll(self.scraper)
        self.site.cards[url] = CARDS[url].replace("3'070", "2'950")
        self.site.fiches[url] = fake_get(url).text.replace("3'070", "2'950")

        second, requested = await self.site.poll(self.scraper)

        self.assertEqual(requested, [CATALOGUE_PAGE, url])
        self.assertEqual(
            [item.price_chf for item in second if item.external_id == YVORNE],
            [295000],
        )
        self.assertEqual(
            [item for item in second if item.external_id != YVORNE],
            [item for item in first if item.external_id != YVORNE],
        )

    async def test_comptoir_new_card_fetches_only_its_fiche(self) -> None:
        """A card that appears is the only fiche downloaded, and its listing comes out."""
        url = card_url(GENEVA)
        del self.site.cards[url]
        first, _ = await self.site.poll(self.scraper)
        self.site.cards[url] = CARDS[url]

        second, requested = await self.site.poll(self.scraper)

        self.assertEqual(requested, [CATALOGUE_PAGE, url])
        self.assertNotIn(GENEVA, [item.external_id for item in first])
        self.assertIn(GENEVA, [item.external_id for item in second])
        self.assertEqual(len(second), len(first) + 1)

    async def test_comptoir_gone_card_drops_listing(self) -> None:
        """A card that left the catalogue is not kept alive by the cache.

        Seen by a full walk of the catalogue (#150), hence the hour that passes.
        """
        url = card_url(GENEVA)
        first, _ = await self.site.poll(self.scraper)
        del self.site.cards[url]
        self.now += 3600

        second, requested = await self.site.poll(self.scraper)
        self.site.cards[url] = CARDS[url]
        _, requested_when_back = await self.site.poll(self.scraper)

        self.assertEqual(requested, [CATALOGUE_PAGE])
        self.assertEqual(second, [item for item in first if item.external_id != GENEVA])
        # Forgotten, not merely hidden: back in the catalogue, its fiche is read anew.
        self.assertEqual(requested_when_back, [CATALOGUE_PAGE, url])


class TestComptoirShortPoll(unittest.IsolatedAsyncioTestCase):
    """An established poll stops at the first catalogue page without a new card (#150)."""

    def setUp(self) -> None:
        """A catalogue of two pages of five cards, and a clock the test moves."""
        self.site = FakeComptoir(per_page=5)
        self.now = 0.0
        self.scraper = ComptoirScraper(
            rate_limiter=AsyncMock(spec=RateLimiter),
            canton_lookup=CANTON_LOOKUP,
            clock=lambda: self.now,
        )

    async def test_comptoir_known_first_page_stops_the_poll(self) -> None:
        """Nothing published: one request, and still every listing."""
        first, requested_first = await self.site.poll(self.scraper)
        self.now += 60

        second, requested = await self.site.poll(self.scraper)

        self.assertEqual(requested_first[:2], [CATALOGUE_PAGE, SECOND_PAGE])
        self.assertEqual(requested, [CATALOGUE_PAGE])
        self.assertEqual(second, first)
        self.assertEqual(len(second), len(CARDS))

    async def test_comptoir_new_card_on_first_page_is_fetched(self) -> None:
        """A new card heads page 1: the next page is read too, then its fiche."""
        url = card_url(GENEVA)
        del self.site.cards[url]
        first, _ = await self.site.poll(self.scraper)
        self.site.cards = {url: CARDS[url], **self.site.cards}
        self.now += 60

        second, requested = await self.site.poll(self.scraper)

        # Page 2 holds no unknown card: the walk stops there, then the fiche is read.
        self.assertEqual(requested, [CATALOGUE_PAGE, SECOND_PAGE, url])
        self.assertIn(GENEVA, [item.external_id for item in second])
        self.assertEqual(len(second), len(first) + 1)

    async def test_comptoir_full_walk_after_one_hour(self) -> None:
        """After an hour every page is read again, and a card gone from page 2 is seen."""
        gone = list(CARDS)[-1]
        first, _ = await self.site.poll(self.scraper)
        del self.site.cards[gone]
        self.now += 61 * 60

        second, requested = await self.site.poll(self.scraper)

        self.assertEqual(requested, [CATALOGUE_PAGE, SECOND_PAGE])
        self.assertEqual(len(second), len(first) - 1)
        self.assertNotIn(
            gone, [item.external_url for item in second], "listing still alive"
        )
