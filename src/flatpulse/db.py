"""PostgreSQL access: the shared connection pool and the CRUD helpers (#71).

The pool is opened once at startup with `open_pool(config.database_url)` and closed
at shutdown with `close_pool()`. Every helper borrows a connection from it for a
single statement: leaving the `pool.connection()` block commits, an exception rolls
back. The SQL is written out in each function, no query builder, no ORM.

Expected conflicts are absorbed in SQL (`ON CONFLICT`): a listing seen again is
updated, a notification sent twice is ignored, a known Telegram user is updated.
Any other database error (unreachable server, foreign key to a missing row) is
raised as the psycopg exception, which names the problem; keeping the pipeline up
when a link fails is the caller's job.

Amounts are in centimes (`price_chf`, `charges_chf`, `min_price`, `max_price`).
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from psycopg import AsyncConnection, sql
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from flatpulse.common.models import Listing

type Pool = AsyncConnectionPool[AsyncConnection[DictRow]]

_pool: Pool | None = None

# Columns `insert_profile` accepts: those of search_profiles a profile describes.
# id, user_id, is_active and created_at are not the caller's to set.
PROFILE_COLUMNS = frozenset(
    {
        "name",
        "listing_type",
        "cities",
        "cantons",
        "min_rooms",
        "max_rooms",
        "min_price",
        "max_price",
        "min_surface",
        "required_amenities",
        "pets_required",
        "custom_criteria",
    }
)

_INSERT_LISTING = """
    INSERT INTO listings (
        source_id, external_id, external_url, fingerprint, title, description,
        property_type, price_chf, charges_chf, nb_rooms, surface_m2, floor,
        address, city, canton, postal_code, images
    )
    SELECT
        id, %(external_id)s, %(external_url)s, %(fingerprint)s, %(title)s,
        %(description)s, %(property_type)s, %(price_chf)s, %(charges_chf)s,
        %(nb_rooms)s, %(surface_m2)s, %(floor)s, %(address)s, %(city)s,
        %(canton)s, %(postal_code)s, %(images)s
    FROM sources
    WHERE slug = %(source_slug)s
    ON CONFLICT (source_id, external_id) DO UPDATE SET
        external_url = EXCLUDED.external_url,
        fingerprint = EXCLUDED.fingerprint,
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        property_type = EXCLUDED.property_type,
        price_chf = EXCLUDED.price_chf,
        charges_chf = EXCLUDED.charges_chf,
        nb_rooms = EXCLUDED.nb_rooms,
        surface_m2 = EXCLUDED.surface_m2,
        floor = EXCLUDED.floor,
        address = EXCLUDED.address,
        city = EXCLUDED.city,
        canton = EXCLUDED.canton,
        postal_code = EXCLUDED.postal_code,
        images = EXCLUDED.images
    RETURNING id
