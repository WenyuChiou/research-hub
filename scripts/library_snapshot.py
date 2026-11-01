"""Read selected Library frontmatter into a task-local, read-only UI snapshot.

No config discovery, note bodies, writes under the vault, remote checks or sync.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

import yaml
from research_hub.clusters import Cluster
from research_hub.dashboard.source_evidence import note_source_identities
from research_hub.workspace.library_snapshot import MAX_SNAPSHOT_BYTES, projection
from research_hub.workspace.obsidian_validation import _lexical, _metadata, _registry

MAX_FRONTMATTER = 128 * 1024
MAX_NOTES = 1000


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError("Invalid or duplicate frontmatter field")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def beneath(root: Path, path: Path, *, directory=False) -> Path:
    path = path.absolute()
    try:
        before = _metadata(path)
        resolved = path.resolve(strict=True)
        after, target = _metadata(path), _metadata(resolved)
    except ValueError:
        raise ValueError("Reparse point or linked path in selected input") from None
    identity = lambda info: (info.st_dev, info.st_ino, info.st_mode)
    if (not resolved.is_relative_to(root) or identity(before) != identity(after)
            or identity(before) != identity(target)):
        raise ValueError("Path outside or changed within selected research scope")
    if directory and not stat.S_ISDIR(before.st_mode):
        raise ValueError("Selected collection must bind a directory")
    return resolved


def canonical_vault(path: Path) -> Path:
    selected = _lexical(path.absolute())
    return beneath(Path(selected.anchor), selected, directory=True)


def output_location(path: Path, vault: Path) -> Path:
    # Preserve the same path spelling the startup reader will validate. Resolving
    # aliases here would publish success for a path that reader must reject.
    selected = _lexical(path.absolute())
    if selected.is_relative_to(vault):
        raise ValueError("Snapshot output must stay outside the vault")
    try:
        existing = _metadata(selected)
    except FileNotFoundError:
        existing = None
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise ValueError("Snapshot output must be a regular file")
    canonical = selected.resolve()
    # Windows short names are physical aliases without reparse attributes.
    # Check canonical containment too, while retaining the reader-valid spelling.
    if canonical.is_relative_to(vault):
        raise ValueError("Snapshot output must stay outside the vault")
    try:
        _metadata(selected)
    except FileNotFoundError:
        pass
    return selected


class UnsafeNoteError(ValueError):
    """An input cannot be read within the selected note boundary."""


def note_info(path: Path):
    try:
        info = _metadata(path)
    except ValueError:
        raise UnsafeNoteError("Unsupported selected note input") from None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise UnsafeNoteError("Selected notes must be regular files without hard links")
    return info


def note_identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink


def frontmatter_only(path: Path) -> tuple[str, dict]:
    path = path.absolute()
    before = note_info(path)
    lines = []
    total = 0
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or
                note_identity(before) != note_identity(opened) or
                note_identity(note_info(path)) != note_identity(opened)):
            raise UnsafeNoteError("Note changed before metadata read")
        with os.fdopen(descriptor, "rb", buffering=0, closefd=False) as stream:
            first = stream.readline(256)
            if first.decode("utf-8-sig").rstrip("\r\n \t") != "---":
                raise ValueError("No frontmatter")
            while True:
                raw = stream.readline(MAX_FRONTMATTER - total + 1)
                total += len(raw)
                if not raw or total > MAX_FRONTMATTER:
                    raise ValueError("Unterminated or oversized frontmatter")
                line = raw.decode("utf-8")
                if line.rstrip("\r\n \t") in {"---", "..."}:
                    break
                lines.append(line)
        if (note_identity(os.fstat(descriptor)) != note_identity(opened) or
                note_identity(note_info(path)) != note_identity(opened)):
            raise UnsafeNoteError("Note changed during metadata read")
    finally:
        os.close(descriptor)
    text = "".join(lines)
    metadata = yaml.load(text, Loader=UniqueLoader) or {}
    if not isinstance(metadata, dict):
        raise ValueError("Frontmatter is not a mapping")
    return text, metadata


def scalar(value, limit=12000):
    return str(value)[:limit] if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def terms(value):
    if isinstance(value, list):
        return [scalar(item, 200) for item in value[:100] if scalar(item, 200)]
    return [part.strip()[:200] for part in value.split(";")[:100] if part.strip()] if isinstance(value, str) else []


def selected_registry(path: Path) -> dict[str, Cluster]:
    # Reuse the bounded, nonblocking, descriptor-validated reader. Construct only
    # the fields this read-only export consumes; never reopen through a writer.
    raw = _registry(path).get("clusters") or {}
    if isinstance(raw, list):
        entries = [(str(item.get("slug", "") or "").strip().lower(), item)
                   for item in raw if isinstance(item, dict)]
        if len(entries) != len(raw):
            raise ValueError("Invalid registry collection")
    elif isinstance(raw, dict):
        entries = list(raw.items())
    else:
        raise ValueError("Invalid registry collections")
    result = {}
    for slug, item in entries:
        if not isinstance(slug, str) or not slug or slug in result or not isinstance(item, dict):
            raise ValueError("Invalid or ambiguous registry collection")
        result[slug] = Cluster(slug=slug, name=item["name"],
                               status=item.get("status", "active"),
                               obsidian_subfolder=item.get("obsidian_subfolder", ""))
    return result


def snapshot(vault: Path, selections: list[str]) -> dict:
    vault = canonical_vault(vault)
    raw = beneath(vault, vault / "raw", directory=True)
    registry_file = beneath(vault, vault / ".research_hub" / "clusters.yaml")
    registry = selected_registry(registry_file)
    notes = []
    collections = []
    selected_folders = set()
    for slug in dict.fromkeys(selections):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", slug):
            raise ValueError("Invalid selected collection")
        cluster = registry.get(slug)
        if cluster is None or cluster.status != "active":
            raise ValueError("Selected collection is not active in the registry")
        folder = beneath(raw, raw / (cluster.obsidian_subfolder or cluster.slug), directory=True)
        if folder == raw:
            raise ValueError("Selected collection must bind a folder under raw")
        if folder in selected_folders:
            raise ValueError("Selected collections bind the same folder; select one unambiguous collection")
        selected_folders.add(folder)
        paths = sorted(folder.glob("*.md"))
        if len(notes) + len(paths) > MAX_NOTES:
            raise ValueError("Selected Library exceeds snapshot item limit")
        collections.append({"id": slug, "name": cluster.name, "note_count": len(paths)})
        for path in paths:
            beneath(folder, path)
            before_note = note_info(path)
            relative = path.relative_to(vault).as_posix()
            data = {
                "title": path.stem, "origin": "obsidian", "read_only": True,
                "record_type": "markdown-note", "note_path": relative,
                "category": cluster.name, "collection_id": slug,
                "collection_name": cluster.name, "reading_level": "note-metadata",
                "identity_status": "unverified", "metadata_status": "unavailable",
                "note_modified_ns": str(before_note.st_mtime_ns),
                "note_size_bytes": before_note.st_size,
            }
            try:
                fm, meta = frontmatter_only(path)
                identity = note_source_identities(fm)
                data.update({
                    "title": scalar(meta.get("title"), 1000) or path.stem,
                    "year": scalar(meta.get("year"), 20),
                    "authors": terms(meta.get("authors")), "labels": terms(meta.get("labels")),
                    "tags": terms(meta.get("tags")), "saved_reading_status": scalar(meta.get("status"), 100),
                    "abstract": scalar(meta.get("abstract")), "doi": identity.get("doi", ""),
                    "zotero_key": identity.get("zotero-key", ""),
                    "locator": scalar(meta.get("url") or meta.get("source_url"), 4000),
                    "frontmatter_sha256": hashlib.sha256(fm.encode("utf-8")).hexdigest(),
                    "metadata_status": "available",
                })
                if not data["locator"] and data["doi"]:
                    data["locator"] = "https://doi.org/" + str(data["doi"])
            except UnsafeNoteError:
                raise
            except (ValueError, UnicodeError, yaml.YAMLError):
                # A note remains a traceable file row; failure never means empty/full-text content.
                pass
            if note_identity(before_note) != note_identity(note_info(path)):
                raise UnsafeNoteError("Note changed during export")
            notes.append({"id": "obsidian:" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24], "kind": "library-note", "data": data})
    return {"schema_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
            "vault_label": vault.name, "read_only": True, "body_read": False,
            "collections": collections, "notes": notes}


def export_selected(args):
    vault = canonical_vault(args.vault)
    output = output_location(args.output, vault)
    result = snapshot(vault, args.collection)
    projection(result)  # Enforce the actual App consumer contract before publish.
    output.parent.mkdir(parents=True, exist_ok=True)
    _metadata(output.parent)
    # Never truncate an existing inode: it may be hardlinked to a vault note.
    descriptor, temporary = tempfile.mkstemp(prefix=".library-snapshot-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.flush()
            if os.fstat(stream.fileno()).st_size > MAX_SNAPSHOT_BYTES:
                raise ValueError("Snapshot exceeds the workspace byte limit")
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"collections": len(result["collections"]), "markdown_notes": len(result["notes"]),
            "available_metadata": sum(n["data"]["metadata_status"] == "available" for n in result["notes"]),
            "body_read": False, "vault_written": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--collection", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = export_selected(args)
    except Exception:
        # A CLI privacy boundary: never render parser source lines, paths or the
        # original exception, including registry data outside selected collections.
        print("Library export failed. Check the selected vault, registry and output destination locally.", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
