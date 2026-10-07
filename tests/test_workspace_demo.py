"""Offline demo creation, measured results, and preservation boundaries."""

import json
import platform
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError
from research_hub.workspace.demo import create_demo


def _bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("existing_empty", [False, True])
def test_demo_creates_two_real_unaccepted_projects_without_services(tmp_path, monkeypatch, existing_empty):
    root = tmp_path / "demo"
    if existing_empty:
        root.mkdir()
    monkeypatch.setenv("RESEARCH_HUB_WRITING_ADAPTER", str(tmp_path / "missing-adapter"))

    def forbidden(*args, **kwargs):
        pytest.fail("Demo creation must not use network, agents, or a writing adapter")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("research_hub.workspace.executor.codex_capability", forbidden)
    monkeypatch.setattr("research_hub.workspace.writing.WritingAdapter", forbidden)
    result = create_demo(root)
    assert result["ok"] is True
    assert result["root"] == str(root.resolve())
    assert result["warnings"]
    workspace = Workspace(root)
    assert {p["id"]: p["archetype"] for p in workspace.list_projects()} == {
        "summation-demo": "empirical", "review-demo": "review",
    }
    for project in result["projects"]:
        snapshot = workspace.snapshot(project["id"])
        assert project["title"].startswith("DEMO:")
        assert snapshot["tasks"] == snapshot["actions"] == []
        assert snapshot["manuscript"] is None
        assert snapshot["workflow"]["status"] == "running"
        assert all(item["current"] and not item.get("superseded_by") for item in snapshot["artifacts"])
        assert all(item["path"].startswith(project["id"] + "/") for item in snapshot["artifacts"])
        assert len([item for item in snapshot["artifacts"] if item["role"] == "main_manuscript"]) == 1
    assert json.loads((root / "demo.json").read_text(encoding="utf-8")) == result


def test_three_cases_are_measured_and_source_reproduces_them(tmp_path):
    root = tmp_path / "demo"
    create_demo(root)
    measured = json.loads((root / "summation-demo/analysis.json").read_text(encoding="utf-8"))
    assert [case["inputs"] for case in measured["cases"]] == [
        [1e16, 1, -1e16], [1e16, -1e16, 1], [1e16, 1, 1, -1e16],
    ]
    assert [case["results"]["naive_loop"] for case in measured["cases"]] == [0.0, 1.0, 0.0]
    assert [case["results"]["math_fsum"] for case in measured["cases"]] == [1.0, 1.0, 2.0]
    assert [case["exact_integer_sum"] for case in measured["cases"]] == [1, 1, 2]
    for case in measured["cases"]:
        assert case["results"]["builtin_sum"] == sum(case["inputs"])
    assert measured["runtime"]["python"] == sys.version
    assert measured["runtime"]["python_version"] == platform.python_version()
    assert measured["runtime"]["platform"] == platform.platform()
    run = subprocess.run([sys.executable, str(root / "summation-demo/summation.py")],
                         capture_output=True, text=True, timeout=10, check=True)
    assert json.loads(run.stdout) == measured
    analysis = next(record for record in Workspace(root).records("summation-demo") if record["kind"] == "analysis")
    assert json.loads(analysis["data"]["result"]) == measured["cases"]


def test_review_records_are_examples_with_unverified_identity_and_support(tmp_path):
    create_demo(tmp_path / "demo")
    records = Workspace(tmp_path / "demo").records("review-demo")
    sources = [record for record in records if record["kind"] == "source"]
    assert {record["data"]["doi"] for record in sources} == {"10.1145/103162.103163", "10.1137/030601818"}
    assert all(record["data"]["identity_status"] == "unverified" for record in sources)
    claims = [record for record in records if record["kind"] == "claim"]
    assert claims and all(record["data"]["verification_status"] == "unverified" and
                          record["data"]["human_acceptance"] == "pending" for record in claims)
    assert len([record for record in records if record["kind"] == "screening"]) == 2
    assert all(record["data"]["example"] for record in records)


def test_second_creation_refuses_and_preserves_every_byte(tmp_path):
    root = tmp_path / "demo"
    create_demo(root)
    before = _bytes(root)
    with pytest.raises(WorkspaceError, match="new or empty") as error:
        create_demo(root)
    assert error.value.code == "conflict"
    assert _bytes(root) == before


def test_existing_original_is_preserved(tmp_path):
    original = tmp_path / "original.md"
    original.write_bytes(b"Researcher's original\r\n")
    with pytest.raises(WorkspaceError, match="new or empty"):
        create_demo(tmp_path)
    assert _bytes(tmp_path) == {"original.md": b"Researcher's original\r\n"}


@pytest.mark.parametrize("name", ["../escape", "unsafe./demo", "unsafe /demo", "file:stream/demo", "CON/demo", "nul.txt/demo"])
def test_ambiguous_or_escaping_root_is_refused(tmp_path, name):
    with pytest.raises(WorkspaceError) as error:
        create_demo(tmp_path / name)
    assert error.value.code == "unsafe_path"
    assert list(tmp_path.iterdir()) == []


def test_file_root_and_missing_parent_are_refused(tmp_path):
    file = tmp_path / "original.txt"
    file.write_bytes(b"keep")
    with pytest.raises(WorkspaceError):
        create_demo(file)
    with pytest.raises(WorkspaceError) as error:
        create_demo(tmp_path / "missing" / "demo")
    assert error.value.code == "missing_parent"
    assert not (tmp_path / "missing").exists()
    assert file.read_bytes() == b"keep"


def test_symlink_ancestor_is_refused_without_touching_target(tmp_path):
    destination = tmp_path / "original"
    destination.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(destination, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit creating test symlinks")
    with pytest.raises(WorkspaceError) as error:
        create_demo(link / "demo")
    assert error.value.code == "unsafe_path"
    assert list(destination.iterdir()) == []


def test_reparse_ancestor_is_refused(tmp_path, monkeypatch):
    original = Path.lstat

    def reparse(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == tmp_path:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(WorkspaceError) as error:
        create_demo(tmp_path / "demo")
    assert error.value.code == "unsafe_path"
    assert list(tmp_path.iterdir()) == []


def test_failure_retains_recoverable_partial_output_and_never_reports_success(tmp_path, monkeypatch):
    original = Workspace.register_artifact

    def fail_second_project(workspace, project_id, **values):
        if project_id == "review-demo":
            raise OSError("injected write failure")
        return original(workspace, project_id, **values)

    monkeypatch.setattr(Workspace, "register_artifact", fail_second_project)
    root = tmp_path / "demo"
    with pytest.raises(WorkspaceError, match="Partial output was preserved") as error:
        create_demo(root)
    assert error.value.code == "demo_incomplete"
    assert str(root) in str(error.value)
    assert (root / "summation-demo/analysis.json").is_file()
    assert not (root / "demo.json").exists()
    before = _bytes(root)
    with pytest.raises(WorkspaceError, match="new or empty"):
        create_demo(root)
    assert _bytes(root) == before


def test_file_collision_during_creation_is_never_overwritten(tmp_path, monkeypatch):
    original = Workspace.create_project
    root = tmp_path / "demo"
    collision = root / "summation-demo/analysis.json"

    def insert_file(workspace, **values):
        project = original(workspace, **values)
        if project["id"] == "summation-demo":
            collision.write_bytes(b"unexpected original")
        return project

    monkeypatch.setattr(Workspace, "create_project", insert_file)
    with pytest.raises(WorkspaceError) as error:
        create_demo(root)
    assert error.value.code == "demo_incomplete"
    assert collision.read_bytes() == b"unexpected original"
    assert not (root / "demo.json").exists()
