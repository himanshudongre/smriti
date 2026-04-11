"""Shared pytest fixtures for the smriti-cli test suite.

The mock_client fixture lives here (rather than inside test_mcp_server.py)
so future test files (test_client.py, test_formatters.py, etc.) can reuse
it without cross-importing.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from smriti_cli import mcp_server
from smriti_cli.client import SmritiClient


@pytest.fixture
def mock_client(monkeypatch) -> MagicMock:
    """Patch mcp_server._client() to return a MagicMock(spec=SmritiClient).

    Returns the mock directly so tests can configure return values and
    assert on method_calls. The spec=SmritiClient argument gives us
    attribute-access validation for free: typing `list_spacse` in a test
    crashes loudly instead of silently passing.
    """
    client = MagicMock(spec=SmritiClient)
    monkeypatch.setattr(mcp_server, "_client", lambda: client)
    return client
