"""Thin HTTP wrapper over the Smriti REST API.

No fancy features. Each method maps to a single endpoint. The CLI layer on
top composes these into user-facing commands and formats output.

All methods raise SmritiError on any non-2xx response. Callers should let
these bubble up to main() which turns them into clean exit codes.
"""

from __future__ import annotations

import os
from typing import Any

import requests


DEFAULT_API_URL = "http://localhost:8000"


class SmritiError(Exception):
    """Raised for any API error or unreachable backend."""

    def __init__(self, message: str, status: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


class SmritiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0):
        self.base_url = (base_url or os.environ.get("SMRITI_API_URL") or DEFAULT_API_URL).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    # ── internals ──────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, *, json: Any = None, params: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.request(
                method=method,
                url=url,
                json=json,
                params=params,
                timeout=self.timeout,
            )
        except requests.ConnectionError as e:
            raise SmritiError(
                f"Could not reach Smriti at {self.base_url}. "
                f"Is the backend running? ({e})"
            )
        except requests.Timeout:
            raise SmritiError(f"Request to {url} timed out after {self.timeout}s")

        if not resp.ok:
            detail_obj: Any = None
            message: str
            try:
                detail_obj = resp.json().get("detail")
            except Exception:
                detail_obj = None
                message = resp.text[:200]
            else:
                if isinstance(detail_obj, str):
                    message = detail_obj
                elif isinstance(detail_obj, dict) and "message" in detail_obj:
                    message = str(detail_obj.get("message"))
                else:
                    message = str(detail_obj) if detail_obj is not None else ""
            raise SmritiError(
                f"{method} {path} failed: HTTP {resp.status_code} — {message}",
                status=resp.status_code,
                detail=detail_obj,
            )

        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # ── spaces (V2) ────────────────────────────────────────────────────────

    def list_spaces(self) -> list[dict]:
        return self._request("GET", "/api/v2/repos")

    def get_space(self, space_id: str) -> dict:
        return self._request("GET", f"/api/v2/repos/{space_id}")

    def create_space(self, name: str, description: str = "") -> dict:
        return self._request(
            "POST",
            "/api/v2/repos",
            json={"name": name, "description": description},
        )

    def delete_space(self, space_id: str) -> None:
        self._request("DELETE", f"/api/v2/repos/{space_id}")

    def resolve_space(self, name_or_id: str) -> dict:
        """Look up a space by UUID or by name. Returns the full space dict.

        Tries UUID lookup first; falls back to scanning the space list and
        matching on name (case-sensitive exact match, then case-insensitive).
        """
        # UUID-ish shape
        if len(name_or_id) == 36 and name_or_id.count("-") == 4:
            try:
                return self.get_space(name_or_id)
            except SmritiError as e:
                if e.status != 404:
                    raise
                # fall through to name lookup

        spaces = self.list_spaces()
        exact = [s for s in spaces if s["name"] == name_or_id]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise SmritiError(
                f"Multiple spaces named '{name_or_id}'. Use the UUID to disambiguate."
            )

        lower = name_or_id.lower()
        case_insensitive = [s for s in spaces if s["name"].lower() == lower]
        if len(case_insensitive) == 1:
            return case_insensitive[0]
        if len(case_insensitive) > 1:
            raise SmritiError(
                f"Multiple spaces matching '{name_or_id}' (case-insensitive). "
                f"Use the UUID to disambiguate."
            )

        raise SmritiError(f"No space found matching '{name_or_id}'")

    # ── checkpoints ────────────────────────────────────────────────────────

    def get_commit(self, commit_id: str) -> dict:
        return self._request("GET", f"/api/v2/commits/{commit_id}")

    def list_commits(self, space_id: str, branch: str | None = None) -> list[dict]:
        params = {"branch": branch} if branch else None
        return self._request("GET", f"/api/v2/repos/{space_id}/commits", params=params)

    def get_head(self, space_id: str) -> dict:
        return self._request("GET", f"/api/v4/chat/spaces/{space_id}/head")

    def get_space_state(self, space_id: str, since: str = "") -> dict:
        """GET /api/v4/chat/spaces/{id}/state

        Returns the multi-branch composite state: space header, main HEAD
        metadata (mirrors /head), full main-branch HEAD commit, up to 5
        active non-main branch summaries, and a lightweight divergence
        signal when any active branch disagrees with main on decisions.

        One round trip, atomic snapshot. Use this instead of
        get_head + get_commit for the continuation brief path — the CLI
        `smriti state` and MCP `smriti_state` both default to this.

        Keys in the returned dict:
            space: {id, name, description}
            head: HeadResponse shape
            commit: full CommitResponse shape (or None if no checkpoints)
            active_branches: list of ActiveBranchSummary
            divergence: DivergenceSummary or None
        """
        params = {}
        if since:
            params["since_commit_id"] = since
        return self._request(
            "GET", f"/api/v4/chat/spaces/{space_id}/state",
            params=params if params else None,
        )

    # ── Work claims ──────────────────────────────────────────────────

    def create_claim(
        self,
        space_id: str,
        agent: str,
        scope: str,
        branch_name: str = "main",
        base_commit_id: str | None = None,
        intent_type: str = "implement",
        ttl_hours: float = 4.0,
    ) -> dict:
        """POST /api/v5/claims — create a work claim."""
        payload = {
            "space_id": space_id,
            "agent": agent,
            "scope": scope,
            "branch_name": branch_name,
            "intent_type": intent_type,
            "ttl_hours": ttl_hours,
        }
        if base_commit_id:
            payload["base_commit_id"] = base_commit_id
        return self._request("POST", "/api/v5/claims", json=payload)

    def update_claim(self, claim_id: str, status: str) -> dict:
        """PATCH /api/v5/claims/{id} — mark done or abandoned."""
        return self._request(
            "PATCH", f"/api/v5/claims/{claim_id}", json={"status": status}
        )

    def list_claims(self, space_id: str, include_expired: bool = False) -> list[dict]:
        """GET /api/v5/claims?space_id=... — list active claims."""
        params = {"space_id": space_id}
        if include_expired:
            params["include_expired"] = "true"
        return self._request("GET", "/api/v5/claims", params=params)

    # ── Branch disposition ────────────────────────────────────────────

    def close_branch(self, space_id: str, branch_name: str, disposition: str) -> dict:
        """PATCH /api/v5/lineage/branches/disposition"""
        return self._request(
            "PATCH",
            "/api/v5/lineage/branches/disposition",
            json={
                "space_id": space_id,
                "branch_name": branch_name,
                "disposition": disposition,
            },
        )

    # ── Checkpoints ──────────────────────────────────────────────────

    def create_chat_commit(self, payload: dict) -> dict:
        """Create a checkpoint via the V4 commit endpoint (full schema).

        Requires session_id. The CLI handles session creation if the caller
        does not supply one.
        """
        return self._request("POST", "/api/v4/chat/commit", json=payload)

    def review_checkpoint(self, commit_id: str) -> dict:
        return self._request("POST", f"/api/v5/checkpoint/{commit_id}/review")

    def extract_checkpoint_content(self, content: str, use_mock: bool = False) -> dict:
        """POST /api/v5/checkpoint/extract

        Sends a freeform markdown document to the extractor endpoint and
        returns the structured checkpoint fields (title, objective, summary,
        decisions, assumptions, tasks, open_questions, entities, artifacts).
        Used by `smriti checkpoint create --extract` to build a commit
        payload from agent output without hand-authoring JSON.
        """
        return self._request(
            "POST",
            "/api/v5/checkpoint/extract",
            json={"content": content, "use_mock": use_mock},
        )

    def compare_checkpoints(self, checkpoint_a_id: str, checkpoint_b_id: str) -> dict:
        """GET /api/v5/lineage/checkpoints/{a}/compare/{b}

        Returns the full CompareResponse dict with `checkpoint_a`,
        `checkpoint_b`, and `diff` (including the new
        `common_ancestor_commit_id` field and normalized shared sets).
        """
        return self._request(
            "GET",
            f"/api/v5/lineage/checkpoints/{checkpoint_a_id}/compare/{checkpoint_b_id}",
        )

    def fork_session(
        self,
        space_id: str,
        checkpoint_id: str,
        branch_name: str = "",
    ) -> dict:
        """POST /api/v5/lineage/sessions/fork

        Returns the ForkSessionResponse: session_id, branch_name,
        forked_from_checkpoint_id, history_base_seq.
        """
        payload: dict = {
            "space_id": space_id,
            "checkpoint_id": checkpoint_id,
        }
        if branch_name:
            payload["branch_name"] = branch_name
        return self._request("POST", "/api/v5/lineage/sessions/fork", json=payload)

    def delete_commit(self, commit_id: str, cascade: bool = False) -> None:
        params = {"cascade": "true"} if cascade else None
        self._request("DELETE", f"/api/v2/commits/{commit_id}", params=params)

    def delete_session(self, session_id: str) -> None:
        self._request("DELETE", f"/api/v4/chat/sessions/{session_id}")

    # ── sessions (used internally by CLI) ──────────────────────────────────

    def create_session(self, repo_id: str, title: str = "", provider: str = "anthropic", model: str = "claude-sonnet-4-6") -> dict:
        return self._request(
            "POST",
            "/api/v4/chat/sessions",
            json={
                "repo_id": repo_id,
                "title": title or "agent-session",
                "provider": provider,
                "model": model,
                "seed_from": "none",
            },
        )
