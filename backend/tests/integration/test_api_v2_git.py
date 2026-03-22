import pytest

def test_repo_lifecycle(client):
    # 1. Create Repo
    repo_resp = client.post("/api/v2/repos", json={
        "name": "Integration Test Repo",
        "description": "Repo testing"
    })
    assert repo_resp.status_code == 201
    repo_id = repo_resp.json()["id"]
    assert repo_resp.json()["name"] == "Integration Test Repo"

    # 2. Get Repo
    get_resp = client.get(f"/api/v2/repos/{repo_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Integration Test Repo"

    # 3. List Repos
    list_resp = client.get("/api/v2/repos")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1
    assert any(r["id"] == repo_id for r in list_resp.json())


def test_commit_lifecycle(client):
    # Setup repo
    repo_resp = client.post("/api/v2/repos", json={"name": "Commit Test Repo"})
    repo_id = repo_resp.json()["id"]

    # 1. Create first commit
    c1_resp = client.post("/api/v2/commits", json={
        "repo_id": repo_id,
        "author_agent": "chatgpt",
        "author_type": "llm",
        "message": "Init",
        "objective": "Start project"
    })
    assert c1_resp.status_code == 201
    c1_id = c1_resp.json()["id"]
    assert c1_resp.json()["parent_commit_id"] is None

    # 2. Create child commit
    c2_resp = client.post("/api/v2/commits", json={
        "repo_id": repo_id,
        "parent_commit_id": c1_id,
        "author_agent": "claude",
        "author_type": "llm",
        "message": "Update 1",
        "objective": "Continue project"
    })
    assert c2_resp.status_code == 201
    c2_id = c2_resp.json()["id"]
    assert c2_resp.json()["parent_commit_id"] == c1_id

    # 3. Get commit explicitly
    get_c1 = client.get(f"/api/v2/commits/{c1_id}")
    assert get_c1.status_code == 200
    assert get_c1.json()["message"] == "Init"

    # 4. List repo commits
    hist_resp = client.get(f"/api/v2/repos/{repo_id}/commits")
    assert hist_resp.status_code == 200
    hist = hist_resp.json()
    assert len(hist) == 2
    # Ensure descending order 
    assert hist[0]["id"] == c2_id
    assert hist[1]["id"] == c1_id

    # 5. Get latest commit
    latest_resp = client.get(f"/api/v2/repos/{repo_id}/commits/latest")
    assert latest_resp.status_code == 200
    assert latest_resp.json()["id"] == c2_id


def test_context_from_commit(client):
    # Setup repo and commit
    repo_resp = client.post("/api/v2/repos", json={"name": "Context Test Repo"})
    repo_id = repo_resp.json()["id"]

    c1_resp = client.post("/api/v2/commits", json={
        "repo_id": repo_id,
        "author_agent": "user",
        "author_type": "user",
        "message": "Setup memory",
        "summary": "This is a summary text.",
        "tasks": ["Task A", "Task B"],
        "decisions": ["Decision 1"]
    })
    c1_id = c1_resp.json()["id"]
    
    # Generate Generic payload
    ctx_resp = client.post("/api/v2/context/from-commit", json={
        "commit_id": c1_id,
        "target": "generic"
    })
    assert ctx_resp.status_code == 200
    content = ctx_resp.json()["content"]
    assert "Context Test Repo" in content
    assert "This is a summary text." in content
    assert "Task A" in content
    assert "Decision 1" in content
    
    # Generate Claude payload
    ctx_resp_claude = client.post("/api/v2/context/from-commit", json={
        "commit_id": c1_id,
        "target": "claude"
    })
    assert ctx_resp_claude.status_code == 200
    content_claude = ctx_resp_claude.json()["content"]
    assert "<smriti_context>" in content_claude
    assert "<summary>This is a summary text.</summary>" in content_claude


def test_parent_delta(client):
    """parent-delta for root commit returns null parent; child commit returns populated parent."""
    # Setup
    repo_resp = client.post("/api/v2/repos", json={"name": "Delta Test Repo"})
    repo_id = repo_resp.json()["id"]

    # Root commit
    c1_resp = client.post("/api/v2/commits", json={
        "repo_id": repo_id,
        "message": "Root state",
        "tasks": ["Task A"],
        "decisions": ["Decision A"],
    })
    assert c1_resp.status_code == 201
    c1_id = c1_resp.json()["id"]

    # Root delta — parent should be null
    delta_root = client.get(f"/api/v2/context/parent-delta/{c1_id}")
    assert delta_root.status_code == 200
    root_data = delta_root.json()
    assert root_data["current"]["id"] == c1_id
    assert root_data["parent"] is None

    # Child commit with different tasks
    c2_resp = client.post("/api/v2/commits", json={
        "repo_id": repo_id,
        "parent_commit_id": c1_id,
        "message": "Second state",
        "tasks": ["Task A", "Task B"],
        "decisions": ["Decision A", "Decision B"],
    })
    assert c2_resp.status_code == 201
    c2_id = c2_resp.json()["id"]

    # Child delta — parent should have c1 data
    delta_child = client.get(f"/api/v2/context/parent-delta/{c2_id}")
    assert delta_child.status_code == 200
    child_data = delta_child.json()
    assert child_data["current"]["id"] == c2_id
    assert child_data["parent"]["id"] == c1_id
    assert "Task A" in child_data["parent"]["tasks"]
    assert "Task B" not in child_data["parent"]["tasks"]
    assert "Task B" in child_data["current"]["tasks"]

