import asyncio
from concurrent.futures import ThreadPoolExecutor
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import AsyncEngine

import backend.app.models  # noqa: F401  (registers tables on Base.metadata)
from backend.app.db.base import Base, UTCDateTime
from backend.app.db.session import create_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from backend.app.core.config import get_settings

    return get_settings().database_url


def _render_item(type_, obj, autogen_context):
    # Migrations stay free of app imports: emit the portable impl for our TypeDecorators.
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite needs batch mode for ALTER
        compare_type=True,
        render_item=_render_item,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


def run_migrations_online() -> None:
    def run() -> None:
        asyncio.run(_run_async(create_engine(_database_url())))

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        run()
        return
    # Called from inside a running loop (e.g. test harnesses): use a worker thread.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(run).result()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
