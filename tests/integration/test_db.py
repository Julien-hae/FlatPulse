"""Tests of the database layer (#71) against a real PostgreSQL.

They need a disposable database loaded with sql/schema.sql, given in
FLATPULSE_TEST_DATABASE_URL: every test empties its tables. The CI provides one
(#141, `.github/workflows/ci.yml`); without the variable they are skipped. Locally,
with docker compose:

    docker compose exec postgres createdb -U flatpulse flatpulse_test
    docker compose exec -T postgres psql -U flatpulse flatpulse_test < sql/schema.sql
    FLATPULSE_TEST_DATABASE_URL=postgresql://flatpulse:<POSTGRES_PASSWORD>@localhost:5432/flatpulse_test \
        python -m unittest tests.integration.test_db
"""

import os
import unittest
from datetime import UTC, datetime, timedelta

from flatpulse import db
from flatpulse.common.models import Listing, PropertyType

TEST_DATABASE_URL = os.environ.get("FLATPULSE_TEST_DATABASE_URL", "")

LISTING = Listing(
    external_id="12345",
    external_url="https://www.naef.ch/louer/appartements/geneve/12345",
    title="Appartement de 3½ pièces à Plainpalais",
    property_type=PropertyType.APARTMENT,
    price_chf=185000,
    nb_rooms=3.5,
    surface_m2=71.5,
    floor=0,
    city="Genève",
    canton="GE",
    postal_code="1205",
    images=("https://www.naef.ch/img/12345-1.jpg",),
)


@unittest.skipUnless(
    TEST_DATABASE_URL, "Set FLATPULSE_TEST_DATABASE_URL to a disposable database"
)
class TestDatabaseLayer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.open_pool(TEST_DATABASE_URL)
        self.addAsyncCleanup(db.close_pool)
        async with db.get_pool().connection() as conn:
            await conn.execute(
                "TRUNCATE notifications, search_profiles, users, listings, sources "
                "RESTART IDENTITY CASCADE"
            )
            await conn.execute(
                "INSERT INTO sources (name, slug, base_url, scraper_class) "
                "VALUES ('Naef', 'naef', 'https://www.naef.ch', 'NaefScraper')"
            )

    async def test_insert_listing_twice_updates_the_same_row(self) -> None:
        first_id = await db.insert_listing(LISTING, source_slug="naef")
        cheaper = Listing(
            external_id=LISTING.external_id,
            external_url=LISTING.external_url,
            title=LISTING.title,
            property_type=PropertyType.APARTMENT,
            price_chf=175000,
        )
        second_id = await db.insert_listing(cheaper, source_slug="naef")

        self.assertGreater(first_id, 0)
        self.assertEqual(first_id, second_id)
        async with db.get_pool().connection() as conn:
            cursor = await conn.execute(
                "SELECT price_chf, fingerprint, property_type FROM listings"
            )
            rows = await cursor.fetchall()
        self.assertEqual(
            rows,
            [
                {
                    "price_chf": 175000,
                    "fingerprint": cheaper.fingerprint,
                    "property_type": "apartment",
                }
            ],
        )

    async def test_insert_listing_unknown_source_raises(self) -> None:
        with self.assertRaises(LookupError):
            await db.insert_listing(LISTING, source_slug="inconnue")

    async def test_get_active_profiles_excludes_inactive(self) -> None:
        user_id = await db.upsert_user(111, "alice@example.ch", "fr")
        await db.insert_profile(user_id, {"name": "Carouge", "cities": ["Carouge"]})
        await db.insert_profile(user_id, {"name": "Onex", "max_price": 200000})
        inactive_id = await db.insert_profile(user_id, {"name": "Ancien"})
        async with db.get_pool().connection() as conn:
            await conn.execute(
                "UPDATE search_profiles SET is_active = FALSE WHERE id = %s",
                (inactive_id,),
            )

        profiles = await db.get_active_profiles()

        by_name = {p["name"]: p for p in profiles}
        self.assertEqual(sorted(by_name), ["Carouge", "Onex"])
        self.assertEqual({p["user_plan"] for p in profiles}, {"free"})
        self.assertEqual(by_name["Carouge"]["cities"], ["Carouge"])

    async def test_get_active_profiles_excludes_inactive_users(self) -> None:
        user_id = await db.upsert_user(222, None, "fr")
        await db.insert_profile(user_id, {"name": "Lancy"})
        async with db.get_pool().connection() as conn:
            await conn.execute(
                "UPDATE users SET is_active = FALSE WHERE id = %s", (user_id,)
            )

        self.assertEqual(await db.get_active_profiles(), [])

    async def test_upsert_user_keeps_id_and_email(self) -> None:
        first_id = await db.upsert_user(333, "bob@example.ch", "fr")
        second_id = await db.upsert_user(333, None, "de")

        self.assertEqual(first_id, second_id)
        async with db.get_pool().connection() as conn:
            cursor = await conn.execute("SELECT email, lang FROM users")
            self.assertEqual(
                await cursor.fetchall(), [{"email": "bob@example.ch", "lang": "de"}]
            )

    async def test_notifications_dedup_and_count(self) -> None:
        user_id = await db.upsert_user(444, None, "fr")
        profile_id = await db.insert_profile(user_id, {"name": "Genève"})
        listing_id = await db.insert_listing(LISTING, source_slug="naef")
        hour_ago = datetime.now(UTC) - timedelta(hours=1)

        self.assertFalse(
            await db.check_notification_exists(user_id, listing_id, "telegram")
        )
        for _ in range(2):
            await db.insert_notification(
                user_id, listing_id, profile_id, "telegram", 87.5
            )

        self.assertTrue(
            await db.check_notification_exists(user_id, listing_id, "telegram")
        )
        self.assertFalse(
            await db.check_notification_exists(user_id, listing_id, "email")
        )
        self.assertEqual(await db.count_notifications_since(user_id, hour_ago), 1)
        self.assertEqual(
            await db.count_notifications_since(user_id, datetime.now(UTC)), 0
        )
