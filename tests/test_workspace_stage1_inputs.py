"""Offline source preparation, not a research run or native Core admission."""
import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from research_hub.workspace import stage1_inputs as module
from research_hub.workspace.core import WorkspaceError
from tests.test_workspace_batch_audit import manifest, snapshot
from tests.test_workspace_task_summary import candidate, near_limit_candidate, replace_task, reseal


requires_directory_export = pytest.mark.skipif(
    not (os.name == "posix" and hasattr(os, "O_NOFOLLOW")
         and hasattr(os, "O_DIRECTORY") and os.open in os.supports_dir_fd),
    reason="Parent-swap protection requires native POSIX no-follow/dir_fd primitives",
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Network must not be used")
    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)


def outside(tmp_path, name="bundle"):
    return tmp_path.parent / (tmp_path.name + "-" + name + ".zip")


def test_exact_selected_bytes_quotes_and_pending_boundary(candidate, tmp_path):
    service, source, _, task = candidate
    root = service.workspace.root
    before = snapshot(root)
    value = manifest(candidate)
    report = module.export(value, outside(tmp_path))
    entry = report["entries"][0]
    pack = task["request"]["research_draft"]["source_pack"]
    assert report["kind"] == "ResearchHubStage1InputBundle"
    assert report["counts"] == {"prepared": 1, "unprepared": 0, "missing": 0, "blocked": 0}
    assert report["native_core_handoff"] is False
    assert report["core_admission"] == report["scientific_acceptance"] == "not_assessed"
    assert report["stage2_execution_authorized"] is False
    assert "eligible_for_stage2" not in report
    assert entry["human_acceptance"] == "pending"
    assert entry["provider_execution"] == "not_verified"
    assert entry["source_selection"]["source"]["publication_version"] == "unknown"
    assert entry["source_selection"]["source"]["identity_status"] == "unverified"
    assert entry["provenance"]["input_hash"] == task["result"]["input_hash"]
    assert "workspace_root" not in json.dumps(report)
    assert str(root) not in json.dumps(report)
    for item in entry["files"]:
        raw = zipfile.ZipFile(outside(tmp_path)).read(item["path"])
        assert len(raw) == item["bytes"]
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    assert zipfile.ZipFile(outside(tmp_path)).read("B2-07/selected-source.txt").decode("utf-8") == pack["text"]
    original = next(x for x in task["result"]["artifacts"] if x["path"].endswith("/draft-response.json"))
    assert zipfile.ZipFile(outside(tmp_path)).read("B2-07/draft-response.json") == (root / original["path"]).read_bytes()
    assert json.loads(zipfile.ZipFile(outside(tmp_path)).read("manifest.json")) == report
    if os.name == "posix":
        assert stat.S_IMODE(outside(tmp_path).stat().st_mode) == 0o600
    assert snapshot(root) == before
    second = module.export(value, outside(tmp_path, "repeat"))
    assert second == report
    assert outside(tmp_path).read_bytes() == outside(tmp_path, "repeat").read_bytes()


def test_large_file_and_blob_selected_sources(near_limit_candidate, tmp_path):
    value = manifest(near_limit_candidate)
    before = snapshot(near_limit_candidate[0].workspace.root)
    report = module.export(value, outside(tmp_path))
    assert report["counts"]["prepared"] == 1
    raw = zipfile.ZipFile(outside(tmp_path)).read("B2-07/draft-response.json")
    assert len(raw) > 100_000
    assert snapshot(near_limit_candidate[0].workspace.root) == before


def test_denominator_and_no_read_for_unprepared(candidate, tmp_path):
    value = manifest(candidate)
    value["entries"].extend([
        {"article_id": "B2-15", "declared_status": "unknown", "reason_codes": ["version_unknown"]},
        {"article_id": "B2-14", "declared_status": "blocked", "reason_codes": ["access_blocked"]}])
    result = module.export(value, outside(tmp_path))
    assert result["counts"] == {"prepared": 1, "unprepared": 2, "missing": 0, "blocked": 0}
    assert result["entries"][1]["declared_source_status"] == "unknown"
    assert result["entries"][2]["reason_codes"] == ["access_blocked"]
    assert result["entries"][1]["files"] == result["entries"][2]["files"] == []
    assert not any(p.startswith("B2-15/") for p in zipfile.ZipFile(outside(tmp_path)).namelist())


