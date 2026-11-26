from __future__ import annotations

import errno
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from research_hub.cli import main
from research_hub.workspace.core import Workspace


def test_open_creates_default_workspace_dir_and_launches_server(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    launched: list[tuple[Path, dict]] = []

    def fake_serve(root, **kwargs):
        launched.append((Path(root), kwargs))

    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", fake_serve)
    rc = main(["open", "--no-browser", "--port", "8791"])
    assert rc == 0

    expected_root = tmp_path / "research-hub-workspace"
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
    assert (target / ".research" / "workspace.sqlite3").exists()
    ws = Workspace(target)
    project_ids = {p["id"] for p in ws.list_projects()}
    assert project_ids == {"review-demo", "summation-demo"}
    assert "Created sample projects" in capsys.readouterr().out

    # Add user project, then re-run `open --demo`: existing data MUST be preserved.
    ws.create_project(id="my-study", title="My Own Study", archetype="review")
    assert main(["open", "--root", str(target), "--demo", "--no-browser"]) == 0
    assert {p["id"] for p in Workspace(target).list_projects()} == {"review-demo", "summation-demo", "my-study"}
    assert "preserving your saved data" in capsys.readouterr().err


def test_open_demo_refuses_non_empty_non_workspace_directory(tmp_path, monkeypatch, capsys):
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


def test_open_reports_actionable_hint_when_port_is_in_use(tmp_path, monkeypatch, capsys):
    def fake_serve(*args, **kwargs):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", fake_serve)
    rc = main(["open", "--root", str(tmp_path / "ws"), "--port", "8765", "--no-browser"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Port 8765 is already in use" in err
    assert "--port 8766" in err


def test_open_rejects_parent_traversal_and_missing_parent(tmp_path, monkeypatch, capsys):
    launched = MagicMock()
    monkeypatch.setattr("research_hub.workspace.open_cli.serve_workspace", launched)

    assert main(["open", "--root", str(tmp_path / "missing-parent" / "ws"), "--no-browser"]) == 1
    assert "Parent directory does not exist" in capsys.readouterr().err

    assert main(["open", "--root", "../escape", "--no-browser"]) == 1
    assert "parent traversal" in capsys.readouterr().err
    assert not launched.called
