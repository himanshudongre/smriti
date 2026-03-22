"""Shared test fixtures and configuration."""

import pathlib

import pytest

from app.domain.enums import MessageRole
from app.domain.models import (
    CodeSnippet,
    Decision,
    Entity,
    ExtractionResult,
    Message,
    OpenQuestion,
    Task,
)
from app.services.llm.mock_provider import MockProvider

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def coding_transcript(fixtures_dir):
    """Load coding session fixture."""
    return (fixtures_dir / "coding_session.txt").read_text()


@pytest.fixture
def planning_transcript(fixtures_dir):
    """Load planning session fixture."""
    return (fixtures_dir / "planning_session.txt").read_text()


@pytest.fixture
def debugging_transcript(fixtures_dir):
    """Load debugging session fixture."""
    return (fixtures_dir / "debugging_session.txt").read_text()


@pytest.fixture
def research_transcript(fixtures_dir):
    """Load research session fixture."""
    return (fixtures_dir / "research_session.txt").read_text()


@pytest.fixture
def unlabeled_transcript(fixtures_dir):
    """Load unlabeled session fixture."""
    return (fixtures_dir / "unlabeled_session.txt").read_text()


@pytest.fixture
def code_heavy_transcript(fixtures_dir):
    """Load code-heavy session fixture."""
    return (fixtures_dir / "code_heavy_session.txt").read_text()


@pytest.fixture
def mock_provider():
    """Mock LLM provider for testing."""
    return MockProvider()


@pytest.fixture
def sample_messages():
    """A set of sample parsed messages for testing."""
    return [
        Message(role=MessageRole.HUMAN, content="Can you help me set up a database?", position=0),
        Message(role=MessageRole.ASSISTANT, content="Sure! I'd recommend using SQLAlchemy. We decided to use PostgreSQL for this project.", position=1),
        Message(role=MessageRole.HUMAN, content="What about the migration tool? We need to handle schema changes.", position=2),
        Message(role=MessageRole.ASSISTANT, content="Use Alembic for migrations. TODO: set up the initial migration script.", position=3),
    ]


@pytest.fixture
def sample_extraction_result():
    """A sample extraction result for testing pack generation."""
    return ExtractionResult(
        summary="Session about setting up a database with SQLAlchemy and PostgreSQL. Discussed migration strategies using Alembic.",
        decisions=[
            Decision(description="Use PostgreSQL as the database", context="Better suited for our use case"),
            Decision(description="Use Alembic for migrations", context="Standard tool for SQLAlchemy"),
        ],
        tasks=[
            Task(description="Set up initial migration script", status="pending"),
            Task(description="Configure database connection pooling", status="pending"),
            Task(description="Create User model", status="completed"),
        ],
        open_questions=[
            OpenQuestion(question="Should we use async SQLAlchemy?", context="Performance considerations"),
        ],
        entities=[
            Entity(name="SQLAlchemy", type="technology", context="ORM framework"),
            Entity(name="PostgreSQL", type="technology", context="Database"),
            Entity(name="Alembic", type="technology", context="Migration tool"),
            Entity(name="models.py", type="file", context="Database models file"),
        ],
        code_snippets=[
            CodeSnippet(
                language="python",
                code="class User(Base):\n    __tablename__ = 'users'\n    id = Column(Integer, primary_key=True)",
                description="User model definition",
            ),
        ],
    )
