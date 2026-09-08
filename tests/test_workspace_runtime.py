"""Actual SQLite/file/state integration; scientific acceptance is not mocked PASS."""

import json
from pathlib import Path
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError, digest, file_hash, safe_path
from research_hub.workspace.service import call_workspace
from research_hub.workspace.tasks import TaskService, _LOCAL_HUMAN


@pytest.fixture
def ws(tmp_path, monkeypatch):
    for name in ("RESEARCH_HUB_AGENT_POLICY", "RESEARCH_HUB_AGENT_CHECKPOINT", "RESEARCH_HUB_WRITING_ADAPTER"):
        monkeypatch.delenv(name, raising=False)
    workspace = Workspace(tmp_path)
    workspace.create_project(id="sample", title="Sample", goal="Test evidence", archetype="empirical")
    (tmp_path / "paper.md").write_text("# Results\nA bounded observation.\n", encoding="utf-8")
    workspace.register_artifact("sample", path="paper.md", role="main_manuscript")
    return workspace


def returned_task(ws, *, mode="handoff", status="completed"):
    service = TaskService(ws)
    task = service.create("sample", operation="review", mode=mode)
    return service.import_result(task["id"], prose="Scope is limited; no external evidence supplied.", status=status, input_hash=digest(task["request"]))


def test_project_persists_and_workflow_is_referenced(ws):
    restored = Workspace(ws.root)
    snapshot = restored.snapshot("sample")
    assert snapshot["workflow"]["workflow_id"] == "workspace-sample"
    assert snapshot["workflow"]["status"] == "running"
    assert snapshot["artifacts"][0]["current"]
    before = (ws.root / "paper.md").read_bytes()
    with pytest.raises(WorkspaceError, match="already exists"):
        restored.create_project(id="sample", title="Overwrite")
    assert (ws.root / "paper.md").read_bytes() == before


def test_revision_registration_keeps_history_without_stale_active_input(ws):
    first = ws.artifacts("sample")[0]
    (ws.root / "paper.md").write_text("New exact revision", encoding="utf-8")
    assert not ws.artifacts("sample")[0]["current"]
    with pytest.raises(WorkspaceError, match="Registered input changed"):
        TaskService(ws).create("sample", operation="draft")
    revised = ws.register_artifact("sample", path="paper.md", role="main_manuscript")
    assert revised["id"] != first["id"]
    assert len(ws.artifacts("sample")) == 1
    assert len(ws.artifacts("sample", history=True)) == 2
    assert TaskService(ws).create("sample", operation="draft")["status"] == "awaiting_agent"


@pytest.mark.parametrize("outcome,expected", [("accept", "completed"), ("decline", "declined"), ("cancel", "cancelled"), ("revise", "awaiting_agent")])
def test_exact_local_decisions_and_revise_history(ws, outcome, expected):
    task = returned_task(ws)
    assert task["status"] == "awaiting_human"
    service = TaskService(ws)
    decision = dict(outcome=outcome, actor="test human transport", rationale="Fixture exercises decision transport, not scientific approval", action_hash=task["action_hash"])
    with pytest.raises(WorkspaceError, match="trusted local human"):
        service.decide(task["id"], **decision)
    decided = service.decide(task["id"], **decision, proof=_LOCAL_HUMAN)
    assert decided["status"] == expected
    assert len(decided["attempts"]) == 1
    if outcome == "revise":
        assert decided["action_hash"] != task["action_hash"]
        assert decided["result"] is None
    else:
        with pytest.raises(WorkspaceError):
            service.import_result(task["id"], prose="late", input_hash=digest(task["request"]))


@pytest.mark.parametrize("status", ["failed", "cancelled", "declined"])
def test_non_success_results_stay_non_success(ws, status):
    assert returned_task(ws, status=status)["status"] == status


def test_handoff_is_not_completion_and_input_hash_is_mandatory(ws):
    tasks = TaskService(ws)
    task = tasks.create("sample", operation="outline")
    packet = tasks.handoff(task["id"])
    assert packet["task"]["status"] == "awaiting_agent"
    assert packet["packet"]["input_hash"] == digest(task["request"])
    for incorrect in (None, "0" * 64):
        with pytest.raises(WorkspaceError, match="input revision"):
            tasks.import_result(task["id"], prose="a result", input_hash=incorrect)
    with pytest.raises(WorkspaceError, match="include prose"):
        tasks.import_result(task["id"], input_hash=digest(task["request"]))


@pytest.mark.parametrize("change", ["file", "record", "candidate"])
def test_stale_inputs_and_candidates_invalidate_acceptance(ws, change):
    service = TaskService(ws)
    task = service.create("sample", operation="revise")
    candidate = ws.root / "proposal.md"
    candidate.write_text("A proposed change", encoding="utf-8")
    task = service.import_result(task["id"], prose="Candidate with limitations", artifacts=[{"path": "proposal.md", "sha256": file_hash(candidate)}], input_hash=digest(task["request"]))
    if change == "file":
        (ws.root / "paper.md").write_text("changed", encoding="utf-8")
    elif change == "record":
        ws.add_record("sample", kind="question", data={"text": "new scope"})
    else:
        candidate.write_text("changed", encoding="utf-8")
    with pytest.raises(WorkspaceError):
        service.decide(task["id"], outcome="accept", actor="fixture", rationale="not scientific approval", action_hash=task["action_hash"], proof=_LOCAL_HUMAN)
    assert service.get(task["id"])["status"] == "awaiting_human"


def test_absolute_alias_cannot_be_imported_as_replacement(ws):
    tasks = TaskService(ws)
    task = tasks.create("sample", operation="draft")
    with pytest.raises(WorkspaceError, match="replace a source"):
        tasks.import_result(task["id"], prose="result", artifacts=[{"path": str(ws.root / "paper.md"), "sha256": file_hash(ws.root / "paper.md")}], input_hash=digest(task["request"]))


