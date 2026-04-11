import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import RepoModel, CommitModel, ChatSession
from app.api.routes.repos import CommitResponse, DEMO_USER_ID

router = APIRouter(prefix="/commits", tags=["commits"])


class CheckpointDependent(BaseModel):
    kind: str  # "child_commit" | "forked_session" | "seeded_session"
    id: uuid.UUID
    label: str


class CheckpointDependentsResponse(BaseModel):
    checkpoint_id: uuid.UUID
    child_commits: list[CheckpointDependent]
    forked_sessions: list[CheckpointDependent]
    seeded_sessions: list[CheckpointDependent]
    blocking_count: int

class CommitCreate(BaseModel):
    repo_id: str
    parent_commit_id: str | None = None
    branch_name: str = "main"
    author_agent: str | None = None
    author_type: str = Field("llm", description="user, llm, agent, system")
    project_root: str | None = None
    message: str
    summary: str = ""
    objective: str = ""
    decisions: list = Field(default_factory=list)
    tasks: list = Field(default_factory=list)
    open_questions: list = Field(default_factory=list)
    entities: list = Field(default_factory=list)
    context_blob: dict = Field(default_factory=dict)
    raw_source_text: str | None = None
    metadata_: dict = Field(default_factory=dict, alias="metadata")

def _generate_commit_hash(payload: CommitCreate) -> str:
    """Generate a deterministic-ish commit hash based on state snapshot."""
    content = {
        "repo_id": payload.repo_id,
        "parent": payload.parent_commit_id,
        "message": payload.message,
        "summary": payload.summary,
        "ts": datetime.utcnow().isoformat()
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()

@router.post("", response_model=CommitResponse, status_code=201)
def create_commit(payload: CommitCreate, db: Session = Depends(get_db)):
    """Create a new commit (state snapshot)."""
    repo = db.get(RepoModel, uuid.UUID(payload.repo_id))
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Repo not found")
        
    parent_id = uuid.UUID(payload.parent_commit_id) if payload.parent_commit_id else None
    if parent_id:
        parent = db.get(CommitModel, parent_id)
        if not parent or parent.repo_id != repo.id:
            raise HTTPException(status_code=400, detail="Invalid parent commit")

    commit_hash = _generate_commit_hash(payload)
    
    new_commit = CommitModel(
        repo_id=repo.id,
        commit_hash=commit_hash,
        parent_commit_id=parent_id,
        branch_name=payload.branch_name,
        author_agent=payload.author_agent,
        author_type=payload.author_type,
        project_root=payload.project_root,
        message=payload.message,
        summary=payload.summary,
        objective=payload.objective,
        decisions=payload.decisions,
        tasks=payload.tasks,
        open_questions=payload.open_questions,
        entities=payload.entities,
        context_blob=payload.context_blob,
        raw_source_text=payload.raw_source_text,
        metadata_=payload.metadata_
    )
    
    db.add(new_commit)
    repo.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(new_commit)
    
    return new_commit

@router.get("/{commit_id}", response_model=CommitResponse)
def get_commit(commit_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific commit."""
    commit = db.get(CommitModel, commit_id)
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")

    repo = db.get(RepoModel, commit.repo_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Commit/Repo not found")

    return commit


def _dependents_payload(
    commit_id: uuid.UUID,
    child_commits: list[CommitModel],
    forks: list[ChatSession],
    seeds: list[ChatSession],
) -> CheckpointDependentsResponse:
    return CheckpointDependentsResponse(
        checkpoint_id=commit_id,
        child_commits=[
            CheckpointDependent(
                kind="child_commit",
                id=c.id,
                label=f"{c.commit_hash[:7]} — {(c.message or '')[:60]}",
            )
            for c in child_commits
        ],
        forked_sessions=[
            CheckpointDependent(
                kind="forked_session",
                id=s.id,
                label=f"{s.branch_name} — {(s.title or 'Untitled')[:60]}",
            )
            for s in forks
        ],
        seeded_sessions=[
            CheckpointDependent(
                kind="seeded_session",
                id=s.id,
                label=(s.title or "Untitled")[:60],
            )
            for s in seeds
        ],
        blocking_count=len(child_commits) + len(forks),
    )


def _collect_descendant_subtree(root_id: uuid.UUID, db: Session) -> list[CommitModel]:
    """BFS down the parent_commit_id DAG; return deepest-first so SET NULL
    never fires on a live row during cascade delete."""
    frontier = [root_id]
    visited: set[uuid.UUID] = set()
    ordered: list[CommitModel] = []
    while frontier:
        next_frontier = []
        for pid in frontier:
            children = db.scalars(
                select(CommitModel).where(CommitModel.parent_commit_id == pid)
            ).all()
            for child in children:
                if child.id in visited:
                    continue
                visited.add(child.id)
                ordered.append(child)
                next_frontier.append(child.id)
        frontier = next_frontier
    return list(reversed(ordered))  # deepest first


@router.delete("/{commit_id}", status_code=204)
def delete_commit(
    commit_id: uuid.UUID,
    cascade: bool = Query(
        False,
        description="Also delete descendant commits and forked sessions",
    ),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a checkpoint. Refuses if it has child commits or forked sessions
    unless cascade=true is passed."""
    commit = db.get(CommitModel, commit_id)
    if not commit:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    repo = db.get(RepoModel, commit.repo_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    child_commits = db.scalars(
        select(CommitModel).where(CommitModel.parent_commit_id == commit_id)
    ).all()
    forked_sessions = db.scalars(
        select(ChatSession).where(ChatSession.forked_from_checkpoint_id == commit_id)
    ).all()
    seeded_sessions = db.scalars(
        select(ChatSession).where(
            ChatSession.seeded_commit_id == commit_id,
            ChatSession.forked_from_checkpoint_id != commit_id,
        )
    ).all()

    blocking_count = len(child_commits) + len(forked_sessions)

    if blocking_count > 0 and not cascade:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Cannot delete checkpoint {commit.commit_hash[:7]}: "
                    f"it has {len(child_commits)} child commit(s) and "
                    f"{len(forked_sessions)} forked session(s). "
                    f"Re-send with ?cascade=true to delete the subtree."
                ),
                "dependents": _dependents_payload(
                    commit_id, list(child_commits), list(forked_sessions), list(seeded_sessions)
                ).model_dump(mode="json"),
            },
        )

    if cascade:
        descendants = _collect_descendant_subtree(commit_id, db)  # deepest first
        ids_in_subtree = {c.id for c in descendants} | {commit_id}
        dep_forks = db.scalars(
            select(ChatSession).where(
                ChatSession.forked_from_checkpoint_id.in_(ids_in_subtree)
            )
        ).all()
        for sess in dep_forks:
            db.delete(sess)  # cascades to TurnEvent
        for descendant in descendants:
            db.delete(descendant)

    db.delete(commit)
    db.commit()
    return Response(status_code=204)
