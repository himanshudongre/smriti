"""
V5 Lineage API routes.

Session forking:
  POST  /api/v5/lineage/sessions/fork                  – fork a new session from a checkpoint

Branch/lineage view:
  GET   /api/v5/lineage/spaces/{space_id}               – full checkpoint + session tree for a space

Checkpoint comparison:
  GET   /api/v5/lineage/checkpoints/{a_id}/compare/{b_id} – structured diff of two checkpoints
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ChatSession, CommitModel, RepoModel, TurnEvent
from app.config_loader import get_config

router = APIRouter(prefix="/lineage", tags=["lineage-v5"])

DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000000a")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_repo(space_id: uuid.UUID, db: Session) -> RepoModel:
    repo = db.get(RepoModel, space_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Space not found")
    return repo


def _get_commit(checkpoint_id: uuid.UUID, db: Session) -> CommitModel:
    commit = db.get(CommitModel, checkpoint_id)
    if not commit:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return commit


# ── Request / Response schemas ────────────────────────────────────────────────

class ForkSessionRequest(BaseModel):
    space_id: str
    checkpoint_id: str
    branch_name: str = ""
    provider: str = ""
    model: str = ""


class ForkSessionResponse(BaseModel):
    session_id: uuid.UUID
    branch_name: str
    forked_from_checkpoint_id: uuid.UUID
    # history_base_seq is always 0 for new forks: the session starts clean.
    # This is an implementation detail exposed so the frontend can pass it
    # back on the first send_message call if needed (though the backend also
    # auto-infers it for forked sessions).
    history_base_seq: int = 0


class CheckpointNode(BaseModel):
    id: uuid.UUID
    commit_hash: str
    message: str
    branch_name: str
    parent_checkpoint_id: Optional[uuid.UUID]
    created_at: datetime
    summary: str
    objective: str
    author_agent: Optional[str] = None

    model_config = {"from_attributes": True}


class SessionNode(BaseModel):
    id: uuid.UUID
    title: str
    branch_name: str
    forked_from_checkpoint_id: Optional[uuid.UUID]
    seeded_commit_id: Optional[uuid.UUID]
    created_at: datetime

    model_config = {"from_attributes": True}


class LineageResponse(BaseModel):
    space_id: uuid.UUID
    checkpoints: list[CheckpointNode]
    sessions: list[SessionNode]


class CheckpointDetail(BaseModel):
    id: uuid.UUID
    commit_hash: str
    message: str
    branch_name: str
    summary: str
    objective: str
    decisions: list
    assumptions: list
    tasks: list
    open_questions: list
    artifacts: list


class CheckpointDiff(BaseModel):
    summary_a: str
    summary_b: str
    objective_a: str
    objective_b: str
    decisions_only_a: list[str]
    decisions_only_b: list[str]
    decisions_shared: list[str]
    assumptions_only_a: list[str] = Field(default_factory=list)
    assumptions_only_b: list[str] = Field(default_factory=list)
    assumptions_shared: list[str] = Field(default_factory=list)
    tasks_only_a: list[str]
    tasks_only_b: list[str]
    tasks_shared: list[str]
    common_ancestor_commit_id: Optional[uuid.UUID] = None


class CompareResponse(BaseModel):
    checkpoint_a: CheckpointDetail
    checkpoint_b: CheckpointDetail
    diff: CheckpointDiff


class ReachableCheckpoint(BaseModel):
    """Full commit data returned by the reachable-checkpoints endpoint.
    Matches the Commit TypeScript type so the frontend can reuse existing types."""
    id: uuid.UUID
    repo_id: uuid.UUID
    commit_hash: str
    parent_commit_id: Optional[uuid.UUID]
    branch_name: str
    author_agent: Optional[str]
    author_type: str
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
    context_blob: dict
    raw_source_text: Optional[str]
    metadata_: dict = Field(serialization_alias="metadata")
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_text(item) -> str:
    """Normalise a decision/task entry to plain text regardless of storage shape."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("description", item.get("text", str(item)))
    return str(item)


def _normalize_text(text: str) -> str:
    """Lightweight normalization for compare shared-set matching.

    Lowercase, strip non-alphanumeric characters (keep spaces), collapse
    whitespace. Catches case and punctuation differences. This is not
    semantic equality — two items that mean the same thing but share
    no tokens ("use stdlib only" vs "no third-party runtime deps") will
    still look different. Semantic match is a later build.
    """
    lowered = text.lower()
    stripped = re.sub(r"[^a-z0-9 ]", "", lowered)
    return " ".join(stripped.split())


