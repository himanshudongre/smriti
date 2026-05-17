"""
V5 Project Current State API — a compact, legible snapshot of where a
space is *right now*.

This is the founder-facing / agent-facing "what is happening, what changed,
what needs my attention" surface. It is computed on demand from existing
tables (commits, work_claims, chat_sessions) — no new schema, no events,
no background jobs. The CLI renders the same payload via `smriti current`.

Endpoint:
  GET /api/v5/current/spaces/{space_id}  – packaged current-state snapshot
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.chat import (
    ActiveClaimSummary,
    _compute_space_divergence,
    _get_active_branch_heads,
    _get_active_claims,
    _get_latest_commit,
    _get_repo,
)
from app.db.database import get_db
from app.db.models import CommitModel

router = APIRouter(prefix="/current", tags=["current-v5"])


# ── Caps & vocabulary ────────────────────────────────────────────────────────
#
# Constants on purpose — this surface is "digestible by default." A caller
# who needs unbounded history hits the lineage / metrics endpoints instead.

INTENT_ORDER = ("implement", "review", "test", "docs", "investigate", "other")
VALID_INTENTS = {"implement", "review", "test", "docs", "investigate"}

RECENT_MILESTONES_CAP = 5
RECENT_ACTIVITY_CAP = 8
OPEN_QUESTIONS_CAP = 6
TASKS_PER_INTENT_CAP = 8
SUMMARY_PREVIEW_CHARS = 280


# ── Response schemas ─────────────────────────────────────────────────────────


class CurrentDirection(BaseModel):
    """Where the project is headed right now — drawn from the latest
    main-branch checkpoint. All fields are None for a space with no
    checkpoints yet."""
    objective: Optional[str] = None
    headline: Optional[str] = None       # latest main checkpoint message/title
    summary: Optional[str] = None        # truncated to SUMMARY_PREVIEW_CHARS
    checkpoint_id: Optional[uuid.UUID] = None
    checkpoint_hash: Optional[str] = None
    author_agent: Optional[str] = None
    updated_at: Optional[datetime] = None


class CurrentCounts(BaseModel):
    """At-a-glance project size signals."""
    checkpoints: int = 0
    agents: int = 0
    active_claims: int = 0
    active_branches: int = 0
    open_tasks: int = 0       # open structured tasks on the latest main checkpoint
    milestones: int = 0       # total milestone notes across all checkpoints


class AttentionSignal(BaseModel):
    """One "needs my attention right now" item.

    kind is one of:
      - "open_question" — an unresolved question on the latest checkpoint
      - "divergence"    — an active branch disagrees with main on decisions
      - "active_work"   — an agent currently holds a claim
    severity is "info" or "warn".
    """
    kind: str
    severity: str
    message: str


class MilestoneEntry(BaseModel):
    """A milestone note and the checkpoint it annotates."""
    checkpoint_id: uuid.UUID
    checkpoint_hash: str
    checkpoint_message: str
    note: str
    author_agent: Optional[str] = None
    created_at: datetime


class CurrentTask(BaseModel):
    """A structured task, normalized from the latest checkpoint's task list."""
    text: str
    id: Optional[str] = None
    intent_hint: Optional[str] = None
    blocked_by: Optional[str] = None
    status: str = "open"

    @field_validator("blocked_by", mode="before")
    @classmethod
    def _coerce_blocked_by(cls, value: object) -> Optional[str]:
        """Normalize blocked_by from whatever real task payloads carry.

        A structured task's `blocked_by` shows up as a string, a list of
        dependency labels (a task blocked by several others), or null.
        Coerce any of them to a single display string so the current-state
        surface never 500s on a list-valued blocked_by.
        """
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, (list, tuple)):
            labels = [str(item).strip() for item in value if str(item).strip()]
            return ", ".join(labels) or None
        return str(value).strip() or None