@pytest.mark.parametrize("change", ["source", "candidate", "hash", "project", "accepted", "offset"])
def test_invalid_or_stale_rows_never_export(candidate, tmp_path, change):
    value = manifest(candidate)
    service, _, _, task = candidate
    if change == "source":
        (service.workspace.root / "source.txt").write_text("PRIVATE CHANGED SOURCE")
    elif change == "candidate":
        (service.workspace.root / task["result"]["artifacts"][0]["path"]).write_text("PRIVATE CHANGED DRAFT")
    elif change == "hash":
        value["entries"][0]["expected_selected_sha256"] = "0" * 64
    elif change == "project":
        value["entries"][0]["project_id"] = "other-project"
    elif change == "accepted":
        task["status"] = "completed"
        task["result"]["semantic_acceptance"] = "accept"
        reseal(task)
        replace_task(candidate, task)
    else:
        task["request"]["research_draft"]["source_selection"]["start"] = 1
        reseal(task)
        replace_task(candidate, task)
    before = snapshot(service.workspace.root)
    report = module.export(value, outside(tmp_path))
    assert report["counts"]["prepared"] == 0
    assert report["entries"][0]["files"] == []
    assert report["entries"][0]["human_acceptance"] == "unknown"
    assert zipfile.ZipFile(outside(tmp_path)).namelist() == ["manifest.json"]
    assert "PRIVATE" not in json.dumps(report)
    assert snapshot(service.workspace.root) == before


def test_capture_change_after_initial_audit(candidate, tmp_path, monkeypatch):
    original = module._capture
    def changed(entry, audit):
        wrong = dict(audit, action_hash="0" * 64)
        return original(entry, wrong)
    monkeypatch.setattr(module, "_capture", changed)
    report = module.export(manifest(candidate), outside(tmp_path))
    assert report["counts"]["blocked"] == 1
    assert report["entries"][0]["diagnostic"] == "changed_or_unavailable_during_capture"
    assert report["entries"][0]["files"] == []


@pytest.mark.parametrize("invalid", ["duplicate", "outside_id", "unknown_field"])
def test_invalid_envelope_before_any_reads(candidate, tmp_path, monkeypatch, invalid):
    value = manifest(candidate)
    if invalid == "duplicate":
        value["entries"] *= 2
    elif invalid == "outside_id":
        value["entries"][0]["article_id"] = "../secret"
    else:
        value["entries"][0]["extra"] = "PRIVATE"
    monkeypatch.setattr(module, "audit_entry", lambda *a: pytest.fail("Unexpected read"))
    with pytest.raises(ValueError):
        module.export(value, outside(tmp_path))
    assert not outside(tmp_path).exists()


@pytest.mark.parametrize("location", ["inside", "existing", "linked", "missing_parent"])
def test_destination_rejected_before_reads(candidate, tmp_path, monkeypatch, location):
    destination = outside(tmp_path)
    if location == "inside":
        destination = candidate[0].workspace.root / "bundle"
    elif location == "existing":
        destination.mkdir()
        (destination / "keep.txt").write_text("must survive")
    elif location == "linked":
        destination.symlink_to(candidate[0].workspace.root, target_is_directory=True)
    else:
        destination = destination / "missing" / "child"
    monkeypatch.setattr(module, "audit_entry", lambda *a: pytest.fail("Unexpected read"))
    with pytest.raises((ValueError, WorkspaceError)):
        module.export(manifest(candidate), destination)
    if location == "existing":
        assert (destination / "keep.txt").read_text() == "must survive"


