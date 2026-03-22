import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import RepoModel, CommitModel
from app.api.routes.repos import CommitResponse, DEMO_USER_ID

router = APIRouter(prefix="/commits", tags=["commits"])

class CommitCreate(BaseModel):
    repo_id: str
    parent_commit_id: str | None = None
    branch_name: str = "main"
    author_agent: str | None = None
    author_type: str = Field("llm", description="user, llm, agent, system")
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
