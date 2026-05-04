"""
V5 Worktree API routes.

Worktrees provide filesystem-level isolation for agents: each agent gets
its own working directory and git index while sharing the same repository
object store. V1 intentionally stays narrow and does not link worktrees to
claims or enrich the state brief.

Endpoints:
  POST   /api/v5/worktrees                     - create a git worktree
  GET    /api/v5/worktrees?space_id=...        - list worktrees for a space
  GET    /api/v5/worktrees/{worktree_id}       - show one worktree row
  DELETE /api/v5/worktrees/{worktree_id}       - close/remove a worktree
"""
from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import CommitModel, RepoModel, WorkTree
from app.services.worktree_probe import _probe_worktree

router = APIRouter(prefix="/worktrees", tags=["worktrees-v5"])

DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000000a")
VALID_STATUSES = {"active", "closed"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _slugify(value: str, fallback: str = "item") -> str:
    """Lowercase a user/project label into a filesystem/branch-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _default_branch_name(agent: str, suffix: str) -> str:
    return f"smriti/{_slugify(agent, fallback='agent')}/{suffix}"


def _default_worktree_path(space_name: str, agent: str, suffix: str) -> str:
    space_slug = _slugify(space_name, fallback="space")
    agent_slug = _slugify(agent, fallback="agent")
    return str(
        Path.home()
        / ".smriti"
        / "worktrees"
        / space_slug
        / f"{agent_slug}-{suffix}"
    )


def _run_git(
    args: list[str],
    *,
    cwd: str | Path | None = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Run git with captured output and consistent infrastructure errors."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="git executable not found")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="git command timed out")


def _get_repo(space_id: uuid.UUID, db: Session) -> RepoModel:
    repo = db.get(RepoModel, space_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Space not found")
    return repo


def _latest_project_root(space_id: uuid.UUID, db: Session) -> Path:
    stmt = (
        select(CommitModel.project_root)
        .where(
            CommitModel.repo_id == space_id,
            CommitModel.project_root.is_not(None),
            CommitModel.project_root != "",
        )
        .order_by(CommitModel.created_at.desc())
        .limit(1)
    )
    project_root = db.scalars(stmt).first()
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail=(
                "No checkpoint with project_root found for this space; "
                "create a checkpoint from the project checkout first."
            ),
        )

    resolved = Path(project_root).expanduser().resolve()
    if not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"project_root does not exist on disk: {resolved}",
        )
    return resolved


def _current_head(project_root: Path) -> str:
    result = _run_git(["rev-parse", "HEAD"], cwd=project_root)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "could not resolve HEAD"
        raise HTTPException(status_code=500, detail=detail)
    return result.stdout.strip()


def _branch_exists(project_root: Path, branch_name: str) -> bool:
    result = _run_git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
        cwd=project_root,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    detail = result.stderr.strip() or "could not check branch existence"
    raise HTTPException(status_code=500, detail=detail)


def _resolve_target_path(path_value: str) -> Path:
    target = Path(path_value).expanduser()
    if not target.is_absolute():
        raise HTTPException(status_code=400, detail="base_path must be absolute")
    return target.resolve()


def _git_error(result: subprocess.CompletedProcess[str], fallback: str) -> str:
    return result.stderr.strip() or result.stdout.strip() or fallback


# -- Request / Response schemas ----------------------------------------------


class CreateWorkTreeRequest(BaseModel):
    space_id: str
    agent: str
    branch_name: str | None = None
    base_commit_sha: str | None = None
    base_path: str | None = Field(
        default=None,
        description="Absolute target path for the new worktree.",
    )


class WorkTreeResponse(BaseModel):
    id: uuid.UUID
    repo_id: uuid.UUID
    agent: str
    path: str
    branch_name: str
    base_commit_sha: str | None = None
    status: str
    created_at: datetime
    closed_at: datetime | None = None

    model_config = {"from_attributes": True}


class WorkTreeProbe(BaseModel):
    dirty_files: int
    dirty_paths: list[str] = Field(default_factory=list)
    ahead: int
    behind: int
    last_commit_sha: str | None = None
    last_commit_relative: str | None = None


class WorkTreeListEntry(WorkTreeResponse):
    probe: WorkTreeProbe | None = None


# -- Endpoints ----------------------------------------------------------------


@router.post("", response_model=WorkTreeResponse, status_code=201)
def create_worktree(
    payload: CreateWorkTreeRequest,
    db: Session = Depends(get_db),
):
    """Create a git worktree and record it after git succeeds."""
    try:
        space_id = uuid.UUID(payload.space_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid space_id")

    repo = _get_repo(space_id, db)
    agent = payload.agent.strip()
    if not agent:
        raise HTTPException(status_code=400, detail="agent must be non-empty")

    project_root = _latest_project_root(space_id, db)
    suffix = uuid.uuid4().hex[:8]
    branch_name = (payload.branch_name or "").strip() or _default_branch_name(agent, suffix)
    target_path = _resolve_target_path(
        payload.base_path or _default_worktree_path(repo.name, agent, suffix)
    )

    if _branch_exists(project_root, branch_name):
        raise HTTPException(
            status_code=409,
            detail=f"Branch already exists: {branch_name}",
        )

    base_commit_sha = (payload.base_commit_sha or "").strip() or _current_head(project_root)
    target_existed = target_path.exists()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    result = _run_git(
        [
            "worktree",
            "add",
            "-b",
            branch_name,
            str(target_path),
            base_commit_sha,
        ],
        cwd=project_root,
    )
    if result.returncode != 0:
        if target_path.exists() and not target_existed:
            shutil.rmtree(target_path, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail=_git_error(result, "git worktree add failed"),
        )

    worktree = WorkTree(
        repo_id=space_id,
        agent=agent,
        path=str(target_path),
        branch_name=branch_name,
        base_commit_sha=base_commit_sha,
        status="active",
    )
    db.add(worktree)
    db.commit()
    db.refresh(worktree)
    return worktree


@router.get("", response_model=list[WorkTreeListEntry])
def list_worktrees(
    space_id: uuid.UUID = Query(..., description="Space UUID"),
    include_closed: bool = Query(False, description="Include closed worktrees"),
    db: Session = Depends(get_db),
):
    """List worktrees for a space, newest first."""
    _get_repo(space_id, db)
    stmt = (
        select(WorkTree)
        .where(WorkTree.repo_id == space_id)
        .order_by(WorkTree.created_at.desc())
    )
    if not include_closed:
        stmt = stmt.where(WorkTree.status == "active")
    entries = []
    for worktree in db.scalars(stmt).all():
        probe = None
        if worktree.status == "active":
            probed = _probe_worktree(
                str(worktree.id),
                worktree.path,
                worktree.branch_name,
            )
            if probed:
                probe = WorkTreeProbe(**probed)
        entries.append(
            WorkTreeListEntry.model_validate(worktree).model_copy(
                update={"probe": probe},
            )
        )
    return entries


@router.get("/{worktree_id}", response_model=WorkTreeResponse)
def get_worktree(worktree_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return one worktree row."""
    worktree = db.get(WorkTree, worktree_id)
    if not worktree:
        raise HTTPException(status_code=404, detail="Worktree not found")
    return worktree


@router.delete("/{worktree_id}", response_model=WorkTreeResponse)
def close_worktree(
    worktree_id: uuid.UUID,
    force: bool = Query(False, description="Force removal even if dirty"),
    db: Session = Depends(get_db),
):
    """Remove a git worktree and mark its row closed."""
    worktree = db.get(WorkTree, worktree_id)
    if not worktree:
        raise HTTPException(status_code=404, detail="Worktree not found")
    if worktree.status == "closed":
        raise HTTPException(status_code=409, detail="Worktree is already closed")
    if worktree.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Worktree has invalid status: {worktree.status}",
        )

    project_root = _latest_project_root(worktree.repo_id, db)
    worktree_path = Path(worktree.path).expanduser().resolve()

    if not force:
        status = _run_git(["status", "--porcelain"], cwd=worktree_path)
        if status.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=_git_error(status, "git status failed"),
            )
        if status.stdout.strip():
            raise HTTPException(
                status_code=409,
                detail="Worktree has uncommitted changes; pass force=true to remove it.",
            )

    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(worktree_path))
    result = _run_git(args, cwd=project_root)
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=_git_error(result, "git worktree remove failed"),
        )

    worktree.status = "closed"
    worktree.closed_at = _utcnow()
    db.commit()
    db.refresh(worktree)
    return worktree