def test_cli_redaction_exit_codes_and_no_overwrite(candidate, tmp_path, capsys):
    value = manifest(candidate)
    value["entries"].append({"article_id": "B2-14", "declared_status": "blocked", "reason_codes": ["blocked"]})
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    assert module.main([str(path), str(outside(tmp_path))]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["counts"]["prepared"] == 1
    assert "blue water" not in output.out and str(tmp_path) not in output.out
    before = outside(tmp_path).read_bytes()
    assert module.main([str(path), str(outside(tmp_path))]) == 2
    assert outside(tmp_path).read_bytes() == before
    assert str(tmp_path) not in capsys.readouterr().err
    path.write_text('{"version":1,"version":1,"entries":[]}')
    assert module.main([str(path), str(outside(tmp_path, "invalid"))]) == 2
    assert not outside(tmp_path, "invalid").exists()


def test_write_failure_has_no_completion_manifest(candidate, tmp_path, monkeypatch):
    original = zipfile.ZipFile.writestr
    def fail(self, info, *args, **kwargs):
        if info.filename.endswith("draft-response.json"):
            raise OSError("PRIVATE FAILURE")
        return original(self, info, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, "writestr", fail)
    before = snapshot(candidate[0].workspace.root)
    with pytest.raises(OSError):
        module.export(manifest(candidate), outside(tmp_path))
    assert "manifest.json" not in zipfile.ZipFile(outside(tmp_path)).namelist()
    assert snapshot(candidate[0].workspace.root) == before


@requires_directory_export
@pytest.mark.parametrize("with_source", [False, True])
def test_replaced_output_does_not_redirect_writes(candidate, tmp_path, monkeypatch, with_source):
    destination = outside(tmp_path)
    moved = outside(tmp_path, "moved")
    victim = tmp_path / "untouched.txt"
    victim.write_text("PRIVATE KEEP")
    original = os.open
    def replace(path, flags, *args, **kwargs):
        descriptor = original(path, flags, *args, **kwargs)
        if flags & os.O_CREAT and Path(path).name == destination.name:
            try:
                destination.rename(moved)
            except OSError:
                # Windows can forbid replacement while the descriptor is open.
                os.close(descriptor)
                raise
            destination.symlink_to(victim)
        return descriptor
    monkeypatch.setattr(os, "open", replace)
    value = manifest(candidate) if with_source else {
        "version": 1, "entries": [{"article_id": "B2-14", "declared_status": "blocked", "reason_codes": ["blocked"]}]}
    before = snapshot(candidate[0].workspace.root)
    with pytest.raises((ValueError, WorkspaceError, OSError)):
        module.export(value, destination)
    assert victim.read_text() == "PRIVATE KEEP"
    assert (moved if moved.exists() else destination).read_bytes() == b""
    assert snapshot(candidate[0].workspace.root) == before


def test_replaced_output_during_write_uses_original_descriptor(candidate, tmp_path, monkeypatch):
    destination, moved = outside(tmp_path), outside(tmp_path, "moved")
    victim = tmp_path / "untouched.txt"
    victim.write_text("PRIVATE KEEP")
    original = zipfile.ZipFile.writestr
    replaced = False
    def replace(archive, *args, **kwargs):
        nonlocal replaced
        if not replaced:
            destination.rename(moved)
            destination.symlink_to(victim)
            replaced = True
        return original(archive, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, "writestr", replace)
    with pytest.raises((ValueError, WorkspaceError, OSError)):
        module.export(manifest(candidate), destination)
    assert victim.read_text() == "PRIVATE KEEP"
    if moved.exists():
        assert "manifest.json" in zipfile.ZipFile(moved).namelist()
    else:
        assert "manifest.json" not in zipfile.ZipFile(destination).namelist()


@requires_directory_export
@pytest.mark.parametrize("component", ["parent", "ancestor"])
@pytest.mark.parametrize("moment", ["after_check", "create"])
@pytest.mark.parametrize("with_source", [False, True])
def test_replaced_parent_never_creates_in_selected_workspace(
        candidate, tmp_path, monkeypatch, component, moment, with_source):
    workspace = candidate[0].workspace.root
    output_root = outside(tmp_path, "output-parent")
    parent = output_root / "nested"
    parent.mkdir(parents=True)
    destination = parent / "bundle.zip"
    swapped = parent if component == "parent" else output_root
    moved = outside(tmp_path, "moved-parent")
    if component == "ancestor":
        (workspace / "nested").mkdir()
    value = manifest(candidate)
    if not with_source:
        value["entries"][0]["task_id"] = "0" * 32
    before = snapshot(workspace)
    changed = False

    def swap():
        nonlocal changed
        assert not changed
        swapped.rename(moved)
        swapped.symlink_to(workspace, target_is_directory=True)
        changed = True

    if moment == "create":
        original = os.open

        def replace(path, flags, *args, **kwargs):
            if flags & os.O_CREAT and Path(path).name == destination.name:
                swap()
            return original(path, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", replace)
    else:
        original = module.safe_path
        checks = 0

        def replace(root, path, **kwargs):
            nonlocal checks
            result = original(root, path, **kwargs)
            if Path(path) == destination:
                checks += 1
                if checks == 2:
                    swap()
            return result

        monkeypatch.setattr(module, "safe_path", replace)

    with pytest.raises((ValueError, WorkspaceError, OSError)):
        module.export(value, destination)
    assert changed
    # Compare all saved paths and bytes, not merely absence of source disclosure.
    assert snapshot(workspace) == before
    pinned_output = moved / ("bundle.zip" if component == "parent" else "nested/bundle.zip")
    if moment == "create":
        assert pinned_output.read_bytes() == b""
    else:
        assert not pinned_output.exists()


@requires_directory_export
def test_parent_traversal_failure_closes_open_directories(candidate, tmp_path, monkeypatch):
    parent = outside(tmp_path, "parent")
    parent.mkdir()
    destination = parent / "bundle.zip"
    original = os.open
    opened = []

    def fail(path, flags, *args, **kwargs):
        if flags & os.O_DIRECTORY and Path(path).name == parent.name:
            raise OSError("Synthetic parent-open failure")
        descriptor = original(path, flags, *args, **kwargs)
        if flags & os.O_DIRECTORY:
            opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(os, "open", fail)
    with pytest.raises(OSError):
        module.export(manifest(candidate), destination)
    assert opened and not destination.exists()
    for descriptor in set(opened):
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_legacy_creation_path_remains_available(candidate, tmp_path, monkeypatch):
    """Compatibility seam only; this is not native Windows race validation."""
    monkeypatch.setattr(module, "_WINDOWS_EXPORT_SUPPORTED", False)
    monkeypatch.setattr(module, "_DIRECTORY_EXPORT_SUPPORTED", False)
    destination = outside(tmp_path)
    original = os.open
    calls = []

    def record(path, flags, *args, **kwargs):
        if flags & os.O_CREAT:
            calls.append((Path(path), kwargs))
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", record)
    before = snapshot(candidate[0].workspace.root)
    result = module.export(manifest(candidate), destination)
    assert result["counts"]["prepared"] == 1
    assert calls == [(destination, {})]
    assert json.loads(zipfile.ZipFile(destination).read("manifest.json")) == result
    assert snapshot(candidate[0].workspace.root) == before


def test_windows_dispatch_includes_only_explicit_workspace_roots(candidate, tmp_path, monkeypatch):
    """Portable integration seam, not a native Windows acceptance test."""
    from contextlib import contextmanager
    from research_hub.workspace import _windows_export
    calls = []
    @contextmanager
    def native(destination, *, workspace_roots):
        calls.append((destination, workspace_roots))
        with destination.open('xb') as stream:
            yield stream
    monkeypatch.setattr(module, '_WINDOWS_EXPORT_SUPPORTED', True)
    monkeypatch.setattr(_windows_export, '_parts', lambda *args, **kwargs: None)
    monkeypatch.setattr(_windows_export, 'destination_stream', native)
    value = manifest(candidate)
    value['entries'].append({'article_id': 'unknown', 'declared_status': 'unknown', 'reason_codes': ['unknown']})
    destination = outside(tmp_path)
    report = module.export(value, destination)
    assert calls == [(destination, (value['entries'][0]['workspace_root'],))]
    assert report['entries'][0]['human_acceptance'] == 'pending'
    assert json.loads(zipfile.ZipFile(destination).read('manifest.json')) == report


def test_windows_native_failure_is_redacted_without_legacy_fallback(candidate, tmp_path, monkeypatch, capsys):
    from research_hub.workspace import _windows_export
    def fail(*args, **kwargs):
        raise OSError('PRIVATE ROOT / source text in native failure')
    monkeypatch.setattr(module, '_WINDOWS_EXPORT_SUPPORTED', True)
    monkeypatch.setattr(_windows_export, '_parts', lambda *args, **kwargs: None)
    monkeypatch.setattr(_windows_export, 'destination_stream', fail)
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest(candidate)))
    destination = outside(tmp_path)
    assert module.main([str(path), str(destination)]) == 2
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err == 'Input preparation failed; no verified bundle completed.\n'
    assert not destination.exists()


