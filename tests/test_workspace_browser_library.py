"""Offline data preflight, not a substitute for the real Chromium assertions."""
import importlib.util
from pathlib import Path
import socket
import subprocess

import pytest

from research_hub.setup_snapshot import read_setup_snapshot
from research_hub.workspace.core import Workspace

SPEC = importlib.util.spec_from_file_location(
    "workspace_browser_library",
    Path(__file__).resolve().parents[1] / "scripts" / "workspace_browser_library.py",
)
library = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(library)


def test_library_fixture_has_exact_counts_outer_ids_and_unknown_current_state(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_HUB_WRITING_ADAPTER", raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pytest.fail("No provider/process"))
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("No network"))
    workspace = Workspace(tmp_path)
    fixture = library.prepare_library_fixture(workspace)
    records = workspace.records(fixture["project_id"])
    sources = [r for r in records if r["kind"] == "source"]
    screenings = [r for r in records if r["kind"] == "screening"]
    assert len(sources) == 4 and len(screenings) == 1
    assert len({r["id"] for r in sources}) == 4
    assert screenings[0]["data"]["source_id"] == sources[1]["id"]
    assert sum(not r["data"]["category"].strip() for r in sources) == 1
    assert sum(not any(isinstance(r["data"].get(k), str) and r["data"][k].strip()
                       for k in ("summary", "abstract")) for r in sources) == 2
    assert {r["data"]["identity_status"] for r in sources} == {"unverified"}
    assert {r["data"]["human_acceptance"] for r in sources} == {"pending"}
    assert sources[3]["data"]["reading_level"] == "abstract-snippet"
    assert 4 - len(screenings) == 3
    snapshot = read_setup_snapshot(workspace.root)
    assert snapshot["freshness"] == "saved"
    assert snapshot["current_status"] == "unknown"
    assert snapshot["observed_at"] == fixture["observed_at"]
    assert all(snapshot["components"][name] == "passed" for name in ("vault", "zotero", "notebooklm_auth"))
    assert not workspace.snapshot(fixture["project_id"])["actions"]


def test_library_fixture_rejects_external_writing_adapter_before_seeding(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_HUB_WRITING_ADAPTER", "not-to-be-used")
    workspace = Workspace(tmp_path)
    with pytest.raises(RuntimeError, match="no external writing adapter"):
        library.prepare_library_fixture(workspace)
    assert not workspace.db_path.exists()
