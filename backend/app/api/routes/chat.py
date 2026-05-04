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

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    ChatSession,
    CommitModel,
    RepoModel,
    TurnEvent,
    WorkClaim,
    WorkTree,
)
from app.config_loader import get_config, providers_status, ProviderNotConfiguredError
from app.providers.registry import get_adapter, get_mock_adapter
from app.services.worktree_probe import _probe_worktree

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
        if ckpt.assumptions:
            lines.append(f"{label} Key Assumptions:")
            for a in ckpt.assumptions:
                lines.append(f"- {a}")
            lines.append("")
        if ckpt.tasks:
            lines.append(f"{label} Open Tasks:")
            for t in ckpt.tasks:
                lines.append(f"- {t}")
            lines.append("")
        if ckpt.artifacts:
            lines.append(f"{label} Attached Artifacts:")
            for art in ckpt.artifacts:
                art_label = art.get('label', 'Untitled') if isinstance(art, dict) else 'Untitled'
                art_content = art.get('content', '') if isinstance(art, dict) else str(art)
                # Cap each artifact at 2000 chars to manage prompt size
                if len(art_content) > 2000:
                    art_content = art_content[:2000] + "\n[… truncated]"
                lines.append(f"\n[{art_label}]:")
                lines.append(art_content)
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
    assumptions: list[str] = Field(default_factory=list)
    tasks: list = Field(default_factory=list)  # str or structured task objects
    open_questions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
    author_agent: Optional[str] = None
    project_root: Optional[str] = None


class CommitResponse(BaseModel):
    id: uuid.UUID
    repo_id: uuid.UUID
    commit_hash: str
    parent_commit_id: Optional[uuid.UUID]
    branch_name: str
    author_agent: Optional[str] = None
    project_root: Optional[str] = None
    message: str
    summary: str
    objective: str
    decisions: list
    assumptions: list
    tasks: list
    open_questions: list
    entities: list
    artifacts: list
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


# ── Space state (multi-branch) schemas ────────────────────────────────────────
#
# `GET /api/v4/chat/spaces/{id}/state` is the richer sibling of `get_head`.
# It returns the main-branch continuation brief the chat UI / CLI already
# knew how to render, plus a concise per-branch summary of non-main activity
# and a lightweight divergence signal when any active branch disagrees with
# main on decisions. Both extensions are capped hard so the aggregate output
# stays digestible for an agent reading it into its context window.

class SpaceBrief(BaseModel):
    """Minimal space header for the state response. Mirrors what the CLI
    formatter already consumes from its `space` arg."""
    id: uuid.UUID
    name: str
    description: Optional[str] = None


class ActiveBranchSummary(BaseModel):
    """One line per non-main branch in the `Active branches` section.
    Kept minimal on purpose — this is not a brief, it is a pointer."""
    branch_name: str
    commit_id: uuid.UUID
    commit_hash: str
    message: str
    author_agent: Optional[str] = None
    created_at: datetime
    # First ~200 chars of the commit's summary. Callers use this as a
    # one-liner in the Active branches section, not a full read.
    summary: str = ""


class DivergencePair(BaseModel):
    """Per-branch divergence entry. `main_only_decisions` are decisions
    present on main but absent from this branch; `branch_only_decisions`
    are the reverse. Both arrays capped at DIVERGENCE_DECISIONS_CAP items
    by the endpoint so the state response cannot blow up on active
    projects."""
    branch_name: str
    branch_commit_hash: str
    main_only_decisions: list[str] = Field(default_factory=list)
    branch_only_decisions: list[str] = Field(default_factory=list)


class DivergenceSummary(BaseModel):
    """Top-level divergence block. Only populated when at least one
    active branch differs from main on decisions. Capped at
    DIVERGENCE_BRANCHES_CAP pairs."""
    pairs: list[DivergencePair] = Field(default_factory=list)


class ActiveWorktreeSummary(BaseModel):
    """Git drift information for a worktree bound to an active claim."""
    id: uuid.UUID
    path: str
    branch: str
    dirty_files: int
    ahead: int
    behind: int
    last_commit_sha: str
    last_commit_relative: str


