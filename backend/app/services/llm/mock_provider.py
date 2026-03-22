"""Mock LLM provider for tests — returns deterministic extraction results."""

from app.domain.models import (
    CodeSnippet,
    Decision,
    Entity,
    ExtractionResult,
    Message,
    OpenQuestion,
    Task,
)


class MockProvider:
    """Deterministic mock LLM provider for testing.

    Returns predictable extraction results based on input message content,
    enabling tests to validate schema structure and pipeline behavior
    without actual LLM calls.
    """

    async def extract(self, messages: list[Message]) -> ExtractionResult:
        """Generate a deterministic extraction result from messages."""
        if not messages:
            return ExtractionResult(
                summary="No messages provided.",
                decisions=[],
                tasks=[],
                open_questions=[],
                entities=[],
                code_snippets=[],
            )

        # Build a simple summary from messages
        all_content = " ".join(m.content for m in messages)
        word_count = len(all_content.split())
        summary = f"Session with {len(messages)} messages and approximately {word_count} words."

        # Extract simple decisions (lines starting with "Decision:" or containing "decided")
        decisions = []
        tasks = []
        open_questions = []
        entities = []
        code_snippets = []

        for msg in messages:
            content = msg.content

            # Look for decision-like patterns
            if "decided" in content.lower() or "decision" in content.lower():
                decisions.append(Decision(
                    description=f"Decision from message {msg.position}",
                    context=content[:200],
                ))

            # Look for task-like patterns
            if "todo" in content.lower() or "task" in content.lower() or "need to" in content.lower():
                tasks.append(Task(
                    description=f"Task from message {msg.position}",
                    status="pending",
                ))

            # Look for question patterns
            if "?" in content:
                open_questions.append(OpenQuestion(
                    question=f"Question from message {msg.position}",
                    context=content[:200],
                ))

            # Look for code blocks
            if "```" in content:
                code_snippets.append(CodeSnippet(
                    language="unknown",
                    code=content,
                    description=f"Code from message {msg.position}",
                ))

        # Always ensure at least one entity
        entities.append(Entity(
            name="session",
            type="concept",
            context="The overall session",
        ))

        return ExtractionResult(
            summary=summary,
            decisions=decisions,
            tasks=tasks,
            open_questions=open_questions,
            entities=entities,
            code_snippets=code_snippets,
        )

    async def extract_memories(self, messages: list[Message]) -> list['app.domain.models.ExtractedMemory']:
        import app.domain.models as models
        if not messages:
            return []
            
        memories = []
        for msg in messages:
            content = msg.content
            if "like" in content.lower() or "prefer" in content.lower():
                memories.append(models.ExtractedMemory(type="preference", content=content))
            elif "task" in content.lower() or "todo" in content.lower():
                memories.append(models.ExtractedMemory(type="task", content=content))
            elif "is a " in content.lower() or "uses " in content.lower():
                memories.append(models.ExtractedMemory(type="semantic", content=content))
            elif len(memories) < 2:
                memories.append(models.ExtractedMemory(type="episodic", content=f"Discussed: {content[:50]}"))
                
        return memories
