"""Portable SQLAlchemy column types.

Smriti's ORM models target PostgreSQL in the shared/team mode and SQLite
in the local/solo mode. These helpers render the strong PostgreSQL type
on the ``postgresql`` dialect and a portable equivalent everywhere else
(SQLite), so the same models and the same ``create_all`` work against
both backends with no per-dialect substitution.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeEngine

from pgvector.sqlalchemy import Vector


def json_column() -> TypeEngine:
    """JSON storage column.

    Renders as ``JSONB`` on PostgreSQL (unchanged from prior behavior)
    and as generic ``JSON`` (TEXT-backed) on SQLite.
    """
    return JSON().with_variant(JSONB(), "postgresql")


def embedding_column(dim: int) -> TypeEngine:
    """Vector embedding column.

    Renders as a pgvector ``VECTOR`` on PostgreSQL and as generic
    ``JSON`` on SQLite. Local mode does not provide vector search; the
    column only needs to round-trip so the legacy memories table can be
    created on SQLite.
    """
    return Vector(dim).with_variant(JSON(), "sqlite")
