"""SQLAlchemy ORM models for all database tables."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_tool: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_transcript: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="processing")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="MessageModel.position"
    )
    extraction_result: Mapped["ExtractionResultModel | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    context_packs: Mapped[list["ContextPackModel"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    session: Mapped["SessionModel"] = relationship(back_populates="messages")


class ExtractionResultModel(Base):
    __tablename__ = "extraction_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decisions: Mapped[dict] = mapped_column(JSONB, default=list)
    tasks: Mapped[dict] = mapped_column(JSONB, default=list)
    open_questions: Mapped[dict] = mapped_column(JSONB, default=list)
    entities: Mapped[dict] = mapped_column(JSONB, default=list)
    code_snippets: Mapped[dict] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    session: Mapped["SessionModel"] = relationship(back_populates="extraction_result")


class ContextPackModel(Base):
    __tablename__ = "context_packs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    target_tool: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(20), default="markdown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    session: Mapped["SessionModel"] = relationship(back_populates="context_packs")


class MemoryItemModel(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)  # OpenAI small model dim
    source: Mapped[str] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    importance: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(50), default="active")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

class RepoModel(Base):
    __tablename__ = "repos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_slug: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    commits: Mapped[list["CommitModel"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan", order_by="CommitModel.created_at.desc()"
    )

class CommitModel(Base):
    __tablename__ = "commits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=False
    )
    commit_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    parent_commit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commits.id", ondelete="SET NULL"), nullable=True
    )
    branch_name: Mapped[str] = mapped_column(String(255), default="main")
    author_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_type: Mapped[str] = mapped_column(String(50), default="user") # user, llm, agent, system
    project_root: Mapped[str | None] = mapped_column(String(512), nullable=True)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # State snapshots
    summary: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    decisions: Mapped[dict] = mapped_column(JSONB, default=list)
    assumptions: Mapped[dict] = mapped_column(JSONB, default=list)
    tasks: Mapped[dict] = mapped_column(JSONB, default=list)
    open_questions: Mapped[dict] = mapped_column(JSONB, default=list)
    entities: Mapped[dict] = mapped_column(JSONB, default=list)
    artifacts: Mapped[dict] = mapped_column(JSONB, default=list)
    context_blob: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    raw_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    repo: Mapped["RepoModel"] = relationship(back_populates="commits")
    parent_commit: Mapped["CommitModel"] = relationship(remote_side=[id])


# ── V4 Chat Models ────────────────────────────────────────────────────────────

class ChatSession(Base):
    """A live conversation runtime inside a Space (Repo)."""
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="")
    active_provider: Mapped[str] = mapped_column(String(50), default="openrouter")
    active_model: Mapped[str] = mapped_column(String(255), default="")
    # The commit that was used to seed this session at open time
    seeded_commit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commits.id", ondelete="SET NULL"), nullable=True
    )
    # Forking: which checkpoint this session branched from (None = not a fork)
    forked_from_checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commits.id", ondelete="SET NULL"), nullable=True
    )
    # Branch identity — "main" for primary sessions, custom name for forks
    branch_name: Mapped[str] = mapped_column(String(255), default="main")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    turns: Mapped[list["TurnEvent"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TurnEvent.sequence_number",
    )


class TurnEvent(Base):
    """One user or assistant message turn inside a ChatSession."""
    __tablename__ = "turn_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)   # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="")
    model: Mapped[str] = mapped_column(String(255), default="")
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Optional back-link to a commit that summarises this turn range
    commit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commits.id", ondelete="SET NULL"), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    session: Mapped["ChatSession"] = relationship(back_populates="turns")


class WorkClaim(Base):
    """A lightweight, time-bounded declaration that an agent is actively
    working on something in a space.

    Work claims are advisory, not locks. They make active intent visible
    to other agents before work produces a checkpoint. The skill pack
    teaches agents to check for overlapping claims before starting work
    and to create their own claim after reading state.

    Claims expire at `expires_at`. Expired claims are excluded from the
    state brief by query-time filtering — no background sweep needed.
    Agents explicitly mark claims as `done` or `abandoned` when work
    finishes; if they forget, the claim expires naturally.
    """
    __tablename__ = "work_claims"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent: Mapped[str] = mapped_column(String(100), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(255), default="main")
    base_commit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commits.id", ondelete="SET NULL"),
        nullable=True,
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    intent_type: Mapped[str] = mapped_column(
        String(20), default="implement",
        doc="One of: implement, review, investigate, docs, test",
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active",
        doc="One of: active, done, abandoned",
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

