"""Saved status contract; all data synthetic, no account/tool probes."""
from datetime import datetime, timedelta, timezone
import json
import os
from types import SimpleNamespace

import pytest

from research_hub.bootstrap_report import BootstrapReport
from research_hub import setup_snapshot as snapshots

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def report():
    return BootstrapReport(vault_path="/private/synthetic/path", zotero_error="SYNTHETIC_SECRET",
        components={key: {"status": "passed", "detail": "SYNTHETIC_SECRET"} for key in snapshots.COMPONENTS})


def payload():
    return {"schema_version": 1, "source": snapshots.SOURCE, "observed_at": NOW.isoformat(),
            "components": {key: "passed" for key in snapshots.COMPONENTS}}


def write(tmp_path, value):
    path = tmp_path / snapshots.RELATIVE_PATH
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def test_opt_in_save_minimizes_data_and_replaces_atomically(tmp_path):
    snapshots.save_setup_snapshot(tmp_path, report(), observed_at=NOW)
    path = tmp_path / snapshots.RELATIVE_PATH
    first = path.read_bytes()
    assert len(first) < snapshots.MAX_BYTES
    assert b"SYNTHETIC_SECRET" not in first and b"private" not in first
    assert set(json.loads(first)) == {"schema_version", "source", "observed_at", "components"}
    snapshots.save_setup_snapshot(tmp_path, BootstrapReport(), observed_at=NOW)
    assert set(json.loads(path.read_bytes())["components"].values()) == {"unknown"}
    assert not list(path.parent.glob(".hub-*"))


@pytest.mark.parametrize("age,freshness", [(0, "saved"), (86400, "saved"), (86401, "stale"), (-1, "clock_skew")])
def test_age_is_display_policy_not_current_readiness(tmp_path, age, freshness):
    snapshots.save_setup_snapshot(tmp_path, report(), observed_at=NOW - timedelta(seconds=age))
    result = snapshots.read_setup_snapshot(tmp_path, observed_now=NOW)
    assert result["freshness"] == freshness
    assert result["current_status"] == "unknown"
    assert set(result["components"].values()) == ({"passed"} if freshness == "saved" else {"unknown"})
    assert result["display_max_age_seconds"] == 86400


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version=True), lambda p: p.update(schema_version=2),
    lambda p: p.pop("observed_at"), lambda p: p.update(observed_at="2026-10-22T12:00:00"),
    lambda p: p.update(observed_at="bad"), lambda p: p.update(source="untrusted-other"),
    lambda p: p.update(secret="SYNTHETIC_SECRET"), lambda p: p["components"].update(vault="ready"),
    lambda p: p["components"].pop("vault"), lambda p: p.update(components=[]),
])
def test_invalid_schema_is_unknown_without_leaking_data(tmp_path, mutation):
    data = payload(); mutation(data); write(tmp_path, data)
    result = snapshots.read_setup_snapshot(tmp_path, observed_now=NOW)
    assert result["freshness"] == "invalid"
    assert set(result["components"].values()) == {"unknown"}
    assert "SYNTHETIC_SECRET" not in json.dumps(result)


@pytest.mark.parametrize("raw", [b"{", b"\xff", b" " * 8193])
def test_invalid_or_oversize_bytes(tmp_path, raw):
    path = write(tmp_path, payload()); path.write_bytes(raw)
    assert snapshots.read_setup_snapshot(tmp_path)["freshness"] == "invalid"


def test_missing_snapshot_read_creates_nothing(tmp_path):
    assert snapshots.read_setup_snapshot(tmp_path)["freshness"] == "missing"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["root", "ancestor", "directory", "file"])
def test_linked_paths_rejected_on_read_and_save(tmp_path, kind):
    actual = tmp_path / "actual"; actual.mkdir()
    root = actual
    write(actual, payload())
    link = tmp_path / "linked"
    if kind in {"root", "ancestor"}:
        link.symlink_to(actual, target_is_directory=True)
        if kind == "ancestor":
            (actual / "child").mkdir(); root = link / "child"
        else:
            root = link
    elif kind == "directory":
        control = actual / ".research_hub"
        control.rename(tmp_path / "control")
        control.symlink_to(tmp_path / "control", target_is_directory=True)
    else:
        path = actual / snapshots.RELATIVE_PATH
        path.rename(tmp_path / "target.json")
        path.symlink_to(tmp_path / "target.json")
    assert snapshots.read_setup_snapshot(root)["freshness"] == "invalid"
    with pytest.raises(ValueError):
        snapshots.save_setup_snapshot(root, report(), observed_at=NOW)


