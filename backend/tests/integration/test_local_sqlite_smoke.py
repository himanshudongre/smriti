"""Local-first SQLite mode — smoke and resolution tests.

Covers:
- db_mode / resolved_database_url resolution (local default, the Postgres
  DATABASE_URL backward-compat bridge, explicit overrides, path override)
- portable JSON type renders JSONB on PostgreSQL, JSON on SQLite
- a persistent file-backed SQLite end-to-end flow (space -> checkpoint ->
  claim -> current state -> note) whose data survives reopening the engine
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import sessionmaker

from app.config import DEFAULT_POSTGRES_URL, Settings
from app.db.database import Base, get_db
from app.db.models import CommitModel, RepoModel
from app.db.types import json_column
from app.main import app


# ── db_mode / URL resolution ─────────────────────────────────────────────────


def _settings(**overrides) -> Settings:
    """Construct Settings hermetically — explicit kwargs win over ambient env."""
    base = {"database_url": "", "smriti_db_mode": "", "smriti_local_db_path": ""}
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_db_mode_defaults_to_local_when_unconfigured():
    s = _settings()
    assert s.db_mode == "local"
    assert s.resolved_database_url.startswith("sqlite:///")
    assert s.resolved_database_url.endswith("smriti.db")


def test_postgres_database_url_preserves_postgres_mode():
    """An explicitly-set Postgres DATABASE_URL keeps Postgres — backward compat."""
    s = _settings(database_url="postgresql://u:p@dbhost:5432/smriti")
    assert s.db_mode == "postgres"
    assert s.resolved_database_url == "postgresql://u:p@dbhost:5432/smriti"


def test_explicit_db_mode_overrides_database_url():
    """SMRITI_DB_MODE=local wins even if a Postgres DATABASE_URL is present."""
    s = _settings(smriti_db_mode="local", database_url="postgresql://u:p@h:5432/db")
    assert s.db_mode == "local"
    assert s.resolved_database_url.startswith("sqlite:///")

    s2 = _settings(smriti_db_mode="postgres")
    assert s2.db_mode == "postgres"
    assert s2.resolved_database_url == DEFAULT_POSTGRES_URL


def test_local_db_path_is_overridable(tmp_path):
    custom = tmp_path / "custom-smriti.db"
    s = _settings(smriti_db_mode="local", smriti_local_db_path=str(custom))
    assert s.db_mode == "local"
    assert s.resolved_database_url.startswith("sqlite:///")
    assert s.resolved_database_url.endswith("custom-smriti.db")


# ── portable types ───────────────────────────────────────────────────────────


def test_portable_json_renders_jsonb_on_postgres_and_json_on_sqlite():
    rendered_pg = json_column().compile(dialect=postgresql.dialect())
    rendered_sqlite = json_column().compile(dialect=sqlite.dialect())
    assert "JSONB" in str(rendered_pg)       # no Postgres regression
    assert "JSON" in str(rendered_sqlite)    # portable on SQLite


# ── persistent file-backed SQLite end-to-end ─────────────────────────────────


def _sqlite_file_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def test_local_sqlite_persistence(tmp_path):
    """A real .db file: full API flow, then data survives an engine reopen."""
    db_file = tmp_path / "smriti.db"
    url = f"sqlite:///{db_file}"

    engine = _sqlite_file_engine(url)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as c:
            r = c.post("/api/v2/repos", json={"name": "Local Smoke Space"})
            assert r.status_code == 201, r.text
            space_id = r.json()["id"]

            r = c.post(
                f"/api/v4/chat/spaces/{space_id}/sessions",
                json={"title": "smoke", "provider": "openrouter", "model": "mock"},
            )
            assert r.status_code == 201, r.text
            session_id = r.json()["id"]

            r = c.post(
                "/api/v4/chat/commit",
                json={
                    "repo_id": space_id,
                    "session_id": session_id,
                    "message": "Local smoke checkpoint",
                    "decisions": ["SQLite local mode works"],
                    "tasks": [{"text": "verify persistence", "intent_hint": "test"}],
                },
            )
            assert r.status_code == 201, r.text
            checkpoint_id = r.json()["id"]

            r = c.post(
                "/api/v5/claims",
                json={
                    "space_id": space_id,
                    "agent": "claude-code",
                    "scope": "local smoke",
                    "intent_type": "test",
                },
            )
            assert r.status_code == 201, r.text

            r = c.get(f"/api/v5/current/spaces/{space_id}")
            assert r.status_code == 200, r.text
            current = r.json()
            assert current["counts"]["checkpoints"] == 1
            assert current["counts"]["active_claims"] == 1

            r = c.post(
                f"/api/v5/checkpoint/{checkpoint_id}/notes",
                json={"text": "local smoke note", "kind": "milestone", "author": "claude-code"},
            )
            assert r.status_code == 201, r.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    # The data must survive a fresh engine opened against the same file.
    assert db_file.exists()
    engine2 = _sqlite_file_engine(url)
    reopened = sessionmaker(autocommit=False, autoflush=False, bind=engine2)()
    try:
        repos = reopened.scalars(select(RepoModel)).all()
        assert [r.name for r in repos] == ["Local Smoke Space"]

        commits = reopened.scalars(select(CommitModel)).all()
        assert len(commits) == 1
        # JSON columns round-trip through SQLite.
        assert commits[0].decisions == ["SQLite local mode works"]
        notes = (commits[0].metadata_ or {}).get("notes") or []
        assert any(n.get("text") == "local smoke note" for n in notes)
    finally:
        reopened.close()
        engine2.dispose()
