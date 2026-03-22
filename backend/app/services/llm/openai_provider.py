"""OpenAI LLM provider for production extraction."""

import json

from openai import AsyncOpenAI

from app.config import settings
from app.domain.models import (
    CodeSnippet,
    Decision,
    Entity,
    ExtractionResult,
    Message,
    OpenQuestion,
    Task,
)

EXTRACTION_SYSTEM_PROMPT = """You are a precise context extraction engine. Given a conversation transcript, extract structured information.

Return a JSON object with exactly these fields:
{
  "summary": "A concise 3-5 sentence summary of what was discussed and accomplished",
  "decisions": [{"description": "what was decided", "context": "why or relevant context"}],
  "tasks": [{"description": "what needs to be done", "status": "pending|in_progress|completed"}],
  "open_questions": [{"question": "the question", "context": "relevant context"}],
  "entities": [{"name": "entity name", "type": "project|file|technology|person|concept", "context": "how it was mentioned"}],
  "code_snippets": [{"language": "the language", "code": "the code", "description": "what this code does"}]
}

Rules:
- Be concise and actionable
- Only include genuinely important items
- Each decision should be a clear statement
- Each task should be concrete
- Entities should be unique and meaningful
- Code snippets should only include significant code, not trivial examples
- Return valid JSON only, no markdown formatting"""


MEMORY_EXTRACTION_SYSTEM_PROMPT = """You are a precise context extraction engine. Given a conversation transcript, extract discrete, structured memories.

Return a JSON object with exactly this field:
{
  "memories": [
    {
      "type": "episodic|semantic|task|preference|decision",
      "content": "A clear, standalone statement of fact, decision, preference, past event, or pending task.",
      "confidence": 0.9,
      "importance": 0.8
    }
  ]
}

Rules:
- Be concise and actionable.
- Ensure each memory is entirely self-contained (do not just say "the user", use explicit names if possible, else "the user").
- Limit output to genuinely important or useful information.
- Output ONLY valid JSON."""


class OpenAIProvider:
    """Production LLM provider using OpenAI API."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    async def extract(self, messages: list[Message]) -> ExtractionResult:
        """Extract structured artifacts using OpenAI API."""
        if not messages:
            return ExtractionResult(summary="No messages provided.")

        # Format messages for the prompt
        formatted = "\n\n".join(
            f"[{m.role.value.upper()}]: {m.content}" for m in messages
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract context from this transcript:\n\n{formatted}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        raw_json = response.choices[0].message.content
        data = json.loads(raw_json)

        return ExtractionResult(
            summary=data.get("summary", ""),
            decisions=[Decision(**d) for d in data.get("decisions", [])],
            tasks=[Task(**t) for t in data.get("tasks", [])],
            open_questions=[OpenQuestion(**q) for q in data.get("open_questions", [])],
            entities=[Entity(**e) for e in data.get("entities", [])],
            code_snippets=[CodeSnippet(**s) for s in data.get("code_snippets", [])],
        )

    async def extract_memories(self, messages: list[Message]) -> list['app.domain.models.ExtractedMemory']:
        import app.domain.models as models
        if not messages:
            return []
            
        formatted = "\n\n".join(
            f"[{m.role.value.upper()}]: {m.content}" for m in messages
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": MEMORY_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract memories from this transcript:\n\n{formatted}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        raw_json = response.choices[0].message.content
        data = json.loads(raw_json)
        
        memories = []
        for item in data.get("memories", []):
            memories.append(models.ExtractedMemory(
                type=item.get("type", "semantic"),
                content=item.get("content", ""),
                confidence=float(item.get("confidence", 1.0)),
                importance=float(item.get("importance", 1.0)),
            ))
            
        return memories
