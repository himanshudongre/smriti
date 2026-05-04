import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import CommitModel, RepoModel

router = APIRouter(prefix="/repos", tags=["repos"])

DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000000a")
logger = logging.getLogger("uvicorn.error")


class RepoCreate(BaseModel):
    name: str = Field(..., description="Name of the repo/project")
    description: str = Field("", description="Optional description")
    project_root: str | None = Field(
        None,
        description="Canonical project checkout path for worktree operations",
    )
    user_id: str | None = Field(None, description="Optional user ID, defaults to demo user")
    metadata_: dict = Field(default_factory=dict, alias="metadata")


class SetProjectRootRequest(BaseModel):
    project_root: str


class RepoResponse(BaseModel):
    id: uuid.UUID
    repo_slug: str | None
    name: str
    description: str
    project_root: str | None
    user_id: uuid.UUID
    metadata_: dict = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CommitResponse(BaseModel):
    id: uuid.UUID
    repo_id: uuid.UUID
    commit_hash: str
    parent_commit_id: uuid.UUID | None
    branch_name: str
    author_agent: str | None
    author_type: str
    project_root: str | None = None
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
    raw_source_text: str | None
    metadata_: dict = Field(serialization_alias="metadata")
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=RepoResponse, status_code=201)
def create_repo(payload: RepoCreate, db: Session = Depends(get_db)):
    """Create a new memory repository."""
    logger.info("request received: POST /api/v2/repos")
    new_repo = RepoModel(
        user_id=uuid.UUID(payload.user_id) if payload.user_id else DEMO_USER_ID,
        name=payload.name,
        description=payload.description,
        project_root=payload.project_root,
        metadata_=payload.metadata_,
    )
    logger.info("before DB call: add")
    db.add(new_repo)
    logger.info("before DB call: commit")
    db.commit()
    logger.info("before DB call: refresh")
    db.refresh(new_repo)
    logger.info("after DB call / before response return")
    return new_repo


@router.get("", response_model=list[RepoResponse])
def list_repos(db: Session = Depends(get_db)):
    """List all repos for the current user."""
    stmt = (
        select(RepoModel)
        .where(RepoModel.user_id == DEMO_USER_ID)
        .order_by(RepoModel.updated_at.desc())
    )
    return db.scalars(stmt).all()


@router.patch("/{repo_id}/project-root", response_model=RepoResponse)
def set_project_root(
    repo_id: uuid.UUID,
    payload: SetProjectRootRequest,
    db: Session = Depends(get_db),
):
    """Set the canonical project_root for a space."""
    repo = db.get(RepoModel, repo_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Space not found")
    if not payload.project_root.strip():
        raise HTTPException(status_code=400, detail="project_root cannot be empty")
    repo.project_root = payload.project_root
    db.commit()
    db.refresh(repo)
    return repo


@router.get("/{repo_id}", response_model=RepoResponse)
def get_repo(repo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific repo."""
    repo = db.get(RepoModel, repo_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


@router.get("/{repo_id}/commits", response_model=list[CommitResponse])
def list_repo_commits(
    repo_id: uuid.UUID,
    branch: str | None = Query(None, description="Filter by branch name"),
    db: Session = Depends(get_db),
):
    """List commits for a repo. Optionally filter by branch name."""
    repo = db.get(RepoModel, repo_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Repo not found")

    stmt = select(CommitModel).where(CommitModel.repo_id == repo_id)
    if branch:
        stmt = stmt.where(CommitModel.branch_name == branch)
    stmt = stmt.order_by(CommitModel.created_at.desc())
    return db.scalars(stmt).all()


@router.get("/{repo_id}/commits/latest", response_model=CommitResponse)
def get_latest_commit(repo_id: uuid.UUID, branch: str = "main", db: Session = Depends(get_db)):
    """Get the latest commit for a repo (and optional branch)."""
    repo = db.get(RepoModel, repo_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Repo not found")

    stmt = (
        select(CommitModel)
        .where(CommitModel.repo_id == repo_id, CommitModel.branch_name == branch)
        .order_by(CommitModel.created_at.desc())
        .limit(1)
    )

    commit = db.scalars(stmt).first()
    if not commit:
        raise HTTPException(status_code=404, detail="No commits found for this repo/branch")
    return commit


@router.delete("/{repo_id}", status_code=204)
def delete_repo(repo_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """Delete a space and cascade to all its commits, sessions, and turns."""
    repo = db.get(RepoModel, repo_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Repo not found")
    db.delete(repo)
    db.commit()
    return Response(status_code=204)
