"""Integration test configuration — uses SQLite in-memory database.

This conftest overrides the FastAPI app's `get_db` dependency to use
a fresh in-memory SQLite database for each test session, enabling
full API integration tests without requiring PostgreSQL.

JSONB columns are mapped to JSON (TEXT-backed) for SQLite compatibility.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign keys in SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Map JSONB → JSON for SQLite (JSONB is Postgres-only)
    # We temporarily swap the impl so create_all works on SQLite
    _render_original = JSONB().compile

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        # Replace JSONB with JSON in DDL statements for SQLite
        if "JSONB" in statement:
            statement = statement.replace("JSONB", "JSON")
        if "VECTOR" in statement:
            statement = statement.replace("VECTOR", "JSON")
        return statement, parameters

    # Create tables, mapping JSONB and Vector for SQLite
    from sqlalchemy.dialects import sqlite as sqlite_dialect
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    from pgvector.sqlalchemy import Vector

    original_visit_jsonb = getattr(SQLiteTypeCompiler, "visit_JSONB", None)
    original_visit_vector = getattr(SQLiteTypeCompiler, "visit_vector", None)
    
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"
    SQLiteTypeCompiler.visit_vector = lambda self, type_, **kw: "JSON"

    Base.metadata.create_all(bind=engine)

    # Restore
    if original_visit_jsonb:
        SQLiteTypeCompiler.visit_JSONB = original_visit_jsonb
    else:
        try:
            del SQLiteTypeCompiler.visit_JSONB
        except AttributeError:
            pass

    if original_visit_vector:
        SQLiteTypeCompiler.visit_vector = original_visit_vector
    else:
        try:
            del SQLiteTypeCompiler.visit_vector
        except AttributeError:
            pass

    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden DB dependency."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
