"""Pytest test-only shims for the sandboxed filesystem."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from _pytest import pathlib as pytest_pathlib
from _pytest import tmpdir as pytest_tmpdir


def _noop_cleanup(_root):
    """Skip pytest symlink cleanup; the sandbox denies directory iteration there."""


pytest_pathlib.cleanup_dead_symlinks = _noop_cleanup
pytest_tmpdir.cleanup_dead_symlinks = _noop_cleanup


@pytest.fixture
def tmp_path() -> Path:
    """Provide a repo-local temp directory instead of pytest's default temp root."""

    base_dir = Path(__file__).resolve().parent.parent / "test_artifacts"
    base_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = base_dir / f"tmp_{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
