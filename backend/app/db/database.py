"""SQLAlchemy database engine and session management."""

import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger("uvicorn.error")


def _build_engine():
    """Create the SQLAlchemy engine for the resolved database URL.

    Local mode runs against a file-backed SQLite database and needs
    cross-thread access plus durability/concurrency pragmas. Postgres
    mode is unchanged from prior behavior.
    """
    url = settings.resolved_database_url
    if url.startswith("sqlite"):
        sqlite_engine = create_engine(
            url,
            echo=settings.debug,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(sqlite_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        return sqlite_engine

    return create_engine(url, echo=settings.debug)


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


_local_db_ready = False


def bootstrap_local_db() -> None:
    """Ensure the local SQLite database exists with the current schema.

    Idempotent. No-op in Postgres mode — Alembic owns that schema. In
    local mode, creates the parent directory (e.g. ~/.smriti) if needed
    and runs create_all, which creates any missing tables and skips
    existing ones.

    Must run after every ORM model module is imported, so that
    Base.metadata is fully populated before create_all.
    """
    global _local_db_ready
    if _local_db_ready or settings.db_mode != "local":
        return
    db_path = settings.local_db_path
    first_run = not db_path.exists()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    if first_run:
        logger.info("Smriti local SQLite database created at %s", db_path)
    _local_db_ready = True


def get_db():
    """Dependency that yields a database session.

    In local mode the SQLite schema is bootstrapped lazily on first use.
    Running the bootstrap here — rather than at import or app startup —
    keeps the integration test suite, which overrides this dependency,
    fully insulated from the real local database file.
    """
    bootstrap_local_db()
    logger.info("get_db: Creating new session...")
    db = SessionLocal()
    logger.info("get_db: Session created.")
    try:
        logger.info("get_db: Yielding session...")
        yield db
    finally:
        logger.info("get_db: Closing session...")
        db.close()
