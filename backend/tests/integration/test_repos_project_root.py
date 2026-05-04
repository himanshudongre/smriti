"""Regression coverage for canonical project_root on spaces."""

from __future__ import annotations

import uuid


def test_create_repo_with_project_root(client):
    r = client.post(
        "/api/v2/repos",
        json={"name": "Rooted Repo", "project_root": "/tmp/rooted-repo"},
    )

    assert r.status_code == 201, r.text
    assert r.json()["project_root"] == "/tmp/rooted-repo"


def test_create_repo_without_project_root(client):
    r = client.post("/api/v2/repos", json={"name": "No Root Repo"})

    assert r.status_code == 201, r.text
    assert r.json()["project_root"] is None


def test_set_project_root_endpoint(client):
    created = client.post("/api/v2/repos", json={"name": "Patch Root"}).json()

    r = client.patch(
        f"/api/v2/repos/{created['id']}/project-root",
        json={"project_root": "/tmp/patched-root"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["project_root"] == "/tmp/patched-root"


def test_set_project_root_empty_rejected(client):
    created = client.post("/api/v2/repos", json={"name": "Empty Root"}).json()

    r = client.patch(
        f"/api/v2/repos/{created['id']}/project-root",
        json={"project_root": "   "},
    )

    assert r.status_code == 400
    assert "project_root cannot be empty" in r.json()["detail"]


def test_set_project_root_nonexistent_repo(client):
    r = client.patch(
        f"/api/v2/repos/{uuid.uuid4()}/project-root",
        json={"project_root": "/tmp/missing"},
    )

    assert r.status_code == 404
    assert "Space not found" in r.json()["detail"]


def test_repo_responses_include_project_root(client):
    created = client.post(
        "/api/v2/repos",
        json={"name": "Response Root", "project_root": "/tmp/response-root"},
    ).json()

    fetched = client.get(f"/api/v2/repos/{created['id']}")
    listed = client.get("/api/v2/repos")

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["project_root"] == "/tmp/response-root"
    assert any(
        repo["id"] == created["id"] and repo["project_root"] == "/tmp/response-root"
        for repo in listed.json()
    )
