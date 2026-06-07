import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.session import build_async_database_url, get_db_session


def test_build_async_database_url_from_psycopg_url() -> None:
    database_url = "postgresql+psycopg://hezo_app:password@localhost:15432/hezo_dev"

    async_database_url = build_async_database_url(database_url)

    assert async_database_url == "postgresql+asyncpg://hezo_app:password@localhost:15432/hezo_dev"


def test_build_async_database_url_from_plain_postgresql_url() -> None:
    database_url = "postgresql://hezo_app:password@localhost:15432/hezo_dev"

    async_database_url = build_async_database_url(database_url)

    assert async_database_url == "postgresql+asyncpg://hezo_app:password@localhost:15432/hezo_dev"


def test_build_async_database_url_keeps_asyncpg_url() -> None:
    database_url = "postgresql+asyncpg://hezo_app:password@localhost:15432/hezo_dev"

    async_database_url = build_async_database_url(database_url)

    assert async_database_url == database_url


def test_base_metadata_is_available() -> None:
    assert Base.metadata is not None


def test_get_db_session_yields_async_session_without_connecting() -> None:
    async def consume_session() -> None:
        session_generator = get_db_session()
        session = await anext(session_generator)
        try:
            assert isinstance(session, AsyncSession)
        finally:
            await session_generator.aclose()

    asyncio.run(consume_session())