class ActiveClaimSummary(BaseModel):
    """One line per active work claim in the `Active work` section."""
    id: uuid.UUID
    agent: str
    branch_name: str
    scope: str
    task_id: Optional[str] = None
    worktree_id: Optional[uuid.UUID] = None
    worktree: Optional[ActiveWorktreeSummary] = None
    intent_type: str
    claimed_at: datetime
    expires_at: datetime
    base_commit_hash: Optional[str] = None

    model_config = {"from_attributes": True}


class FreshnessCheckpoint(BaseModel):
    """One entry in the freshness 'new checkpoints' list."""
    commit_hash: str
    author_agent: Optional[str] = None
    message: str
    created_at: datetime


class FreshnessInfo(BaseModel):
    """Pull-time freshness signal. Included in SpaceStateResponse only
    when the caller provides since_commit_id."""
    changed: bool
    since_commit_hash: str
    current_head_hash: str
    new_checkpoints_count: int = 0
    new_checkpoints: list[FreshnessCheckpoint] = Field(default_factory=list)


class SpaceStateResponse(BaseModel):
    """Composite response for `GET /spaces/{id}/state`.

    One round trip, atomic snapshot. Replaces the CLI's previous 3-call
    dance (resolve_space → get_head → get_commit) for the state brief.
    """
    space: SpaceBrief
    head: HeadResponse
    commit: Optional[CommitResponse] = None  # None when space has no checkpoints
    active_branches: list[ActiveBranchSummary] = Field(default_factory=list)
    active_claims: list[ActiveClaimSummary] = Field(default_factory=list)
    divergence: Optional[DivergenceSummary] = None
    freshness: Optional[FreshnessInfo] = None


