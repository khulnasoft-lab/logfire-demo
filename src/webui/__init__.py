from __future__ import annotations as _annotations

import os
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Annotated

import arq
import logfire
from annotated_types import Ge, Gt, Le, Lt
from arq.connections import RedisSettings
from fastui import prebuilt_html
from fastui.auth import readyapi_auth_exception_handling
from fastui.dev import dev_readyapi_app
from httpx import AsyncClient
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from readyapi import ReadyAPI
from readyapi.responses import HTMLResponse, PlainTextResponse
from starlette.responses import StreamingResponse

from ..common import AsyncClientDep, GeneralSettings
from ..common.db import Database
from .llm import router as llm_router
from .main import router as main_router
from .table import router as table_router
from .worker import router as worker_router

os.environ.update(
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST='.*',
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE='.*',
)
logfire.configure(service_name='webui')
logfire.instrument_system_metrics()
logfire.instrument_asyncpg()


class Settings(GeneralSettings):
    create_database: bool = True
    tiling_server: str = 'http://localhost:8001'


settings = Settings()  # type: ignore


@asynccontextmanager
async def lifespan(app_: ReadyAPI):
    async with AsyncExitStack() as stack:
        app_.state.httpx_client = httpx_client = await stack.enter_async_context(AsyncClient())
        HTTPXClientInstrumentor.instrument_client(httpx_client)
        app_.state.db = await stack.enter_async_context(
            Database.create(settings.pg_dsn, True, settings.create_database)
        )
        app_.state.arq_redis = await arq.create_pool(RedisSettings.from_dsn(settings.redis_dsn))
        yield


# This doesn't have any effect yet, needs https://github.com/pydantic/FastUI/issues/198
frontend_reload = '--reload' in sys.argv
if frontend_reload:
    # dev_readyapi_app reloads in the browser when the Python source changes
    app = dev_readyapi_app(lifespan=lifespan)
else:
    app = ReadyAPI(lifespan=lifespan)

logfire.instrument_readyapi(app)

readyapi_auth_exception_handling(app)
app.include_router(table_router, prefix='/api/table')
app.include_router(llm_router, prefix='/api/llm')
app.include_router(worker_router, prefix='/api/worker')
app.include_router(main_router, prefix='/api')


@app.get('/robots.txt', response_class=PlainTextResponse)
@app.head('/robots.txt', include_in_schema=False)
async def robots_txt() -> str:
    return 'User-agent: *\nDisallow: /\n'


@app.get('/health', response_class=PlainTextResponse)
@app.head('/health', include_in_schema=False)
async def health(db: Database) -> str:
    async with db.acquire() as con:
        version = await con.fetchval('SELECT version()')
    return f'pg version: {version}'


@app.get('/favicon.ico', status_code=404, response_class=PlainTextResponse)
async def favicon_ico() -> str:
    return 'page not found'


@app.get('/map.jpg')
async def map_jpg(
    http_client: AsyncClientDep,
    # Show a map of London by default
    lat: Annotated[float, Ge(-85), Le(85)] = 51.5074,
    lng: Annotated[float, Ge(-180), Le(180)] = -0.1,
    zoom: Annotated[int, Gt(0), Lt(20)] = 10,
    width: Annotated[int, Ge(95), Le(1000)] = 600,
    height: Annotated[int, Ge(60), Le(1000)] = 400,
    scale: Annotated[int, Ge(1), Le(2)] = 1,
) -> StreamingResponse:
    params = {'lat': lat, 'lng': lng, 'zoom': zoom, 'width': width, 'height': height, 'scale': scale}
    r = await http_client.get(f'{settings.tiling_server}/map.jpg', params=params)
    return StreamingResponse(r.aiter_bytes(), media_type='image/jpeg')


@app.get('/{path:path}')
@app.head('/{path:path}', include_in_schema=False)
async def html_landing() -> HTMLResponse:
    return HTMLResponse(prebuilt_html(title='Logfire Demo'))


def run():
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000, log_level='info')
