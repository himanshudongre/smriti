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
    assert data["database"]["mode"] in {"local", "postgres"}
    assert "url_scheme" in data["database"]
    assert "background_intelligence" in data["providers"]


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
        "worktrees",
        "worktree_binding",
        "activation_health",
    ]
    for cap in required:
        assert cap in caps, f"Missing capability: {cap}"


def test_health_exposes_safe_database_status(client):
    """Database status is useful for doctor without exposing credentials."""
    r = client.get("/health")
    data = r.json()
    db = data["database"]

    assert db["mode"] in {"local", "postgres"}
    if db["mode"] == "local":
        assert db["local_db_path"]
        assert "database_url_set" not in db
    else:
        assert "database_url_set" in db
        assert "DATABASE_URL" not in db
