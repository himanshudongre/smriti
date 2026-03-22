from enum import StrEnum


class TargetTool(StrEnum):
    """Supported target tools for context pack generation."""
    CHATGPT = "chatgpt"
    CLAUDE = "claude"
    CURSOR = "cursor"
    GENERIC = "generic"


class SourceTool(StrEnum):
    """Source tools that generated the original transcript."""
    CHATGPT = "chatgpt"
    CLAUDE = "claude"
    CURSOR = "cursor"
    OTHER = "other"


class SessionStatus(StrEnum):
    """Processing status of a session."""
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageRole(StrEnum):
    """Role of a message sender in a transcript."""
    HUMAN = "human"
    ASSISTANT = "assistant"
    UNKNOWN = "unknown"
