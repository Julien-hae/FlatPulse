"""Unit tests for the database layer (#71), with the psycopg pool mocked."""

import unittest
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from psycopg import sql

from flatpulse import db
from flatpulse.common.models import Listing, PropertyType

LISTING = Listing(
    external_id="12345",
    external_url="https://www.naef.ch/louer/appartements/geneve/12345",
    title="Appartement de 4 pièces à Carouge",
    property_type=PropertyType.APARTMENT,
    price_chf=245000,
    charges_chf=25000,
    nb_rooms=4.0,
    surface_m2=92.5,
    floor=3,
    address="Rue Ancienne 12",
    postal_code="1227",
    city="Carouge",
    canton="GE",
    description="Lumineux, proche du tram.",
    images=("https://www.naef.ch/img/12345-1.jpg",),
)


def mock_pool(
    fetchone: Any = None, fetchall: list[dict[str, Any]] | None = None
) -> tuple[MagicMock, AsyncMock]:
    """A fake pool whose connection answers `fetchone` and `fetchall`.

    Returns the pool and the connection's `execute`, to inspect the SQL sent.
    """
    cursor = MagicMock()
    cursor.fetchone = AsyncMock(return_value=fetchone)
    cursor.fetchall = AsyncMock(return_value=fetchall or [])
    connection = MagicMock()
    connection.execute = AsyncMock(return_value=cursor)
    pool = MagicMock()
    pool.connection.return_value.__aenter__.return_value = connection
    return pool, connection.execute


def sent_query(execute: AsyncMock) -> str:
    """The SQL of the last query, whitespace collapsed to single spaces."""
    query = execute.call_args.args[0]
    if isinstance(query, sql.Composable):
        query = query.as_string()
    return " ".join(str(query).split())


def sent_params(execute: AsyncMock) -> Any:
    """The parameters of the last query."""
    return execute.call_args.args[1]


