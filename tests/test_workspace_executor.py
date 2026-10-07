"""Real process containment plus replay transport checks; no mocked live PASS."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from research_hub.workspace import process_guard
from research_hub.workspace.core import Workspace, WorkspaceError, digest
from research_hub.workspace.tasks import TaskService


def wait_for(predicate, seconds=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    pytest.fail("Bounded process condition did not occur")


def test_guard_returns_real_process_output(tmp_path):
    with (tmp_path / "out").open("w+") as output:
        with process_guard.guarded_process([sys.executable, "-c", "print('scoped child')"],
                cwd=tmp_path, stdin=subprocess.DEVNULL, stdout=output, stderr=output, timeout=5) as child:
            assert child.wait(timeout=5) == 0
        output.seek(0)
        assert "scoped child" in output.read()


@pytest.mark.parametrize("parent_crash", [False, True])
def test_descendants_do_not_outlive_guard(tmp_path, parent_crash):
    # Each helper self-expires as a final test safety bound, even on a failure.
    pulse = tmp_path / "heartbeat"
    heartbeat = "import pathlib,time; p=pathlib.Path(" + repr(str(pulse)) + "); end=time.monotonic()+12\nwhile time.monotonic()<end: p.write_text(str(time.monotonic())); time.sleep(.05)"
    child_code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(heartbeat) + "]); time.sleep(12)"
    source = str(Path(process_guard.__file__).resolve().parents[2])
    parent_code = (
        "import sys,subprocess,time; sys.path.insert(0," + repr(source) + ")\n"
        "from research_hub.workspace.process_guard import guarded_process\n"
        "with guarded_process([sys.executable,'-c'," + repr(child_code) + "],cwd=" + repr(str(tmp_path)) +
        ",stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=12) as child:\n"
        " while not __import__('pathlib').Path(" + repr(str(pulse)) + ").exists(): time.sleep(.05)\n"
        + (" time.sleep(12)\n" if parent_crash else " time.sleep(.15)\n")
    )
    parent = subprocess.Popen([sys.executable, "-c", parent_code])
    try:
        wait_for(pulse.exists)
        if parent_crash:
            parent.kill()  # Only the exact test-owned PID, not its descendants.
        parent.wait(timeout=6)
        time.sleep(0.5)
        previous = pulse.read_text()
        time.sleep(0.4)
        assert pulse.read_text() == previous, "Descendant remained active after host exit"
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)


@pytest.fixture
def task_context(tmp_path, monkeypatch):
    for name in ("RESEARCH_HUB_AGENT_POLICY", "RESEARCH_HUB_AGENT_CHECKPOINT", "RESEARCH_HUB_WRITING_ADAPTER"):
        monkeypatch.delenv(name, raising=False)
    ws = Workspace(tmp_path)
    ws.create_project(id="test", title="Process replay")
    tasks = TaskService(ws)
    return ws, tasks, tasks.create("test", operation="outline")


@pytest.mark.parametrize("events,prose,expected", [
    ([{"type": "turn.completed", "usage": {"input_tokens": 1}}], "Research prose with uncertainty", "completed"),
    ([{"type": "turn.failed"}], "Preserved partial research", "failed"),
    ([{"type": "turn.completed"}], "", "invalid_output"),
    ([None], "Completed prose must survive a protocol error", "invalid_output"),
    ([{"type": "item.completed", "item": {"type": "error", "message": "Skill descriptions were shortened"}}, {"type": "turn.completed"}], "Research prose must survive a context diagnostic", "executor_diagnostic"),
    ([{"type": "item.completed", "item": {"type": "mcp_tool_call"}}, {"type": "turn.completed"}], "No approval", "executor_boundary"),
])
def test_real_subprocess_replay_retains_prose(task_context, monkeypatch, events, prose, expected):
    ws, tasks, task = task_context
    from research_hub.workspace import executor
    # This is a transport fixture, not a model or scientific-verification claim.
    script = "import sys,pathlib; pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text(" + repr(prose) + ",encoding='utf-8'); print(" + repr("\n".join(json.dumps(e) for e in events)) + ")"
    monkeypatch.setattr(executor, "codex_command", lambda: [sys.executable, "-c", script])
    monkeypatch.setattr(executor, "codex_capability", lambda: {"status": "available"})
    adapter = type("Fixture", (), {"instructions": lambda self, skill: {"fixture": "No real skill execution"}})()
    if expected in {"completed", "failed"}:
        assert executor.run_codex(ws, task, adapter, timeout=5)["status"] == expected
    else:
        with pytest.raises(WorkspaceError) as error:
            executor.run_codex(ws, task, adapter, timeout=5)
        assert error.value.code == expected
    retained = list((ws.root / ".research/tasks" / task["id"] / "executions").glob("*/raw-proposal.txt"))
    assert len(retained) == 1
    assert retained[0].read_text(encoding="utf-8") == prose


def test_running_task_cannot_be_preempted_by_import_or_recover(task_context):
    ws, tasks, task = task_context
    with ws.db(write=True) as db:
        task.update(status="running", owner_pid=os.getpid())
        tasks._save(db, task)
    with pytest.raises(WorkspaceError, match="live executor"):
        tasks.import_result(task["id"], prose="forged early result", input_hash=digest(task["request"]))
    with pytest.raises(WorkspaceError, match="still alive"):
        tasks.recover(task["id"])
    assert tasks.cancel(task["id"])["status"] == "cancelled"


def test_connected_revise_keeps_distinct_execution_receipts(task_context, monkeypatch):
    from research_hub.workspace import executor, writing
    from research_hub.workspace.tasks import _LOCAL_HUMAN
    ws, tasks, _ = task_context
    state = ws.root / "fixture-state.json"
    state.write_text('{}', encoding="utf-8")
    # A transport adapter fixture, not a public skill audit or live model.
    class Adapter:
        sha256 = "fixture-adapter"
        def bind(self, *_):
            return state
        def instructions(self, *_):
            return {"fixture": "No scientific endorsement"}
    monkeypatch.setattr(writing, "WritingAdapter", Adapter)
    monkeypatch.setenv("RESEARCH_HUB_WRITING_ADAPTER", "fixture")
    prompt_path = ws.root / "actual-prompt.txt"
    script = "import sys,pathlib; pathlib.Path(" + repr(str(prompt_path)) + ").write_text(sys.stdin.read(),encoding='utf-8'); pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('Bounded transport proposal',encoding='utf-8'); print('{\"type\":\"turn.completed\"}')"
    monkeypatch.setattr(executor, "codex_command", lambda: [sys.executable, "-c", script])
    monkeypatch.setattr(executor, "codex_capability", lambda: {"status": "available"})
    task = tasks.create("test", operation="outline", mode="connected")
    first = tasks.start(task["id"])
    revised = tasks.decide(first["id"], outcome="revise", actor="test transport", rationale="Exercise a second attempt", action_hash=first["action_hash"], proof=_LOCAL_HUMAN)
    packet = tasks.handoff(revised["id"])["packet"]
    assert packet["revision_context"] == {
        "prose": first["result"]["prose"], "artifacts": first["result"]["artifacts"],
        "reviewed_action_hash": first["action_hash"],
    }
    assert packet["revision_instruction"] == "Exercise a second attempt"
    assert packet["untrusted_excerpts"][0]["text"] == "Bounded transport proposal\n"
    second = tasks.start(revised["id"])
    prompt = json.loads(prompt_path.read_text(encoding="utf-8").split("\n\n", 1)[1])
    assert prompt["task"]["revision_context"] == packet["revision_context"]
    assert prompt["task"]["revision_instruction"] == packet["revision_instruction"]
    assert prompt["untrusted_excerpts"][0]["sha256"] == first["result"]["artifacts"][0]["sha256"]
    assert second["status"] == "awaiting_human"
    assert first["execution_id"] != second["execution_id"]
    assert first["result"]["artifacts"][0]["path"] != second["result"]["artifacts"][0]["path"]
    for attempt in (first, second):
        assert (ws.root / attempt["execution_provenance"]["event_log"]).is_file()
        assert (ws.root / attempt["result"]["artifacts"][0]["path"]).is_file()
    assert second["attempts"][0]["execution_provenance"] == first["execution_provenance"]
    third = tasks.decide(second["id"], outcome="revise", actor="test transport", rationale="Scope another revision", action_hash=second["action_hash"], proof=_LOCAL_HUMAN)
    assert "revision_context" not in third["request"]["revision_context"]
    assert third["request"]["revision_context"]["reviewed_action_hash"] == second["action_hash"]
    candidate = ws.root / second["result"]["artifacts"][0]["path"]
    candidate.write_text("Changed after the revision decision", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="Reviewed candidate changed"):
        tasks.handoff(third["id"])
    with pytest.raises(WorkspaceError, match="Reviewed candidate changed"):
        tasks.start(third["id"])


def test_stderr_only_failure_is_retained_with_locator(task_context, monkeypatch):
    from research_hub.workspace import executor
    ws, _, task = task_context
    script = "import sys; sys.stderr.write('Transport fixture: authentication expired\\n'); sys.exit(7)"
    monkeypatch.setattr(executor, "codex_command", lambda: [sys.executable, "-c", script])
    monkeypatch.setattr(executor, "codex_capability", lambda: {"status": "available"})
    adapter = type("Fixture", (), {"instructions": lambda *_: {}})()
    result = executor.run_codex(ws, task, adapter, timeout=5)
    assert result["status"] == "failed"
    assert "exit 7" in result["prose"]
    assert (ws.root / result["provenance"]["stderr_log"]).read_text(encoding="utf-8") == "Transport fixture: authentication expired\n"
    assert result["provenance"]["stderr_truncated"] is False


def test_revision_context_limit_does_not_silently_truncate(task_context):
    from research_hub.workspace.tasks import _LOCAL_HUMAN
    _, tasks, task = task_context
    task = tasks.import_result(task["id"], prose="x" * 120_001, input_hash=digest(task["request"]))
    with pytest.raises(WorkspaceError, match="revision context limit"):
        tasks.decide(task["id"], outcome="revise", actor="fixture", rationale="Shorten", action_hash=task["action_hash"], proof=_LOCAL_HUMAN)
    assert tasks.get(task["id"])["status"] == "awaiting_human"


def test_protocol_exception_persists_error_and_stderr_locator(task_context, monkeypatch):
    from research_hub.workspace import executor, writing
    ws, tasks, task = task_context
    task.update(status="running", execution_id="protocol-fixture", owner_pid=os.getpid())
    with ws.db(write=True) as db:
        tasks._save(db, task)
    monkeypatch.setattr(writing, "WritingAdapter", lambda: type("Fixture", (), {"instructions": lambda *_: {}})())
    script = "import sys; sys.stderr.write('Protocol fixture diagnostic'); print('not-json')"
    monkeypatch.setattr(executor, "codex_command", lambda: [sys.executable, "-c", script])
    monkeypatch.setattr(executor, "codex_capability", lambda: {"status": "available"})
    with pytest.raises(WorkspaceError, match="event stream is invalid"):
        tasks.execute_claimed(task)
    persisted = TaskService(Workspace(ws.root)).get(task["id"])
    assert persisted["status"] == "failed"
    assert "event stream is invalid" in persisted["error"]
    assert (ws.root / persisted["execution_provenance"]["stderr_log"]).read_text() == "Protocol fixture diagnostic"


def test_stderr_retention_is_byte_bounded(task_context, monkeypatch):
    from research_hub.workspace import executor
    ws, _, task = task_context
    script = "import sys; sys.stderr.buffer.write(b'x'*2000002); sys.exit(9)"
    monkeypatch.setattr(executor, "codex_command", lambda: [sys.executable, "-c", script])
    monkeypatch.setattr(executor, "codex_capability", lambda: {"status": "available"})
    adapter = type("Fixture", (), {"instructions": lambda *_: {}})()
    result = executor.run_codex(ws, task, adapter, timeout=5)
    assert result["status"] == "failed"
    assert result["provenance"]["stderr_truncated"] is True
    assert (ws.root / result["provenance"]["stderr_log"]).stat().st_size == 2_000_000


@pytest.mark.parametrize("cancel", [False, True])
def test_real_timeout_and_cancel_are_not_success(task_context, monkeypatch, cancel):
    from research_hub.workspace import executor
    ws, _, task = task_context
    script = "import time; time.sleep(8)"
    monkeypatch.setattr(executor, "codex_command", lambda: [sys.executable, "-c", script])
    monkeypatch.setattr(executor, "codex_capability", lambda: {"status": "available"})
    adapter = type("Fixture", (), {"instructions": lambda *_: {}})()
    result = executor.run_codex(ws, task, adapter, timeout=1, cancelled=lambda: cancel)
    assert result["status"] == ("cancelled" if cancel else "failed")
