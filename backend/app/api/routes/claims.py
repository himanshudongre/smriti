"""
V5 Work Claims API routes.

Work claims are lightweight, time-bounded declarations that an agent
is actively working on something in a space. They make pre-work intent
visible to other agents before work produces a checkpoint.

Claims are advisory — not locks. The skill pack teaches agents to
check for overlapping claims before starting work and to create their
own claim after reading state.

Endpoints:
  POST   /api/v5/claims                     – create a new work claim
  PATCH  /api/v5/claims/{claim_id}          – update status (done / abandoned)
  GET    /api/v5/claims?space_id=...        – list active claims for a space
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import CommitModel, RepoModel, WorkClaim, WorkTree

router = APIRouter(prefix="/claims", tags=["claims-v5"])

DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000000a")
DEFAULT_TTL_HOURS = 4

VALID_INTENT_TYPES = {"implement", "review", "investigate", "docs", "test"}
VALID_STATUSES = {"active", "done", "abandoned"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_repo(space_id: uuid.UUID, db: Session) -> RepoModel:
    repo = db.get(RepoModel, space_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Space not found")
    return repo


# ── Request / Response schemas ────────────────────────────────────────────────


class CreateClaimRequest(BaseModel):
    space_id: str
    agent: str
    scope: str
    branch_name: str = "main"
    base_commit_id: Optional[str] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = Field(
        default=None,
        description="Optional reference to a structured task's id from the checkpoint.",
    )
    worktree_id: Optional[str] = Field(
        default=None,
        description="Optional worktree UUID this claim is bound to.",
    )
    intent_type: str = "implement"
    ttl_hours: float = Field(
        default=DEFAULT_TTL_HOURS,
        description="Hours until the claim expires. Default 4.",
    )


class UpdateClaimRequest(BaseModel):
    status: str = Field(
        description="New status: 'done' or 'abandoned'",
    )


class ClaimResponse(BaseModel):
    id: uuid.UUID
    repo_id: uuid.UUID
    agent: str
    branch_name: str
    base_commit_id: Optional[uuid.UUID] = None
    task_id: Optional[str] = None
    worktree_id: Optional[uuid.UUID] = None
    scope: str
    intent_type: str
    status: str
    claimed_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=ClaimResponse, status_code=201)
def create_claim(payload: CreateClaimRequest, db: Session = Depends(get_db)):
    """Create a new work claim.

    Agents call this after reading state but before starting substantial
    work. The claim makes their intent visible to other agents via
    `smriti state` and `smriti claim list`.
    """
    try:
        space_id = uuid.UUID(payload.space_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid space_id")

    _get_repo(space_id, db)

    if payload.intent_type not in VALID_INTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid intent_type '{payload.intent_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_INTENT_TYPES))}",
        )

    base_commit_id = None
    if payload.base_commit_id:
        try:
            base_commit_id = uuid.UUID(payload.base_commit_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid base_commit_id")
        if not db.get(CommitModel, base_commit_id):
            raise HTTPException(status_code=404, detail="Base checkpoint not found")

    session_id = None
    if payload.session_id:
        try:
            session_id = uuid.UUID(payload.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id")

    worktree_id = None
    if payload.worktree_id:
        try:
            worktree_id = uuid.UUID(payload.worktree_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid worktree_id")
        worktree = db.get(WorkTree, worktree_id)
        if not worktree:
            raise HTTPException(status_code=404, detail="Worktree not found")
        if worktree.repo_id != space_id:
            raise HTTPException(
                status_code=400,
                detail="Worktree belongs to a different space",
            )
        if worktree.status != "active":
            raise HTTPException(status_code=400, detail="Worktree is not active")

    now = _utcnow()
    claim = WorkClaim(
        repo_id=space_id,
        session_id=session_id,
        agent=payload.agent,
        branch_name=payload.branch_name,
        base_commit_id=base_commit_id,
        worktree_id=worktree_id,
        scope=payload.scope,
        task_id=payload.task_id,
        intent_type=payload.intent_type,
        status="active",
        claimed_at=now,
        expires_at=now + timedelta(hours=payload.ttl_hours),
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim


@router.patch("/{claim_id}", response_model=ClaimResponse)
def update_claim(claim_id: uuid.UUID, payload: UpdateClaimRequest, db: Session = Depends(get_db)):
    """Update a claim's status to 'done' or 'abandoned'.

    Agents call this when work finishes — either successfully (done)
    or because they stopped for some reason (abandoned). Claims are
    NOT auto-closed by checkpointing; the agent explicitly marks the
    disposition.
    """
    claim = db.get(WorkClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    if payload.status not in {"done", "abandoned"}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{payload.status}'. Must be 'done' or 'abandoned'.",
        )

    if claim.status != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Claim is already '{claim.status}' — cannot update.",
        )

    claim.status = payload.status
    db.commit()
    db.refresh(claim)
    return claim


@router.get("", response_model=list[ClaimResponse])
def list_claims(
    space_id: uuid.UUID = Query(..., description="Space UUID"),
    include_expired: bool = Query(False, description="Include expired claims"),
    db: Session = Depends(get_db),
):
    """List work claims for a space.

    By default, only active (non-expired) claims are returned. Pass
    `include_expired=true` to see all claims including done, abandoned,
    and expired ones.
    """
    stmt = (
        select(WorkClaim)
        .where(WorkClaim.repo_id == space_id)
        .order_by(WorkClaim.claimed_at.desc())
    )

    if not include_expired:
        now = _utcnow()
        stmt = stmt.where(
            WorkClaim.status == "active",
            WorkClaim.expires_at > now,
        )

    return list(db.scalars(stmt).all())
