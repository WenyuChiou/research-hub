"""Offline preflight only: does not import Playwright or launch a browser."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

from research_hub.workspace.core import Workspace
from research_hub.workspace.service import WorkspaceService
from research_hub.workspace.tasks import TaskService

SPEC = importlib.util.spec_from_file_location(
    "workspace_browser_fixtures",
    Path(__file__).resolve().parents[1] / "scripts" / "workspace_browser_fixtures.py",
)
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    for name in ("RESEARCH_HUB_WRITING_ADAPTER", "RESEARCH_HUB_AGENT_POLICY", "RESEARCH_HUB_AGENT_CHECKPOINT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("No process or provider allowed"))
    ws = Workspace(tmp_path)
    return ws, fixtures.prepare_abstract_fixtures(ws)


def test_actual_preview_and_selected_only_prepare(seeded):
    ws, data = seeded
    result = WorkspaceService(ws.root).preview_text(
        data["project_id"], artifact_id=data["artifact"]["id"],
    )["preview"]
    assert result["text"] == fixtures.SOURCE
    assert result["truncated"] is False
    task = TaskService(ws).create(
        data["project_id"], operation="paper-abstract-draft", mode="connected",
        source_selection=data["selection"],
    )
    pack = task["request"]["research_draft"]["source_pack"]
    assert pack["text"] == fixtures.ABSTRACT
    assert pack["source_record_id"] == data["source"]["id"]
    assert pack["artifact_id"] == data["artifact"]["id"]
    assert pack["source_sha256"] == result["sha256"]
    assert "UNSELECTED" not in pack["text"]
    assert task["status"] == "ready"
    assert not ws.snapshot(data["project_id"])["actions"]


def test_synthetic_accepted_abstracts_use_real_stale_unknown_checks(seeded):
    ws, data = seeded
    tasks = TaskService(ws)
    changed = data["accepted"]["changed"]
    other = data["accepted"]["current"]
    assert len(tasks.list(data["project_id"])) == 2
    assert tasks.get(changed["id"])["freshness"]["status"] == "current"
    changed["path"].write_text("Changed synthetic candidate", encoding="utf-8")
    assert tasks.get(changed["id"])["freshness"]["status"] == "stale"
    changed["path"].unlink()
    assert tasks.get(changed["id"])["freshness"]["status"] == "unknown"
    assert tasks.get(other["id"])["freshness"]["status"] == "current"
    assert tasks.get(changed["id"])["status"] == "completed"
    assert tasks.get(changed["id"])["result"]["semantic_acceptance"] == "accept"
    assert data["source_path"].read_bytes() == fixtures.SOURCE.encode("utf-8")
    assert not ws.snapshot(data["project_id"])["actions"]


def test_fixture_rejects_external_writing_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_HUB_WRITING_ADAPTER", "not-to-be-invoked")
    with pytest.raises(RuntimeError, match="no external writing adapter"):
        fixtures.prepare_abstract_fixtures(Workspace(tmp_path))