class RecentActivityEntry(BaseModel):
    """One recent checkpoint, newest-first. Spans all branches so the
    surface honestly reflects 'what has been happening'."""
    checkpoint_id: uuid.UUID
    checkpoint_hash: str
    message: str
    author_agent: Optional[str] = None
    branch_name: str
    created_at: datetime
    has_milestone: bool = False


class CurrentStateResponse(BaseModel):
    """Composite, packaged snapshot for `GET /current/spaces/{id}`.

    One round trip. Shared payload contract between this endpoint, the
    `smriti current` CLI command, and the Project Current State UI panel.
    """
    space_id: uuid.UUID
    name: str
    description: Optional[str] = None
    current_direction: CurrentDirection
    counts: CurrentCounts
    attention: list[AttentionSignal] = Field(default_factory=list)
    active_work: list[ActiveClaimSummary] = Field(default_factory=list)
    recent_milestones: list[MilestoneEntry] = Field(default_factory=list)
    open_tasks_by_intent: dict[str, list[CurrentTask]] = Field(default_factory=dict)
    recent_activity: list[RecentActivityEntry] = Field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_task(raw: object) -> Optional[CurrentTask]:
    """Coerce a raw task entry into a CurrentTask.

    Tasks in `CommitModel.tasks` (JSONB) are either legacy strings or
    structured dicts. Returns None for empty / unusable entries.
    """
    if isinstance(raw, str):
        text = raw.strip()
        return CurrentTask(text=text) if text else None
    if isinstance(raw, dict):
        text = str(raw.get("text") or "").strip()
        if not text:
            return None
        status = raw.get("status") or "open"
        intent = raw.get("intent_hint") or raw.get("intent_type")
        return CurrentTask(
            text=text,
            id=(raw.get("id") or None),
            intent_hint=(intent or None),
            blocked_by=(raw.get("blocked_by") or None),
            status=status if status in ("open", "done") else "open",
        )
    return None


# ── Endpoint ─────────────────────────────────────────────────────────────────


