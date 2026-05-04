"""SQLite-first regression test for the repos.project_root migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def _load_migration():
    path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "2026_05_04_0300_d1e2f3a4b5c6_add_project_root_to_repos.py"
    )
    spec = importlib.util.spec_from_file_location("project_root_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_project_root_migration_upgrade_and_downgrade_on_sqlite(monkeypatch):
    migration = _load_migration()
    engine = create_engine("sqlite://")

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE repos (id VARCHAR PRIMARY KEY)"))
        context = MigrationContext.configure(conn)
        operations = Operations(context)
        monkeypatch.setattr(migration, "op", operations)

        migration.upgrade()
        columns = {c["name"]: c for c in inspect(conn).get_columns("repos")}
        assert columns["project_root"]["nullable"] is True

        migration.downgrade()
        columns = {c["name"] for c in inspect(conn).get_columns("repos")}
        assert "project_root" not in columns
