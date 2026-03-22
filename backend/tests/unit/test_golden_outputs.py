"""Golden output tests — snapshot-based validation.

Verifies that the parser and pack generator produce stable, expected output
for representative fixture transcripts. If a service change alters output,
these tests will catch it.

To update golden snapshots after intentional changes, run:
    pytest tests/unit/test_golden_outputs.py --update-golden
"""

import json
import pathlib

import pytest

from app.domain.enums import MessageRole, TargetTool
from app.domain.models import (
    CodeSnippet,
    Decision,
    Entity,
    ExtractionResult,
    OpenQuestion,
    Task,
)
from app.services.parser import parse_transcript
from app.services.pack_generator import generate_pack

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures"
GOLDEN_DIR = pathlib.Path(__file__).parent.parent / "golden"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


def _load_golden(name: str) -> dict | None:
    path = GOLDEN_DIR / name
    if path.exists():
        return json.loads(path.read_text())
    return None


def _save_golden(name: str, data: dict) -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (GOLDEN_DIR / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# ── Standard extraction result used for pack generation goldens ──────────

STANDARD_EXTRACTION = ExtractionResult(
    summary="Session about database setup with SQLAlchemy and Alembic. Covered User and Task models, migration strategy, and input validation with Pydantic.",
    decisions=[
        Decision(description="Use SQLAlchemy 2.0 mapped_column style", context="Modern approach"),
        Decision(description="Use Alembic with autogenerate for migrations", context="Standard SQLAlchemy migration tool"),
        Decision(description="No soft delete for MVP", context="Keep it simple"),
    ],
    tasks=[
        Task(description="Add indexes on email and status columns", status="pending"),
        Task(description="Create initial migration", status="pending"),
        Task(description="Add error handling middleware", status="pending"),
    ],
    open_questions=[
        OpenQuestion(question="Should we add pagination to the task listing endpoint?", context="API design"),
    ],
    entities=[
        Entity(name="SQLAlchemy", type="technology", context="ORM framework"),
        Entity(name="Alembic", type="technology", context="Migration tool"),
        Entity(name="Pydantic", type="technology", context="Validation"),
        Entity(name="models.py", type="file", context="Database models"),
    ],
    code_snippets=[
        CodeSnippet(
            language="python",
            code="class User(Base):\n    __tablename__ = 'users'\n    id: Mapped[int] = mapped_column(primary_key=True)",
            description="User model",
        ),
    ],
)


class TestParserGolden:
    """Verify parser output stability for fixture transcripts."""

    @pytest.mark.parametrize(
        "fixture_name",
        ["coding_session.txt", "planning_session.txt", "code_heavy_session.txt", "unlabeled_session.txt"],
    )
    def test_parser_output_stable(self, fixture_name, request):
        """Parser produces consistent output for fixture transcripts."""
        raw = _load_fixture(fixture_name)
        messages = parse_transcript(raw)

        golden_name = f"parser_{fixture_name.replace('.txt', '.json')}"
        actual = {
            "message_count": len(messages),
            "roles": [m.role.value for m in messages],
            "positions": [m.position for m in messages],
            "content_lengths": [len(m.content) for m in messages],
        }

        golden = _load_golden(golden_name)
        if golden is None or request.config.getoption("--update-golden", default=False):
            _save_golden(golden_name, actual)
            pytest.skip(f"Golden snapshot created: {golden_name}")
        else:
            assert actual["message_count"] == golden["message_count"], (
                f"Message count changed: {golden['message_count']} → {actual['message_count']}"
            )
            assert actual["roles"] == golden["roles"], "Role detection changed"
            assert actual["positions"] == golden["positions"], "Positions changed"

    def test_coding_session_structure(self):
        """Coding fixture produces expected message structure."""
        raw = _load_fixture("coding_session.txt")
        messages = parse_transcript(raw)

        assert len(messages) >= 4  # Multi-turn conversation
        assert messages[0].role == MessageRole.HUMAN
        assert messages[1].role == MessageRole.ASSISTANT
        # Should preserve code blocks
        has_code = any("```" in m.content for m in messages)
        assert has_code, "Code blocks should be preserved in messages"

    def test_unlabeled_session_fallback(self):
        """Unlabeled fixture falls back to single unknown message."""
        raw = _load_fixture("unlabeled_session.txt")
        messages = parse_transcript(raw)

        assert len(messages) == 1
        assert messages[0].role == MessageRole.UNKNOWN


class TestPackGeneratorGolden:
    """Verify pack generator output stability."""

    @pytest.mark.parametrize("target", list(TargetTool))
    def test_pack_output_stable(self, target, request):
        """Pack generator produces consistent output for standard extraction."""
        pack = generate_pack(STANDARD_EXTRACTION, target)

        golden_name = f"pack_{target.value}.json"
        actual = {
            "target_tool": pack.target_tool.value,
            "format": pack.format,
            "content_length": len(pack.content),
            "content": pack.content,
        }

        golden = _load_golden(golden_name)
        if golden is None or request.config.getoption("--update-golden", default=False):
            _save_golden(golden_name, actual)
            pytest.skip(f"Golden snapshot created: {golden_name}")
        else:
            assert actual["content"] == golden["content"], (
                f"Pack content changed for target {target.value}"
            )

    def test_chatgpt_pack_structure(self):
        """ChatGPT pack has expected conversational structure."""
        pack = generate_pack(STANDARD_EXTRACTION, TargetTool.CHATGPT)
        assert "I'm continuing" in pack.content
        assert "Key decisions already made" in pack.content
        assert "Outstanding tasks" in pack.content

    def test_claude_pack_structure(self):
        """Claude pack has expected XML structure."""
        pack = generate_pack(STANDARD_EXTRACTION, TargetTool.CLAUDE)
        assert "<context>" in pack.content
        assert "<summary>" in pack.content
        assert "<decisions>" in pack.content
        assert "</context>" in pack.content

    def test_cursor_pack_structure(self):
        """Cursor pack has expected code-focused structure."""
        pack = generate_pack(STANDARD_EXTRACTION, TargetTool.CURSOR)
        assert "# Continuation Context" in pack.content
        assert "## Task Checklist" in pack.content
        assert "[ ]" in pack.content  # Pending tasks
        assert "## Technologies" in pack.content

    def test_generic_pack_structure(self):
        """Generic pack has all expected Markdown sections."""
        pack = generate_pack(STANDARD_EXTRACTION, TargetTool.GENERIC)
        assert "# Session Continuation Pack" in pack.content
        assert "## Summary" in pack.content
        assert "## Key Decisions" in pack.content
        assert "## Tasks" in pack.content
        assert "## Open Questions" in pack.content
        assert "## Entities" in pack.content
