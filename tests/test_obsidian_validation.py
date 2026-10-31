"""Synthetic-only validation boundaries; no credentials or real vault fixtures."""
import json
import os
from pathlib import Path
import stat
import threading
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from research_hub.workspace import obsidian_validation as module
from research_hub.workspace.obsidian_validation import ObsidianValidation
from research_hub.workspace.server import WorkspaceServer


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "selected-vault"
    (root / ".obsidian").mkdir(parents=True)
    (root / "raw" / "selected").mkdir(parents=True)
    (root / ".research_hub").mkdir()
    (root / ".research_hub" / "clusters.yaml").write_text(
        "schema_version: '1.0'\nclusters:\n  selected:\n    name: Synthetic collection\n    status: active\n    obsidian_subfolder: selected\n", encoding="utf-8")
    (root / "raw" / "selected" / "note.md").write_bytes(b"SYNTHETIC BODY MUST NOT BE READ\xff")
    return root


def test_validates_only_registry_and_does_not_read_notes_or_write(vault, monkeypatch):
    note = vault / "raw" / "selected" / "note.md"
    before = {str(path.relative_to(vault)): path.stat().st_mtime_ns for path in vault.rglob("*")}
    opened = []
    real_open = module.os.open
    real_path_open = Path.open
    def registry_only(path, flags):
        assert Path(path) == vault / ".research_hub" / "clusters.yaml"
        assert flags & os.O_WRONLY == 0 and flags & os.O_RDWR == 0
        opened.append(path)
        return real_open(path, flags)
    # os is shared with shutil; release spies before the vault fixture cleans up.
    with monkeypatch.context() as checks:
        checks.setattr(module.os, "open", registry_only)
        checks.setattr(Path, "open", lambda *a, **k: pytest.fail("No note/config Path.open permitted"))
        result = ObsidianValidation(vault).validate(str(vault))
    assert module.os.open is real_open and Path.open is real_path_open
    assert result["status"] == "valid" and result["collection_count"] == 1
    assert result["saved"] is False and result["note_bodies_read"] is False
    assert len(opened) == 1 and note.stat().st_size == len(b"SYNTHETIC BODY MUST NOT BE READ\xff")
    assert before == {str(path.relative_to(vault)): path.stat().st_mtime_ns for path in vault.rglob("*")}


@pytest.mark.parametrize("configured", [True, False])
def test_wrong_or_disabled_scope_stops_before_any_filesystem_query(tmp_path, monkeypatch, configured):
    validator = ObsidianValidation(tmp_path / "authorized") if configured else ObsidianValidation()
    monkeypatch.setattr(Path, "lstat", lambda *a, **k: pytest.fail("Out-of-scope path was probed"))
    monkeypatch.setattr(Path, "resolve", lambda *a, **k: pytest.fail("Out-of-scope path was resolved"))
    result = validator.validate(str(tmp_path / "unselected"))
    assert result["ok"] is False
    assert result["code"] == ("vault_scope_denied" if configured else "vault_validation_unavailable")


@pytest.mark.parametrize("bad", ["", "relative/vault", "C:drive-relative", r"\\host\share", r"\\?\C:\vault", "//host/share", "/synthetic/../elsewhere", "/synthetic/trailing."])
def test_ambiguous_startup_scopes_are_rejected_without_filesystem_access(bad, monkeypatch):
    monkeypatch.setattr(Path, "lstat", lambda *a, **k: pytest.fail("Invalid scope was probed"))
    with pytest.raises(ValueError):
        ObsidianValidation(bad)


def test_missing_file_and_nonvault_are_distinct(tmp_path):
    missing = tmp_path / "missing"
    assert ObsidianValidation(missing).validate(str(missing))["status"] == "not_found"
    regular = tmp_path / "file"
    regular.write_text("Synthetic", encoding="utf-8")
    assert ObsidianValidation(regular).validate(str(regular))["status"] == "not_directory"
    plain = tmp_path / "plain"
    plain.mkdir()
    assert ObsidianValidation(plain).validate(str(plain))["status"] == "not_vault"
    (plain / ".obsidian").mkdir()
    assert ObsidianValidation(plain).validate(str(plain))["status"] == "registry_missing"


@pytest.mark.parametrize("payload,expected", [
    ("schema_version: '99'\nclusters: {}", "invalid_registry"),
    ("clusters: []\nclusters: {}", "invalid_registry"),
    ("clusters: [broken", "invalid_registry"),
    ("clusters: []\n" + "x" * 140000, "invalid_registry"),
    ("clusters:\n  missing:\n    status: active", "registry_mismatch"),
    ("clusters:\n  selected:\n    obsidian_subfolder: ../unselected", "registry_mismatch"),
])
def test_registry_failures_do_not_expose_contents(vault, payload, expected):
    (vault / ".research_hub" / "clusters.yaml").write_text(payload, encoding="utf-8")
    result = ObsidianValidation(vault).validate(str(vault))
    assert result["status"] == expected
    assert str(vault) not in json.dumps(result)
    assert "obsidian_subfolder" not in json.dumps(result)


def test_reparse_component_is_rejected(vault, monkeypatch):
    original = Path.lstat
    def metadata(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400, st_reparse_tag=0xA0000003) if path == vault else info
    monkeypatch.setattr(Path, "lstat", metadata)
    assert ObsidianValidation(vault).validate(str(vault))["status"] == "unsafe_path"


