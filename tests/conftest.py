"""Shared pytest fixtures for the Research Hub test suite."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "stress: stress/load tests (opt-in via pytest tests/stress/)",
    )


@pytest.fixture
def tmp_path() -> Path:
    root = Path.cwd() / ".pytest-work"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def mock_require_config(monkeypatch):
    monkeypatch.setattr("research_hub.cli.get_config", lambda: None)


@pytest.fixture(autouse=True)
def _auto_mock_require_config(request, monkeypatch):
    """Auto-mock config loading for tests that call cli.main([...]) directly.

    These tests exercise argparse routing and must not depend on whether the
    test environment has a research-hub config installed (CI doesn't).

    Patterns covered:
    - tests/test_cli_*.py (added v0.30-A10 for cli routing tests)
    - tests/test_v0NN_*.py for v030+ feature tests that include CLI dispatch
      (e.g. test_v032_screenshot.py asserts on `main(["dashboard", ...])` and
      hits require_config() in the dispatcher)
    """
    fspath = str(request.node.fspath).replace("\\", "/")
    needs_mock = (
        "/tests/test_cli_" in fspath
        or "/tests/test_v030_" in fspath
        or "/tests/test_v031_" in fspath
        or "/tests/test_v032_" in fspath
        or "/tests/test_v033_" in fspath
        or "/tests/test_v034_" in fspath
    )
    if not needs_mock:
        return
    # Patch get_config only — the cli.main dispatcher detects whether it's
    # been swapped (cli.get_config is require_config.__globals__["get_config"])
    # and skips require_config(). Replacing require_config itself would break
    # that detection because lambda has different __globals__.
    monkeypatch.setattr("research_hub.cli.get_config", lambda: None, raising=False)
