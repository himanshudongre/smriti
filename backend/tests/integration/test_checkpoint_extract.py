"""Integration tests for POST /api/v5/checkpoint/extract.

Tests use MockAdapter's JSON-mode path (registry._MOCK_JSON_RESPONSE),
which returns a deterministic canned blob when the caller passes
response_format={"type": "json_object"}. The extract endpoint always
requests JSON mode, so every test hits the canned response.
"""


def _sample_markdown() -> str:
    return """# Design: envdiff CLI

## Objective
Build a stdlib-only CLI that compares two .env files.

## Decisions
- Use argparse, not click
- Single file, not a package

## Assumptions
- Python 3.11+ is available

```python
def main():
    print("hello")
```
"""


def test_extract_happy_path_with_mock(client):
    """Extract endpoint returns canned mock fields when use_mock=True."""
    r = client.post(
        "/api/v5/checkpoint/extract",
        json={"content": _sample_markdown(), "use_mock": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # MockAdapter JSON mode returns the canned _MOCK_JSON_RESPONSE in
    # registry.py — these are the exact values defined there.
    assert data["title"] == "Mock Checkpoint"
    assert data["summary"].startswith("Mock summary")
    assert "Mock decision from provider" in data["decisions"]
    assert "Mock assumption from provider" in data["assumptions"]
    assert "Mock task from provider" in data["tasks"]
    assert "Mock open question from provider" in data["open_questions"]
    assert "MockEntity" in data["entities"]
    assert len(data["artifacts"]) == 1
    assert data["artifacts"][0]["label"] == "Mock artifact"


def test_extract_default_path_returns_shape(client):
    """Default path (no use_mock flag) returns a valid CheckpointExtractResponse
    shape regardless of which provider answers. In a test env with no API
    keys this hits MockAdapter via the allow_mock=True fallback; in a dev
    env with real keys it hits the real provider and returns real extracted
    fields. Either way the response must be well-shaped.
    """
    r = client.post(
        "/api/v5/checkpoint/extract",
        json={"content": _sample_markdown()},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Response shape: every field present, strings are strings, lists are lists.
    assert isinstance(data["title"], str)
    assert isinstance(data["objective"], str)
    assert isinstance(data["summary"], str)
    assert isinstance(data["decisions"], list)
    assert isinstance(data["assumptions"], list)
    assert isinstance(data["tasks"], list)
    assert isinstance(data["open_questions"], list)
    assert isinstance(data["entities"], list)
    assert isinstance(data["artifacts"], list)
    # Something must have been extracted from the sample — the title must be
    # non-empty and at least one decision should appear since the sample has
    # a "## Decisions" section with two bullet points.
    assert data["title"].strip() != ""
    assert len(data["decisions"]) > 0


def test_extract_rejects_empty_content(client):
    """Empty content is a 422 validation error."""
    r = client.post(
        "/api/v5/checkpoint/extract",
        json={"content": "   "},
    )
    assert r.status_code == 422, r.text


def test_extract_rejects_oversized_content(client):
    """Content exceeding 200000 character cap is a 422 validation error."""
    r = client.post(
        "/api/v5/checkpoint/extract",
        json={"content": "x" * 300_000},
    )
    assert r.status_code == 422, r.text
