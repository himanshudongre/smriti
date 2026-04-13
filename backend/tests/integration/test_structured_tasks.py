"""Integration tests for structured task round-trip through the API.

Validates the full pipeline:
1. Create a checkpoint with structured task objects via V4 chat commit
2. Read it back via V2 commits endpoint
3. Verify the JSONB round-trip preserves intent_hint, blocked_by, and status
4. Verify backward compatibility: string tasks also round-trip correctly

Also tests the formatter rendering of structured tasks in the state brief.
"""
import uuid

from smriti_cli.formatters import _task_section, format_state_brief


# ── Helpers ──────────────────────────────────────────────────────────────────

DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000000a")


def _create_space(client, name: str = "test-structured-tasks") -> dict:
    """Create a space and return its dict."""
    r = client.post("/api/v2/repos", json={
        "name": name,
        "description": "Test space for structured tasks",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _create_session(client, space_id: str) -> dict:
    """Create a chat session in the given space."""
    r = client.post("/api/v4/chat/sessions", json={
        "repo_id": space_id,
        "title": "test session",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _create_commit_with_tasks(client, space_id: str, session_id: str, tasks: list) -> dict:
    """Create a checkpoint with the given tasks list."""
    r = client.post("/api/v4/chat/commit", json={
        "repo_id": space_id,
        "session_id": session_id,
        "message": "Test checkpoint with structured tasks",
        "summary": "Testing structured task round-trip",
        "objective": "Validate task objects persist through JSONB",
        "decisions": ["Use structured tasks"],
        "tasks": tasks,
        "open_questions": [],
        "entities": ["structured tasks"],
        "artifacts": [],
        "author_agent": "test-agent",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


# ── Tests ────────────────────────────────────────────────────────────────────


def test_structured_task_round_trip(client):
    """Structured task objects survive JSONB round-trip."""
    space = _create_space(client)
    session = _create_session(client, space["id"])

    tasks = [
        {"text": "Implement the endpoint", "intent_hint": "implement"},
        {"text": "Write integration tests", "intent_hint": "test", "blocked_by": "endpoint-impl"},
        {"text": "Update docs", "intent_hint": "docs"},
    ]

    commit = _create_commit_with_tasks(client, space["id"], session["id"], tasks)

    # Read back via V2 commits endpoint
    r = client.get(f"/api/v2/commits/{commit['id']}")
    assert r.status_code == 200, r.text
    data = r.json()

    # Verify tasks round-tripped as structured objects
    assert len(data["tasks"]) == 3

    t0 = data["tasks"][0]
    assert t0["text"] == "Implement the endpoint"
    assert t0["intent_hint"] == "implement"

    t1 = data["tasks"][1]
    assert t1["text"] == "Write integration tests"
    assert t1["intent_hint"] == "test"
    assert t1["blocked_by"] == "endpoint-impl"

    t2 = data["tasks"][2]
    assert t2["text"] == "Update docs"
    assert t2["intent_hint"] == "docs"


def test_mixed_string_and_structured_tasks_round_trip(client):
    """Mix of legacy strings and structured objects survives round-trip."""
    space = _create_space(client, name="test-mixed-tasks")
    session = _create_session(client, space["id"])

    tasks = [
        "Legacy string task",
        {"text": "Structured task", "intent_hint": "implement"},
    ]

    commit = _create_commit_with_tasks(client, space["id"], session["id"], tasks)

    r = client.get(f"/api/v2/commits/{commit['id']}")
    assert r.status_code == 200, r.text
    data = r.json()

    assert len(data["tasks"]) == 2
    # String task round-trips as a string (JSONB preserves the shape)
    assert data["tasks"][0] == "Legacy string task"
    # Structured task round-trips as an object
    assert data["tasks"][1]["text"] == "Structured task"
    assert data["tasks"][1]["intent_hint"] == "implement"


def test_structured_tasks_in_state_brief_formatter():
    """Formatter renders structured tasks with intent tags and blocked_by."""
    tasks = [
        {"text": "Implement freshness", "intent_hint": "implement"},
        {"text": "Write freshness tests", "intent_hint": "test", "blocked_by": "freshness-impl"},
        {"text": "Update README", "intent_hint": "docs", "status": "done"},
        "Legacy string task",
    ]

    out = _task_section(tasks)

    assert "## In progress" in out
    assert "- Implement freshness [implement]" in out
    assert "- Write freshness tests [test] → blocked by: freshness-impl" in out
    assert "- Update README [docs] (done)" in out
    assert "- Legacy string task" in out
    # Legacy task should NOT have intent or status annotations
    lines = out.strip().split("\n")
    legacy_line = [l for l in lines if "Legacy string task" in l][0]
    assert "[" not in legacy_line
    assert "→" not in legacy_line


def test_structured_tasks_in_full_state_brief():
    """End-to-end: structured tasks render correctly inside format_state_brief."""
    space = {"id": "space-uuid", "name": "test-project", "description": ""}
    head = {
        "repo_id": "space-uuid",
        "commit_hash": "abc1234567890",
        "commit_id": "commit-uuid",
        "summary": "",
        "objective": "",
        "latest_session_id": "session-uuid",
        "latest_session_title": "test",
    }
    commit = {
        "id": "commit-uuid",
        "commit_hash": "abc1234567890",
        "branch_name": "main",
        "author_agent": "claude-code",
        "message": "Test checkpoint",
        "summary": "Testing structured tasks in state brief",
        "objective": "Validate rendering",
        "decisions": [],
        "assumptions": [],
        "tasks": [
            {"text": "Build the feature", "intent_hint": "implement"},
            {"text": "Test the feature", "intent_hint": "test", "blocked_by": "build-feature"},
            {"text": "Document it", "intent_hint": "docs"},
        ],
        "open_questions": [],
        "entities": [],
        "artifacts": [],
        "created_at": "2026-04-13T20:00:00Z",
    }

    out = format_state_brief(space, head, commit)

    assert "## In progress" in out
    assert "Build the feature [implement]" in out
    assert "Test the feature [test] → blocked by: build-feature" in out
    assert "Document it [docs]" in out
