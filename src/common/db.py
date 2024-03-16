import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Self, Annotated
from urllib.parse import urlparse

from fastapi import Request, Depends

import logfire
import asyncpg
from asyncpg.connection import Connection

__all__ = ('Database',)


@dataclass
class _Database:
    """
    Wrapper for asyncpg with some utilities and usable as a fastapi dependency.
    """

    _pool: asyncpg.Pool

    @classmethod
    @asynccontextmanager
    async def create(cls, dsn: str, prepare_db: bool = False) -> AsyncIterator[Self]:
        if prepare_db:
            with logfire.span('prepare DB'):
                await _prepare_db(dsn)
        pool = await asyncpg.create_pool(dsn)
        try:
            yield cls(_pool=pool)
        finally:
            await asyncio.wait_for(pool.close(), timeout=2.0)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Connection]:
        con = await self._pool.acquire()
        try:
            yield con
        finally:
            await self._pool.release(con)

    @asynccontextmanager
    async def acquire_trans(self) -> AsyncIterator[Connection]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn


def _get_db(request: Request) -> _Database:
    return request.app.state.db


Database = Annotated[_Database, Depends(_get_db)]


async def _prepare_db(dsn: str) -> None:
    parse_result = urlparse(dsn)
    database = parse_result.path.lstrip('/')
    server_dsn = dsn[: dsn.rindex('/')]
    with logfire.span('check and create DB'):
        conn = await asyncpg.connect(server_dsn)
        try:
            db_exists = await conn.fetchval('SELECT 1 FROM pg_database WHERE datname = $1', database)
            if not db_exists:
                await conn.execute(f'CREATE DATABASE {database}')
        finally:
            await conn.close()

    with logfire.span('create schema'):
        conn = await asyncpg.connect(dsn)
        try:
            async with conn.transaction():
                await _create_schema(conn)
        finally:
            await conn.close()


async def _create_schema(conn: Connection) -> None:
    await conn.execute("""
CREATE TABLE IF NOT EXISTS cities (
    id INT PRIMARY KEY,
    city TEXT NOT NULL,
    city_ascii TEXT NOT NULL,
    lat NUMERIC NOT NULL,
    lng NUMERIC NOT NULL,
    country TEXT NOT NULL,
    iso2 TEXT NOT NULL,
    iso3 TEXT NOT NULL,
    admin_name TEXT,
    capital TEXT,
    population INT NOT NULL
);
CREATE INDEX IF NOT EXISTS cities_country_idx ON cities (country);
CREATE INDEX IF NOT EXISTS cities_iso3_idx ON cities (iso3);
CREATE INDEX IF NOT EXISTS cities_population_idx ON cities (population desc);

CREATE TABLE IF NOT EXISTS chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS chats_created_at_idx ON chats (created_at desc);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    cost INT
);
CREATE INDEX IF NOT EXISTS messages_chat_id_idx ON messages (chat_id);
CREATE INDEX IF NOT EXISTS messages_created_at_idx ON messages (created_at);
""")
    from .cities import create_cities

    await create_cities(conn)
