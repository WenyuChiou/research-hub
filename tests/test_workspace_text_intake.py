"""Bounded synthetic local text intake, not live publication identity evidence."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
import sqlite3
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError
from research_hub.workspace.service import WorkspaceService
from research_hub.workspace.server import WorkspaceServer
from research_hub.workspace.text_intake import TextIntake
from research_hub.workspace import text_intake as module


# Native filesystem behavior is exercised only where the production backend's
# required no-follow/directory-relative primitives actually exist. In particular,
# a Windows skip is NOT a successful Windows intake or safety test.
requires_publication = pytest.mark.skipif(
    not module.publication_supported(),
    reason="Native text publication requires backend POSIX no-follow/dir_fd primitives; Windows intake unsupported",
)


@pytest.fixture
def intake(tmp_path):
    ws = Workspace(tmp_path)
    ws.create_project(id="paper", title="Synthetic intake project")
    raw = "\ufeffSynthetic abstract\r\n研究😀: no reduction.\r\n".encode("utf-8")
    payload = {"intake_request": {"version": 1, "workspace_instance_id": ws.preparation_namespace(), "key": str(uuid.uuid4())},
               "title": "Synthetic source", "reading_scope": "unknown", "input_kind": "file", "format": "md",
               "content_base64": base64.b64encode(raw).decode("ascii")}
    return ws, payload, raw


@pytest.fixture
def validation_only(intake, monkeypatch):
    """Portable validator unit seam, NOT mocked native publication support.

    Bypass only the entry capability rejection so invalid payloads reach the real
    validator on every OS. Any filesystem publication or DB write is a failure.
    The separate unsupported-platform tests exercise the real fail-closed gate.
    """
    ws, _, _ = intake
    before = ws.db_path.read_bytes()
    original_db = Workspace.db

    @contextmanager
    def readonly(self, *, write=False):
        if write:
            pytest.fail("Invalid intake must not open a write transaction")
        with original_db(self, write=False) as db:
            yield db

    monkeypatch.setattr(module, "_supported", lambda: None)
    monkeypatch.setattr(module, "_publish_copy",
                        lambda *_a, **_k: pytest.fail("Invalid intake must not publish files"))
    monkeypatch.setattr(Workspace, "db", readonly)
    yield
    assert ws.db_path.read_bytes() == before
    assert not (ws.root / "hub-sources").exists()


def submit(ws, payload, project="paper"):
    return WorkspaceService(ws.root).dispatch("project", "source_text", {"project_id": project, **payload})


@requires_publication
def test_dropped_response_replay_preserves_bytes_and_pair(intake):
    ws, payload, raw = intake
    first = submit(ws, payload)
    result = submit(ws, payload)
    assert result["intake"]["disposition"] == "existing"
    assert result["record"]["id"] == first["record"]["id"]
    assert result["artifact"]["id"] == first["artifact"]["id"]
    assert (ws.root / result["artifact"]["path"]).read_bytes() == raw
    assert result["preview"]["text"].encode("utf-8") == raw
    assert result["record"]["data"]["locator"].startswith("hub-source:")
    assert result["record"]["data"]["identity_status"] == "unverified"
    assert len(ws.records("paper")) == len(ws.artifacts("paper")) == 1


@requires_publication
def test_concurrent_same_intake_creates_one_linked_pair(intake):
    ws, payload, _ = intake
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(ws, payload), range(2)))
    assert len({result["record"]["id"] for result in results}) == 1
    assert sorted(result["intake"]["disposition"] for result in results) == ["created", "existing"]
    assert len(ws.records("paper")) == len(ws.artifacts("paper")) == 1


@requires_publication
def test_changed_payload_same_intake_key_conflicts(intake):
    ws, payload, _ = intake
    first = submit(ws, payload)
    with pytest.raises(WorkspaceError) as error:
        submit(ws, {**payload, "title": "Changed intent"})
    assert error.value.code == "request_key_conflict"
    assert len(ws.records("paper")) == len(ws.artifacts("paper")) == 1
    assert ws.records("paper")[0]["id"] == first["record"]["id"]


@requires_publication
def test_local_copy_preserves_original_and_has_no_task_or_request_journal(intake):
    ws, payload, raw = intake
    original = ws.root / "original.md"
    original.write_bytes(raw)
    result = submit(ws, payload)
    assert original.read_bytes() == raw
    assert result["artifact"]["path"] != "original.md"
    assert result["record"]["data"]["reading_scope"] == "unknown"
    assert result["record"]["data"]["publication_version"] == "unknown"
    assert result["record"]["data"]["human_acceptance"] == "pending"
    assert str(ws.root) not in json.dumps(result)
    assert "original.md" not in json.dumps(result)
    with ws.db() as db:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM prepare_requests").fetchone()[0] == 0
        assert {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
            "projects", "artifacts", "records", "tasks", "decisions", "actions", "workspace_metadata", "prepare_requests"}


@requires_publication
def test_exact_lookup_is_read_only_and_miss_is_not_success(intake):
    ws, payload, _ = intake
    identity = payload["intake_request"]
    values = {"workspace_instance_id": identity["workspace_instance_id"], "key": identity["key"]}
    before = ws.db_path.read_bytes()
    missing = TextIntake(ws).lookup("paper", **values)
    assert missing["intake"]["state"] == "not_observed" and "record" not in missing
    assert ws.db_path.read_bytes() == before
    first = submit(ws, payload)
    before = ws.db_path.read_bytes()
    found = TextIntake(ws).lookup("paper", **values)
    assert found["record"]["id"] == first["record"]["id"]
    assert found["intake"]["state"] == "found"
    assert ws.db_path.read_bytes() == before


@pytest.mark.parametrize("raw", [b"", b" \r\n\t", b"\xef\xbb\xbf \r\n", b"bad\x00text", b"\xff", b"\xed\xa0\x80",
                                pytest.param(b"a" * 40001, id="utf8-over-limit-40001-bytes")])
def test_invalid_or_oversized_bytes_never_write(intake, validation_only, raw):
    ws, payload, _ = intake
    before = ws.db_path.read_bytes()
    with pytest.raises(WorkspaceError):
        submit(ws, {**payload, "content_base64": base64.b64encode(raw).decode("ascii")})
    assert not (ws.root / "hub-sources").exists()
    assert ws.db_path.read_bytes() == before


@pytest.mark.parametrize("value", ["%%%%", "YQ==\n", "YR==", "é",
                                  pytest.param("x" * 53337, id="base64-over-limit-53337-chars"), None])
def test_base64_must_be_strict_bounded_and_canonical(intake, validation_only, value):
    ws, payload, _ = intake
    with pytest.raises(WorkspaceError):
        submit(ws, {**payload, "content_base64": value})
    assert not (ws.root / "hub-sources").exists()


@pytest.mark.parametrize("field,value", [("title", ""), ("title", "a" * 2001), ("title", "\ud800"),
                                          ("locator", "a" * 2001), ("locator", "\ud800"), ("reading_scope", "full-text"),
                                          ("format", "pdf"), ("input_kind", "url")])
def test_invalid_metadata_rejected_before_writes(intake, validation_only, field, value):
    ws, payload, _ = intake
    with pytest.raises(WorkspaceError):
        submit(ws, {**payload, field: value})
    assert not (ws.root / "hub-sources").exists()


@requires_publication
def test_exact_limit_multibyte_and_inert_markup(intake):
    ws, payload, _ = intake
    raw = ("😀" * 9990 + "<script>x</script>" + "x" * 22).encode("utf-8")
    assert len(raw) == 40000
    result = submit(ws, {**payload, "content_base64": base64.b64encode(raw).decode("ascii"),
                          "title": "<img src=x onerror=alert(1)>", "locator": "javascript:alert(1)"})
    assert result["preview"]["text"].encode("utf-8") == raw
    assert result["record"]["data"]["title"] == "<img src=x onerror=alert(1)>"
    assert result["record"]["data"]["locator"] == "javascript:alert(1)"
    assert result["record"]["data"]["identity_status"] == "unverified"


@requires_publication
def test_unicode_crlf_saved_selection_uses_existing_prepare_contract(intake):
    ws, payload, raw = intake
    saved = submit(ws, payload)
    text = raw.decode("utf-8")
    start = text.index("研究")
    task = WorkspaceService(ws.root).tasks.create("paper", operation="paper-abstract-draft", source_selection={
        "artifact_id": saved["artifact"]["id"], "source_record_id": saved["record"]["id"], "start": start, "end": len(text)})
    pack = task["request"]["research_draft"]["source_pack"]
    assert pack["text"] == text[start:] and "\r\n" in pack["text"]
    assert pack["source_sha256"] == saved["artifact"]["sha256"]
    assert pack["source"]["publication_version"] == "unknown"
    assert task["status"] == "awaiting_agent" and task["result"] is None


@pytest.mark.parametrize("target", ["artifacts", "records"])
@requires_publication
def test_insert_failure_rolls_back_pair_and_same_key_reuses_copy(intake, target):
    ws, payload, raw = intake
    with ws.db(write=True) as db:
        db.execute(f"CREATE TRIGGER fail_intake BEFORE INSERT ON {target} BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        submit(ws, payload)
    assert ws.records("paper") == ws.artifacts("paper") == []
    copies = list((ws.root / "hub-sources").rglob("*.md"))
    assert len(copies) == 1 and copies[0].read_bytes() == raw
    identity = payload["intake_request"]
    before = ws.db_path.read_bytes()
    assert TextIntake(ws).lookup("paper", key=identity["key"], workspace_instance_id=identity["workspace_instance_id"])["intake"]["state"] == "not_observed"
    assert ws.db_path.read_bytes() == before and copies[0].read_bytes() == raw
    inode = copies[0].stat().st_ino
    with ws.db(write=True) as db:
        db.execute("DROP TRIGGER fail_intake")
    result = submit(ws, payload)
    assert (ws.root / result["artifact"]["path"]).stat().st_ino == inode
    assert len(ws.records("paper")) == len(ws.artifacts("paper")) == 1


@requires_publication
def test_before_commit_failure_preserves_orphan_but_no_saved_claim(intake, monkeypatch):
    ws, payload, _ = intake
    original = ws.db

    @contextmanager
    def fail_commit(*, write=False):
        with original(write=write) as db:
            yield db
            if write:
                assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 1
                raise OSError("synthetic before-commit failure")

    monkeypatch.setattr(ws, "db", fail_commit)
    with pytest.raises(WorkspaceError) as error:
        TextIntake(ws).save("paper", **payload)
    assert error.value.code == "storage_unavailable"
    monkeypatch.setattr(ws, "db", original)
    assert ws.records("paper") == ws.artifacts("paper") == []
    assert submit(ws, payload)["intake"]["disposition"] == "created"


@requires_publication
def test_after_commit_response_failure_reconciles_without_rewrite(intake, monkeypatch):
    ws, payload, _ = intake
    original = TextIntake._result
    monkeypatch.setattr(TextIntake, "_result", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("lost response")))
    with pytest.raises(OSError):
        submit(ws, payload)
    monkeypatch.setattr(TextIntake, "_result", original)
    identity = payload["intake_request"]
    found = TextIntake(ws).lookup("paper", key=identity["key"], workspace_instance_id=identity["workspace_instance_id"])
    assert found["intake"]["state"] == "found"
    assert submit(ws, payload)["intake"]["disposition"] == "existing"


@requires_publication
def test_complete_publish_before_temp_unlink_failure_is_reusable(intake, monkeypatch):
    ws, payload, raw = intake
    original = module.os.unlink
    monkeypatch.setattr(module.os, "unlink", lambda *_a, **_k: (_ for _ in ()).throw(OSError("synthetic crash boundary")))
    # Keep feature detection stable while fault-injecting its primitive.
    monkeypatch.setattr(module, "publication_supported", lambda: True)
    with pytest.raises(WorkspaceError):
        submit(ws, payload)
    assert ws.records("paper") == []
    final = next((ws.root / "hub-sources").rglob("*.md"))
    assert final.read_bytes() == raw and final.stat().st_nlink == 2
    monkeypatch.setattr(module.os, "unlink", original)
    result = submit(ws, payload)
    assert result["preview"]["text"].encode("utf-8") == raw
    assert len(list((ws.root / "hub-sources").rglob("*.md"))) == 1


@requires_publication
def test_partial_temporary_write_never_publishes(intake, monkeypatch):
    ws, payload, _ = intake
    original = module.os.fdopen

    class Partial:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *_args): self.stream.close()
        def write(self, value):
            self.stream.write(value[:3])
            raise OSError("synthetic mid-write interruption")

    def partial(fd, mode):
        stream = original(fd, mode)
        return Partial(stream) if mode == "wb" else stream

    monkeypatch.setattr(module.os, "fdopen", partial)
    with pytest.raises(WorkspaceError):
        submit(ws, payload)
    assert ws.records("paper") == ws.artifacts("paper") == []
    assert not list((ws.root / "hub-sources").rglob("*.md"))
    assert not list((ws.root / "hub-sources").rglob("*.tmp"))


@pytest.mark.parametrize("change", ["modify", "delete"])
@requires_publication
def test_committed_copy_stale_or_missing_is_never_reconstructed(intake, change):
    ws, payload, _ = intake
    saved = submit(ws, payload)
    path = ws.root / saved["artifact"]["path"]
    if change == "modify":
        path.write_bytes(b"Researcher changed the saved copy")
    else:
        path.unlink()
    result = submit(ws, payload)
    assert result["intake"]["disposition"] == "existing"
    assert result["preview"] is None and not result["artifact"]["current"]
    if change == "modify":
        assert path.read_bytes() == b"Researcher changed the saved copy"
    else:
        assert not path.exists()


@requires_publication
def test_same_key_project_isolation_and_separate_intents(intake):
    ws, payload, _ = intake
    first = submit(ws, payload)
    ws.create_project(id="other", title="Other")
    second = submit(ws, payload, "other")
    assert first["record"]["id"] != second["record"]["id"]
    other_key = {**payload, "intake_request": {**payload["intake_request"], "key": str(uuid.uuid4())}}
    third = submit(ws, other_key)
    assert third["record"]["id"] != first["record"]["id"]
    assert len(ws.records("paper")) == 2 and len(ws.records("other")) == 1


@pytest.mark.parametrize("field,value", [("key", "../../original"), ("key", "x" * 1000), ("version", True), ("workspace_instance_id", str(uuid.uuid4()))])
def test_invalid_or_cross_workspace_identity_never_writes(intake, validation_only, field, value):
    ws, payload, _ = intake
    with pytest.raises(WorkspaceError):
        submit(ws, {**payload, "intake_request": {**payload["intake_request"], field: value}})
    assert not (ws.root / "hub-sources").exists()


@requires_publication
def test_symlink_parent_cannot_redirect_publication(intake, tmp_path):
    ws, payload, _ = intake
    elsewhere = tmp_path / "outside"
    elsewhere.mkdir()
    (ws.root / "hub-sources").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(WorkspaceError):
        submit(ws, payload)
    assert list(elsewhere.iterdir()) == []
    assert ws.records("paper") == []


@requires_publication
def test_parent_swapped_after_path_validation_is_not_followed(intake, tmp_path, monkeypatch):
    ws, payload, _ = intake
    elsewhere = tmp_path / "outside-swap"
    elsewhere.mkdir()
    original = module._directory

    @contextmanager
    def swap(root, parts, *, create):
        (root / "hub-sources").symlink_to(elsewhere, target_is_directory=True)
        with original(root, parts, create=create) as directory:
            yield directory

    monkeypatch.setattr(module, "_directory", swap)
    with pytest.raises(WorkspaceError):
        submit(ws, payload)
    assert list(elsewhere.iterdir()) == []
    assert ws.records("paper") == []


@requires_publication
def test_temporary_replaced_before_link_never_commits_unverified_target(intake, monkeypatch):
    ws, payload, _ = intake
    outside = ws.root / "do-not-touch.txt"
    outside.write_bytes(b"Original private synthetic content")
    original = module.os.link

    def replace_temporary(source, target, **kwargs):
        os.unlink(source, dir_fd=kwargs["src_dir_fd"])
        os.symlink(str(outside), source, dir_fd=kwargs["src_dir_fd"])
        return original(source, target, **kwargs)

    monkeypatch.setattr(module.os, "link", replace_temporary)
    monkeypatch.setattr(module, "publication_supported", lambda: True)
    with pytest.raises(WorkspaceError):
        submit(ws, payload)
    assert ws.records("paper") == ws.artifacts("paper") == []
    assert outside.read_bytes() == b"Original private synthetic content"


@requires_publication
def test_final_collision_never_overwrites_or_deletes_unknown_file(intake, monkeypatch):
    ws, payload, _ = intake
    original = module._publish_copy
    def collision(workspace, relative, raw):
        destination = workspace.root / relative
        parent = workspace.root
        for part in destination.relative_to(workspace.root).parts[:-1]:
            parent = parent / part
            parent.mkdir(mode=0o700, exist_ok=True)
        destination.write_bytes(b"Unknown content must survive")
        original(workspace, relative, raw)
    monkeypatch.setattr(module, "_publish_copy", collision)
    with pytest.raises(WorkspaceError) as error:
        submit(ws, payload)
    assert error.value.code == "file_conflict"
    assert next((ws.root / "hub-sources").rglob("*.md")).read_bytes() == b"Unknown content must survive"
    assert ws.records("paper") == []


def test_platform_without_safe_primitives_is_explicitly_unsupported(intake, monkeypatch):
    ws, payload, _ = intake
    monkeypatch.setattr(module, "publication_supported", lambda: False)
    cap = module.capability(ws)
    assert cap["status"] == "unavailable" and "Windows" in cap["message"]
    before = ws.db_path.read_bytes()
    with pytest.raises(WorkspaceError) as error:
        submit(ws, payload)
    assert error.value.code == "unsupported_capability"
    assert ws.db_path.read_bytes() == before
    assert not (ws.root / "hub-sources").exists()


@pytest.mark.parametrize("corruption", ["malformed_source", "wrong_path", "missing_artifact", "missing_source"])
@requires_publication
def test_damaged_linkage_is_explicit_error_not_missing_or_repair(intake, corruption):
    ws, payload, _ = intake
    saved = submit(ws, payload)
    with ws.db(write=True) as db:
        if corruption == "malformed_source":
            db.execute("UPDATE records SET body='[]' WHERE id=?", (saved["record"]["id"],))
        elif corruption == "wrong_path":
            artifact = {**saved["artifact"], "path": "unrelated.txt"}
            db.execute("UPDATE artifacts SET body=? WHERE id=?", (json.dumps(artifact), saved["artifact"]["id"]))
        elif corruption == "missing_source":
            db.execute("DELETE FROM records WHERE id=?", (saved["record"]["id"],))
        else:
            db.execute("DELETE FROM artifacts WHERE id=?", (saved["artifact"]["id"],))
    before = ws.db_path.read_bytes()
    identity = payload["intake_request"]
    with pytest.raises(WorkspaceError) as error:
        TextIntake(ws).lookup("paper", key=identity["key"], workspace_instance_id=identity["workspace_instance_id"])
    assert error.value.code == "ledger_unavailable"
    assert ws.db_path.read_bytes() == before


@pytest.fixture
def server(intake):
    host = WorkspaceServer(intake[0].root, port=0)
    worker = threading.Thread(target=host.serve_forever, daemon=True)
    worker.start()
    try:
        yield host
    finally:
        host.shutdown()
        host.server_close()
        worker.join(timeout=3)


def http(host, path, *, data=None, headers=None):
    request = Request(f"http://127.0.0.1:{host.server_port}/api/v1{path}",
                      data=None if data is None else json.dumps(data).encode(), headers=headers or {})
    try:
        response = urlopen(request, timeout=4)
    except HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), json.loads(response.read())


@requires_publication
def test_http_saved_pair_read_and_csrf(intake, server):
    ws, payload, _ = intake
    status, _, denied = http(server, "/projects/paper/source-text", data=payload, headers={"Content-Type": "application/json"})
    assert status == 403 and denied["code"] == "forbidden"
    status, _, saved = http(server, "/projects/paper/source-text", data=payload, headers={"Content-Type": "application/json", "X-CSRF-Token": server.csrf})
    assert status == 200
    identity = payload["intake_request"]
    status, headers, found = http(server, f"/projects/paper/source-text/{identity['key']}", headers={"X-Workspace-Instance": identity["workspace_instance_id"]})
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert found["record"]["id"] == saved["record"]["id"]
    assert str(ws.root) not in json.dumps(found)


@pytest.mark.parametrize("extra", [{"Origin": "https://other.example"}, {"Host": "other.example"}, {"Sec-Fetch-Site": "cross-site"}])
def test_key_does_not_bypass_trusted_origin(intake, server, extra):
    _, payload, _ = intake
    identity = payload["intake_request"]
    status, _, denied = http(server, f"/projects/paper/source-text/{identity['key']}", headers={"X-Workspace-Instance": identity["workspace_instance_id"], **extra})
    assert status == 403 and denied["code"] == "forbidden"


def test_missing_lookup_is_read_only_without_publication_primitives(intake, monkeypatch):
    ws, payload, _ = intake
    monkeypatch.setattr(module, "publication_supported", lambda: False)
    identity = payload["intake_request"]
    before = ws.db_path.read_bytes()
    result = TextIntake(ws).lookup(
        "paper", workspace_instance_id=identity["workspace_instance_id"], key=identity["key"])
    assert result["intake"]["state"] == "not_observed"
    assert "record" not in result and "artifact" not in result
    assert ws.db_path.read_bytes() == before
    assert not (ws.root / "hub-sources").exists()


def test_http_unsupported_publication_keeps_csrf_and_writes_nothing(intake, server, monkeypatch):
    ws, payload, _ = intake
    monkeypatch.setattr(module, "publication_supported", lambda: False)
    before = ws.db_path.read_bytes()
    status, _, denied = http(server, "/projects/paper/source-text", data=payload,
                             headers={"Content-Type": "application/json"})
    assert status == 403 and denied["code"] == "forbidden"
    status, _, unsupported = http(server, "/projects/paper/source-text", data=payload,
                                  headers={"Content-Type": "application/json", "X-CSRF-Token": server.csrf})
    assert status == 400 and unsupported["code"] == "unsupported_capability"
    assert ws.db_path.read_bytes() == before
    assert not (ws.root / "hub-sources").exists()
    assert ws.records("paper") == ws.artifacts("paper") == []


def test_native_capability_matches_actual_platform_gate(intake):
    ws, payload, _ = intake
    supported = module.publication_supported()
    assert module.capability(ws)["status"] == ("available" if supported else "unavailable")
    if supported:
        return  # Actual supported publication is exercised by the marked cases.
    before = ws.db_path.read_bytes()
    with pytest.raises(WorkspaceError) as error:
        submit(ws, payload)
    assert error.value.code == "unsupported_capability"
    assert ws.db_path.read_bytes() == before
    assert not (ws.root / "hub-sources").exists()
    assert ws.records("paper") == ws.artifacts("paper") == []


def test_oversized_parameter_ids_are_bounded_without_shrinking_payloads():
    # pytest includes the node ID in PYTEST_CURRENT_TEST on setup/call/teardown.
    # Windows rejects an environment value above 32767 characters, before our
    # validator executes. Keep the full negative inputs, not their default repr.
    cases = [(test_invalid_or_oversized_bytes_never_write, 40001),
             (test_base64_must_be_strict_bounded_and_canonical, 53337)]
    for function, expected_length in cases:
        marker = next(mark for mark in function.pytestmark if mark.name == "parametrize")
        oversized = [case for case in marker.args[1]
                     if len(getattr(case, "values", (case,))[0] or b"") == expected_length]
        assert len(oversized) == 1
        parameter_id = getattr(oversized[0], "id", None)
        assert isinstance(parameter_id, str) and 0 < len(parameter_id) <= 64