def test_nonregular_and_hardlinked_snapshots_do_not_read(tmp_path):
    path = tmp_path / snapshots.RELATIVE_PATH; path.parent.mkdir()
    path.mkdir()
    assert snapshots.read_setup_snapshot(tmp_path)["freshness"] == "invalid"
    path.rmdir()
    if hasattr(os, "mkfifo"):
        os.mkfifo(path)
        assert snapshots.read_setup_snapshot(tmp_path)["freshness"] == "invalid"
        path.unlink()
    target = tmp_path / "source.json"; target.write_text(json.dumps(payload()))
    os.link(target, path)
    assert snapshots.read_setup_snapshot(tmp_path)["freshness"] == "invalid"


@pytest.mark.parametrize("intake_supported", [True, False])
def test_capabilities_read_is_local_read_only_and_preserves_existing_capabilities(tmp_path, monkeypatch, intake_supported):
    from research_hub.workspace.service import WorkspaceService
    from research_hub import setup_command
    monkeypatch.setattr(setup_command, "run_autonomous", lambda **kw: pytest.fail("probe on GET"))
    monkeypatch.setattr(setup_command, "run_notebooklm_login", lambda: pytest.fail("login on GET"))
    monkeypatch.setattr("research_hub.workspace.executor.codex_capability", lambda: {"status": "unavailable", "message": "stub"})
    monkeypatch.setattr("research_hub.workspace.writing.writing_capability", lambda: {"status": "available", "message": "stub"})
    # Exercise both advertised platform states without performing publication.
    monkeypatch.setattr("research_hub.workspace.text_intake.publication_supported", lambda: intake_supported)
    svc = WorkspaceService(tmp_path)
    result = svc.capabilities(human=True)
    assert result["capabilities"] == {"codex": {"status": "unavailable", "message": "stub"},
        "writing": {"status": "available", "message": "stub"},
        "text_intake": {
            "version": 1, "status": "available" if intake_supported else "unavailable",
            "workspace_instance_id": None, "max_source_bytes": 40000, "formats": ["txt", "md"],
            "message": ("Local bounded text copies only; no PDF reading or model execution."
                        if intake_supported else "Safe text publication primitives are unavailable on this platform. Windows text intake is not supported by this implementation."),
        },
        "approval": {"status": "available", "message": "Local operator review session enabled"}}
    assert result["setup_snapshot"]["current_status"] == "unknown"
    assert list(tmp_path.iterdir()) == []


def test_setup_saves_only_when_explicit_and_invalid_flag_does_not_probe(tmp_path, monkeypatch, capsys):
    from research_hub import setup_command
    monkeypatch.setattr(setup_command, "run_autonomous", lambda **kw: report())
    args = SimpleNamespace(autonomous=True, vault=str(tmp_path), persona="agent", save_report=False)
    assert setup_command.run_setup(args) == 1  # legacy ready false unchanged
    assert list(tmp_path.iterdir()) == []
    args.save_report = True
    assert setup_command.run_setup(args) == 1
    assert (tmp_path / snapshots.RELATIVE_PATH).is_file()
    args.autonomous = False
    monkeypatch.setattr(setup_command, "run_autonomous", lambda **kw: pytest.fail("unexpected probe"))
    assert setup_command.run_setup(args) == 1
    assert "requires --autonomous" in capsys.readouterr().out


def test_exact_byte_limit_and_actual_read_limit(tmp_path, monkeypatch):
    path = write(tmp_path, payload())
    raw = path.read_bytes(); path.write_bytes(raw + b" " * (snapshots.MAX_BYTES - len(raw)))
    assert snapshots.read_setup_snapshot(tmp_path, observed_now=NOW)["freshness"] == "saved"
    # Simulate growth after lstat: bounded read must still reject it.
    original_open = snapshots.os.open
    def growing_open(name, flags):
        path.write_bytes(path.read_bytes() + b" ")
        return original_open(name, flags)
    with monkeypatch.context() as patch:
        patch.setattr(snapshots.os, "open", growing_open)
        assert snapshots.read_setup_snapshot(tmp_path, observed_now=NOW)["freshness"] == "invalid"


def test_atomic_replace_failure_preserves_previous_snapshot(tmp_path, monkeypatch):
    snapshots.save_setup_snapshot(tmp_path, report(), observed_at=NOW)
    path = tmp_path / snapshots.RELATIVE_PATH; original = path.read_bytes()
    def failed_replace(*args):
        raise OSError("synthetic replace failed")
    monkeypatch.setattr(os, "replace", failed_replace)
    with pytest.raises(OSError):
        snapshots.save_setup_snapshot(tmp_path, BootstrapReport(), observed_at=NOW)
    assert path.read_bytes() == original
    assert not list(path.parent.glob(".hub-*"))