@pytest.mark.parametrize("mode,links", [(stat.S_IFIFO,1),(stat.S_IFREG,2)])
def test_special_registry_is_rejected_before_open(vault, monkeypatch, mode, links):
    original = module._metadata
    real_open = module.os.open
    registry = vault / ".research_hub" / "clusters.yaml"
    def metadata(path):
        return SimpleNamespace(st_mode=mode, st_nlink=links, st_size=0) if path == registry else original(path)
    with monkeypatch.context() as checks:
        checks.setattr(module, "_metadata", metadata)
        checks.setattr(module.os, "open", lambda *a, **k: pytest.fail("Special registry opened"))
        assert ObsidianValidation(vault).validate(str(vault))["status"] == "invalid_registry"
    assert module.os.open is real_open and module._metadata is original


def test_registry_identity_change_during_open_is_not_read(vault, monkeypatch):
    original = module.os.fstat
    real_read = module.os.read
    def changed(fd):
        value = original(fd)
        return SimpleNamespace(st_mode=value.st_mode, st_nlink=1, st_dev=value.st_dev, st_ino=value.st_ino + 1,
                               st_size=value.st_size, st_mtime_ns=value.st_mtime_ns)
    with monkeypatch.context() as checks:
        checks.setattr(module.os, "fstat", changed)
        checks.setattr(module.os, "read", lambda *a, **k: pytest.fail("Changed registry read"))
        assert ObsidianValidation(vault).validate(str(vault))["status"] == "invalid_registry"
    assert module.os.fstat is original and module.os.read is real_read


def test_hardlinked_registry_is_not_read(vault, tmp_path, monkeypatch):
    registry = vault / ".research_hub" / "clusters.yaml"
    real_open = module.os.open
    try:
        os.link(registry, tmp_path / "registry-alias.yaml")
    except OSError:
        pytest.skip("Host does not permit synthetic hardlinks")
    with monkeypatch.context() as checks:
        checks.setattr(module.os, "open", lambda *a, **k: pytest.fail("Hardlinked registry opened"))
        assert ObsidianValidation(vault).validate(str(vault))["status"] == "invalid_registry"
    assert module.os.open is real_open


def test_workspace_cannot_initialize_storage_inside_readonly_vault(vault):
    before = {str(p.relative_to(vault)) for p in vault.rglob("*")}
    with pytest.raises(ValueError, match="outside the read-only"):
        WorkspaceServer(vault, port=0, obsidian_vault=vault)
    assert before == {str(p.relative_to(vault)) for p in vault.rglob("*")}


def test_unsafe_startup_scope_cannot_initialize_workspace_storage(vault, tmp_path, monkeypatch):
    original = Path.lstat
    def reparse(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400,st_reparse_tag=0xA0000003) if path == vault.parent else info
    monkeypatch.setattr(Path,"lstat",reparse)
    monkeypatch.setattr(WorkspaceServer,"_service_type",lambda *a,**k:pytest.fail("Storage initialized before scope rejection"))
    with pytest.raises(ValueError,match="Linked"):
        WorkspaceServer(tmp_path/"other-workspace",port=0,obsidian_vault=vault)


def test_http_validation_retains_original_origin_and_csrf_guards(vault, tmp_path, monkeypatch):
    server = WorkspaceServer(tmp_path / "workspace", port=0, obsidian_vault=vault)
    monkeypatch.setattr(server.service,"capabilities",lambda **kwargs:{"ok":True,"capabilities":{}})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    body = json.dumps({"vault_path": str(vault)}).encode()
    def post(headers):
        request = Request(base + "/api/v1/integrations/obsidian/validate", data=body,
                          headers={"Content-Type":"application/json", **headers})
        try:
            with urlopen(request, timeout=3) as result:
                return result.status, json.load(result)
        except HTTPError as error:
            return error.code, json.load(error)
    try:
        assert post({})[0] == 403
        assert post({"X-CSRF-Token":server.csrf, "Origin":"https://outside.invalid"})[0] == 403
        status, result = post({"X-CSRF-Token":server.csrf})
        assert status == 200 and result["status"] == "valid"
        with urlopen(base + "/api/v1/workspace", timeout=3) as result:
            capability = json.load(result)["capabilities"]["obsidian_validation"]
        assert capability["read_only"] and capability["authorized_vault"] == str(module._lexical(vault))
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        assert not thread.is_alive()


def test_cli_scope_flag_is_workspace_only_and_does_not_discover_config(tmp_path, monkeypatch):
    from research_hub import cli
    from research_hub.workspace import server
    monkeypatch.setattr(cli, "get_config", lambda: pytest.fail("Global config discovery"))
    monkeypatch.setattr(cli, "require_config", lambda: pytest.fail("Global config discovery"))
    calls = []
    monkeypatch.setattr(server, "serve_workspace", lambda *a, **kw: calls.append((a, kw)))
    with pytest.raises(SystemExit):
        cli.main(["serve", "--obsidian-vault", str(tmp_path / "selected")])
    assert not calls
    assert cli.main(["serve", "--workspace", "--root", str(tmp_path / "workspace"), "--obsidian-vault", str(tmp_path / "selected"), "--no-browser"]) == 0
    assert calls[0][1]["obsidian_vault"] == str(tmp_path / "selected")
