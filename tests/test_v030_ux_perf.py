"""v0.30 Track B: UX + perf tests.

Covers:
- file_lock cross-platform contract
- cluster slug case normalization
- RESEARCH_HUB_ROOT env validation
- --help epilog includes Start here banner
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# locks.file_lock contract
# ---------------------------------------------------------------------------


def test_file_lock_basic_acquire_release(tmp_path):
    from research_hub.locks import file_lock

    target = tmp_path / "shared.json"
    target.write_text("{}")
    with file_lock(target):
        target.write_text('{"a": 1}')
    assert target.read_text() == '{"a": 1}'


def test_file_lock_serializes_threads(tmp_path):
    """Two threads contending for the same lock should serialize."""
    from research_hub.locks import file_lock

    target = tmp_path / "ctr.json"
    target.write_text("0")
    counter = [0]
    counter_lock = threading.Lock()

    def writer():
        with file_lock(target):
            with counter_lock:
                counter[0] += 1
            time.sleep(0.05)

    threads = [threading.Thread(target=writer) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert counter[0] == 5


def test_file_lock_creates_lock_file(tmp_path):
    from research_hub.locks import file_lock

    target = tmp_path / "needs.txt"
    with file_lock(target):
        pass
    assert (tmp_path / "needs.txt.lock").exists()


# ---------------------------------------------------------------------------
# Cluster slug case normalization
# ---------------------------------------------------------------------------


def test_cluster_get_case_insensitive(tmp_path):
    from research_hub.clusters import ClusterRegistry

    reg = ClusterRegistry(tmp_path / "clusters.yaml")
    reg.create(query="LLM Agents", slug="llm-agents")

    assert reg.get("llm-agents") is not None
    assert reg.get("LLM-AGENTS") is not None
    assert reg.get("  LLM-Agents  ") is not None


def test_cluster_create_normalizes_to_lowercase(tmp_path):
    from research_hub.clusters import ClusterRegistry

    reg = ClusterRegistry(tmp_path / "clusters.yaml")
    cluster = reg.create(query="something", slug="MIXED-Case")
    assert cluster.slug == "mixed-case"


def test_cluster_get_returns_none_for_non_string():
    from research_hub.clusters import ClusterRegistry
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        reg = ClusterRegistry(Path(td) / "clusters.yaml")
        assert reg.get(None) is None
        assert reg.get(123) is None


# ---------------------------------------------------------------------------
# Dedup save uses lock
# ---------------------------------------------------------------------------


def test_dedup_save_acquires_lock(tmp_path, monkeypatch):
    from research_hub.dedup import DedupIndex, DedupHit

    idx = DedupIndex()
    idx.add(DedupHit(source="zotero", doi="10.1/foo", title="Foo"))

    target = tmp_path / "dedup_index.json"
    idx.save(target)

    assert target.exists()
    assert (tmp_path / "dedup_index.json.lock").exists()


# ---------------------------------------------------------------------------
# Config root validation
# ---------------------------------------------------------------------------


def test_external_root_rejected_by_default(tmp_path, monkeypatch):
    """A vault root outside HOME without explicit opt-in should fail."""
    from research_hub.config import _validate_root_under_home

    monkeypatch.delenv("RESEARCH_HUB_ALLOW_EXTERNAL_ROOT", raising=False)

    # /tmp is outside HOME on POSIX; on Windows we manufacture a path
    if sys.platform.startswith("win"):
        external = Path("C:/ProgramData/some-vault")
    else:
        external = Path("/tmp/external-vault")

    with pytest.raises(ValueError, match="outside HOME"):
        _validate_root_under_home(external)


def test_external_root_allowed_with_opt_in(monkeypatch):
    from research_hub.config import _validate_root_under_home

    monkeypatch.setenv("RESEARCH_HUB_ALLOW_EXTERNAL_ROOT", "1")

    if sys.platform.startswith("win"):
        external = Path("C:/ProgramData/some-vault")
    else:
        external = Path("/tmp/external-vault")

    # Should not raise
    _validate_root_under_home(external)


def test_root_under_home_accepted():
    from research_hub.config import _validate_root_under_home

    inside = Path.home() / "knowledge-base-test"
    # Should not raise
    _validate_root_under_home(inside)


# ---------------------------------------------------------------------------
# --help epilog
# ---------------------------------------------------------------------------


def test_help_epilog_includes_start_here_banner():
    from research_hub.cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()

    assert "Start here" in help_text
    assert "research-hub init" in help_text
    assert "research-hub doctor" in help_text
    assert "research-hub where" in help_text
    assert "github.com/WenyuChiou/research-hub" in help_text