def test_windows_invalid_spelling_rejected_before_capture(candidate, tmp_path, monkeypatch):
    from research_hub.workspace import _windows_export
    def invalid(*args, **kwargs):
        raise ValueError('Invalid Windows path component')
    monkeypatch.setattr(module, '_WINDOWS_EXPORT_SUPPORTED', True)
    monkeypatch.setattr(_windows_export, '_parts', invalid)
    monkeypatch.setattr(module, 'prepare', lambda *args: pytest.fail('unexpected capture'))
    with pytest.raises(ValueError, match='Invalid Windows path component'):
        module.export(manifest(candidate), outside(tmp_path))
    assert not outside(tmp_path).exists()


@pytest.mark.parametrize('moment', ['before_write', 'after_flush'])
def test_windows_dispatch_retains_destination_identity_gate(candidate, tmp_path, monkeypatch, moment):
    from contextlib import contextmanager
    from research_hub.workspace import _windows_export
    @contextmanager
    def native(destination, *, workspace_roots):
        with destination.open('xb') as stream:
            yield stream
    monkeypatch.setattr(module, '_WINDOWS_EXPORT_SUPPORTED', True)
    monkeypatch.setattr(_windows_export, '_parts', lambda *args, **kwargs: None)
    monkeypatch.setattr(_windows_export, 'destination_stream', native)
    destination = outside(tmp_path)
    original = module.safe_path
    checks = 0
    def replace(root, path, **kwargs):
        nonlocal checks
        if path == destination:
            checks += 1
            if checks == (3 if moment == 'before_write' else 4):
                raise ValueError('Bundle destination changed')
        return original(root, path, **kwargs)
    monkeypatch.setattr(module, 'safe_path', replace)
    with pytest.raises(ValueError, match='Bundle destination changed'):
        module.export(manifest(candidate), destination)
    if moment == 'before_write':
        assert destination.read_bytes() == b''
    else:
        assert 'manifest.json' in zipfile.ZipFile(destination).namelist()


