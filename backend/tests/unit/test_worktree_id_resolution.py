"""Unit coverage for worktree UUID/prefix resolution."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes.worktrees import _resolve_worktree_id


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, *, get_result=None, prefix_rows=None):
        self.get_result = get_result
        self.prefix_rows = prefix_rows or []

    def get(self, model, key):
        return self.get_result

    def scalars(self, stmt):
        return _Scalars(self.prefix_rows)


def _worktree(value: str):
    return SimpleNamespace(id=uuid.UUID(value))


def test_resolve_worktree_id_rejects_too_short_prefix():
    with pytest.raises(HTTPException) as exc:
        _resolve_worktree_id("abc", _FakeSession())

    assert exc.value.status_code == 400
    assert "at least 4 characters" in exc.value.detail


def test_resolve_worktree_id_returns_full_uuid_match():
    row = _worktree("11111111-1111-4111-8111-111111111111")

    assert _resolve_worktree_id(str(row.id), _FakeSession(get_result=row)) is row


def test_resolve_worktree_id_prefix_no_match():
    with pytest.raises(HTTPException) as exc:
        _resolve_worktree_id("deadbeef", _FakeSession(prefix_rows=[]))

    assert exc.value.status_code == 404
    assert "No worktree matches prefix" in exc.value.detail


def test_resolve_worktree_id_prefix_ambiguous():
    rows = [
        _worktree("abcd1111-1111-4111-8111-111111111111"),
        _worktree("abcd2222-2222-4222-8222-222222222222"),
    ]

    with pytest.raises(HTTPException) as exc:
        _resolve_worktree_id("abcd", _FakeSession(prefix_rows=rows))

    assert exc.value.status_code == 422
    assert "ambiguous" in exc.value.detail
    assert "abcd1111" in exc.value.detail
    assert "abcd2222" in exc.value.detail
