"""Minimal smoke test to prove the pytest harness is wired.

This file exists to ensure the dev tooling (pytest discovery, conftest
loading, package import paths) works from the first commit, before any
real tests land. It should stay passing as the test suite grows.
"""
from __future__ import annotations


def test_smriti_cli_package_imports():
    """The smriti_cli package imports cleanly in the test environment."""
    import smriti_cli

    assert smriti_cli.__version__
