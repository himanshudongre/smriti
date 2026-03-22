import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import RepoModel, CommitModel

router = APIRouter(prefix="/context", tags=["commits"])

# Assuming demo user id checking here if needed
DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000000a")

class ContextFromCommitRequest(BaseModel):
    commit_id: str
    target: str = Field("generic", description="Target platform: chatgpt, claude, cursor, generic")

class ContextBuildResponse(BaseModel):
    content: str
    target_tool: str
    format: str = "markdown"

def _format_list(items: list, title: str) -> str:
    if not items:
        return ""
    bulleted = "\n".join(f"- {item}" for item in items)
    return f"## {title}\n{bulleted}\n\n"

@router.post("/from-commit", response_model=ContextBuildResponse)
def build_context_from_commit(payload: ContextFromCommitRequest, db: Session = Depends(get_db)):
    """Generate a structured continuation context from a specific commit."""
    commit = db.get(CommitModel, uuid.UUID(payload.commit_id))
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")
        
    repo = db.get(RepoModel, commit.repo_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Repo/Commit access denied")

    # Build structured text depending on target
    content = ""
    target = payload.target.lower()
    
    if target == "cursor":
        content += f"# Project State: {repo.name}\n\n"
        content += f"Commit Ref: `{commit.commit_hash}`\n"
        content += f"Branch: `{commit.branch_name}`\n\n"
        if commit.summary:
            content += f"## Summary\n{commit.summary}\n\n"
        if commit.objective:
            content += f"## Current Objective\n{commit.objective}\n\n"
            
        content += _format_list(commit.tasks, "Active Tasks")
        content += _format_list(commit.decisions, "Key Decisions")
        content += _format_list(commit.open_questions, "Open Questions")
        content += _format_list(commit.entities, "Entities")
        
        content += "## Instructions for Cursor\n"
        content += "Please review the tasks and open questions above, and guide me on the next implementation steps."
        
    elif target == "claude":
        content += "<smriti_context>\n"
        content += f"  <repo name=\"{repo.name}\" />\n"
        content += f"  <commit ref=\"{commit.commit_hash}\" />\n"
        if commit.summary:
            content += f"  <summary>{commit.summary}</summary>\n"
        if commit.objective:
            content += f"  <objective>{commit.objective}</objective>\n"
            
        if commit.decisions:
            content += "  <decisions>\n" + "\n".join(f"    <decision>{d}</decision>" for d in commit.decisions) + "\n  </decisions>\n"
        if commit.tasks:
            content += "  <tasks>\n" + "\n".join(f"    <task>{t}</task>" for t in commit.tasks) + "\n  </tasks>\n"
        content += "</smriti_context>\n\n"
        content += "Please assume this state and help me continue working toward the objective."

    else:
        # Generic / ChatGPT
        content += f"--- SMRITI CONTEXT PACK ---\n"
        content += f"Repo: {repo.name}\n"
        content += f"Commit: {commit.commit_hash}\n"
        content += f"---\n\n"
        if commit.summary:
            content += f"**Summary**: {commit.summary}\n\n"
        if commit.objective:
            content += f"**Objective**: {commit.objective}\n\n"
            
        content += _format_list(commit.decisions, "Decisions")
        content += _format_list(commit.tasks, "Tasks")
        content += _format_list(commit.open_questions, "Open Questions")
        content += _format_list(commit.entities, "Entities")
        
        content += "Please use this context as our shared starting point. Acknowledge and let's begin."

    return ContextBuildResponse(
        content=content.strip(),
        target_tool=payload.target,
    )


class CommitSnapshot(BaseModel):
    """Minimal commit fields needed for delta comparison."""
    id: uuid.UUID
    commit_hash: str
    message: str
    summary: str
    objective: str
    decisions: list
    tasks: list
    open_questions: list
    entities: list
    author_agent: str | None
    author_type: str
    branch_name: str
    parent_commit_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ParentDeltaResponse(BaseModel):
    current: CommitSnapshot
    parent: CommitSnapshot | None


@router.get("/parent-delta/{commit_id}", response_model=ParentDeltaResponse)
def get_parent_delta(commit_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return the current commit and its parent (if any) so the frontend can compute diffs."""
    commit = db.get(CommitModel, commit_id)
    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")

    repo = db.get(RepoModel, commit.repo_id)
    if not repo or repo.user_id != DEMO_USER_ID:
        raise HTTPException(status_code=404, detail="Commit access denied")

    parent = None
    if commit.parent_commit_id:
        parent = db.get(CommitModel, commit.parent_commit_id)

    return ParentDeltaResponse(
        current=CommitSnapshot.model_validate(commit),
        parent=CommitSnapshot.model_validate(parent) if parent else None,
    )

