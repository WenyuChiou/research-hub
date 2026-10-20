"""Offline transaction regressions for concurrent workflow state writers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread, current_thread

import pytest
import yaml

from research_hub import workflow_runtime as runtime
from research_hub.locks import file_lock


FIXTURE = Path(__file__).parent / "fixtures" / "research_workflow_state_valid.yml"


@pytest.fixture(autouse=True)
def no_configured_policy(monkeypatch):
    monkeypatch.delenv(runtime.POLICY_ENV, raising=False)
    monkeypatch.delenv(runtime.CHECKPOINT_ENV, raising=False)


def _write(path, document):
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _legacy_state(path):
    state = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    state["schema_version"] = "1.0"
    _write(path, state)
    return path.read_bytes()


@contextmanager
def _paused_transaction(
    monkeypatch, operation, *, hook_owner=runtime, hook_name="_atomic_write_yaml",
    pause_path=None,
):
    """Pause a real transaction; contending writers use the real lock, no wait.

    The first writer stops before its selected state observation or update.
    Main-thread writers then deterministically encounter the held OS lock rather
    than relying on sleeps or favorable scheduling. The production timeout and
    lock implementation are unchanged. The worker always gets released and joined.
    """
    paused = Event()
    release = Event()
    results = []
    errors = []
    original_hook = getattr(hook_owner, hook_name)

    def intercepted(*args, **kwargs):
        if current_thread() is worker and (pause_path is None or args[0] == pause_path):
            paused.set()
            if not release.wait(5):
                raise AssertionError("test did not release the paused workflow writer")
        return original_hook(*args, **kwargs)

    @contextmanager
    def bounded_lock(path, *, timeout=30.0):
        with file_lock(path, timeout=timeout if current_thread() is worker else 0):
            yield

    def run():
        try:
            results.append(operation())
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=run, name="paused-workflow-writer", daemon=True)
    with monkeypatch.context() as patch:
        patch.setattr(hook_owner, hook_name, intercepted)
        patch.setattr(runtime, "file_lock", bounded_lock)
        worker.start()
        try:
            assert paused.wait(5), "workflow writer never reached the controlled pause"
            yield results
        finally:
            release.set()
            worker.join(5)
            assert not worker.is_alive(), "workflow writer did not terminate"
            if errors:
                raise errors[0]


@pytest.mark.parametrize("hook", ["load_state", "_atomic_write_yaml"])
def test_resume_serializes_with_external_preparation(monkeypatch, tmp_path, hook):
    path = Path(runtime.initialize_workflow(tmp_path)["state_path"])
    action = {"action_id": "write", "payload": {"value": "A"}}

    with _paused_transaction(
        monkeypatch, lambda: runtime.resume_workflow(path), hook_name=hook,
    ):
        with pytest.raises(TimeoutError, match="could not acquire"):
            runtime.prepare_external_action(path, action)

    prepared = runtime.prepare_external_action(path, action)
    persisted = runtime.load_state(path)
    assert persisted["pending_external_action"]["action_hash"] == prepared["action_hash"]
    assert persisted["recovery_status"] == "pending_external_action"
    assert runtime.resume_workflow(path)["reason"] == "reconcile_required"
    with pytest.raises(runtime.WorkflowContractError, match="unresolved external action"):
        runtime.prepare_external_action(path, action)


@pytest.mark.parametrize("hook", ["load_state", "_atomic_write_yaml"])
def test_resume_serializes_with_external_result_recording(monkeypatch, tmp_path, hook):
    path = Path(runtime.initialize_workflow(tmp_path)["state_path"])
    action = {"action_id": "write", "payload": {"value": "A"}}
    action_hash = runtime.prepare_external_action(path, action)["action_hash"]

    with _paused_transaction(
        monkeypatch, lambda: runtime.resume_workflow(path), hook_name=hook,
    ):
        with pytest.raises(TimeoutError, match="could not acquire"):
            runtime.record_external_result(path, action_hash=action_hash, result_ref="saved:1")

    runtime.record_external_result(path, action_hash=action_hash, result_ref="saved:1")
    persisted = runtime.load_state(path)
    assert persisted["pending_external_action"] is None
    assert persisted["recovery_status"] == "clean"
    assert [item["action_hash"] for item in persisted["external_write_ledger"]] == [action_hash]
    assert runtime.resume_workflow(path)["resumed"] is True
    with pytest.raises(runtime.WorkflowContractError, match="already recorded"):
        runtime.prepare_external_action(path, action)


@pytest.mark.parametrize("outcome", ["decline", "cancel"])
@pytest.mark.parametrize("hook", ["load_state", "_atomic_write_yaml"])
def test_decision_serializes_with_resume(monkeypatch, tmp_path, outcome, hook):
    path = tmp_path / "state.yml"
    state = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    state["status"] = "waiting_for_human"
    state["pending_action"]["gate"] = "external_write"
    _write(path, state)

    def decide():
        return runtime.decide_workflow(
            path, outcome=outcome, actor="human:researcher", rationale="Stop this action",
            action_hash=state["pending_action"]["action_hash"],
        )

    with _paused_transaction(monkeypatch, decide, hook_name=hook):
        with pytest.raises(TimeoutError, match="could not acquire"):
            runtime.resume_workflow(path)

    expected = "declined" if outcome == "decline" else "cancelled"
    assert runtime.resume_workflow(path)["reason"] == f"terminal:{expected}"
    persisted = runtime.load_state(path)
    assert persisted["status"] == expected
    assert persisted["decisions"][-1]["outcome"] == outcome


@pytest.mark.parametrize("hook", ["exists", "_atomic_write_yaml"])
def test_initialize_serializes_existence_check(monkeypatch, tmp_path, hook):
    path = tmp_path / runtime.DEFAULT_STATE_PATH
    with _paused_transaction(
        monkeypatch, lambda: runtime.initialize_workflow(tmp_path, workflow_id="first"),
        hook_owner=Path if hook == "exists" else runtime, hook_name=hook,
        pause_path=path,
    ):
        with pytest.raises(TimeoutError, match="could not acquire"):
            runtime.initialize_workflow(tmp_path, workflow_id="second")

    with pytest.raises(runtime.WorkflowContractError, match="already exists"):
        runtime.initialize_workflow(tmp_path, workflow_id="second")
    assert runtime.load_state(path)["workflow_id"] == "first"


@pytest.mark.parametrize("hook", ["load_state", "copy2", "_atomic_write_yaml"])
def test_migrate_serializes_original_backup_and_replacement(monkeypatch, tmp_path, hook):
    path = tmp_path / "state.yml"
    original = _legacy_state(path)

    with _paused_transaction(
        monkeypatch, lambda: runtime.migrate_workflow(path, apply=True),
        hook_owner=runtime.shutil if hook == "copy2" else runtime, hook_name=hook,
    ) as results:
        with pytest.raises(TimeoutError, match="could not acquire"):
            runtime.migrate_workflow(path, apply=True)

    assert Path(results[0]["backup_path"]).read_bytes() == original
    assert runtime.load_state(path)["schema_version"] == "1.1"
    assert runtime.validate_workflow(path)["ok"] is True
    assert runtime.migrate_workflow(path, apply=True)["applied"] is False
    assert len(list(tmp_path.glob("*.bak"))) == 1


def test_migration_preview_creates_no_lock_or_backup(tmp_path):
    path = tmp_path / "state.yml"
    original = _legacy_state(path)
    report = runtime.migrate_workflow(path)
    assert report["dry_run"] is True
    assert path.read_bytes() == original
    assert sorted(item.name for item in tmp_path.iterdir()) == ["state.yml"]


def test_failed_atomic_write_preserves_state_and_releases_lock(monkeypatch, tmp_path):
    path = Path(runtime.initialize_workflow(tmp_path)["state_path"])
    original = path.read_bytes()

    def failed_replace(*args):
        raise OSError("injected replacement failure")

    with monkeypatch.context() as patch:
        patch.setattr(runtime.os, "replace", failed_replace)
        with pytest.raises(OSError, match="injected replacement failure"):
            runtime.resume_workflow(path)

    assert path.read_bytes() == original
    assert list(path.parent.glob("*.tmp")) == []
    with file_lock(path, timeout=0):
        pass
    assert runtime.resume_workflow(path)["resumed"] is True


def test_failed_migration_preserves_original_backup_and_releases_lock(monkeypatch, tmp_path):
    path = tmp_path / "state.yml"
    original = _legacy_state(path)

    def failed_replace(*args):
        raise OSError("injected migration replacement failure")

    with monkeypatch.context() as patch:
        patch.setattr(runtime.os, "replace", failed_replace)
        with pytest.raises(OSError, match="injected migration replacement failure"):
            runtime.migrate_workflow(path, apply=True)

    assert path.read_bytes() == original
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []
    with file_lock(path, timeout=0):
        pass
    assert runtime.migrate_workflow(path, apply=True)["applied"] is True
    assert backups[0].read_bytes() == original
    assert runtime.validate_workflow(path)["ok"] is True