"""


async def open_pool(database_url: str) -> Pool:
    """Open the shared pool on `database_url`, waiting for its first connections.

    Called once at startup. An unreachable database raises `psycopg_pool.PoolTimeout`
    here rather than at the first query.

    Raises:
        RuntimeError: The pool is already open.
    """
    global _pool  # noqa: PLW0603 -- the story wants one pool for the whole process
    if _pool is not None:
        raise RuntimeError("The database pool is already open")
    pool: Pool = AsyncConnectionPool(
        database_url,
        open=False,
        connection_class=AsyncConnection[DictRow],
        kwargs={"row_factory": dict_row},
    )
    await pool.open(wait=True)
    _pool = pool
    return pool


def get_pool() -> Pool:
    """The shared pool opened by `open_pool`.

    Raises:
        RuntimeError: `open_pool` has not been called, or the pool was closed.
    """
    if _pool is None:
        raise RuntimeError(
            "The database pool is not open: call open_pool(config.database_url) "
            "at startup"
        )
    return _pool


async def close_pool() -> None:
    """Close the shared pool at shutdown; does nothing if it is not open."""
    global _pool  # noqa: PLW0603 -- forgets the pool `open_pool` stored
    if _pool is not None:
        await _pool.close()
        _pool = None


async def insert_listing(listing: Listing, source_slug: str) -> int:
    """Store `listing` for the source `source_slug` and return its id.

    A listing already stored for this source and `external_id` is updated in place
    and keeps its id: its fingerprint changes with its price or title. Columns the
    scrapers don't produce (`enriched`, `first_seen_at`, `is_active`) are left alone.

    Raises:
        LookupError: No row of `sources` has the slug `source_slug`.
    """
    params = {
        "source_slug": source_slug,
        "external_id": listing.external_id,
        "external_url": listing.external_url,
        "fingerprint": listing.fingerprint,
        "title": listing.title,
        "description": listing.description,
        # The value ("apartment"), as the CHECK expects: psycopg would send the name.
        "property_type": listing.property_type and listing.property_type.value,
        "price_chf": listing.price_chf,
        "charges_chf": listing.charges_chf,
        "nb_rooms": listing.nb_rooms,
        "surface_m2": listing.surface_m2,
        "floor": listing.floor,
        "address": listing.address,
        "city": listing.city,
        "canton": listing.canton,
        "postal_code": listing.postal_code,
        "images": list(listing.images),  # a list is a PostgreSQL array, a tuple not
    }
    async with get_pool().connection() as conn:
        cursor = await conn.execute(_INSERT_LISTING, params)
        row = await cursor.fetchone()
    if row is None:
        raise LookupError(
            f"Unknown source {source_slug!r}: no row in sources has this slug "
            f"({listing.external_url})"
        )
    return int(row["id"])


async def get_active_profiles() -> list[dict[str, Any]]:
    """Every active search profile of an active user, with the user's `user_plan`.

    Each dict holds the columns of `search_profiles` plus `user_plan`.
    """
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            """
            SELECT sp.*, u.plan AS user_plan
            FROM search_profiles sp
            JOIN users u ON u.id = sp.user_id
            WHERE sp.is_active AND u.is_active
            ORDER BY sp.id
            """
        )
        return await cursor.fetchall()


async def insert_notification(
    user_id: int, listing_id: int, profile_id: int, channel: str, score: float
) -> None:
    """Record that `listing_id` was sent to `user_id` on `channel`.

    A notification already recorded for this user, listing and channel is left as
    it is: recording it twice is not an error.
    """
    async with get_pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO notifications
                (user_id, listing_id, profile_id, channel, match_score)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, listing_id, channel) DO NOTHING
            """,
            (user_id, listing_id, profile_id, channel, score),
        )


async def check_notification_exists(
    user_id: int, listing_id: int, channel: str
) -> bool:
    """Whether `listing_id` was already sent to `user_id` on `channel`."""
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM notifications
                WHERE user_id = %s AND listing_id = %s AND channel = %s
            ) AS exists
            """,
            (user_id, listing_id, channel),
        )
        row = await cursor.fetchone()
    return row is not None and bool(row["exists"])


async def count_notifications_since(user_id: int, since: datetime) -> int:
    """How many notifications `user_id` received from `since` on, all channels."""
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            """
            SELECT COUNT(*) AS count FROM notifications
            WHERE user_id = %s AND sent_at >= %s
            """,
            (user_id, since),
        )
        row = await cursor.fetchone()
    return 0 if row is None else int(row["count"])


async def upsert_user(telegram_id: int, email: str | None, lang: str) -> int:
    """Create or update the user with this `telegram_id` and return their id.

    A known user gets the new `lang`; their email is replaced only by a non-null
    one, so a `/start` without email keeps the address given earlier.
    """
    async with get_pool().connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO users (telegram_id, email, lang)
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE SET
                email = COALESCE(EXCLUDED.email, users.email),
                lang = EXCLUDED.lang
            RETURNING id
            """,
            (telegram_id, email, lang),
        )
        row = await cursor.fetchone()
    if row is None:  # RETURNING always yields the row inserted or updated
        raise RuntimeError(f"upsert_user returned no id for {telegram_id}")
    return int(row["id"])


async def insert_profile(user_id: int, profile_data: Mapping[str, object]) -> int:
    """Create a search profile for `user_id` from `profile_data`; return its id.

    `profile_data` maps columns of `search_profiles` (see `PROFILE_COLUMNS`) to
    their values; a column left out takes its default. Prices are in centimes.

    Raises:
        ValueError: A key of `profile_data` is not in `PROFILE_COLUMNS`.
    """
    unknown = sorted(set(profile_data) - PROFILE_COLUMNS)
    if unknown:
        raise ValueError(f"Unknown search profile columns: {', '.join(unknown)}")
    columns = ["user_id", *profile_data]
    query = sql.SQL("INSERT INTO search_profiles ({}) VALUES ({}) RETURNING id").format(
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() * len(columns)),
    )
    async with get_pool().connection() as conn:
        cursor = await conn.execute(query, [user_id, *profile_data.values()])
        row = await cursor.fetchone()
    if row is None:  # RETURNING always yields the inserted row
        raise RuntimeError(f"insert_profile returned no id for user {user_id}")
    return int(row["id"])
