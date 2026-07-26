from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol


class _Logger(Protocol):
    def info(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...


@asynccontextmanager
async def lifespan(
    app: Any,
    *,
    logger: _Logger,
    ensure_migrations: Callable[[Any], None],
    get_db_path: Callable[[], Any],
    load_config: Callable[[], Any],
    init_db: Callable[[], None],
    seed_default_sources: Callable[[], Any],
    start_usage_writer: Callable[[], Any],
    stop_usage_writer: Callable[[], Any],
    start_worker: Callable[[], None],
    stop_worker: Callable[[], bool],
) -> AsyncIterator[Any]:
    """Run application services in their required startup and shutdown order."""
    logger.info("KI server starting — init DB + worker")
    ensure_migrations(get_db_path())
    load_config()
    init_db()
    seed_default_sources()
    start_usage_writer()
    worker_started = False
    worker_quiesced = False
    try:
        start_worker()
        worker_started = True
        logger.info("KI server ready")
        try:
            yield
        finally:
            logger.info("KI server shutting down")
            worker_quiesced = stop_worker() is True
    finally:
        if not worker_started or worker_quiesced:
            stop_usage_writer()
        else:
            logger.error(
                "Ingest worker is still active; keeping usage writer available until process exit"
            )
