"""Shared pytest fixtures for the smriti-cli test suite.

The mock_client fixture is added here (rather than in test_mcp_server.py)
so that future test files (test_client.py, test_formatters.py, etc.) can
reuse it without cross-importing.
"""
from __future__ import annotations