@pytest.mark.parametrize("directory_relative", [False, pytest.param(True, marks=requires_directory_export)])
def test_fdopen_failure_closes_output_descriptor(
        candidate, tmp_path, monkeypatch, capsys, directory_relative):
    """A refused stream transfer retains no descriptor or private-path error."""
    import errno
    monkeypatch.setattr(module, "_WINDOWS_EXPORT_SUPPORTED", False)
    monkeypatch.setattr(module, "_DIRECTORY_EXPORT_SUPPORTED", directory_relative)
    destination = outside(tmp_path, "fdopen-refused")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest(candidate)))
    before = snapshot(candidate[0].workspace.root)
    descriptors = []

    def refuse(descriptor, *args, **kwargs):
        descriptors.append(descriptor)
        raise OSError(errno.EMFILE, "Synthetic refusal with private path: " + str(destination))

    monkeypatch.setattr(os, "fdopen", refuse)
    assert module.main([str(path), str(destination)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Input preparation failed; no verified bundle completed.\n"
    assert destination.read_bytes() == b""  # Never delete a refused output implicitly.
    assert snapshot(candidate[0].workspace.root) == before
    assert len(descriptors) == 1
    # Close a leaked descriptor after the assertion so baseline sensitivity does
    # not itself leave process resources behind.
    try:
        with pytest.raises(OSError) as error:
            os.fstat(descriptors[0])
        assert error.value.errno == errno.EBADF
    finally:
        try:
            os.close(descriptors[0])
        except OSError as error:
            assert error.errno == errno.EBADF
