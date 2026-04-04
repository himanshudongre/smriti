"""API request and response schemas using Pydantic."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.enums import SessionStatus, TargetTool


# ── Request Schemas ──────────────────────────────────────────────────────────


class SessionCreateRequest(BaseModel):
    """Request body for creating a new session."""
    raw_transcript: str = Field(..., min_length=1, description="The raw transcript text")
    title: str | None = Field(None, max_length=255, description="Optional session title")
    source_tool: str | None = Field(None, description="Source AI tool")


class ContextPackCreateRequest(BaseModel):
    """Request body for generating a context pack."""
    target_tool: TargetTool = Field(..., description="Target tool for continuation pack")


# ── Response Schemas ─────────────────────────────────────────────────────────


class SessionResponse(BaseModel):
    """Response for a session."""
    id: uuid.UUID
    title: str | None
    source_tool: str | None
    status: SessionStatus
    raw_transcript: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DecisionResponse(BaseModel):
    description: str
    context: str = ""


class TaskResponse(BaseModel):
    description: str
    status: str = "pending"


class OpenQuestionResponse(BaseModel):
    question: str
    context: str = ""


class EntityResponse(BaseModel):
    name: str
    type: str
    context: str = ""


class CodeSnippetResponse(BaseModel):
    language: str
    code: str
    description: str = ""


class ArtifactsResponse(BaseModel):
    """Response for extracted artifacts."""
    summary: str
    decisions: list[DecisionResponse]
    tasks: list[TaskResponse]
    open_questions: list[OpenQuestionResponse]
    entities: list[EntityResponse]
    code_snippets: list[CodeSnippetResponse]


class ContextPackResponse(BaseModel):
    """Response for a generated context pack."""
    id: uuid.UUID
    session_id: uuid.UUID
    target_tool: str
    content: str
    format: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: str | None = None

class CheckpointDraftRequest(BaseModel):
    session_id: uuid.UUID
    num_turns: int = Field(15, ge=1, le=100)
    mounted_checkpoint_id: Optional[str] = Field(
        None,
        description="If set, draft only uses turns after history_base_seq (mirrors send_message isolation)."
    )
    history_base_seq: Optional[int] = Field(
        None,
        description="Sequence boundary from mount event. Only turns with sequence_number > this value are included."
    )

class CheckpointDraftResponse(BaseModel):
    title: str = ""
    objective: str = ""
    summary: str = ""
    decisions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class ReviewIssue(BaseModel):
    type: str   # contradiction, hidden_assumption, resolved_question, unused_entity
    description: str


class CheckpointReviewResponse(BaseModel):
    checkpoint_id: uuid.UUID
    issues: list[ReviewIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
