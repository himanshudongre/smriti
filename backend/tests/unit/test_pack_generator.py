"""Unit tests for context pack generation — TDD-first test definitions.

These tests validate the generate_pack() pure function which renders
target-specific continuation packs from extraction results.
"""

import pytest

from app.domain.enums import TargetTool
from app.domain.models import ExtractionResult
from app.services.pack_generator import generate_pack


class TestChatGPTPack:
    """Tests for ChatGPT-targeted pack generation."""

    def test_chatgpt_pack_format(self, sample_extraction_result):
        """G1: ChatGPT pack contains conversational continuation prompt."""
        pack = generate_pack(sample_extraction_result, TargetTool.CHATGPT)

        assert "continuing" in pack.content.lower() or "continue" in pack.content.lower()
        assert pack.target_tool == TargetTool.CHATGPT

    def test_chatgpt_pack_includes_summary(self, sample_extraction_result):
        """G5 (ChatGPT): Summary is present in pack."""
        pack = generate_pack(sample_extraction_result, TargetTool.CHATGPT)
        # Summary content should appear
        assert "SQLAlchemy" in pack.content or "database" in pack.content.lower()


class TestClaudePack:
    """Tests for Claude-targeted pack generation."""

    def test_claude_pack_format(self, sample_extraction_result):
        """G2: Claude pack contains structured XML-style sections."""
        pack = generate_pack(sample_extraction_result, TargetTool.CLAUDE)

        assert "<context>" in pack.content
        assert "<summary>" in pack.content
        assert "</context>" in pack.content
        assert pack.target_tool == TargetTool.CLAUDE

    def test_claude_pack_includes_decisions(self, sample_extraction_result):
        """G7 (Claude): Decisions are included in pack."""
        pack = generate_pack(sample_extraction_result, TargetTool.CLAUDE)
        assert "<decisions>" in pack.content
        assert "PostgreSQL" in pack.content


class TestCursorPack:
    """Tests for Cursor-targeted pack generation."""

    def test_cursor_pack_format(self, sample_extraction_result):
        """G3: Cursor pack contains code-focused content with task list."""
        pack = generate_pack(sample_extraction_result, TargetTool.CURSOR)

        assert "## Task Checklist" in pack.content or "## Tasks" in pack.content
        assert "[ ]" in pack.content or "[x]" in pack.content
        assert pack.target_tool == TargetTool.CURSOR

    def test_cursor_pack_code_context(self, sample_extraction_result):
        """G3b: Cursor pack includes code context."""
        pack = generate_pack(sample_extraction_result, TargetTool.CURSOR)
        assert "## Code Context" in pack.content or "```" in pack.content


class TestGenericPack:
    """Tests for generic Markdown pack generation."""

    def test_generic_pack_format(self, sample_extraction_result):
        """G4: Generic pack is clean Markdown with all sections."""
        pack = generate_pack(sample_extraction_result, TargetTool.GENERIC)

        assert "# Session Continuation Pack" in pack.content
        assert "## Summary" in pack.content
        assert pack.target_tool == TargetTool.GENERIC
        assert pack.format == "markdown"

    def test_generic_pack_includes_all_sections(self, sample_extraction_result):
        """G4b: Generic pack includes all artifact sections."""
        pack = generate_pack(sample_extraction_result, TargetTool.GENERIC)

        assert "## Key Decisions" in pack.content
        assert "## Tasks" in pack.content
        assert "## Open Questions" in pack.content
        assert "## Entities" in pack.content


class TestPackContent:
    """Tests for pack content quality across all targets."""

    @pytest.mark.parametrize("target", list(TargetTool))
    def test_pack_includes_summary(self, sample_extraction_result, target):
        """G5: Summary present in every target format."""
        pack = generate_pack(sample_extraction_result, target)
        # The summary content or a reference to it should appear
        assert len(pack.content) > 50  # Pack should have meaningful content

    @pytest.mark.parametrize("target", list(TargetTool))
    def test_pack_includes_tasks(self, sample_extraction_result, target):
        """G6: Active tasks listed in pack."""
        pack = generate_pack(sample_extraction_result, target)
        # Tasks should be mentioned
        assert "migration" in pack.content.lower() or "task" in pack.content.lower()

    @pytest.mark.parametrize("target", list(TargetTool))
    def test_pack_includes_open_questions(self, sample_extraction_result, target):
        """G8: Open questions included in pack."""
        pack = generate_pack(sample_extraction_result, target)
        assert "async" in pack.content.lower() or "question" in pack.content.lower()

    @pytest.mark.parametrize("target", list(TargetTool))
    def test_pack_concise(self, sample_extraction_result, target):
        """G9: Output under 2000 words."""
        pack = generate_pack(sample_extraction_result, target)
        word_count = len(pack.content.split())
        assert word_count < 2000

    def test_all_targets_produce_different_output(self, sample_extraction_result):
        """G11: Each target format is distinct."""
        packs = {
            target: generate_pack(sample_extraction_result, target)
            for target in TargetTool
        }

        contents = [p.content for p in packs.values()]
        # All should be unique
        assert len(set(contents)) == len(contents)


class TestPackEdgeCases:
    """Edge case tests for pack generation."""

    @pytest.mark.parametrize("target", list(TargetTool))
    def test_empty_extraction_result(self, target):
        """G10: Empty extraction result produces valid but minimal pack."""
        empty_result = ExtractionResult(summary="No significant content found.")
        pack = generate_pack(empty_result, target)

        assert isinstance(pack.content, str)
        assert len(pack.content) > 0
        assert pack.target_tool == target

    @pytest.mark.parametrize("target", list(TargetTool))
    def test_pack_is_copy_paste_ready(self, sample_extraction_result, target):
        """G12: No broken formatting in output."""
        pack = generate_pack(sample_extraction_result, target)

        # Should not have incomplete markdown or broken tags
        assert pack.content.count("```") % 2 == 0  # Even number of code fences
        if target == TargetTool.CLAUDE:
            assert pack.content.count("<context>") == pack.content.count("</context>")
