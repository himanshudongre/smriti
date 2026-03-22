"""
V4 Chat API routes.

Session lifecycle:
  POST   /api/v4/chat/spaces/{repo_id}/sessions       – create session (seeds context from head commit)
  GET    /api/v4/chat/spaces/{repo_id}/sessions/{sid} – get session
  GET    /api/v4/chat/spaces/{repo_id}/sessions/{sid}/turns – list turns

Conversation:
  POST   /api/v4/chat/send                             – send a user message, get assistant reply
  POST   /api/v4/chat/commit                           – manually commit session state as a Commit

Space head:
  GET    /api/v4/chat/spaces/{repo_id}/head            – latest commit + latest session

Provider status:
  GET    /api/v4/chat/providers                        – list provider config status
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ChatSession, CommitModel, RepoModel, TurnEvent
from app.config_loader import get_config, providers_status, ProviderNotConfiguredError
from app.providers.registry import get_adapter, get_mock_adapter

router = APIRouter(prefix="/chat", tags=["chat-v4"])

DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000000a")
MAX_CONTEXT_TURNS = 20   # how many recent turns to pass as conversation history


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_repo(repo_id: uuid.UUID, db: Session) -> RepoModel:
    repo = db.get(RepoModel, repo_id) if repo_id else None
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Space not found")
    return repo


def _get_latest_commit(repo_id: uuid.UUID, db: Session) -> CommitModel | None:
    stmt = (
        select(CommitModel)
        .where(CommitModel.repo_id == repo_id, CommitModel.branch_name == "main")
        .order_by(CommitModel.created_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def _get_latest_commit_on_branch(repo_id: uuid.UUID, branch: str, db: Session) -> CommitModel | None:
    """Return the most recent commit on a specific branch within a repo."""
    stmt = (
        select(CommitModel)
        .where(CommitModel.repo_id == repo_id, CommitModel.branch_name == branch)
        .order_by(CommitModel.created_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def _get_checkpoints_for_scope(repo_id: uuid.UUID, db: Session, scope: str) -> list[CommitModel]:
    """Return checkpoints based on memory scope (oldest-first)."""
    n = 3 if scope == "latest_3" else 1
    stmt = (
        select(CommitModel)
        .where(CommitModel.repo_id == repo_id, CommitModel.branch_name == "main")
        .order_by(CommitModel.created_at.desc())
        .limit(n)
    )
    return list(reversed(db.scalars(stmt).all()))  # oldest first


def _walk_ancestors(commit: CommitModel, db: Session, n: int) -> list[CommitModel]:
    """Walk parent chain and return up to n checkpoints, oldest-first."""
    chain = [commit]
    current = commit
    for _ in range(n - 1):
        if not current.parent_commit_id:
            break
        parent = db.get(CommitModel, current.parent_commit_id)
        if not parent:
            break
        chain.append(parent)
        current = parent
    return list(reversed(chain))  # oldest first


def _resolve_checkpoints(
    repo_id: Optional[uuid.UUID],
    mounted_checkpoint_id: Optional[str],
    scope: str,
    db: Session,
) -> list[CommitModel]:
    """
    Resolve which checkpoints to mount for context building.

    Priority:
    1. If mounted_checkpoint_id is set, use that specific checkpoint as anchor.
       - scope latest_1 → only that checkpoint
       - scope latest_3 → that checkpoint + up to 2 ancestors
    2. Otherwise fall back to _get_checkpoints_for_scope (latest N from repo head).
    """
    if mounted_checkpoint_id:
        try:
            commit = db.get(CommitModel, uuid.UUID(mounted_checkpoint_id))
        except (ValueError, Exception):
            commit = None
        if commit:
            n = 3 if scope == "latest_3" else 1
            return _walk_ancestors(commit, db, n)
    if repo_id:
        return _get_checkpoints_for_scope(repo_id, db, scope)
    return []


def build_prompt_from_checkpoints(checkpoints: list[CommitModel], recent_messages: list[TurnEvent], user_input: str) -> str:
    """Reconstructs the conversation context from Smriti memory (supports multiple checkpoints)."""
    lines = ["You are continuing a conversation.\n"]

    for i, ckpt in enumerate(checkpoints):
        label = f"Checkpoint {i + 1}" if len(checkpoints) > 1 else "Checkpoint"
        if ckpt.summary:
            lines.append(f"{label} Summary:")
            lines.append(ckpt.summary + "\n")
        if ckpt.decisions:
            lines.append(f"{label} Key Decisions:")
            for d in ckpt.decisions:
                lines.append(f"- {d}")
            lines.append("")
        if ckpt.tasks:
            lines.append(f"{label} Open Tasks:")
            for t in ckpt.tasks:
                lines.append(f"- {t}")
            lines.append("")

    if recent_messages:
        lines.append("Recent Conversation:")
        for m in recent_messages:
            role = "User" if m.role == "user" else "Assistant"
            lines.append(f"{role}: {m.content}")
        lines.append("")

    lines.append("User Query:")
    lines.append(user_input)

    return "\n".join(lines)


# Keep single-checkpoint variant for backwards compatibility (used internally)
def build_prompt_from_checkpoint(checkpoint: CommitModel | None, recent_messages: list[TurnEvent], user_input: str) -> str:
    checkpoints = [checkpoint] if checkpoint else []
    return build_prompt_from_checkpoints(checkpoints, recent_messages, user_input)


def _generate_commit_hash(repo_id: str, message: str) -> str:
    content = {"repo_id": repo_id, "message": message, "ts": _utcnow().isoformat()}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


# ── Response/Request schemas ──────────────────────────────────────────────────

class SessionResponse(BaseModel):
    id: uuid.UUID
    repo_id: Optional[uuid.UUID]
    title: str
    active_provider: str
    active_model: str
    seeded_commit_id: Optional[uuid.UUID]
    forked_from_checkpoint_id: Optional[uuid.UUID]
    branch_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TurnResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    provider: str
    model: str
    sequence_number: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateSessionRequest(BaseModel):
    repo_id: Optional[str] = None
    title: str = ""
    provider: str = ""
    model: str = ""
    seed_from: str = "head"   # "head" | "none" | "<commit_id>"


class SendMessageRequest(BaseModel):
    session_id: str
    repo_id: Optional[str] = None
    provider: str
    model: str
    message: str
    use_mock: bool = Field(
        False,
        description="If true, use the deterministic mock adapter (no API key required)"
    )
    memory_scope: str = Field(
        "latest_1",
        description="Memory scope for context: 'latest_1' or 'latest_3'"
    )
    mounted_checkpoint_id: Optional[str] = Field(
        None,
        description="Explicit checkpoint id to anchor context. If set, overrides latest-head selection."
    )
    history_base_seq: Optional[int] = Field(
        None,
        description="When mounting a specific commit, the sequence number of the last turn before mounting. Only turns with sequence_number > history_base_seq are included as history, preventing pre-mount turns from bleeding into the mounted context."
    )


class SendMessageResponse(BaseModel):
    reply: str
    session_id: uuid.UUID
    turn_count: int
    provider: str
    model: str


class ManualCommitRequest(BaseModel):
    repo_id: str
    session_id: str
    message: str
    summary: str = ""
    objective: str = ""
    decisions: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class CommitResponse(BaseModel):
    id: uuid.UUID
    repo_id: uuid.UUID
    commit_hash: str
    parent_commit_id: Optional[uuid.UUID]
    branch_name: str
    message: str
    summary: str
    objective: str
    decisions: list
    tasks: list
    open_questions: list
    entities: list
    created_at: datetime

    model_config = {"from_attributes": True}


class HeadResponse(BaseModel):
    repo_id: uuid.UUID
    commit_hash: Optional[str]
    commit_id: Optional[uuid.UUID]
    summary: Optional[str]
    objective: Optional[str]
    latest_session_id: Optional[uuid.UUID]
    latest_session_title: Optional[str]


# ── Session endpoints ─────────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session_generic(payload: CreateSessionRequest, db: Session = Depends(get_db)):
    repo_id = uuid.UUID(payload.repo_id) if payload.repo_id else None
    if repo_id:
        _get_repo(repo_id, db)

    seeded_commit_id = None
    if repo_id and payload.seed_from == "head":
        latest = _get_latest_commit(repo_id, db)
        if latest:
            seeded_commit_id = latest.id
    elif payload.seed_from not in ("none", "head", ""):
        try:
            c = db.get(CommitModel, uuid.UUID(payload.seed_from))
            if c and c.repo_id == repo_id:
                seeded_commit_id = c.id
        except (ValueError, Exception):
            pass

    cfg = get_config()
    provider = payload.provider or cfg.chat.default_provider
    title = payload.title or f"Session {_utcnow().strftime('%b %d %H:%M')}"

    session = ChatSession(
        repo_id=repo_id,
        title=title,
        active_provider=provider,
        active_model=payload.model,
        seeded_commit_id=seeded_commit_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[SessionResponse])
def list_recent_sessions(db: Session = Depends(get_db)):
    stmt = select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(50)
    return db.scalars(stmt).all()


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session_generic(session_id: uuid.UUID, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions/{session_id}/title", response_model=SessionResponse)
def generate_session_title(session_id: uuid.UUID, db: Session = Depends(get_db)):
    """Generate a meaningful title for a session using the background intelligence model."""
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    turns = db.scalars(
        select(TurnEvent)
        .where(TurnEvent.session_id == session_id)
        .order_by(TurnEvent.sequence_number)
        .limit(4)
    ).all()
    if not turns:
        raise HTTPException(status_code=400, detail="No turns to generate title from")

    transcript = "\n".join(f"{t.role.upper()}: {t.content[:300]}" for t in turns)
    prompt = (
        "Generate a concise 3–5 word title for this conversation. "
        "Output ONLY the title, no quotes, no punctuation, no explanation.\n\n"
        f"{transcript}\n\nTitle:"
    )

    try:
        cfg = get_config()
        bg_provider = cfg.background.provider
        bg_model = cfg.background.model
        adapter = get_adapter(bg_provider, allow_mock=False)
        raw_title = adapter.send([{"role": "user", "content": prompt}], model=bg_model).strip()
        title = raw_title.strip("\"'").strip()
        if len(title) > 60:
            title = title[:60]
        session.title = title
        session.updated_at = _utcnow()
        db.commit()
        db.refresh(session)
    except Exception:
        pass  # Return unchanged session if title generation fails

    return session


@router.get("/sessions/{session_id}/turns", response_model=list[TurnResponse])
def list_turns_generic(session_id: uuid.UUID, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    stmt = select(TurnEvent).where(TurnEvent.session_id == session_id).order_by(TurnEvent.sequence_number)
    return db.scalars(stmt).all()


class AttachSessionRequest(BaseModel):
    repo_id: str

@router.put("/sessions/{session_id}/attach", response_model=SessionResponse)
def attach_session(session_id: uuid.UUID, payload: AttachSessionRequest, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    repo_id = uuid.UUID(payload.repo_id)
    _get_repo(repo_id, db)
    
    session.repo_id = repo_id
    # Update turns to match new namespace
    from sqlalchemy import update
    db.execute(update(TurnEvent).where(TurnEvent.session_id == session_id).values(repo_id=repo_id))
    db.commit()
    db.refresh(session)
    return session


# Legacy detail routes for debug views
@router.post("/spaces/{repo_id}/sessions", response_model=SessionResponse, status_code=201)
def create_session(
    repo_id: uuid.UUID,
    payload: CreateSessionRequest,
    db: Session = Depends(get_db),
):
    payload.repo_id = str(repo_id)
    return create_session_generic(payload, db)

@router.get("/spaces/{repo_id}/sessions/{session_id}", response_model=SessionResponse)
def get_session(
    repo_id: uuid.UUID,
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    return get_session_generic(session_id, db)

@router.get("/spaces/{repo_id}/sessions/{session_id}/turns", response_model=list[TurnResponse])
def list_turns(
    repo_id: uuid.UUID,
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    return list_turns_generic(session_id, db)


# ── Send endpoint ─────────────────────────────────────────────────────────────

@router.post("/send", response_model=SendMessageResponse)
def send_message(payload: SendMessageRequest, db: Session = Depends(get_db)):
    """
    Send a user message and receive an assistant reply.

    Context strategy:
    - On the FIRST user turn (sequence_number == 0): if the session has a
      seeded_commit_id, inject a system message built from that commit snapshot.
    - On subsequent turns: pass only the recent session turns as history.
    - Provider switching: handled naturally — the new provider receives all
      prior turns as conversation history (no extra re-injection).
    """
    session_id = uuid.UUID(payload.session_id)
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    repo_id = session.repo_id

    if not payload.model:
        raise HTTPException(status_code=400, detail="Model must be specified")

    # Determine next sequence number
    stmt = (
        select(TurnEvent)
        .where(TurnEvent.session_id == session_id)
        .order_by(TurnEvent.sequence_number.desc())
        .limit(1)
    )
    last_turn = db.scalars(stmt).first()
    next_seq = (last_turn.sequence_number + 1) if last_turn else 0

    # Determine effective checkpoint anchor.
    #
    # Priority order:
    # 1. Explicit mounted_checkpoint_id from request (user is temporarily mounting a
    #    specific checkpoint in an existing session — the isolation boundary is
    #    history_base_seq supplied by the frontend at mount time).
    # 2. session.forked_from_checkpoint_id (permanent fork — the session branched from
    #    this checkpoint and has no inherited live turns; history_base_seq is 0).
    # 3. Scope-based HEAD resolution (normal HEAD mode).
    effective_checkpoint_id = payload.mounted_checkpoint_id
    effective_base_seq: Optional[int] = payload.history_base_seq
    is_isolated = False

    if effective_checkpoint_id is not None and effective_base_seq is not None:
        # Case 1: explicit temporary mount
        is_isolated = True
    elif effective_checkpoint_id is None and session.forked_from_checkpoint_id is not None:
        # Case 2: forked session — auto-inherit, treat start-of-session as boundary
        effective_checkpoint_id = str(session.forked_from_checkpoint_id)
        effective_base_seq = 0
        is_isolated = True

    checkpoints = _resolve_checkpoints(repo_id, effective_checkpoint_id, payload.memory_scope, db)
    latest_checkpoint = checkpoints[-1] if checkpoints else None

    # Get recent messages using the appropriate isolation boundary.
    #
    # Isolated mode (explicit mount OR forked session): only turns with
    # sequence_number > effective_base_seq are included, so pre-fork / pre-mount
    # turns from other branches cannot bleed in.
    #
    # HEAD mode: turns since the latest checkpoint was committed.
    history_stmt = (
        select(TurnEvent)
        .where(TurnEvent.session_id == session_id, TurnEvent.role != "system")
    )
    if is_isolated:
        history_stmt = history_stmt.where(TurnEvent.sequence_number > effective_base_seq)
    elif latest_checkpoint:
        # HEAD mode: turns since the checkpoint was created
        history_stmt = history_stmt.where(TurnEvent.created_at >= latest_checkpoint.created_at)

    history_stmt = history_stmt.order_by(TurnEvent.sequence_number.asc()).limit(MAX_CONTEXT_TURNS)
    recent_turns = db.scalars(history_stmt).all()

    # Reconstruct the unified prompt using Smriti memory engine (scope-aware)
    prompt_text = build_prompt_from_checkpoints(checkpoints, recent_turns, payload.message)
    
    # Store user turn in DB (for future memory queries), but we send the reconstructed prompt to the LLM
    user_turn = TurnEvent(
        session_id=session_id,
        repo_id=repo_id,
        role="user",
        content=payload.message,
        provider=payload.provider,
        model=payload.model,
        sequence_number=next_seq,
    )
    db.add(user_turn)
    db.flush()

    # The reconstructed prompt bypasses standard chat roles to ensure strict cross-model continuation 
    messages = [{"role": "user", "content": prompt_text}]

    # Select adapter
    try:
        adapter = (
            get_mock_adapter()
            if payload.use_mock
            else get_adapter(payload.provider, allow_mock=False)
        )
    except ProviderNotConfiguredError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Call provider
    try:
        reply_text = adapter.send(messages, model=payload.model)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")

    # Store assistant turn
    assistant_turn = TurnEvent(
        session_id=session_id,
        repo_id=repo_id,
        role="assistant",
        content=reply_text,
        provider=payload.provider,
        model=payload.model,
        sequence_number=next_seq + 1,
    )
    db.add(assistant_turn)

    # Update session active provider/model
    session.active_provider = payload.provider
    session.active_model = payload.model
    session.updated_at = _utcnow()

    db.commit()

    turn_count = next_seq + 2  # user + assistant
    return SendMessageResponse(
        reply=reply_text,
        session_id=session_id,
        turn_count=turn_count,
        provider=payload.provider,
        model=payload.model,
    )


# ── Manual commit endpoint ────────────────────────────────────────────────────

@router.post("/commit", response_model=CommitResponse, status_code=201)
def manual_commit(payload: ManualCommitRequest, db: Session = Depends(get_db)):
    """
    Manually create a Commit from the current session state.
    The commit captures whatever structured state the user provides.
    """
    repo_id = uuid.UUID(payload.repo_id)
    session_id = uuid.UUID(payload.session_id)

    repo = _get_repo(repo_id, db)
    session = db.get(ChatSession, session_id)
    if not session or session.repo_id != repo_id:
        raise HTTPException(status_code=404, detail="Session not found")

    # Derive branch identity from the session — the session row is the source of truth.
    # For main-branch sessions: parent = latest main commit (existing behaviour).
    # For fork-branch sessions: parent = latest commit on the session's own branch,
    #   falling back to the fork source checkpoint when no branch-local commits exist yet.
    session_branch = session.branch_name  # e.g. "main" or "branch-2026-03-21"

    if session_branch == "main":
        parent = _get_latest_commit(repo_id, db)
    else:
        parent = _get_latest_commit_on_branch(repo_id, session_branch, db)
        if parent is None and session.forked_from_checkpoint_id is not None:
            # First checkpoint on this fork — its parent is the fork source
            parent = db.get(CommitModel, session.forked_from_checkpoint_id)

    parent_id = parent.id if parent else None

    commit_hash = _generate_commit_hash(str(repo_id), payload.message)

    commit = CommitModel(
        repo_id=repo_id,
        commit_hash=commit_hash,
        parent_commit_id=parent_id,
        branch_name=session_branch,
        author_agent=session.active_provider,
        author_type="llm",
        message=payload.message,
        summary=payload.summary,
        objective=payload.objective,
        decisions=payload.decisions,
        tasks=payload.tasks,
        open_questions=payload.open_questions,
        entities=payload.entities,
        metadata_={"session_id": str(session_id)},
    )
    db.add(commit)
    repo.updated_at = _utcnow()
    db.commit()
    db.refresh(commit)
    return commit


# ── Head endpoint ─────────────────────────────────────────────────────────────

@router.get("/spaces/{repo_id}/head", response_model=HeadResponse)
def get_head(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return the latest commit + latest session metadata for a Space."""
    _get_repo(repo_id, db)

    latest_commit = _get_latest_commit(repo_id, db)

    # Latest session
    session_stmt = (
        select(ChatSession)
        .where(ChatSession.repo_id == repo_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(1)
    )
    latest_session = db.scalars(session_stmt).first()

    return HeadResponse(
        repo_id=repo_id,
        commit_hash=latest_commit.commit_hash if latest_commit else None,
        commit_id=latest_commit.id if latest_commit else None,
        summary=latest_commit.summary if latest_commit else None,
        objective=latest_commit.objective if latest_commit else None,
        latest_session_id=latest_session.id if latest_session else None,
        latest_session_title=latest_session.title if latest_session else None,
    )


# ── Provider status endpoint ──────────────────────────────────────────────────

@router.get("/providers")
def list_providers():
    """Return provider configuration status. Safe to expose — never returns keys."""
    return providers_status()
