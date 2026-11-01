"""Exporter privacy, selected-input scope and metadata fidelity; synthetic only."""
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("snapshot_exporter_safety", ROOT / "scripts/library_snapshot.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    (root / ".research_hub").mkdir(parents=True)
    (root / "raw/selected").mkdir(parents=True)
    (root / ".research_hub/clusters.yaml").write_text("clusters:\n  selected:\n    name: Selected\n    status: active\n", encoding="utf-8")
    return root


def test_indented_scalar_separators_preserve_abstract_and_later_identity(vault):
    note = vault / "raw/selected/note.md"
    note.write_text("---\nabstract: |\n  First line\n  ---\n  ...\n  Last line\ndoi: 10.1000/synthetic\n---\nUNREAD BODY", encoding="utf-8")
    frontmatter, data = exporter.frontmatter_only(note)
    assert data["abstract"] == "First line\n---\n...\nLast line\n"
    assert data["doi"] == "10.1000/synthetic"
    assert "UNREAD BODY" not in frontmatter


def test_hardlinked_note_cannot_publish_unselected_metadata(vault):
    unselected = vault / "raw/unselected"
    unselected.mkdir()
    original = unselected / "private.md"
    original.write_text("---\ntitle: PRIVATE_UNSELECTED\ndoi: 10.1000/unselected\n---\n", encoding="utf-8")
    alias = vault / "raw/selected/alias.md"
    os.link(original, alias)
    with pytest.raises(ValueError):
        exporter.snapshot(vault, ["selected"])


@pytest.mark.parametrize("mode,links", [(stat.S_IFIFO, 1), (stat.S_IFREG, 2)], ids=["special-type", "multiple-links"])
def test_note_metadata_type_and_links_are_checked_before_open(vault, monkeypatch, mode, links):
    note = vault / "raw/selected/note.md"
    note.write_text("---\ntitle: Synthetic\n---\n", encoding="utf-8")
    original_stat, original_lstat, original_open = Path.stat, Path.lstat, Path.open
    def altered(path, original, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == note:
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            values.update(st_mode=mode | 0o600, st_nlink=links)
            return SimpleNamespace(**values)
        return info
    def no_note_open(path, *args, **kwargs):
        if path == note:
            pytest.fail("Unsupported note reached a byte open")
        return original_open(path, *args, **kwargs)
    with monkeypatch.context() as changes:
        changes.setattr(Path, "stat", lambda path, *a, **k: altered(path, original_stat, *a, **k))
        changes.setattr(Path, "lstat", lambda path, *a, **k: altered(path, original_lstat, *a, **k))
        changes.setattr(Path, "open", no_note_open)
        with pytest.raises(ValueError):
            exporter.frontmatter_only(note)


def test_changed_open_descriptor_is_rejected_before_constructing_stream(vault, monkeypatch):
    note = vault / "raw/selected/note.md"
    note.write_text("---\ntitle: Synthetic\n---\n", encoding="utf-8")
    original_open, original_stat, original_stream = os.open, os.fstat, os.fdopen
    owned = []
    def opened(path, flags, *args, **kwargs):
        if path == note and hasattr(os, "O_NONBLOCK"):
            assert flags & os.O_NONBLOCK
        fd = original_open(path, flags, *args, **kwargs)
        if path == note:
            owned.append(fd)
        return fd
    def changed(fd):
        info = original_stat(fd)
        if fd in owned:
            values = list(info); values[0] = stat.S_IFIFO | 0o600
            return os.stat_result(values)
        return info
    def no_stream(fd, *args, **kwargs):
        if fd in owned:
            pytest.fail("Special descriptor reached a byte reader")
        return original_stream(fd, *args, **kwargs)
    with monkeypatch.context() as changes:
        changes.setattr(exporter.os, "open", opened)
        changes.setattr(exporter.os, "fstat", changed)
        changes.setattr(exporter.os, "fdopen", no_stream)
        with pytest.raises(ValueError):
            exporter.frontmatter_only(note)
    assert owned
    for fd in owned:
        with pytest.raises(OSError):
            original_stat(fd)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named-pipe fixture")
def test_real_fifo_is_rejected_without_entering_any_byte_open(vault, monkeypatch):
    note = vault / "raw/selected/pipe.md"
    os.mkfifo(note)
    original_path_open, original_fd_open = Path.open, os.open
    def path_open(path, *args, **kwargs):
        if path == note:
            pytest.fail("FIFO would enter a blocking file open")
        return original_path_open(path, *args, **kwargs)
    def fd_open(path, *args, **kwargs):
        if path == note:
            pytest.fail("FIFO should reject before open")
        return original_fd_open(path, *args, **kwargs)
    with monkeypatch.context() as changes:
        changes.setattr(Path, "open", path_open)
        changes.setattr(exporter.os, "open", fd_open)
        with pytest.raises(ValueError):
            exporter.frontmatter_only(note)


@pytest.mark.parametrize("failure", ["registry", "destination"])
def test_cli_errors_do_not_expose_unselected_content_or_private_paths(vault, tmp_path, failure):
    note = vault / "raw/selected/note.md"
    note.write_text("---\ntitle: Synthetic\n---\n", encoding="utf-8")
    output = tmp_path / "snapshot.json"
    output.write_bytes(b"previous synthetic output")
    if failure == "registry":
        (vault / ".research_hub/clusters.yaml").write_text("clusters: [PRIVATE_UNSELECTED_VALUE\n", encoding="utf-8")
    else:
        parent = tmp_path / "PRIVATE_DESTINATION"
        parent.write_bytes(b"unchanged synthetic blocker")
        output = parent / "snapshot.json"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/library_snapshot.py"), "--vault", str(vault), "--collection", "selected", "--output", str(output)], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 1
    assert "PRIVATE_" not in result.stdout + result.stderr
    assert str(vault) not in result.stdout + result.stderr
    assert "Library export failed" in result.stderr
    if failure == "registry":
        assert output.read_bytes() == b"previous synthetic output"
    else:
        assert output.parent.read_bytes() == b"unchanged synthetic blocker"