def test_read_existing_snapshot_does_not_write_or_probe(tmp_path, monkeypatch):
    snapshots.save_setup_snapshot(tmp_path, report(), observed_at=NOW)
    path = tmp_path / snapshots.RELATIVE_PATH; original = path.read_bytes(); before = path.stat().st_mtime_ns
    monkeypatch.setattr(snapshots, "atomic_json", lambda *a, **kw: pytest.fail("write during read"))
    result = snapshots.read_setup_snapshot(tmp_path, observed_now=NOW)
    assert result["freshness"] == "saved"
    assert path.read_bytes() == original and path.stat().st_mtime_ns == before


def test_parent_traversal_and_missing_root_do_not_create_directories(tmp_path):
    with pytest.raises(ValueError):
        snapshots.save_setup_snapshot(tmp_path / ".." / tmp_path.name, report())
    with pytest.raises(ValueError):
        snapshots.save_setup_snapshot(tmp_path / "missing", report())
    assert list(tmp_path.iterdir()) == []


def test_reparse_control_directory_is_unknown_and_not_written(tmp_path, monkeypatch):
    from pathlib import Path
    control = tmp_path / ".research_hub"; control.mkdir()
    original = Path.lstat
    def reparse(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == control:
            return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400)
        return result
    monkeypatch.setattr(Path, "lstat", reparse)
    assert snapshots.read_setup_snapshot(tmp_path)["freshness"] == "invalid"
    with pytest.raises(ValueError):
        snapshots.save_setup_snapshot(tmp_path, report())
    assert list(control.iterdir()) == []


def test_network_style_root_rejected_before_filesystem_access(monkeypatch):
    monkeypatch.setattr(snapshots, "safe_path", lambda *a, **kw: pytest.fail("Unexpected path access"))
    for root in ("//server/share", "\\\\server\\share"):
        with pytest.raises(ValueError):
            snapshots.save_setup_snapshot(root, report())


def test_decoder_recursion_error_is_unknown(tmp_path, monkeypatch):
    write(tmp_path, payload())
    def exhausted_decoder(_):
        raise RecursionError("synthetic decoder limit")
    with monkeypatch.context() as patch:
        patch.setattr(snapshots.json, "loads", exhausted_decoder)
        assert snapshots.read_setup_snapshot(tmp_path)["freshness"] == "invalid"


def test_http_snapshot_adds_no_probes_or_writes(tmp_path, monkeypatch):
    import threading
    from urllib.request import urlopen
    from research_hub.workspace.server import WorkspaceServer
    import research_hub.workspace.executor as executor
    import research_hub.workspace.writing as writing
    import research_hub.setup_command as bootstrap
    path = write(tmp_path, payload())
    before = path.read_bytes(), path.stat().st_mtime_ns
    calls = []
    monkeypatch.setattr(executor, "codex_capability", lambda: calls.append("existing_codex") or {"status": "unavailable"})
    monkeypatch.setattr(writing, "writing_capability", lambda: {"status": "unavailable"})
    monkeypatch.setattr(bootstrap, "run_autonomous", lambda *a, **kw: pytest.fail("Setup probe in GET"))
    monkeypatch.setattr(snapshots, "atomic_json", lambda *a, **kw: pytest.fail("Snapshot write in GET"))
    server = WorkspaceServer(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/v1/workspace", timeout=5) as response:
            result = json.load(response)
        assert result["setup_snapshot"]["current_status"] == "unknown"
        assert result["setup_snapshot"]["source"] == "saved_local_setup_snapshot"
        assert calls == ["existing_codex"]
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    assert not thread.is_alive()


def test_real_report_mapping_saves_fail_skip_and_unknown_without_probing(tmp_path, monkeypatch, capsys):
    import research_hub.setup_command as setup
    monkeypatch.setattr(setup, "_probe_required_env_vars", lambda _: ({"SYNTHETIC_REQUIRED": False}, ["SYNTHETIC_REQUIRED"]))
    monkeypatch.setattr(setup, "_probe_nlm_auth_status", lambda _: "present")
    monkeypatch.setattr(setup, "_detect_llm_cli", lambda: "synthetic-cli")
    monkeypatch.setattr(setup, "_probe_installed_skills", lambda _: ["synthetic-skill"])
    monkeypatch.setattr(setup, "detect_host", lambda: None)
    monkeypatch.setattr(setup, "_probe_zotero_reachability", lambda _: pytest.fail("Unexpected Zotero probe"))
    args = SimpleNamespace(autonomous=True, save_report=True, vault=str(tmp_path), persona="agent")
    assert setup.run_setup(args) == 1
    capsys.readouterr()
    snapshot = snapshots.read_setup_snapshot(tmp_path)
    assert snapshot["components"] == {
        "environment": "failed", "vault": "passed", "zotero": "skipped",
        "notebooklm_auth": "unknown", "llm_cli": "unknown", "skills": "unknown",
    }
    assert snapshot["current_status"] == "unknown"
