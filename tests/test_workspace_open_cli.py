from __future__ import annotations

import errno
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from research_hub.cli import main
from research_hub.workspace.core import Workspace


def test_open_creates_default_workspace_dir_and_launches_server_without_legacy_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        "research_hub.cli.require_config",
        lambda *a, **kw: pytest.fail("open must not require legacy vault config"),
    )
    launched: list[tuple[Path, dict]] = []

    def fake_serve(root, **kwargs):
        launched.append((Path(root), kwargs))

    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", fake_serve)
    rc = main(["open", "--no-browser", "--port", "8791"])
    assert rc == 0

    expected_root = (tmp_path / "research-hub-workspace").resolve()
    assert expected_root.is_dir()
    assert len(launched) == 1
    assert launched[0][0] == expected_root
    assert launched[0][1]["port"] == 8791
    assert launched[0][1]["open_browser"] is False
    assert launched[0][1]["human"] is False
    assert launched[0][1]["integrations_config"] == "auto"
    assert str(expected_root) in capsys.readouterr().out


def test_open_demo_populates_empty_dir_and_preserves_existing_workspace(tmp_path, monkeypatch, capsys):
    target = tmp_path / "demo-root"
    launched = MagicMock()
    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", launched)

    # First run seeds the two offline sample projects cleanly.
    assert main(["open", "--root", str(target), "--demo", "--no-browser"]) == 0
    assert (target / ".research" / "workspace.sqlite3").is_file()
    ws = Workspace(target)
    project_ids = {p["id"] for p in ws.list_projects()}
    assert project_ids == {"review-demo", "summation-demo"}
    assert "Created sample projects" in capsys.readouterr().out

    # Add user project, then re-run `open --demo`: existing data MUST be preserved.
    ws.create_project(id="my-study", title="My Own Study", archetype="review")
    assert main(["open", "--root", str(target), "--demo", "--no-browser"]) == 0
    assert {p["id"] for p in Workspace(target).list_projects()} == {"review-demo", "summation-demo", "my-study"}
    assert "preserving your saved data" in capsys.readouterr().err


def test_open_demo_refuses_non_empty_non_workspace_directory_and_dir_named_sqlite(tmp_path, monkeypatch, capsys):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "notes.txt").write_text("user notes", encoding="utf-8")
    launched = MagicMock()
    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", launched)

    rc = main(["open", "--root", str(occupied), "--demo", "--no-browser"])
    assert rc == 1
    assert not launched.called
    assert "not empty" in capsys.readouterr().err
    assert (occupied / "notes.txt").read_text(encoding="utf-8") == "user notes"

    # A directory named .research/workspace.sqlite3 must not fool `--demo` into thinking it's a valid DB.
    bogus = tmp_path / "bogus-db"
    (bogus / ".research" / "workspace.sqlite3").mkdir(parents=True)
    rc2 = main(["open", "--root", str(bogus), "--demo", "--no-browser"])
    assert rc2 == 1
    assert not launched.called
    assert "regular file" in capsys.readouterr().err


