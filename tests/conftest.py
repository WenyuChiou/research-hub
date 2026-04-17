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