@router.get("/spaces/{space_id}", response_model=CurrentStateResponse)
def get_current_state(space_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return the packaged current-state snapshot for a space.

    Contains:
      - space header (id, name, description)
      - current_direction — the latest main-branch checkpoint
      - counts — checkpoints, agents, active claims, active branches,
        open tasks, milestones
      - attention — open questions, branch divergence, and active claims,
        as a flat list of typed signals
      - active_work — active work claims (with worktree drift when bound)
      - recent_milestones — milestone notes, newest-first, capped
      - open_tasks_by_intent — open structured tasks from the latest main
        checkpoint, grouped by intent
      - recent_activity — recent checkpoints across all branches, capped

    All data is derived from existing tables. No schema, no events.
    """
    repo = _get_repo(space_id, db)

    # One ordered fetch of every checkpoint, newest-first. The metrics
    # endpoint uses the same all-in-Python pattern — fast at smriti scale.
    all_commits = list(
        db.scalars(
            select(CommitModel)
            .where(CommitModel.repo_id == space_id)
            .order_by(CommitModel.created_at.desc())
        )
    )

    main_head = _get_latest_commit(space_id, db)

    # ── current_direction ────────────────────────────────────────────
    if main_head:
        direction = CurrentDirection(
            objective=(main_head.objective or None),
            headline=(main_head.message or None),
            summary=((main_head.summary or "")[:SUMMARY_PREVIEW_CHARS] or None),
            checkpoint_id=main_head.id,
            checkpoint_hash=main_head.commit_hash,
            author_agent=main_head.author_agent,
            updated_at=main_head.created_at,
        )
    else:
        direction = CurrentDirection()

    # ── single pass: recent activity + milestone scan ────────────────
    recent_activity: list[RecentActivityEntry] = []
    recent_milestones: list[MilestoneEntry] = []
    milestone_total = 0
    for c in all_commits:
        notes = (c.metadata_ or {}).get("notes") or []
        milestone_notes = [
            n for n in notes
            if isinstance(n, dict) and n.get("kind") == "milestone"
        ]
        milestone_total += len(milestone_notes)
        if len(recent_activity) < RECENT_ACTIVITY_CAP:
            recent_activity.append(
                RecentActivityEntry(
                    checkpoint_id=c.id,
                    checkpoint_hash=c.commit_hash,
                    message=c.message or "",
                    author_agent=c.author_agent,
                    branch_name=c.branch_name,
                    created_at=c.created_at,
                    has_milestone=bool(milestone_notes),
                )
            )
        for n in milestone_notes:
            if len(recent_milestones) >= RECENT_MILESTONES_CAP:
                break
            note_text = str(n.get("text") or "").strip()
            if not note_text:
                continue
            recent_milestones.append(
                MilestoneEntry(
                    checkpoint_id=c.id,
                    checkpoint_hash=c.commit_hash,
                    checkpoint_message=c.message or "",
                    note=note_text,
                    author_agent=(n.get("author") or c.author_agent),
                    created_at=(n.get("created_at") or c.created_at),
                )
            )

    # ── counts inputs ────────────────────────────────────────────────
    agents = {c.author_agent for c in all_commits if c.author_agent}
    active_branch_commits = _get_active_branch_heads(space_id, db)
    active_claims = _get_active_claims(space_id, db)

    # ── open tasks grouped by intent (latest main checkpoint) ────────
    open_tasks_by_intent: dict[str, list[CurrentTask]] = {}
    open_task_total = 0
    if main_head:
        grouped: dict[str, list[CurrentTask]] = {k: [] for k in INTENT_ORDER}
        for raw in (main_head.tasks or []):
            task = _normalize_task(raw)
            if task is None or task.status == "done":
                continue
            intent = task.intent_hint if task.intent_hint in VALID_INTENTS else "other"
            grouped[intent].append(task)
            open_task_total += 1
        # Fixed intent order; only non-empty groups appear in the dict.
        for intent in INTENT_ORDER:
            capped = grouped[intent][:TASKS_PER_INTENT_CAP]
            if capped:
                open_tasks_by_intent[intent] = capped

    counts = CurrentCounts(
        checkpoints=len(all_commits),
        agents=len(agents),
        active_claims=len(active_claims),
        active_branches=len(active_branch_commits),
        open_tasks=open_task_total,
        milestones=milestone_total,
    )

    # ── attention signals ────────────────────────────────────────────
    attention: list[AttentionSignal] = []

    # Open questions on the latest main checkpoint.
    if main_head:
        open_qs = [
            str(q).strip()
            for q in (main_head.open_questions or [])
            if str(q).strip()
        ]
        for text in open_qs[:OPEN_QUESTIONS_CAP]:
            attention.append(
                AttentionSignal(kind="open_question", severity="info", message=text)
            )

    # Branch divergence — an active branch disagrees with main on decisions.
    if main_head and active_branch_commits:
        divergence = _compute_space_divergence(main_head, active_branch_commits)
        if divergence and divergence.pairs:
            for pair in divergence.pairs:
                attention.append(
                    AttentionSignal(
                        kind="divergence",
                        severity="warn",
                        message=(
                            f"Branch '{pair.branch_name}' "
                            f"({pair.branch_commit_hash[:7]}) diverges from main "
                            f"on decisions — run compare to reconcile."
                        ),
                    )
                )

    # Active work — an agent currently holds a claim. Part of the
    # founder-facing "check before starting overlapping work" story.
    for claim in active_claims:
        attention.append(
            AttentionSignal(
                kind="active_work",
                severity="info",
                message=(
                    f"{claim.agent} is working on \"{claim.scope}\" "
                    f"[{claim.intent_type}] — check before starting "
                    f"overlapping work."
                ),
            )
        )

    return CurrentStateResponse(
        space_id=repo.id,
        name=repo.name,
        description=repo.description,
        current_direction=direction,
        counts=counts,
        attention=attention,
        active_work=active_claims,
        recent_milestones=recent_milestones,
        open_tasks_by_intent=open_tasks_by_intent,
        recent_activity=recent_activity,
    )
