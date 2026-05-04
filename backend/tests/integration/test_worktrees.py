"""Integration tests for the V5 worktree API.

These tests use a real temporary git repository on disk. That is the
important safety boundary for this feature: V1 is about filesystem/index
isolation, so the API must exercise real `git worktree` behavior.
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from app.api.routes import worktrees


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def _create_repo(client, name="Worktree Test Repo"):
    r = client.post("/api/v2/repos", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_session(client, repo_id, title="worktree test"):
    r = client.post(
        f"/api/v4/chat/spaces/{repo_id}/sessions",
        json={"title": title, "provider": "openrouter", "model": "mock"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _commit_with_root(client, repo_id, session_id, project_root: Path):
    payload = {
        "repo_id": repo_id,
        "session_id": session_id,
        "message": "base",
        "summary": "base",
        "project_root": str(project_root),
    }
    r = client.post("/api/v4/chat/commit", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_project_with_root(client, git_repo: Path):
    repo_id = _create_repo(client)
    session_id = _create_session(client, repo_id)
    _commit_with_root(client, repo_id, session_id, git_repo)
    return repo_id


def _create_worktree(client, space_id: str, **kwargs):
    payload = {
        "space_id": space_id,
        "agent": kwargs.pop("agent", "codex-local"),
        **kwargs,
    }
    return client.post("/api/v5/worktrees", json=payload)


def test_create_worktree_inserts_row_creates_directory_and_branch(
    client,
    tmp_path,
    monkeypatch,
):
    git_repo = _init_git_repo(tmp_path)
    space_id = _create_project_with_root(client, git_repo)
    monkeypatch.setattr(worktrees.Path, "home", lambda: tmp_path / "home")

    r = _create_worktree(client, space_id, agent="Codex Local")

    assert r.status_code == 201, r.text
    data = r.json()
    worktree_path = Path(data["path"])
    assert worktree_path.exists()
    assert data["agent"] == "Codex Local"
    assert data["branch_name"].startswith("smriti/codex-local/")
    assert data["base_commit_sha"] == _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    assert data["status"] == "active"
    assert _git(
        git_repo,
        "show-ref",
        "--verify",
        f"refs/heads/{data['branch_name']}",
    ).returncode == 0


def test_create_worktree_honors_explicit_branch_base_and_path(client, tmp_path):
    git_repo = _init_git_repo(tmp_path)
    space_id = _create_project_with_root(client, git_repo)
    base_sha = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    target = tmp_path / "custom-worktree"

    r = _create_worktree(
        client,
        space_id,
        branch_name="feature/custom-worktree",
        base_commit_sha=base_sha,
        base_path=str(target),
    )

    assert r.status_code == 201, r.text
    data = r.json()
    assert data["branch_name"] == "feature/custom-worktree"
    assert data["base_commit_sha"] == base_sha
    assert data["path"] == str(target.resolve())
    assert target.exists()


def test_create_worktree_existing_branch_rejected_without_row_or_directory(
    client,
    tmp_path,
):
    git_repo = _init_git_repo(tmp_path)
    space_id = _create_project_with_root(client, git_repo)
    _git(git_repo, "branch", "existing-worktree-branch")
    target = tmp_path / "should-not-exist"

    r = _create_worktree(
        client,
        space_id,
        branch_name="existing-worktree-branch",
        base_path=str(target),
    )

    assert r.status_code == 409
    assert "Branch already exists" in r.json()["detail"]
    assert not target.exists()
    assert client.get(f"/api/v5/worktrees?space_id={space_id}").json() == []


def test_list_show_and_close_clean_worktree(client, tmp_path):
    git_repo = _init_git_repo(tmp_path)
    space_id = _create_project_with_root(client, git_repo)
    target = tmp_path / "list-show-close"
    created = _create_worktree(client, space_id, base_path=str(target)).json()

    list_r = client.get(f"/api/v5/worktrees?space_id={space_id}")
    assert list_r.status_code == 200
    assert [w["id"] for w in list_r.json()] == [created["id"]]

    show_r = client.get(f"/api/v5/worktrees/{created['id']}")
    assert show_r.status_code == 200
    assert show_r.json()["path"] == str(target.resolve())

    close_r = client.delete(f"/api/v5/worktrees/{created['id']}")
    assert close_r.status_code == 200, close_r.text
    closed = close_r.json()
    assert closed["status"] == "closed"
    assert closed["closed_at"] is not None
    assert not target.exists()

    active_r = client.get(f"/api/v5/worktrees?space_id={space_id}")
    assert active_r.status_code == 200
    assert active_r.json() == []

    all_r = client.get(f"/api/v5/worktrees?space_id={space_id}&include_closed=true")
    assert len(all_r.json()) == 1


def test_list_includes_probe_data_for_active_worktrees(client, tmp_path, monkeypatch):
    git_repo = _init_git_repo(tmp_path)
    space_id = _create_project_with_root(client, git_repo)
    target = tmp_path / "probe-worktree"
    created = _create_worktree(client, space_id, base_path=str(target)).json()

    def fake_probe(worktree_id, path, branch):
        assert worktree_id == created["id"]
        assert path == str(target.resolve())
        assert branch == created["branch_name"]
        return {
            "id": worktree_id,
            "path": path,
            "branch": branch,
            "dirty_files": 3,
            "dirty_paths": ["cli/main.py", "backend/app/api/routes/worktrees.py"],
            "ahead": 1,
            "behind": 0,
            "last_commit_sha": "abc1234",
            "last_commit_relative": "5 minutes ago",
        }

    monkeypatch.setattr(worktrees, "_probe_worktree", fake_probe)

    r = client.get(f"/api/v5/worktrees?space_id={space_id}")

    assert r.status_code == 200, r.text
    data = r.json()
    assert data[0]["id"] == created["id"]
    assert data[0]["probe"] == {
        "dirty_files": 3,
        "dirty_paths": ["cli/main.py", "backend/app/api/routes/worktrees.py"],
        "ahead": 1,
        "behind": 0,
        "last_commit_sha": "abc1234",
        "last_commit_relative": "5 minutes ago",
    }


def test_list_probe_null_for_closed_worktrees(client, tmp_path, monkeypatch):
    git_repo = _init_git_repo(tmp_path)
    space_id = _create_project_with_root(client, git_repo)
    created = _create_worktree(
        client,
        space_id,
        base_path=str(tmp_path / "closed-probe"),
    ).json()
    close_r = client.delete(f"/api/v5/worktrees/{created['id']}")
    assert close_r.status_code == 200, close_r.text

    def fail_probe(worktree_id, path, branch):
        raise AssertionError("closed worktrees should not be probed")

    monkeypatch.setattr(worktrees, "_probe_worktree", fail_probe)

    r = client.get(f"/api/v5/worktrees?space_id={space_id}&include_closed=true")

    assert r.status_code == 200, r.text
    assert r.json()[0]["id"] == created["id"]
    assert r.json()[0]["probe"] is None


def test_show_nonexistent_worktree_returns_404(client):
    r = client.get(f"/api/v5/worktrees/{uuid.uuid4()}")
    assert r.status_code == 404


def test_close_dirty_worktree_requires_force(client, tmp_path):
    git_repo = _init_git_repo(tmp_path)
    space_id = _create_project_with_root(client, git_repo)
    target = tmp_path / "dirty-worktree"
    created = _create_worktree(client, space_id, base_path=str(target)).json()
    (target / "dirty.txt").write_text("uncommitted\n")

    r = client.delete(f"/api/v5/worktrees/{created['id']}")

    assert r.status_code == 409
    assert "uncommitted changes" in r.json()["detail"]
    assert target.exists()

    force_r = client.delete(f"/api/v5/worktrees/{created['id']}?force=true")
    assert force_r.status_code == 200, force_r.text
    assert force_r.json()["status"] == "closed"
    assert not target.exists()


def test_close_already_closed_returns_409(client, tmp_path):
    git_repo = _init_git_repo(tmp_path)
    space_id = _create_project_with_root(client, git_repo)
    created = _create_worktree(
        client,
        space_id,
        base_path=str(tmp_path / "already-closed"),
    ).json()
    first = client.delete(f"/api/v5/worktrees/{created['id']}")
    assert first.status_code == 200

    second = client.delete(f"/api/v5/worktrees/{created['id']}")

    assert second.status_code == 409
    assert "already closed" in second.json()["detail"]


def test_create_worktree_requires_project_root(client, tmp_path):
    space_id = _create_repo(client)
    target = tmp_path / "no-root-worktree"

    r = _create_worktree(client, space_id, base_path=str(target))

    assert r.status_code == 400
    assert "project_root" in r.json()["detail"]
    assert not target.exists()


def test_git_infrastructure_error_does_not_write_row_or_leave_target(
    client,
    tmp_path,
    monkeypatch,
):
    git_repo = _init_git_repo(tmp_path)
    space_id = _create_project_with_root(client, git_repo)
    target = tmp_path / "git-missing"
    head_sha = _git(git_repo, "rev-parse", "HEAD").stdout.strip()

    def fake_run_git(args, *, cwd=None, timeout=30.0):
        if args[0] == "show-ref":
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if args[0] == "rev-parse":
            return SimpleNamespace(returncode=0, stdout=f"{head_sha}\n", stderr="")
        if args[:2] == ["worktree", "add"]:
            raise HTTPException(status_code=500, detail="git executable not found")
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(worktrees, "_run_git", fake_run_git)

    r = _create_worktree(client, space_id, base_path=str(target))

    assert r.status_code == 500
    assert "git executable not found" in r.json()["detail"]
    assert not target.exists()
    assert client.get(f"/api/v5/worktrees?space_id={space_id}").json() == []


def _init_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "project"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("hello\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    return repo