def _diff_lists(a: list, b: list) -> tuple[list[str], list[str], list[str]]:
    """Return (only_in_a, only_in_b, in_both) using normalized keys for
    matching but returning the original strings.

    Matching uses _normalize_text as the equivalence key. When two items
    normalize to the same key, the A-side original wins (deterministic).
    Items whose normalized form is empty (e.g. "---", "..." or whitespace
    only) are treated as unmatchable and fall into only_a / only_b based
    on their origin, never into shared.
    """
    a_items = [_extract_text(x) for x in a]
    b_items = [_extract_text(x) for x in b]

    a_norm: dict[str, str] = {}
    a_unmatchable: list[str] = []
    for item in a_items:
        key = _normalize_text(item)
        if not key:
            a_unmatchable.append(item)
        elif key not in a_norm:
            a_norm[key] = item

    b_norm: dict[str, str] = {}
    b_unmatchable: list[str] = []
    for item in b_items:
        key = _normalize_text(item)
        if not key:
            b_unmatchable.append(item)
        elif key not in b_norm:
            b_norm[key] = item

    a_keys = set(a_norm.keys())
    b_keys = set(b_norm.keys())

    only_a = sorted([a_norm[k] for k in (a_keys - b_keys)] + a_unmatchable)
    only_b = sorted([b_norm[k] for k in (b_keys - a_keys)] + b_unmatchable)
    shared = sorted(a_norm[k] for k in (a_keys & b_keys))

    return only_a, only_b, shared


def _find_common_ancestor(
    a_id: uuid.UUID,
    b_id: uuid.UUID,
    db: Session,
    max_depth: int = 1000,
) -> Optional[uuid.UUID]:
    """Find the lowest common ancestor of two checkpoints by walking
    parent_commit_id chains.

    Walk A's chain upward, collecting every ancestor id into a set, then
    walk B's chain upward and return the first id that appears in A's set.
    Returns None if the two checkpoints share no ancestor within max_depth.

    max_depth bounds both walks so a corrupt parent cycle can't hang the
    endpoint. Smriti histories are shallow in practice (dozens of commits
    for a long-running project, not thousands), so 1000 is generous.

    When a_id == b_id, the checkpoint is its own LCA — returns a_id.
    """
    a_ancestors: set[uuid.UUID] = set()
    current: Optional[uuid.UUID] = a_id
    for _ in range(max_depth):
        if current is None:
            break
        if current in a_ancestors:
            break  # cycle guard
        a_ancestors.add(current)
        commit = db.get(CommitModel, current)
        if commit is None:
            break
        current = commit.parent_commit_id

    current = b_id
    seen_on_b: set[uuid.UUID] = set()
    for _ in range(max_depth):
        if current is None:
            return None
        if current in a_ancestors:
            return current
        if current in seen_on_b:
            return None  # cycle guard
        seen_on_b.add(current)
        commit = db.get(CommitModel, current)
        if commit is None:
            return None
        current = commit.parent_commit_id
    return None


# ── Fork endpoint ─────────────────────────────────────────────────────────────

