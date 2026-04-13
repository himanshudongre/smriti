"""Checkpoint routes for auto drafting and review."""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ChatSession, CommitModel, TurnEvent
from app.schemas import (
    CheckpointDraftRequest,
    CheckpointDraftResponse,
    CheckpointExtractRequest,
    CheckpointExtractResponse,
    CheckpointReviewResponse,
    ReviewIssue,
)
from app.providers.registry import get_adapter, get_mock_adapter
from app.config_loader import get_config

router = APIRouter()
logger = logging.getLogger(__name__)

_VALID_TASK_INTENTS = {"implement", "review", "investigate", "docs", "test"}


def _normalize_tasks(raw_tasks: list) -> list:
    """Normalize tasks to structured objects.

    Accepts both plain strings and structured objects from the LLM.
    Strings become {"text": string}. Objects are validated: intent_hint
    must be one of the 5 valid intents, blocked_by must be a non-empty
    string. Invalid or empty items are dropped. Deduplicates by text.
    """
    seen: set[str] = set()
    result: list[dict] = []
    for item in raw_tasks:
        if not item:
            continue
        if isinstance(item, str):
            text = item.strip()
            if text and text not in seen:
                seen.add(text)
                result.append({"text": text})
        elif isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            task: dict = {"text": text}
            hint = item.get("intent_hint")
            if isinstance(hint, str) and hint.strip().lower() in _VALID_TASK_INTENTS:
                task["intent_hint"] = hint.strip().lower()
            blocked = item.get("blocked_by")
            if isinstance(blocked, str) and blocked.strip():
                task["blocked_by"] = blocked.strip()
            result.append(task)
    return result


def _fetch_turns_for_draft(
    session_id: uuid.UUID,
    mounted_checkpoint_id: Optional[str],
    history_base_seq: Optional[int],
    num_turns: int,
    db: Session,
) -> list[TurnEvent]:
    """
    Fetch the turns that should be included in the draft.

    Mirrors the three-way isolation logic used by send_message:

    Case 1 — explicit mount (mounted_checkpoint_id + history_base_seq both set):
        Only turns with sequence_number > history_base_seq (post-mount turns only).

    Case 2 — forked session, no explicit mount:
        The session row is the source of truth. If session.forked_from_checkpoint_id
        is set and no explicit mount is active, apply sequence_number > 0 to include
        only fork-local turns and exclude any hypothetical pre-fork leakage.

    Case 3 — main session, HEAD mode:
        All turns in the session (no boundary applied here; the caller can
        further restrict via num_turns).

    Capped at num_turns most recent turns, ordered oldest-first.
    """
    # Load session to inspect fork identity — the session row is the source of truth.
    session = db.get(ChatSession, session_id)

    stmt = (
        select(TurnEvent)
        .where(TurnEvent.session_id == session_id, TurnEvent.role != "system")
    )

    if mounted_checkpoint_id is not None and history_base_seq is not None:
        # Case 1: explicit temporary mount
        stmt = stmt.where(TurnEvent.sequence_number > history_base_seq)
    elif session is not None and session.forked_from_checkpoint_id is not None:
        # Case 2: forked session, no explicit mount — only fork-local turns
        stmt = stmt.where(TurnEvent.sequence_number > 0)
    # Case 3: no filter — all session turns

    stmt = stmt.order_by(TurnEvent.sequence_number.desc()).limit(num_turns)

    # Reverse to chronological order for transcript building
    return list(reversed(db.scalars(stmt).all()))