# Hard caps for the state response. These are constants on purpose —
# not query params — because the agent-facing contract is "digestible by
# default." Callers who need an unbounded view should hit the lineage
# endpoint (/api/v5/lineage/spaces/{id}) which is already that.
ACTIVE_BRANCHES_CAP = 5
DIVERGENCE_BRANCHES_CAP = 2
DIVERGENCE_DECISIONS_CAP = 3


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


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session_generic(session_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """Delete a chat session and cascade to its turn events. Commits authored
    by this session are preserved (they are owned by the space, not the session)."""
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.repo_id is not None:
        repo = db.get(RepoModel, session.repo_id)
        if not repo or repo.user_id != DEMO_USER_ID:
            raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
    return Response(status_code=204)


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
        # Agent identity: explicit payload value wins over the session's
        # active provider. Allows a CLI caller (or any client) to tag the
        # checkpoint with a real agent name instead of just the provider
        # (e.g. "claude-code" vs. "anthropic"). Falls back to the session's
        # active provider when the payload omits it.
        author_agent=payload.author_agent or session.active_provider,
        author_type="llm",
        project_root=payload.project_root,
        message=payload.message,
        summary=payload.summary,
        objective=payload.objective,
        decisions=payload.decisions,
        assumptions=payload.assumptions,
        tasks=payload.tasks,
        open_questions=payload.open_questions,
        entities=payload.entities,
        artifacts=payload.artifacts,
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


# ── Space state endpoint (multi-branch) ──────────────────────────────────────


def _get_active_branch_heads(
    repo_id: uuid.UUID, db: Session, limit: int = ACTIVE_BRANCHES_CAP
) -> list[CommitModel]:
    """Return the most recent checkpoint on each non-main branch of this space
    that has at least one session with branch_disposition == 'active'.

    Branches marked 'integrated' or 'abandoned' are excluded — they no
    longer appear in ## Active branches or ## Divergence signal. They
    remain in the lineage tree and in `smriti branch list` for history.

    Implemented in two steps so the SQL stays portable across the
    SQLAlchemy dialects we use in tests: first fetch every non-main
    checkpoint, then collapse per branch in Python and filter by
    session disposition.
    """
    # Step 1: find which branches have at least one active session.
    active_branches_stmt = (
        select(ChatSession.branch_name)
        .where(
            ChatSession.repo_id == repo_id,
            ChatSession.branch_name != "main",
            ChatSession.branch_disposition == "active",
        )
        .distinct()
    )
    active_branch_names = set(db.scalars(active_branches_stmt).all())

    if not active_branch_names:
        return []

    # Step 2: find the latest checkpoint per active branch.
    stmt = (
        select(CommitModel)
        .where(
            CommitModel.repo_id == repo_id,
            CommitModel.branch_name != "main",
        )
        .order_by(CommitModel.created_at.desc())
    )
    seen: set[str] = set()
    heads: list[CommitModel] = []
    for commit in db.scalars(stmt):
        if commit.branch_name in seen:
            continue
        if commit.branch_name not in active_branch_names:
            seen.add(commit.branch_name)
            continue
        seen.add(commit.branch_name)
        heads.append(commit)
        if len(heads) >= limit:
            break
    return heads


def _compute_space_divergence(
    main_head: CommitModel,
    branch_heads: list[CommitModel],
) -> Optional[DivergenceSummary]:
    """Compute decision-level divergence between main HEAD and each
    non-main branch HEAD. Returns `None` if no branch differs, otherwise
    a capped `DivergenceSummary`.

    Reuses `lineage._diff_lists` so matching stays consistent with what
    `smriti compare` surfaces — case and punctuation differences already
    normalize to the same key, so two agents saying "Use Pydantic" and
    "use pydantic." do not look divergent.
    """
    # Imported lazily so we don't create a hard circular import at
    # module load time between chat.py and lineage.py (both can be
    # imported in either order by the FastAPI app bootstrap).
    from app.api.routes.lineage import _diff_lists

    pairs: list[DivergencePair] = []
    for branch_head in branch_heads[:DIVERGENCE_BRANCHES_CAP]:
        only_main, only_branch, _shared = _diff_lists(
            main_head.decisions or [],
            branch_head.decisions or [],
        )
        if not only_main and not only_branch:
            continue
        pairs.append(
            DivergencePair(
                branch_name=branch_head.branch_name,
                branch_commit_hash=branch_head.commit_hash,
                main_only_decisions=only_main[:DIVERGENCE_DECISIONS_CAP],
                branch_only_decisions=only_branch[:DIVERGENCE_DECISIONS_CAP],
            )
        )
    return DivergenceSummary(pairs=pairs) if pairs else None


FRESHNESS_NEW_CHECKPOINTS_CAP = 5


@router.get("/spaces/{repo_id}/state", response_model=SpaceStateResponse)
def get_space_state(
    repo_id: uuid.UUID,
    since_commit_id: Optional[uuid.UUID] = Query(None, description="Checkpoint ID to check freshness against"),
    db: Session = Depends(get_db),
):
    """Return the richer, multi-branch continuation brief for a space.

    Contains:
      - space header (id, name, description)
      - main-branch HEAD metadata (same shape as /head)
      - full main-branch HEAD commit (or None if no checkpoints yet)
      - up to ACTIVE_BRANCHES_CAP most recent non-main branch heads
      - a divergence summary when any active branch disagrees with main
        on decisions — capped at DIVERGENCE_BRANCHES_CAP branches and
        DIVERGENCE_DECISIONS_CAP decisions per side per pair.
      - freshness signal (when since_commit_id is provided): whether HEAD
        has moved past the caller's known checkpoint, and if so, a compact
        list of new checkpoints.

    The divergence section is the lightweight signal an agent or human
    needs to notice cross-branch drift without reading the full compare
    output. If the signal fires, the agent is expected to run
    `smriti_compare` on the specific branches for the full diff.
    """
    repo = _get_repo(repo_id, db)
    main_head_commit = _get_latest_commit(repo_id, db)

    # Latest session (same query get_head uses — mirror it so clients can
    # treat `head` in the state response as interchangeable with /head).
    session_stmt = (
        select(ChatSession)
        .where(ChatSession.repo_id == repo_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(1)
    )
    latest_session = db.scalars(session_stmt).first()

    head_resp = HeadResponse(
        repo_id=repo_id,
        commit_hash=main_head_commit.commit_hash if main_head_commit else None,
        commit_id=main_head_commit.id if main_head_commit else None,
        summary=main_head_commit.summary if main_head_commit else None,
        objective=main_head_commit.objective if main_head_commit else None,
        latest_session_id=latest_session.id if latest_session else None,
        latest_session_title=latest_session.title if latest_session else None,
    )

    commit_resp = (
        CommitResponse.model_validate(main_head_commit)
        if main_head_commit
        else None
    )

    active_branch_commits = _get_active_branch_heads(
        repo_id, db, limit=ACTIVE_BRANCHES_CAP
    )

    active_branches = [
        ActiveBranchSummary(
            branch_name=c.branch_name,
            commit_id=c.id,
            commit_hash=c.commit_hash,
            message=c.message or "",
            author_agent=c.author_agent,
            created_at=c.created_at,
            # Cap at ~200 chars so the Active branches section stays a
            # pointer, not a brief. Callers render this on one line.
            summary=(c.summary or "")[:200],
        )
        for c in active_branch_commits
    ]

    divergence = None
    if main_head_commit and active_branch_commits:
        divergence = _compute_space_divergence(main_head_commit, active_branch_commits)

    # Active work claims — query-time expiration filter.
    now = _utcnow()
    claims_stmt = (
        select(WorkClaim)
        .where(
            WorkClaim.repo_id == repo_id,
            WorkClaim.status == "active",
            WorkClaim.expires_at > now,
        )
        .order_by(WorkClaim.claimed_at.desc())
        .limit(10)
    )
    active_claims = []
    for wc in db.scalars(claims_stmt):
        base_hash = None
        if wc.base_commit_id:
            base_commit = db.get(CommitModel, wc.base_commit_id)
            base_hash = base_commit.commit_hash[:7] if base_commit else None
        worktree_summary = None
        if wc.worktree_id:
            worktree = db.get(WorkTree, wc.worktree_id)
            if worktree and worktree.status == "active":
                probed = _probe_worktree(
                    str(worktree.id),
                    worktree.path,
                    worktree.branch_name,
                )
                if probed:
                    worktree_summary = ActiveWorktreeSummary(**probed)
        active_claims.append(
            ActiveClaimSummary(
                id=wc.id,
                agent=wc.agent,
                branch_name=wc.branch_name,
                scope=wc.scope,
                task_id=wc.task_id,
                worktree_id=wc.worktree_id,
                worktree=worktree_summary,
                intent_type=wc.intent_type,
                claimed_at=wc.claimed_at,
                expires_at=wc.expires_at,
                base_commit_hash=base_hash,
            )
        )

    # Freshness check: if since_commit_id is provided, determine whether
    # HEAD has moved and list new checkpoints since the caller's base.
    freshness = None
    if since_commit_id and main_head_commit:
        since_commit = db.get(CommitModel, since_commit_id)
        since_hash = since_commit.commit_hash[:7] if since_commit else str(since_commit_id)[:7]
        current_hash = main_head_commit.commit_hash[:7]

        if since_commit_id == main_head_commit.id:
            freshness = FreshnessInfo(
                changed=False,
                since_commit_hash=since_hash,
                current_head_hash=current_hash,
            )
        else:
            # Walk main checkpoints backward from HEAD to find those newer
            # than since_commit_id. Stop at since_commit_id or chain end.
            new_commits: list[FreshnessCheckpoint] = []
            stmt = (
                select(CommitModel)
                .where(
                    CommitModel.repo_id == repo_id,
                    CommitModel.branch_name == "main",
                )
                .order_by(CommitModel.created_at.desc())
            )
            for c in db.scalars(stmt):
                if c.id == since_commit_id:
                    break
                new_commits.append(FreshnessCheckpoint(
                    commit_hash=c.commit_hash[:7],
                    author_agent=c.author_agent,
                    message=c.message or "",
                    created_at=c.created_at,
                ))
                if len(new_commits) >= 50:  # safety cap
                    break

            freshness = FreshnessInfo(
                changed=True,
                since_commit_hash=since_hash,
                current_head_hash=current_hash,
                new_checkpoints_count=len(new_commits),
                new_checkpoints=new_commits[:FRESHNESS_NEW_CHECKPOINTS_CAP],
            )

    return SpaceStateResponse(
        space=SpaceBrief(
            id=repo.id,
            name=repo.name,
            description=repo.description,
        ),
        head=head_resp,
        commit=commit_resp,
        active_branches=active_branches,
        active_claims=active_claims,
        divergence=divergence,
        freshness=freshness,
    )


# ── Provider status endpoint ──────────────────────────────────────────────────

@router.get("/providers")
def list_providers():
    """Return provider configuration status. Safe to expose — never returns keys."""
    return providers_status()
