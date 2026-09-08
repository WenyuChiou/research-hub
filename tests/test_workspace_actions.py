"""Real ZIP delivery receipts, interruption and duplicate-request invariants."""

from pathlib import Path
import zipfile

import pytest

from research_hub.workspace.actions import ActionService
from research_hub.workspace.core import Workspace, WorkspaceError, digest, file_hash
from research_hub.workspace.tasks import TaskService, _LOCAL_HUMAN


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_HUB_WRITING_ADAPTER", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_AGENT_POLICY", raising=False)
    ws = Workspace(tmp_path)
    ws.create_project(id="study", title="Study")
    tasks = TaskService(ws)
    task = tasks.create("study", operation="review")
    candidate = tmp_path / "candidate.md"
    candidate.write_text("# Candidate\nExplicit evidence limitation.\n", encoding="utf-8")
    task = tasks.import_result(task["id"], prose="Fixture review, not scientific endorsement", artifacts=[{"path": "candidate.md", "sha256": file_hash(candidate)}], input_hash=digest(task["request"]))
    task = tasks.decide(task["id"], outcome="accept", actor="test transport", rationale="Exercise gate invariants", action_hash=task["action_hash"], proof=_LOCAL_HUMAN)
    action = ActionService(ws).prepare_delivery("study", task_ids=[task["id"]])
    return ws, action


def approve(ws, action):
    return ActionService(ws).decide(action["id"], outcome="accept", actor="test transport", rationale="Exercise local delivery only", action_hash=action["action_hash"], proof=_LOCAL_HUMAN)


def test_duplicate_prepare_and_execute_create_one_verified_zip(prepared):
    ws, action = prepared
    actions = ActionService(ws)
    duplicate = actions.prepare_delivery("study", task_ids=[action["packet"]["tasks"][0]["id"]])
    assert duplicate["id"] == action["id"]
    with pytest.raises(WorkspaceError):
        actions.execute(action["id"])
    approve(ws, action)
    first = actions.execute(action["id"])
    second = actions.execute(action["id"])
    assert first["receipt"] == second["receipt"]
    assert len(list((ws.root / ".research/deliveries").glob("*.zip"))) == 1
    with zipfile.ZipFile(ws.root / first["receipt"]["path"]) as archive:
        assert archive.read("candidates/candidate.md") == (ws.root / "candidate.md").read_bytes()


def test_crash_after_write_reconciles_without_replay(prepared, monkeypatch):
    ws, action = prepared
    actions = ActionService(ws)
    approve(ws, action)
    real = actions.reconcile
    monkeypatch.setattr(actions, "reconcile", lambda _id: (_ for _ in ()).throw(RuntimeError("injected after-write crash")))
    with pytest.raises(RuntimeError):
        actions.execute(action["id"])
    assert ActionService(Workspace(ws.root)).get(action["id"])["status"] == "pending_external_action"
    with pytest.raises(WorkspaceError, match="no replay"):
        ActionService(ws).execute(action["id"])
    assert real(action["id"])["status"] == "completed"


@pytest.mark.parametrize("outcome", ["decline", "cancel"])
def test_decline_cancel_cannot_ship(prepared, outcome):
    ws, action = prepared
    actions = ActionService(ws)
    with pytest.raises(WorkspaceError, match="human decision"):
        actions.decide(action["id"], outcome=outcome, actor="agent", rationale="claimed human", action_hash=action["action_hash"])
    actions.decide(action["id"], outcome=outcome, actor="fixture", rationale="test decline", action_hash=action["action_hash"], proof=_LOCAL_HUMAN)
    with pytest.raises(WorkspaceError):
        actions.execute(action["id"])
    assert not (ws.root / ".research/deliveries").exists()


def test_changed_candidate_and_tampered_receipt_fail_closed(prepared):
    ws, action = prepared
    actions = ActionService(ws)
    approve(ws, action)
    original = (ws.root / "candidate.md").read_bytes()
    (ws.root / "candidate.md").write_text("changed", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="candidate changed"):
        actions.execute(action["id"])
    (ws.root / "candidate.md").write_bytes(original)
    done = actions.execute(action["id"])
    (ws.root / done["receipt"]["path"]).write_bytes(b"tampered")
    with pytest.raises(WorkspaceError, match="No replay"):
        actions.execute(action["id"])


def test_shared_path_cannot_hide_a_stale_accepted_candidate(prepared):
    ws, action = prepared
    tasks = TaskService(ws)
    old = action["packet"]["tasks"][0]
    candidate = ws.root / "candidate.md"
    candidate.write_text("A different candidate revision", encoding="utf-8")
    task = tasks.create("study", operation="review")
    task = tasks.import_result(task["id"], prose="Second fixture review", artifacts=[{"path": "candidate.md", "sha256": file_hash(candidate)}], input_hash=digest(task["request"]))
    task = tasks.decide(task["id"], outcome="accept", actor="test transport", rationale="Exercise conflicting revisions", action_hash=task["action_hash"], proof=_LOCAL_HUMAN)
    with pytest.raises(WorkspaceError, match="candidate changed"):
        ActionService(ws).prepare_delivery("study", task_ids=[old["id"], task["id"]])