def test_open_validates_obsidian_vault_boundary_before_creating_files(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    inside = vault / "workspace-inside-vault"
    launched = MagicMock()
    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", launched)

    rc = main(["open", "--root", str(inside), "--demo", "--obsidian-vault", str(vault), "--no-browser"])
    assert rc == 1
    assert not inside.exists()
    assert not launched.called
    assert "outside" in capsys.readouterr().err.lower() or "vault" in capsys.readouterr().err.lower() or rc == 1


def test_open_passes_through_valid_obsidian_vault_and_library_snapshot(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    snapshot = tmp_path / "library.json"
    snapshot.write_text("{}", encoding="utf-8")
    target = tmp_path / "ws"
    launched: list[tuple[Path, dict]] = []
    monkeypatch.setattr(
        "research_hub.workspace.open_cli.serve_workspace",
        lambda root, **kw: launched.append((Path(root), kw)),
    )

    rc = main([
        "open",
        "--root", str(target),
        "--obsidian-vault", str(vault),
        "--library-snapshot", str(snapshot),
        "--no-browser",
    ])
    assert rc == 0
    assert launched[0][1]["obsidian_vault"] == str(vault)
    assert launched[0][1]["library_snapshot"] == str(snapshot)


@pytest.mark.parametrize("exc_factory", [
    lambda: OSError(errno.EADDRINUSE, "Address already in use"),
    lambda: type("WinBusy", (OSError,), {"winerror": 10048})(0, "Only one usage of each socket address"),
])
def test_open_port_conflict_preserves_original_command_guidance(tmp_path, monkeypatch, capsys, exc_factory):
    def fake_serve(*args, **kwargs):
        raise exc_factory()

    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", fake_serve)
    rc = main(["open", "--root", str(tmp_path / "my-ws"), "--port", "8765", "--no-browser"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Port 8765 is already in use" in err
    assert "--port 8766" in err
    assert "original command" in err


def test_open_handles_permission_error_during_directory_prep_cleanly(tmp_path, monkeypatch, capsys):
    target = tmp_path / "unwritable-ws"
    monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: (_ for _ in ()).throw(PermissionError("read-only fs")))
    launched = MagicMock()
    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", launched)

    rc = main(["open", "--root", str(target), "--no-browser"])
    assert rc == 1
    assert not launched.called
    assert "read-only fs" in capsys.readouterr().err


def test_open_rejects_unsafe_paths_and_bad_ports(tmp_path, monkeypatch, capsys):
    launched = MagicMock()
    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", launched)

    existing_file = tmp_path / "not-a-dir.txt"
    existing_file.write_text("hi", encoding="utf-8")

    fs_root = str(Path(tmp_path.anchor))
    for bad_root in (
        str(tmp_path / "missing-parent" / "ws"),
        "../escape",
        str(tmp_path / "bad\x00name"),
        fs_root,
        "//server/share/ws",
        str(tmp_path / "CON .txt"),
        str(tmp_path / "trailing."),
        str(existing_file),
    ):
        assert main(["open", "--root", bad_root, "--no-browser"]) == 1

    # Simulated Windows reparse point on target is rejected.
    reparse_dir = tmp_path / "reparse-target"
    reparse_dir.mkdir()
    real_lstat = Path.lstat

    def fake_lstat(self, *a, **kw):
        res = real_lstat(self, *a, **kw)
        if self.resolve() == reparse_dir.resolve():
            return SimpleNamespace(st_mode=res.st_mode, st_file_attributes=0x400, st_reparse_tag=0xA0000003)
        return res

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    assert main(["open", "--root", str(reparse_dir), "--no-browser"]) == 1
    monkeypatch.setattr(Path, "lstat", real_lstat)

    # Port out of bounds exits with argparse error (SystemExit 2).
    for bad_port in ("-1", "65536"):
        with pytest.raises(SystemExit) as excinfo:
            main(["open", "--root", str(tmp_path / "ok"), "--port", bad_port, "--no-browser"])
        assert excinfo.value.code == 2

    assert not launched.called


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink creation does not require elevated privilege")
def test_open_rejects_symlink_target_and_symlink_control_dir(tmp_path, monkeypatch):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link_dir = tmp_path / "link"
    link_dir.symlink_to(real_dir)
    launched = MagicMock()
    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", launched)

    assert main(["open", "--root", str(link_dir), "--no-browser"]) == 1

    ws_with_link = tmp_path / "ws-link-ctrl"
    ws_with_link.mkdir()
    (ws_with_link / ".research").symlink_to(real_dir)
    assert main(["open", "--root", str(ws_with_link), "--demo", "--no-browser"]) == 1
    assert not launched.called


def test_open_human_approvals_validates_root_first_and_handles_tty_eof_and_confirmation(tmp_path, monkeypatch, capsys):
    launched: list[tuple[Path, dict]] = []
    monkeypatch.setattr(
        "research_hub.workspace.open_cli.serve_workspace",
        lambda root, **kw: launched.append((Path(root), kw)),
    )

    # Invalid root is rejected BEFORE interactive confirmation prompt runs.
    monkeypatch.setattr("builtins.input", lambda: pytest.fail("must not prompt for invalid root"))
    assert main(["open", "--root", "../escape", "--human-approvals", "--no-browser"]) == 1

    # Non-TTY rejects --human-approvals cleanly.
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit) as excinfo:
        main(["open", "--root", str(tmp_path / "ws-human"), "--human-approvals", "--no-browser"])
    assert excinfo.value.code == 2

    # Interactive TTY: EOF returns 1 cleanly, wrong phrase returns 1, exact phrase enables human=True.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(EOFError()))
    assert main(["open", "--root", str(tmp_path / "ws-human"), "--human-approvals", "--no-browser"]) == 1

    monkeypatch.setattr("builtins.input", lambda: "wrong phrase")
    assert main(["open", "--root", str(tmp_path / "ws-human"), "--human-approvals", "--no-browser"]) == 1

    monkeypatch.setattr("builtins.input", lambda: "enable local review")
    assert main(["open", "--root", str(tmp_path / "ws-human"), "--human-approvals", "--no-browser"]) == 0
    assert len(launched) == 1 and launched[0][1]["human"] is True