@router.post("/sessions/fork", response_model=ForkSessionResponse, status_code=201)
def fork_session(payload: ForkSessionRequest, db: Session = Depends(get_db)):
    """
    Create a new session branching from a specific checkpoint.

    The forked session:
    - starts with no live turns (history_base_seq = 0)
    - receives its context exclusively from the checkpoint state snapshot
    - accumulates its own turns independently from that point forward
    """
    try:
        space_id = uuid.UUID(payload.space_id)
        checkpoint_id = uuid.UUID(payload.checkpoint_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid space_id or checkpoint_id")

    _get_repo(space_id, db)
    commit = _get_commit(checkpoint_id, db)

    if commit.repo_id != space_id:
        raise HTTPException(status_code=400, detail="Checkpoint does not belong to this space")

    cfg = get_config()
    provider = payload.provider or cfg.chat.default_provider
    branch = payload.branch_name or f"branch-{_utcnow().strftime('%Y-%m-%d')}"

    session = ChatSession(
        repo_id=space_id,
        title=f"Fork from {commit.commit_hash[:7]}",
        active_provider=provider,
        active_model=payload.model,
        seeded_commit_id=checkpoint_id,
        forked_from_checkpoint_id=checkpoint_id,
        branch_name=branch,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return ForkSessionResponse(
        session_id=session.id,
        branch_name=session.branch_name,
        forked_from_checkpoint_id=checkpoint_id,
        history_base_seq=0,
    )


# ── Branch disposition endpoint ────────────────────────────────────────────────

VALID_DISPOSITIONS = {"active", "integrated", "abandoned"}


class BranchDispositionRequest(BaseModel):
    space_id: str
    branch_name: str
    disposition: str = Field(
        description="One of: active, integrated, abandoned",
    )


class BranchDispositionResponse(BaseModel):
    space_id: uuid.UUID
    branch_name: str
    disposition: str
    sessions_updated: int


@router.patch("/branches/disposition", response_model=BranchDispositionResponse)
def set_branch_disposition(
    payload: BranchDispositionRequest,
    db: Session = Depends(get_db),
):
    """Set the disposition of a branch (all sessions on that branch).

    Marks a branch as integrated, abandoned, or active. Sessions with
    matching branch_name in the space have their branch_disposition
    updated. This controls whether the branch appears in the
    ## Active branches section of smriti state.

    Branch name is passed in the request body (not the URL) because
    branch names frequently contain slashes (e.g. codex/config-reload)
    which conflict with URL path routing.

    Reversible: setting back to 'active' re-shows the branch.
    """
    try:
        space_id = uuid.UUID(payload.space_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid space_id")

    _get_repo(space_id, db)

    if payload.disposition not in VALID_DISPOSITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid disposition '{payload.disposition}'. "
            f"Must be one of: {', '.join(sorted(VALID_DISPOSITIONS))}",
        )

    # Find all sessions on this branch in this space.
    stmt = (
        select(ChatSession)
        .where(
            ChatSession.repo_id == space_id,
            ChatSession.branch_name == payload.branch_name,
        )
    )
    sessions = list(db.scalars(stmt).all())

    if not sessions:
        raise HTTPException(
            status_code=404,
            detail=f"No sessions found on branch '{payload.branch_name}' in this space.",
        )

    for session in sessions:
        session.branch_disposition = payload.disposition

    db.commit()

    return BranchDispositionResponse(
        space_id=space_id,
        branch_name=payload.branch_name,
        disposition=payload.disposition,
        sessions_updated=len(sessions),
    )


# ── Lineage (branch tree) endpoint ────────────────────────────────────────────

@router.get("/spaces/{space_id}", response_model=LineageResponse)
def get_lineage(space_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Return all checkpoints and sessions for a space, structured for tree rendering.

    The frontend builds the visual branch tree from this data:
    - checkpoints carry parent_checkpoint_id for the commit ancestry chain
    - sessions carry forked_from_checkpoint_id to locate where each branch began
    """
    _get_repo(space_id, db)

    commits = db.scalars(
        select(CommitModel)
        .where(CommitModel.repo_id == space_id)
        .order_by(CommitModel.created_at.asc())
    ).all()

    sessions = db.scalars(
        select(ChatSession)
        .where(ChatSession.repo_id == space_id)
        .order_by(ChatSession.created_at.asc())
    ).all()

    checkpoint_nodes = [
        CheckpointNode(
            id=c.id,
            commit_hash=c.commit_hash,
            message=c.message,
            branch_name=c.branch_name,
            parent_checkpoint_id=c.parent_commit_id,
            created_at=c.created_at,
            summary=c.summary or "",
            objective=c.objective or "",
            author_agent=c.author_agent,
        )
        for c in commits
    ]

    session_nodes = [
        SessionNode(
            id=s.id,
            title=s.title or "",
            branch_name=s.branch_name,
            forked_from_checkpoint_id=s.forked_from_checkpoint_id,
            seeded_commit_id=s.seeded_commit_id,
            created_at=s.created_at,
        )
        for s in sessions
    ]

    return LineageResponse(
        space_id=space_id,
        checkpoints=checkpoint_nodes,
        sessions=session_nodes,
    )


# ── Compare endpoint ──────────────────────────────────────────────────────────

@router.get("/checkpoints/{a_id}/compare/{b_id}", response_model=CompareResponse)
def compare_checkpoints(a_id: uuid.UUID, b_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Return a structured diff of two checkpoint state snapshots.

    Decisions and tasks are compared by normalised text equality.
    Summary and objective are returned as-is for side-by-side reading.
    """
    commit_a = _get_commit(a_id, db)
    commit_b = _get_commit(b_id, db)

    lca = _find_common_ancestor(commit_a.id, commit_b.id, db)

    dec_only_a, dec_only_b, dec_shared = _diff_lists(
        commit_a.decisions or [], commit_b.decisions or []
    )
    assump_only_a, assump_only_b, assump_shared = _diff_lists(
        commit_a.assumptions or [], commit_b.assumptions or []
    )
    task_only_a, task_only_b, task_shared = _diff_lists(
        commit_a.tasks or [], commit_b.tasks or []
    )

    def _to_detail(c: CommitModel) -> CheckpointDetail:
        return CheckpointDetail(
            id=c.id,
            commit_hash=c.commit_hash,
            message=c.message,
            branch_name=c.branch_name,
            summary=c.summary or "",
            objective=c.objective or "",
            decisions=[_extract_text(d) for d in (c.decisions or [])],
            assumptions=[_extract_text(a) for a in (c.assumptions or [])],
            tasks=[_extract_text(t) for t in (c.tasks or [])],
            open_questions=[_extract_text(q) for q in (c.open_questions or [])],
            artifacts=c.artifacts or [],
        )

    return CompareResponse(
        checkpoint_a=_to_detail(commit_a),
        checkpoint_b=_to_detail(commit_b),
        diff=CheckpointDiff(
            summary_a=commit_a.summary or "",
            summary_b=commit_b.summary or "",
            objective_a=commit_a.objective or "",
            objective_b=commit_b.objective or "",
            decisions_only_a=dec_only_a,
            decisions_only_b=dec_only_b,
            decisions_shared=dec_shared,
            assumptions_only_a=assump_only_a,
            assumptions_only_b=assump_only_b,
            assumptions_shared=assump_shared,
            tasks_only_a=task_only_a,
            tasks_only_b=task_only_b,
            tasks_shared=task_shared,
            common_ancestor_commit_id=lca,
        ),
    )


# ── Reachable checkpoints endpoint ────────────────────────────────────────────

@router.get("/sessions/{session_id}/checkpoints", response_model=list[ReachableCheckpoint])
def get_session_reachable_checkpoints(session_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Return the reachable checkpoint set for a session.

    Reachability rules (same-Space, branch-local semantics):

    Main-branch session:
      - All commits where branch_name == 'main', newest first.

    Forked session (session.forked_from_checkpoint_id is set):
      - Commits on the session's own branch (fork-local, created after fork).
      - The fork source checkpoint itself.
      - All ancestors of the fork source (walking parent_commit_id upward).
      NOT included:
      - Child commits on main created AFTER the fork point.
      - Sibling branch commits.

    This is the single authoritative reachability query used by the
    checkpoint history panel and mount-candidate list. It ensures that
    the panel never offers cross-branch checkpoints as mount targets.
    """
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.branch_name == "main" or session.forked_from_checkpoint_id is None:
        # Main-branch session: all main commits, newest first
        commits = db.scalars(
            select(CommitModel)
            .where(
                CommitModel.repo_id == session.repo_id,
                CommitModel.branch_name == "main",
            )
            .order_by(CommitModel.created_at.desc())
        ).all()
        return list(commits)

    # Forked session: collect fork-local checkpoints + ancestors of fork source
    seen_ids: set[uuid.UUID] = set()
    result: list[CommitModel] = []

    # 1. Fork-local commits (same branch as the session, created after the fork)
    fork_local = db.scalars(
        select(CommitModel)
        .where(
            CommitModel.repo_id == session.repo_id,
            CommitModel.branch_name == session.branch_name,
        )
        .order_by(CommitModel.created_at.desc())
    ).all()
    for c in fork_local:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            result.append(c)

    # 2. Fork source + all its ancestors (walk upward through parent_commit_id)
    #    This includes the exact checkpoint the session was forked from and any
    #    earlier history — but NOT any commits created on main after that point.
    current: Optional[CommitModel] = db.get(CommitModel, session.forked_from_checkpoint_id)
    while current is not None:
        if current.id not in seen_ids:
            seen_ids.add(current.id)
            result.append(current)
        if current.parent_commit_id is None:
            break
        current = db.get(CommitModel, current.parent_commit_id)

    # Sort newest first (fork-local commits are already newest-first, but the
    # ancestor walk may interleave with them if branches share commit timestamps)
    result.sort(key=lambda c: c.created_at, reverse=True)
    return result
