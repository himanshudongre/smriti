"""Integration tests for GET /health capabilities manifest.

Validates that the health endpoint returns the capabilities list and
git_sha that agents use to detect stale backends.
"""


def test_health_returns_capabilities(client):
    """Health endpoint includes status, git_sha, and capabilities."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()

    assert data["status"] == "ok"
    assert "git_sha" in data
    assert isinstance(data["git_sha"], str)
    assert len(data["git_sha"]) > 0

    assert "capabilities" in data
    assert isinstance(data["capabilities"], list)


def test_health_includes_required_capabilities(client):
    """All shipped features are listed in capabilities."""
    r = client.get("/health")
    data = r.json()
    caps = data["capabilities"]

    required = [
        "claims",
        "structured_tasks",
        "task_ids",
        "checkpoint_notes",
        "branch_disposition",
        "freshness",
        "compact_state",
    ]
    for cap in required:
        assert cap in caps, f"Missing capability: {cap}"