class TestPool(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        db._pool = None

    async def test_open_pool_opens_once_with_database_url(self) -> None:
        with patch("flatpulse.db.AsyncConnectionPool") as pool_class:
            pool_class.return_value.open = AsyncMock()
            pool = await db.open_pool("postgresql://flatpulse@localhost/flatpulse")

        self.assertEqual(
            pool_class.call_args.args[0], "postgresql://flatpulse@localhost/flatpulse"
        )
        self.assertFalse(pool_class.call_args.kwargs["open"])
        pool.open.assert_awaited_once_with(wait=True)
        self.assertIs(db.get_pool(), pool)

    async def test_open_pool_twice_raises(self) -> None:
        with patch("flatpulse.db.AsyncConnectionPool") as pool_class:
            pool_class.return_value.open = AsyncMock()
            await db.open_pool("postgresql://localhost/flatpulse")
            with self.assertRaises(RuntimeError):
                await db.open_pool("postgresql://localhost/flatpulse")

    def test_get_pool_before_open_raises(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "open_pool"):
            db.get_pool()

    async def test_close_pool_closes_and_forgets_it(self) -> None:
        pool = MagicMock()
        pool.close = AsyncMock()
        db._pool = pool

        await db.close_pool()

        pool.close.assert_awaited_once_with()
        with self.assertRaises(RuntimeError):
            db.get_pool()


class TestInsertListing(unittest.IsolatedAsyncioTestCase):
    async def test_insert_listing_returns_id(self) -> None:
        pool, execute = mock_pool(fetchone={"id": 42})

        with patch("flatpulse.db.get_pool", return_value=pool):
            listing_id = await db.insert_listing(LISTING, source_slug="naef")

        self.assertIsInstance(listing_id, int)
        self.assertGreater(listing_id, 0)
        self.assertIn("INSERT INTO listings", sent_query(execute))
        params = sent_params(execute)
        self.assertEqual(params["source_slug"], "naef")
        self.assertEqual(params["fingerprint"], LISTING.fingerprint)
        self.assertEqual(params["property_type"], "apartment")
        self.assertEqual(params["price_chf"], 245000)
        self.assertEqual(params["images"], ["https://www.naef.ch/img/12345-1.jpg"])

    async def test_insert_listing_on_conflict_updates(self) -> None:
        pool, execute = mock_pool(fetchone={"id": 42})
        cheaper = Listing(
            external_id=LISTING.external_id,
            external_url=LISTING.external_url,
            title=LISTING.title,
            price_chf=230000,
        )

        with patch("flatpulse.db.get_pool", return_value=pool):
            first_id = await db.insert_listing(LISTING, source_slug="naef")
            second_id = await db.insert_listing(cheaper, source_slug="naef")

        self.assertEqual(first_id, second_id)
        query = sent_query(execute)
        self.assertRegex(query, r"ON CONFLICT \(source_id, external_id\) DO UPDATE SET")
        self.assertIn("fingerprint = EXCLUDED.fingerprint", query)
        self.assertIn("price_chf = EXCLUDED.price_chf", query)
        self.assertEqual(sent_params(execute)["price_chf"], 230000)

    async def test_insert_listing_unknown_source_raises(self) -> None:
        pool, _ = mock_pool(fetchone=None)

        with (
            patch("flatpulse.db.get_pool", return_value=pool),
            self.assertRaisesRegex(LookupError, "inconnue"),
        ):
            await db.insert_listing(LISTING, source_slug="inconnue")

    async def test_insert_listing_without_property_type_sends_null(self) -> None:
        pool, execute = mock_pool(fetchone={"id": 7})
        bare = Listing(
            external_id="9", external_url="https://www.naef.ch/9", title="Objet"
        )

        with patch("flatpulse.db.get_pool", return_value=pool):
            await db.insert_listing(bare, source_slug="naef")

        self.assertIsNone(sent_params(execute)["property_type"])
        self.assertIsNone(sent_params(execute)["price_chf"])


class TestGetActiveProfiles(unittest.IsolatedAsyncioTestCase):
    async def test_get_active_profiles_excludes_inactive(self) -> None:
        # The filter runs in SQL: the mock answers what PostgreSQL would for
        # 2 active profiles and 1 inactive one. tests/integration/test_db.py
        # checks the exclusion itself against a real PostgreSQL.
        active_rows = [
            {"id": 1, "user_id": 10, "is_active": True, "user_plan": "free"},
            {"id": 2, "user_id": 11, "is_active": True, "user_plan": "pro"},
        ]
        pool, execute = mock_pool(fetchall=active_rows)

        with patch("flatpulse.db.get_pool", return_value=pool):
            profiles = await db.get_active_profiles()

        self.assertEqual(len(profiles), 2)
        for profile in profiles:
            self.assertIn("user_plan", profile)
        query = sent_query(execute)
        self.assertIn("u.plan AS user_plan", query)
        self.assertIn("JOIN users u ON u.id = sp.user_id", query)
        self.assertIn("WHERE sp.is_active AND u.is_active", query)


class TestNotifications(unittest.IsolatedAsyncioTestCase):
    async def test_insert_notification_ignores_duplicate(self) -> None:
        pool, execute = mock_pool()

        with patch("flatpulse.db.get_pool", return_value=pool):
            result = await db.insert_notification(
                user_id=10, listing_id=42, profile_id=1, channel="telegram", score=87.5
            )

        self.assertIsNone(result)
        query = sent_query(execute)
        self.assertIn("INSERT INTO notifications", query)
        self.assertIn("ON CONFLICT (user_id, listing_id, channel) DO NOTHING", query)
        self.assertEqual(sent_params(execute), (10, 42, 1, "telegram", 87.5))

    async def test_check_notification_exists(self) -> None:
        for row, expected in (({"exists": True}, True), ({"exists": False}, False)):
            pool, execute = mock_pool(fetchone=row)
            with (
                self.subTest(expected=expected),
                patch("flatpulse.db.get_pool", return_value=pool),
            ):
                exists = await db.check_notification_exists(10, 42, "telegram")
                self.assertIs(exists, expected)
                self.assertEqual(sent_params(execute), (10, 42, "telegram"))

    async def test_count_notifications_since(self) -> None:
        pool, execute = mock_pool(fetchone={"count": 3})
        since = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)

        with patch("flatpulse.db.get_pool", return_value=pool):
            count = await db.count_notifications_since(10, since)

        self.assertEqual(count, 3)
        self.assertIn("sent_at >= %s", sent_query(execute))
        self.assertEqual(sent_params(execute), (10, since))


class TestUsersAndProfiles(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_user_returns_id(self) -> None:
        pool, execute = mock_pool(fetchone={"id": 10})

        with patch("flatpulse.db.get_pool", return_value=pool):
            user_id = await db.upsert_user(123456789, None, "fr")

        self.assertEqual(user_id, 10)
        query = sent_query(execute)
        self.assertIn("ON CONFLICT (telegram_id) DO UPDATE SET", query)
        self.assertIn("COALESCE(EXCLUDED.email, users.email)", query)
        self.assertEqual(sent_params(execute), (123456789, None, "fr"))

    async def test_insert_profile_returns_id(self) -> None:
        pool, execute = mock_pool(fetchone={"id": 5})
        profile = {
            "name": "Carouge 4 pièces",
            "cities": ["Carouge"],
            "max_price": 260000,
        }

        with patch("flatpulse.db.get_pool", return_value=pool):
            profile_id = await db.insert_profile(10, profile)

        self.assertEqual(profile_id, 5)
        self.assertEqual(
            sent_query(execute),
            'INSERT INTO search_profiles ("user_id", "name", "cities", "max_price") '
            "VALUES (%s, %s, %s, %s) RETURNING id",
        )
        self.assertEqual(
            sent_params(execute), [10, "Carouge 4 pièces", ["Carouge"], 260000]
        )

    async def test_insert_profile_unknown_column_raises(self) -> None:
        pool, execute = mock_pool(fetchone={"id": 5})

        with (
            patch("flatpulse.db.get_pool", return_value=pool),
            self.assertRaisesRegex(ValueError, "is_active"),
        ):
            await db.insert_profile(10, {"name": "x", "is_active": False})
        execute.assert_not_awaited()
