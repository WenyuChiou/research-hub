"""Exporter privacy, selected-input scope and metadata fidelity; synthetic only."""
import importlib.util
import json
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


@pytest.mark.parametrize("mode,links,size", [(stat.S_IFIFO, 1, 0), (stat.S_IFREG, 2, 40), (stat.S_IFREG, 1, 128 * 1024 + 1)], ids=["special-type", "hardlink", "oversized"])
def test_registry_input_is_validated_before_byte_read(vault, monkeypatch, mode, links, size):
    registry = vault / ".research_hub/clusters.yaml"
    original_lstat, original_stat, original_read = Path.lstat, Path.stat, Path.read_text
    def altered(path, original, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == registry:
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            values.update(st_mode=mode | 0o600, st_nlink=links, st_size=size)
            return SimpleNamespace(**values)
        return info
    def no_registry_read(path, *args, **kwargs):
        if path == registry:
            pytest.fail("Unsafe registry reached an unbounded byte read")
        return original_read(path, *args, **kwargs)
    with monkeypatch.context() as changes:
        changes.setattr(Path, "lstat", lambda p, *a, **k: altered(p, original_lstat, *a, **k))
        changes.setattr(Path, "stat", lambda p, *a, **k: altered(p, original_stat, *a, **k))
        changes.setattr(Path, "read_text", no_registry_read)
        with pytest.raises(ValueError):
            exporter.snapshot(vault, ["selected"])


def test_list_registry_keeps_selected_folder_name_and_active_default(vault):
    (vault / ".research_hub/clusters.yaml").write_text("schema_version: '1.0'\nclusters:\n  - slug: selected\n    name: Selected list collection\n    obsidian_subfolder: bound\n  - slug: retired\n    name: Retired\n    status: merged\n", encoding="utf-8")
    folder = vault / "raw/bound"
    folder.mkdir()
    (folder / "one.md").write_text("---\ntitle: List selected note\n---\n", encoding="utf-8")
    result = exporter.snapshot(vault, ["selected"])
    assert result["collections"] == [{"id": "selected", "name": "Selected list collection", "note_count": 1}]
    assert result["notes"][0]["data"]["note_path"] == "raw/bound/one.md"
    with pytest.raises(ValueError):
        exporter.snapshot(vault, ["retired"])


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named-pipe registry fixture")
def test_fifo_registry_rejects_before_any_open(vault, monkeypatch):
    registry = vault / ".research_hub/clusters.yaml"
    registry.unlink()
    os.mkfifo(registry)
    original_read, original_open = Path.read_text, os.open
    def no_read(path, *args, **kwargs):
        if path == registry:
            pytest.fail("FIFO registry reached blocking read")
        return original_read(path, *args, **kwargs)
    def no_open(path, *args, **kwargs):
        if path == registry:
            pytest.fail("FIFO registry should reject before open")
        return original_open(path, *args, **kwargs)
    with monkeypatch.context() as changes:
        changes.setattr(Path, "read_text", no_read)
        changes.setattr(exporter.os, "open", no_open)
        with pytest.raises(ValueError):
            exporter.snapshot(vault, ["selected"])


def test_intermediate_link_is_rejected_before_resolving_the_folder(vault, monkeypatch):
    ancestor = vault / "raw/selected-parent"
    folder = ancestor / "sub"
    folder.mkdir(parents=True)
    root = (vault / "raw").resolve()
    original_lstat, original_resolve = Path.lstat, Path.resolve
    def linked(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == ancestor:
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            values["st_mode"] = stat.S_IFLNK | 0o777
            return SimpleNamespace(**values)
        return info
    def no_resolve(path, *args, **kwargs):
        if path == folder:
            pytest.fail("Linked collection was resolved before ancestor validation")
        return original_resolve(path, *args, **kwargs)
    with monkeypatch.context() as changes:
        changes.setattr(Path, "lstat", linked)
        changes.setattr(Path, "resolve", no_resolve)
        with pytest.raises(ValueError):
            exporter.beneath(root, folder)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink scope fixture; no Windows privilege changes")
def test_real_intermediate_symlink_cannot_relabel_unselected_notes(vault):
    target = vault / "raw/unselected/sub"
    target.mkdir(parents=True)
    (target / "note.md").write_text("---\ntitle: Unselected synthetic note\n---\n", encoding="utf-8")
    (vault / "raw/selected-parent").symlink_to(target.parent, target_is_directory=True)
    (vault / ".research_hub/clusters.yaml").write_text("clusters:\n  selected:\n    name: Selected\n    obsidian_subfolder: selected-parent/sub\n", encoding="utf-8")
    with pytest.raises(ValueError):
        exporter.snapshot(vault, ["selected"])


def test_collection_binding_cannot_treat_a_regular_file_as_an_empty_folder(vault):
    (vault / "raw/not-a-folder").write_text("Synthetic file", encoding="utf-8")
    (vault / ".research_hub/clusters.yaml").write_text("clusters:\n  selected:\n    name: Selected\n    obsidian_subfolder: not-a-folder\n", encoding="utf-8")
    with pytest.raises(ValueError, match="directory"):
        exporter.snapshot(vault, ["selected"])


def test_startup_vault_alias_is_checked_before_resolving(vault, monkeypatch):
    original_metadata, original_resolve = exporter._metadata, Path.resolve
    def linked(path):
        if path == vault:
            raise ValueError("Linked path")
        return original_metadata(path)
    def no_resolve(path, *args, **kwargs):
        if path == vault:
            pytest.fail("Vault alias resolved before metadata validation")
        return original_resolve(path, *args, **kwargs)
    with monkeypatch.context() as changes:
        changes.setattr(exporter, "_metadata", linked)
        changes.setattr(Path, "resolve", no_resolve)
        with pytest.raises(ValueError):
            exporter.snapshot(vault, ["selected"])


@pytest.mark.parametrize("count", [128, 129])
def test_published_selection_respects_consumer_collection_limit(vault, tmp_path, monkeypatch, count):
    from research_hub.workspace.library_snapshot import LibrarySnapshot
    registry = {f"collection-{i}": {"name": f"Synthetic {i}"} for i in range(count)}
    for slug in registry:
        (vault / "raw" / slug).mkdir()
    import yaml
    (vault / ".research_hub/clusters.yaml").write_text(yaml.safe_dump({"clusters": registry}), encoding="utf-8")
    output = tmp_path / "snapshot.json"
    original = b"previous synthetic snapshot"
    output.write_bytes(original)
    arguments = ["library_snapshot", "--vault", str(vault), "--output", str(output)]
    for slug in registry:
        arguments += ["--collection", slug]
    monkeypatch.setattr(sys, "argv", arguments)
    if count == 128:
        assert exporter.main() == 0
        assert len(LibrarySnapshot(output).read()["collections"]) == 128
    else:
        assert exporter.main() == 1
        assert output.read_bytes() == original


def test_utf8_serialized_limit_keeps_previous_usable_snapshot(vault, tmp_path, monkeypatch):
    from research_hub.workspace.library_snapshot import LibrarySnapshot, MAX_SNAPSHOT_BYTES, projection
    previous = exporter.snapshot(vault, ["selected"])
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    output = output_dir / "snapshot.json"
    original = json.dumps(previous).encode("utf-8")
    output.write_bytes(original)
    oversized = {**previous, "notes": [{"id": f"obsidian:{i:024x}", "kind": "library-note", "data": {"origin": "obsidian", "read_only": True, "record_type": "markdown-note", "reading_level": "note-metadata", "identity_status": "unverified", "metadata_status": "available", "note_path": f"raw/selected/{i}.md", "abstract": "字" * 12000}} for i in range(500)]}
    assert len(json.dumps(oversized, ensure_ascii=False).encode("utf-8")) > MAX_SNAPSHOT_BYTES
    assert len(projection(oversized)["notes"]) == 500
    monkeypatch.setattr(exporter, "snapshot", lambda *_: oversized)
    monkeypatch.setattr(sys, "argv", ["library_snapshot", "--vault", str(vault), "--collection", "selected", "--output", str(output)])
    assert exporter.main() == 1
    assert output.read_bytes() == original
    assert LibrarySnapshot(output).read() == previous
    assert [p.name for p in output_dir.iterdir()] == ["snapshot.json"]


def test_output_ancestor_alias_rejects_before_replacing_destination(vault, tmp_path, monkeypatch):
    parent = tmp_path / "output"
    parent.mkdir()
    output = parent / "snapshot.json"
    original = b"previous synthetic snapshot"
    output.write_bytes(original)
    original_lstat = Path.lstat
    def linked(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == parent:
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            values["st_mode"] = stat.S_IFLNK | 0o777
            return SimpleNamespace(**values)
        return info
    monkeypatch.setattr(Path, "lstat", linked)
    monkeypatch.setattr(sys, "argv", ["library_snapshot", "--vault", str(vault), "--collection", "selected", "--output", str(output)])
    assert exporter.main() == 1
    assert output.read_bytes() == original


@pytest.mark.parametrize("entrypoint", ["snapshot", "cli"])
def test_changed_vault_resolution_cannot_read_a_different_vault(vault, tmp_path, monkeypatch, entrypoint):
    other = tmp_path / "other-vault"
    (other / ".research_hub").mkdir(parents=True)
    (other / "raw/selected").mkdir(parents=True)
    (other / ".research_hub/clusters.yaml").write_text("clusters:\n  selected:\n    name: Other synthetic vault\n", encoding="utf-8")
    original_resolve = Path.resolve
    def changed(path, *args, **kwargs):
        return original_resolve(other, *args, **kwargs) if path == vault else original_resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", changed)
    if entrypoint == "snapshot":
        with pytest.raises(ValueError):
            exporter.snapshot(vault, ["selected"])
    else:
        output = tmp_path / "snapshot.json"
        original = b"previous synthetic snapshot"
        output.write_bytes(original)
        monkeypatch.setattr(sys, "argv", ["library_snapshot", "--vault", str(vault), "--collection", "selected", "--output", str(output)])
        assert exporter.main() == 1
        assert output.read_bytes() == original


def test_canonical_output_containment_is_checked_before_publication(vault, tmp_path, monkeypatch):
    output = tmp_path / "different-spelling.json"
    original = b"previous synthetic snapshot"
    output.write_bytes(original)
    real_resolve = Path.resolve
    def alternate_spelling(path, *args, **kwargs):
        return vault / "inside-vault.json" if path == output else real_resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", alternate_spelling)
    monkeypatch.setattr(sys, "argv", ["library_snapshot", "--vault", str(vault), "--collection", "selected", "--output", str(output)])
    assert exporter.main() == 1
    assert output.read_bytes() == original
    assert not (vault / "inside-vault.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows short-name spelling fixture")
def test_native_short_name_output_cannot_write_inside_vault(vault, monkeypatch):
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    function = api.GetShortPathNameW
    function.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    function.restype = wintypes.DWORD
    size = function(str(vault), None, 0)
    if not size:
        pytest.skip("Volume has no existing alternate short name")
    buffer = ctypes.create_unicode_buffer(size + 1)
    assert function(str(vault), buffer, len(buffer))
    short = Path(buffer.value)
    if short == vault:
        pytest.skip("Volume returns only the original path spelling")
    output = vault / "protected.json"
    original = b"previous synthetic vault file"
    output.write_bytes(original)
    monkeypatch.setattr(sys, "argv", ["library_snapshot", "--vault", str(vault), "--collection", "selected", "--output", str(short / output.name)])
    assert exporter.main() == 1
    assert output.read_bytes() == original
