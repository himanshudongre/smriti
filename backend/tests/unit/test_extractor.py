"""Unit tests for the extraction service — TDD-first test definitions.

These tests validate the ExtractorService using the MockProvider,
ensuring schema compliance and structural correctness of extraction results.
"""

import pytest

from app.domain.enums import MessageRole
from app.domain.models import ExtractionResult, Message
from app.services.extractor import ExtractorService
from app.services.llm.mock_provider import MockProvider


@pytest.fixture
def extractor():
    """ExtractorService with MockProvider."""
    return ExtractorService(llm_provider=MockProvider())


class TestExtractionResultSchema:
    """Tests that extraction results conform to expected schema."""

    @pytest.mark.asyncio
    async def test_extraction_result_schema(self, extractor, sample_messages):
        """E1: Result matches ExtractionResult structure."""
        result = await extractor.extract(sample_messages)

        assert isinstance(result, ExtractionResult)
        assert isinstance(result.summary, str)
        assert isinstance(result.decisions, list)
        assert isinstance(result.tasks, list)
        assert isinstance(result.open_questions, list)
        assert isinstance(result.entities, list)
        assert isinstance(result.code_snippets, list)

    @pytest.mark.asyncio
    async def test_summary_non_empty(self, extractor, sample_messages):
        """E2: Summary is non-empty."""
        result = await extractor.extract(sample_messages)
        assert len(result.summary) > 0

    @pytest.mark.asyncio
    async def test_summary_bounded_length(self, extractor, sample_messages):
        """E3: Summary is under 500 words."""
        result = await extractor.extract(sample_messages)
        word_count = len(result.summary.split())
        assert word_count < 500


class TestExtractionArtifactStructure:
    """Tests that individual artifact types are well-formed."""

    @pytest.mark.asyncio
    async def test_decisions_well_formed(self, extractor):
        """E4: Each Decision has a description field."""
        messages = [
            Message(role=MessageRole.HUMAN, content="We decided to use PostgreSQL", position=0),
            Message(role=MessageRole.ASSISTANT, content="Good decision. PostgreSQL is reliable.", position=1),
        ]
        result = await extractor.extract(messages)

        for decision in result.decisions:
            assert hasattr(decision, "description")
            assert isinstance(decision.description, str)
            assert len(decision.description) > 0

    @pytest.mark.asyncio
    async def test_tasks_well_formed(self, extractor):
        """E5: Each Task has description and status."""
        messages = [
            Message(role=MessageRole.HUMAN, content="We need to set up the database. TODO: create schema.", position=0),
            Message(role=MessageRole.ASSISTANT, content="I'll add that task.", position=1),
        ]
        result = await extractor.extract(messages)

        for task in result.tasks:
            assert hasattr(task, "description")
            assert hasattr(task, "status")
            assert isinstance(task.description, str)
            assert isinstance(task.status, str)

    @pytest.mark.asyncio
    async def test_open_questions_well_formed(self, extractor):
        """E6: Each OpenQuestion has a question field."""
        messages = [
            Message(role=MessageRole.HUMAN, content="Should we use Redis? What about caching?", position=0),
            Message(role=MessageRole.ASSISTANT, content="Good questions to consider.", position=1),
        ]
        result = await extractor.extract(messages)

        for question in result.open_questions:
            assert hasattr(question, "question")
            assert isinstance(question.question, str)

    @pytest.mark.asyncio
    async def test_entities_well_formed(self, extractor, sample_messages):
        """E7: Each Entity has name and type."""
        result = await extractor.extract(sample_messages)

        assert len(result.entities) > 0
        for entity in result.entities:
            assert hasattr(entity, "name")
            assert hasattr(entity, "type")
            assert isinstance(entity.name, str)
            assert isinstance(entity.type, str)

    @pytest.mark.asyncio
    async def test_code_snippets_well_formed(self, extractor):
        """E8: Each CodeSnippet has language and code."""
        messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content="Here's the code:\n```python\ndef hello(): pass\n```",
                position=0,
            ),
        ]
        result = await extractor.extract(messages)

        for snippet in result.code_snippets:
            assert hasattr(snippet, "language")
            assert hasattr(snippet, "code")
            assert isinstance(snippet.language, str)
            assert isinstance(snippet.code, str)


class TestExtractionEdgeCases:
    """Tests for edge cases in extraction."""

    @pytest.mark.asyncio
    async def test_empty_messages_handling(self, extractor):
        """E9: Empty list produces valid but minimal result."""
        result = await extractor.extract([])

        assert isinstance(result, ExtractionResult)
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0  # Should have some default message

    @pytest.mark.asyncio
    async def test_mock_provider_deterministic(self, extractor, sample_messages):
        """E10: Same input produces same output every time."""
        result1 = await extractor.extract(sample_messages)
        result2 = await extractor.extract(sample_messages)

        assert result1.summary == result2.summary
        assert len(result1.decisions) == len(result2.decisions)
        assert len(result1.tasks) == len(result2.tasks)

    @pytest.mark.asyncio
    async def test_extraction_with_coding_fixture(self, extractor, coding_transcript):
        """E11: Coding transcript fixture extraction succeeds."""
        from app.services.parser import parse_transcript

        messages = parse_transcript(coding_transcript)
        result = await extractor.extract(messages)
        assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_extraction_with_planning_fixture(self, extractor, planning_transcript):
        """E12: Planning transcript fixture extraction succeeds."""
        from app.services.parser import parse_transcript

        messages = parse_transcript(planning_transcript)
        result = await extractor.extract(messages)
        assert isinstance(result, ExtractionResult)