@router.post("/draft", response_model=CheckpointDraftResponse)
def draft_checkpoint(request: CheckpointDraftRequest, db: Session = Depends(get_db)):
    # 1. Fetch Session
    session = db.get(ChatSession, request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 2. Fetch turns — respects mount isolation
    turns = _fetch_turns_for_draft(
        session_id=request.session_id,
        mounted_checkpoint_id=request.mounted_checkpoint_id,
        history_base_seq=request.history_base_seq,
        num_turns=request.num_turns,
        db=db,
    )

    if not turns:
        return CheckpointDraftResponse()

    transcript = ""
    for turn in turns:
        transcript += f"{turn.role.upper()}: {turn.content}\n\n"

    # 3. Prompt — extract ONLY from the current conversation.
    #    No prior checkpoint context is injected to avoid cross-session contamination.
    prompt = f"""You are a precise metadata extraction assistant.
Your task: extract structured information from the conversation below.
Extract ONLY what is explicitly discussed or decided in this conversation.
Do NOT infer, hallucinate, or carry over content from any other context.
If a field has nothing relevant in the conversation, return an empty string or empty array.

CONVERSATION:
{transcript}

Return a STRICT JSON object with exactly this schema — no extra keys, no markdown:
{{
  "title": "3-5 word title capturing the core topic of this conversation",
  "objective": "The main goal the user is working toward in this conversation (1 sentence, or empty string if unclear)",
  "summary": "Concise narrative of what was discussed and figured out (2-4 sentences)",
  "decisions": ["An explicit decision made in the conversation", "Another explicit decision"],
  "assumptions": ["Something taken for granted but not explicitly decided"],
  "tasks": [
    {{
      "text": "A concrete action item from the conversation",
      "intent_hint": "implement|review|investigate|docs|test or null",
      "blocked_by": "short label of a dependency, or null"
    }}
  ],
  "open_questions": ["An unresolved question from the conversation"],
  "entities": ["Key concept, tool, place, or system mentioned"]
}}

Rules:
- decisions: only include choices explicitly made in the conversation, not hypothetical ones
- assumptions: things the conversation takes for granted that were NOT explicitly debated or decided (e.g., implicit constraints, assumed technology choices, timeline expectations treated as given)
- tasks: action items as objects with "text" (required), "intent_hint" (one of
  "implement", "review", "investigate", "docs", "test", or null), and "blocked_by"
  (short label of a dependency, or null). A plain string is also accepted.
- entities: proper nouns and key technical/domain terms only
- All arrays may be empty if nothing relevant was discussed
- Output ONLY valid JSON. No markdown, no explanation.
"""

    messages = [{"role": "user", "content": prompt}]

    # 4. Call background intelligence provider
    try:
        cfg = get_config()
        bg_provider = cfg.background.provider
        bg_model = cfg.background.model
        adapter = get_adapter(bg_provider, allow_mock=False)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Background provider not configured in Settings. Error: {e}"
        )

    try:
        raw_response = adapter.send(messages, model=bg_model, response_format={"type": "json_object"})
        data = json.loads(raw_response)

        _dedup = lambda items: list(dict.fromkeys([str(x).strip() for x in items if x]))

        return CheckpointDraftResponse(
            title=str(data.get("title", "")).strip(),
            objective=str(data.get("objective", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            decisions=_dedup(data.get("decisions", [])),
            assumptions=_dedup(data.get("assumptions", [])),
            tasks=_normalize_tasks(data.get("tasks", [])),
            open_questions=_dedup(data.get("open_questions", [])),
            entities=_dedup(data.get("entities", [])),
        )

    except json.JSONDecodeError:
        logger.error(f"LLM returned invalid JSON: {raw_response}")
        raise HTTPException(status_code=502, detail="Failed to parse drafted checkpoint (invalid JSON from provider).")
    except Exception as e:
        logger.error(f"LLM extraction error: {e}")
        raise HTTPException(status_code=502, detail=f"Drafting failed: {e}")


# ── Review endpoint ──────────────────────────────────────────────────────────

def _format_bullet_list(items: list, fallback: str = "None listed") -> str:
    if not items:
        return fallback
    return "\n".join(f"- {item}" for item in items)


@router.post("/{checkpoint_id}/review", response_model=CheckpointReviewResponse)
def review_checkpoint(checkpoint_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Review a checkpoint for reasoning consistency.

    Sends the checkpoint's structured fields to the background intelligence
    provider and returns a small number of high-signal issues.
    """
    commit = db.get(CommitModel, checkpoint_id)
    if not commit:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    prompt = f"""You are a reasoning consistency reviewer.
Review this structured checkpoint that captures the state of a reasoning process.

CHECKPOINT:
Title: {commit.message}
Objective: {commit.objective or "(not set)"}
Summary: {commit.summary or "(not set)"}

Assumptions:
{_format_bullet_list(commit.assumptions or [])}

Decisions:
{_format_bullet_list(commit.decisions or [])}

Tasks:
{_format_bullet_list(commit.tasks or [])}

Open Questions:
{_format_bullet_list(commit.open_questions or [])}

Entities:
{", ".join(commit.entities or []) or "None listed"}

Identify ONLY these issue types:

1. CONTRADICTION: Two decisions, or a decision and an assumption, that appear to conflict with each other.
2. HIDDEN_ASSUMPTION: Something the summary or decisions clearly rely on that is not listed as an assumption or decision. Only flag when the implicit reliance is obvious.
3. RESOLVED_QUESTION: An open question that appears already answered by a decision or the summary.
4. UNUSED_ENTITY: An entity that is not referenced in the summary, decisions, tasks, or objective.

Rules:
- Be conservative. Only flag issues you are confident about.
- Prefer precision over recall — it is better to miss an issue than to flag a false one.
- Reference specific text from the checkpoint in each description.
- Return at most 5 issues.
- Suggestions should be brief and actionable.
- If no issues are found, return empty arrays.

Return STRICT JSON — no markdown, no explanation:
{{
  "issues": [
    {{
      "type": "contradiction | hidden_assumption | resolved_question | unused_entity",
      "description": "Brief description referencing specific checkpoint text"
    }}
  ],
  "suggestions": ["Brief actionable suggestion"]
}}"""

    try:
        cfg = get_config()
        bg_provider = cfg.background.provider
        bg_model = cfg.background.model
        adapter = get_adapter(bg_provider, allow_mock=False)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Background provider not configured. Error: {e}"
        )

    try:
        raw_response = adapter.send(
            [{"role": "user", "content": prompt}],
            model=bg_model,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw_response)

        issues = []
        for item in data.get("issues", []):
            issue_type = str(item.get("type", "")).strip()
            desc = str(item.get("description", "")).strip()
            if issue_type and desc:
                issues.append(ReviewIssue(type=issue_type, description=desc))

        suggestions = [str(s).strip() for s in data.get("suggestions", []) if s]

        return CheckpointReviewResponse(
            checkpoint_id=checkpoint_id,
            issues=issues[:5],
            suggestions=suggestions[:5],
        )

    except json.JSONDecodeError:
        logger.error(f"Review returned invalid JSON: {raw_response}")
        raise HTTPException(status_code=502, detail="Failed to parse review response.")
    except Exception as e:
        logger.error(f"Review error: {e}")
        raise HTTPException(status_code=502, detail=f"Review failed: {e}")


# ── Extract endpoint ─────────────────────────────────────────────────────────


@router.post("/extract", response_model=CheckpointExtractResponse)
def extract_checkpoint_content(request: CheckpointExtractRequest):
    """
    Extract Smriti checkpoint schema fields from a freeform markdown document.

    Stateless LLM call that maps the content into title, objective, summary,
    decisions, assumptions, tasks, open_questions, entities, and artifacts.
    Intended to be called from `smriti checkpoint create --extract`, where
    the caller pipes an agent's output document and gets back a ready-to-
    commit payload without hand-writing JSON.
    """
    prompt = f"""You are a precise metadata extraction assistant.
Your task: extract structured checkpoint fields from the freeform markdown document below.
Extract ONLY what is explicitly stated in the document.
Do NOT infer, hallucinate, or add content beyond what the document says.
If a field has nothing relevant, return an empty string or empty array.

If the document already has headed sections matching these field names
("Decisions", "Assumptions", "Tasks", "Open Questions", etc.), preserve
the items in those sections verbatim. If the document uses different
wording but the meaning is clear, map it to the right field.

DOCUMENT:
{request.content}

Return a STRICT JSON object with exactly this schema — no extra keys, no markdown:
{{
  "title": "Short 3-8 word title capturing the core topic",
  "objective": "The main goal this document is working toward (1 sentence)",
  "summary": "Concise narrative of what the document covers (2-5 sentences)",
  "decisions": ["An explicit choice made in the document"],
  "assumptions": ["Something taken for granted but not explicitly debated"],
  "tasks": [
    {{
      "text": "A concrete action item or next step",
      "intent_hint": "implement|review|investigate|docs|test or null",
      "blocked_by": "short label of another task this depends on, or null"
    }}
  ],
  "open_questions": ["An unresolved question"],
  "entities": ["Key concept, tool, technology, or place mentioned"],
  "artifacts": [
    {{
      "id": "short-alpha-id",
      "type": "python|markdown|json|bash|text",
      "label": "Short descriptive label",
      "content": "Full content of the artifact"
    }}
  ]
}}

Rules:
- decisions: only explicit choices from the document, not hypothetical ones
- assumptions: things the document takes for granted that were NOT explicitly debated
- tasks: concrete next steps as objects. Each task has:
  - "text": the action item (required)
  - "intent_hint": classify as "implement", "review", "investigate", "docs", or "test".
    Use null if the intent is unclear. This helps agents pick complementary work.
  - "blocked_by": if this task depends on another task being done first, set to that
    task's short label (e.g. "freshness-impl"). Use null if unblocked.
  - A plain string is also accepted and treated as {{text: string, intent_hint: null, blocked_by: null}}
- entities: proper nouns and technical terms only
- artifacts: fenced code blocks, JSON blocks, or other structured content that should
  be preserved verbatim. The "type" field should match the code fence language when
  present (python, json, bash, etc.) or "text"/"markdown" otherwise. Choose short,
  alphanumeric "id" values (e.g. "a1", "plan", "sample"). Label each artifact briefly.
- All arrays may be empty if nothing relevant appears in the document.
- Output ONLY valid JSON. No markdown wrappers, no explanation.
"""

    try:
        if request.use_mock:
            adapter = get_mock_adapter()
            bg_model = "mock"
        else:
            cfg = get_config()
            bg_model = cfg.background.model
            # allow_mock=True so an unconfigured test env falls back to
            # MockAdapter (which supports JSON-mode responses); production
            # envs always have a real provider configured and go through
            # the real adapter path.
            adapter = get_adapter(cfg.background.provider, allow_mock=True)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Background provider not configured. Error: {e}",
        )

    try:
        raw_response = adapter.send(
            [{"role": "user", "content": prompt}],
            model=bg_model,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw_response)

        _dedup = lambda items: list(dict.fromkeys([str(x).strip() for x in items if x]))

        return CheckpointExtractResponse(
            title=str(data.get("title", "")).strip(),
            objective=str(data.get("objective", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            decisions=_dedup(data.get("decisions", [])),
            assumptions=_dedup(data.get("assumptions", [])),
            tasks=_normalize_tasks(data.get("tasks", [])),
            open_questions=_dedup(data.get("open_questions", [])),
            entities=_dedup(data.get("entities", [])),
            artifacts=[a for a in data.get("artifacts", []) if isinstance(a, dict)],
        )
    except json.JSONDecodeError:
        logger.error(f"Extract LLM returned invalid JSON: {raw_response}")
        raise HTTPException(
            status_code=502,
            detail="Failed to parse extracted checkpoint (invalid JSON from provider).",
        )
    except Exception as e:
        logger.error(f"Extract LLM call failed: {e}")
        raise HTTPException(status_code=502, detail=f"Extract failed: {e}")


# ── Checkpoint notes ─────────────────────────────────────────────────────────

from pydantic import BaseModel, Field
from datetime import datetime, timezone

VALID_NOTE_KINDS = {"note", "milestone", "noise"}


class AddNoteRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    author: str = Field(default="founder", max_length=100)
    kind: str = Field(default="note")


class NoteResponse(BaseModel):
    id: str
    author: str
    text: str
    kind: str
    created_at: str
    checkpoint_id: str


@router.post("/{checkpoint_id}/notes", response_model=NoteResponse, status_code=201)
def add_checkpoint_note(
    checkpoint_id: uuid.UUID,
    payload: AddNoteRequest,
    db: Session = Depends(get_db),
):
    """Add an additive note to a checkpoint without modifying its immutable fields.

    Notes are stored in the checkpoint's metadata_ JSONB field under the
    'notes' key. The checkpoint's decisions, summary, artifacts, and all
    other fields remain untouched. Notes are append-only in v1.
    """
    commit = db.get(CommitModel, checkpoint_id)
    if not commit:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    if payload.kind not in VALID_NOTE_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid kind '{payload.kind}'. Must be one of: {', '.join(sorted(VALID_NOTE_KINDS))}",
        )

    note_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    note = {
        "id": note_id,
        "author": payload.author,
        "text": payload.text,
        "kind": payload.kind,
        "created_at": now,
    }

    # Append to existing notes array in metadata_, creating it if absent.
    meta = dict(commit.metadata_ or {})
    notes = list(meta.get("notes", []))
    notes.append(note)
    meta["notes"] = notes
    commit.metadata_ = meta

    # Force SQLAlchemy to detect the JSONB mutation.
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(commit, "metadata_")

    db.commit()

    return NoteResponse(
        id=note_id,
        author=payload.author,
        text=payload.text,
        kind=payload.kind,
        created_at=now,
        checkpoint_id=str(checkpoint_id),
    )