def test_review_comment_is_not_a_new_scientific_input(ws):
    task = returned_task(ws)
    ws.add_record("sample", kind="review", data={"comment": "Preserve the limitation", "severity": "S1"})
    TaskService(ws).check_inputs(task)
    assert TaskService(ws).get(task["id"])["status"] == "awaiting_human"


def test_new_active_manuscript_invalidates_old_task_even_when_old_file_unchanged(ws):
    task = returned_task(ws)
    (ws.root / "replacement.md").write_text("New intended manuscript", encoding="utf-8")
    ws.register_artifact("sample", path="replacement.md", role="main_manuscript")
    with pytest.raises(WorkspaceError, match="Active project artifacts changed"):
        TaskService(ws).check_inputs(task)


@pytest.mark.parametrize("broken", [None, {"project": None}, {"project": {"id": "sample"}, "artifacts": [None], "contract": {}}, {"project": {"id": "sample"}, "artifacts": [], "contract": {"questions": [{"id": [], "text": "bad"}]}}])
def test_malformed_alignment_fails_closed_without_internal_error(ws, broken):
    from research_hub.workspace.writing import check_alignment
    with pytest.raises(WorkspaceError) as failure:
        check_alignment(ws, "sample", broken)
    assert failure.value.code == "stale_alignment"


def test_stale_manuscript_alignment_is_reported_without_rewrite(ws):
    from research_hub.workspace.writing import check_alignment
    artifacts = ws.artifacts("sample")
    state = {"project": {"id": "sample"}, "artifacts": [{**a, "status": "ACTIVE"} for a in artifacts], "contract": {"questions": []}}
    check_alignment(ws, "sample", state)
    (ws.root / "paper.md").write_text("A new revision", encoding="utf-8")
    ws.register_artifact("sample", path="paper.md", role="main_manuscript")
    with pytest.raises(WorkspaceError, match="alignment is stale"):
        check_alignment(ws, "sample", state)
    assert state["artifacts"][0]["id"] == artifacts[0]["id"]


def test_manuscript_scope_keeps_research_inputs_as_authority_not_prose(ws):
    from research_hub.workspace.writing import WritingAdapter, PREFIX
    (ws.root / "analysis.py").write_text("print(1 + 1)", encoding="utf-8")
    source = ws.register_artifact("sample", path="analysis.py", role="analysis")
    # Minimal binding fixture; actual public bundle is exercised by opt-in dogfood.
    adapter = WritingAdapter.__new__(WritingAdapter)
    adapter.root = ws.root / "fixture-bundle"
    adapter.template_path = PREFIX + "assets/manuscript_state_template.json"
    template = adapter.root / adapter.template_path
    template.parent.mkdir(parents=True)
    template.write_text(json.dumps({"project": {}, "contract": {}, "release": {}}), encoding="utf-8")
    path = adapter.bind(ws, "sample")
    state = json.loads(path.read_text(encoding="utf-8"))
    assert [a["path"] for a in state["artifacts"]] == ["paper.md"]
    assert state["authority_sources"][0]["id"] == source["id"]
    assert source["id"] in {a["id"] for a in TaskService(ws).create("sample", operation="review")["request"]["artifacts"]}
    assert adapter.bind(ws, "sample") == path


@pytest.mark.parametrize("path", ["../outside.md", "paper.md:stream", ".research/../../outside.md"])
def test_unsafe_paths_fail(ws, path):
    with pytest.raises(WorkspaceError):
        safe_path(ws.root, path)


def test_claim_identity_support_and_acceptance_are_not_caller_assertions(ws):
    source = ws.add_record("sample", kind="source", data={"title": "A source", "locator": "https://example.org", "identity_status": "verified"})
    claim = ws.add_record("sample", kind="claim", data={"text": "A claim", "source_ids": [source["id"]], "verification_status": "supported", "human_acceptance": "accepted"})
    assert source["data"]["identity_status"] == "unverified"
    assert claim["data"]["verification_status"] == "unverified"
    assert claim["data"]["human_acceptance"] == "pending"


def test_cli_service_and_mcp_share_project_contract(ws, capsys):
    from research_hub.cli import main
    assert main(["project", "show", "--root", str(ws.root), "--project", "sample", "--json"]) == 0
    cli = json.loads(capsys.readouterr().out)
    direct = call_workspace(ws.root, "project", "show", {"project_id": "sample"})
    assert cli == direct
    from research_hub.mcp_server import workspace_project
    func = getattr(workspace_project, "fn", workspace_project)
    assert func(str(ws.root), "show", {"project_id": "sample"}) == direct


def test_http_origin_csrf_and_no_agent_approval(ws, monkeypatch):
    from research_hub.workspace.server import WorkspaceServer
    monkeypatch.setattr("research_hub.workspace.executor.codex_capability", lambda: {"status": "unavailable", "message": "offline fixture"})
    server = WorkspaceServer(ws.root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        html = urlopen(base + "/app/", timeout=5).read().decode()
        assert 'name="research-hub-csrf-token"' in html
        assert 'name="research-hub-human-token"' not in html
        request = Request(base + "/api/v1/projects", data=b'{"id":"other","title":"Other"}', headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as exc:
            urlopen(request, timeout=5)
        assert exc.value.code == 403
        request.add_header("X-CSRF-Token", server.csrf)
        result = json.load(urlopen(request, timeout=5))
        assert result["project"]["id"] == "other"
        request = Request(base + "/api/v1/workspace", headers={"Host": "attacker.invalid"})
        with pytest.raises(HTTPError) as exc:
            urlopen(request, timeout=5)
        assert exc.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
