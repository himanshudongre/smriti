"""
V5 Space Metrics API — computed-on-demand project KPIs.

All metrics are derived from existing tables (commits, work_claims,
chat_sessions). No new schema, no event stream, no background jobs.

Endpoint:
  GET /api/v5/metrics/spaces/{space_id}  – project-level metrics
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, case, text
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import CommitModel, RepoModel, WorkClaim, ChatSession

router = APIRouter(prefix="/metrics", tags=["metrics-v5"])

DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000000a")


# ── Response schemas ─────────────────────────────────────────────────────────


class CoordinationMetrics(BaseModel):
    total_checkpoints: int = 0
    unique_agents: int = 0
    agent_checkpoints: dict[str, int] = Field(default_factory=dict)
    cross_agent_continuations: int = 0
    total_claims: int = 0
    claims_done: int = 0
    claims_abandoned: int = 0
    claims_with_task_id: int = 0
    claim_completion_rate: Optional[float] = None


class StateQualityMetrics(BaseModel):
    avg_decisions_per_checkpoint: float = 0.0
    avg_tasks_per_checkpoint: float = 0.0
    checkpoints_with_structured_tasks: int = 0
    checkpoints_with_task_ids: int = 0
    milestone_count: int = 0
    noise_count: int = 0


class BranchMetrics(BaseModel):
    active: int = 0
    integrated: int = 0
    abandoned: int = 0


class SpaceMetricsResponse(BaseModel):
    space_id: uuid.UUID
    space_name: str
    computed_at: datetime
    coordination: CoordinationMetrics
    state_quality: StateQualityMetrics
    branches: BranchMetrics


# ── Endpoint ─────────────────────────────────────────────────────────────────


@router.get("/spaces/{space_id}", response_model=SpaceMetricsResponse)
def get_space_metrics(space_id: uuid.UUID, db: Session = Depends(get_db)):
    """Computed-on-demand project metrics for a space.

    All data derived from existing tables — no new storage, no events.
    Returns coordination activity, state quality, and branch lifecycle.
    """
    repo = db.get(RepoModel, space_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Space not found")

    now = datetime.now(timezone.utc)

    # ── Coordination metrics ─────────────────────────────────────────

    # Checkpoint counts + agent distribution
    checkpoint_stmt = (
        select(
            func.count().label("total"),
            func.count(func.distinct(CommitModel.author_agent)).label("unique_agents"),
        )
        .where(CommitModel.repo_id == space_id)
    )
    cp_row = db.execute(checkpoint_stmt).one()

    agent_dist_stmt = (
        select(CommitModel.author_agent, func.count().label("cnt"))
        .where(CommitModel.repo_id == space_id)
        .group_by(CommitModel.author_agent)
    )
    agent_checkpoints = {
        (row[0] or "(none)"): row[1]
        for row in db.execute(agent_dist_stmt)
    }

    # Cross-agent continuations: checkpoints where author_agent differs
    # from parent's author_agent. Uses a self-join on parent_commit_id.
    ParentCommit = CommitModel.__table__.alias("parent")
    cross_agent_stmt = (
        select(func.count())
        .select_from(CommitModel.__table__)
        .join(
            ParentCommit,
            CommitModel.__table__.c.parent_commit_id == ParentCommit.c.id,
        )
        .where(
            CommitModel.__table__.c.repo_id == space_id,
            CommitModel.__table__.c.author_agent.isnot(None),
            ParentCommit.c.author_agent.isnot(None),
            CommitModel.__table__.c.author_agent != ParentCommit.c.author_agent,
        )
    )
    cross_agent_count = db.execute(cross_agent_stmt).scalar() or 0

    # Claim stats
    claim_stmt = (
        select(
            func.count().label("total"),
            func.count().filter(WorkClaim.status == "done").label("done"),
            func.count().filter(WorkClaim.status == "abandoned").label("abandoned"),
            func.count().filter(WorkClaim.task_id.isnot(None)).label("with_task_id"),
        )
        .where(WorkClaim.repo_id == space_id)
    )
    cl_row = db.execute(claim_stmt).one()
    total_resolved = cl_row.done + cl_row.abandoned
    completion_rate = round(cl_row.done / total_resolved, 2) if total_resolved > 0 else None

    coordination = CoordinationMetrics(
        total_checkpoints=cp_row.total,
        unique_agents=cp_row.unique_agents,
        agent_checkpoints=agent_checkpoints,
        cross_agent_continuations=cross_agent_count,
        total_claims=cl_row.total,
        claims_done=cl_row.done,
        claims_abandoned=cl_row.abandoned,
        claims_with_task_id=cl_row.with_task_id,
        claim_completion_rate=completion_rate,
    )

    # ── State quality metrics ────────────────────────────────────────

    # Fetch all checkpoints to compute JSONB-based metrics in Python.
    # For 56-500 checkpoints this is fast. At scale, use Postgres JSONB
    # functions directly.
    all_commits = db.scalars(
        select(CommitModel)
        .where(CommitModel.repo_id == space_id)
    ).all()

    total_decisions = 0
    total_tasks = 0
    structured_task_count = 0
    task_id_count = 0
    milestone_count = 0
    noise_count = 0

    for c in all_commits:
        decisions = c.decisions or []
        tasks = c.tasks or []
        total_decisions += len(decisions)
        total_tasks += len(tasks)

        # Structured tasks: at least one task is a dict with intent_hint
        has_structured = any(
            isinstance(t, dict) and t.get("intent_hint")
            for t in tasks
        )
        if has_structured:
            structured_task_count += 1

        # Task IDs: at least one task has an id field
        has_ids = any(
            isinstance(t, dict) and t.get("id")
            for t in tasks
        )
        if has_ids:
            task_id_count += 1

        # Notes from metadata_
        notes = (c.metadata_ or {}).get("notes", [])
        for n in notes:
            kind = n.get("kind", "note")
            if kind == "milestone":
                milestone_count += 1
            elif kind == "noise":
                noise_count += 1

    n_checkpoints = len(all_commits) or 1  # avoid division by zero
    state_quality = StateQualityMetrics(
        avg_decisions_per_checkpoint=round(total_decisions / n_checkpoints, 1),
        avg_tasks_per_checkpoint=round(total_tasks / n_checkpoints, 1),
        checkpoints_with_structured_tasks=structured_task_count,
        checkpoints_with_task_ids=task_id_count,
        milestone_count=milestone_count,
        noise_count=noise_count,
    )

    # ── Branch metrics ───────────────────────────────────────────────

    branch_stmt = (
        select(
            ChatSession.branch_disposition,
            func.count().label("cnt"),
        )
        .where(
            ChatSession.repo_id == space_id,
            ChatSession.branch_name != "main",
        )
        .group_by(ChatSession.branch_disposition)
    )
    branch_counts = {row[0]: row[1] for row in db.execute(branch_stmt)}

    branches = BranchMetrics(
        active=branch_counts.get("active", 0),
        integrated=branch_counts.get("integrated", 0),
        abandoned=branch_counts.get("abandoned", 0),
    )

    return SpaceMetricsResponse(
        space_id=repo.id,
        space_name=repo.name,
        computed_at=now,
        coordination=coordination,
        state_quality=state_quality,
        branches=branches,
    )
