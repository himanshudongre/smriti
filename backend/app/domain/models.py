"""Domain models — pure data structures, no IO."""

from dataclasses import dataclass, field

from app.domain.enums import MessageRole, SessionStatus, TargetTool


@dataclass
class Message:
    """A single message parsed from a transcript."""
    role: MessageRole
    content: str
    position: int


@dataclass
class Decision:
    """A key decision extracted from a session."""
    description: str
    context: str = ""


@dataclass
class Task:
    """A task extracted from a session."""
    description: str
    status: str = "pending"


@dataclass
class OpenQuestion:
    """An unresolved question from a session."""
    question: str
    context: str = ""


@dataclass
class Entity:
    """An important entity mentioned in a session."""
    name: str
    type: str  # e.g., "project", "file", "technology", "person"
    context: str = ""


@dataclass
class CodeSnippet:
    """A significant code snippet from a session."""
    language: str
    code: str
    description: str = ""


@dataclass
class ExtractionResult:
    """The full set of artifacts extracted from a session."""
    summary: str
    decisions: list[Decision] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    open_questions: list[OpenQuestion] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    code_snippets: list[CodeSnippet] = field(default_factory=list)


@dataclass
class ExtractedMemory:
    """A single discrete memory extracted from a conversation."""
    type: str  # e.g., 'episodic', 'semantic', 'task', 'preference', 'decision'
    content: str
    confidence: float = 1.0
    importance: float = 1.0


@dataclass
class ContextPack:
    """A target-specific continuation pack."""
    target_tool: TargetTool
    content: str
    format: str = "markdown"
