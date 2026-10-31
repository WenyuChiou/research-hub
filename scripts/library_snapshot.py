"""Read selected Library frontmatter into a task-local, read-only UI snapshot.

No config discovery, note bodies, writes under the vault, remote checks or sync.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import yaml
from research_hub.clusters import ClusterRegistry
from research_hub.dashboard.source_evidence import note_source_identities

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


def beneath(root: Path, path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or path.is_symlink():
        raise ValueError("Path outside selected research scope")
    # Windows junctions/reparse points must not broaden a selected input.
    for part in [path, *path.parents]:
        if part == root:
            break
        info = part.lstat()
        if (getattr(info, "st_file_attributes", 0) & 0x400 or
                getattr(info, "st_reparse_tag", 0) or
                getattr(part, "is_junction", lambda: False)()):
            raise ValueError("Reparse point in selected input")
    return resolved


def frontmatter_only(path: Path) -> tuple[str, dict]:
    before = path.stat()
    lines = []
    total = 0
    with path.open("rb", buffering=0) as stream:
        first = stream.readline(256)
        if first.decode("utf-8-sig").strip() != "---":
            raise ValueError("No frontmatter")
        while True:
            raw = stream.readline(MAX_FRONTMATTER - total + 1)
            total += len(raw)
            if not raw or total > MAX_FRONTMATTER:
                raise ValueError("Unterminated or oversized frontmatter")
            line = raw.decode("utf-8")
            if line.strip() in {"---", "..."}:
                break
            lines.append(line)
    after = path.stat()
    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
        raise ValueError("Note changed during metadata read")
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


def snapshot(vault: Path, selections: list[str]) -> dict:
    vault = vault.resolve(strict=True)
    raw = beneath(vault, vault / "raw")
    registry_file = beneath(vault, vault / ".research_hub" / "clusters.yaml")
    registry = {item.slug: item for item in ClusterRegistry(registry_file).list()}
    notes = []
    collections = []
    for slug in dict.fromkeys(selections):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", slug):
            raise ValueError("Invalid selected collection")
        cluster = registry.get(slug)
        if cluster is None or cluster.status != "active":
            raise ValueError("Selected collection is not active in the registry")
        folder = beneath(raw, raw / slug)
        paths = sorted(folder.glob("*.md"))
        if len(notes) + len(paths) > MAX_NOTES:
            raise ValueError("Selected Library exceeds snapshot item limit")
        collections.append({"id": slug, "name": cluster.name, "note_count": len(paths)})
        for path in paths:
            beneath(folder, path)
            relative = path.relative_to(vault).as_posix()
            data = {
                "title": path.stem, "origin": "obsidian", "read_only": True,
                "record_type": "markdown-note", "note_path": relative,
                "category": cluster.name, "collection_id": slug,
                "collection_name": cluster.name, "reading_level": "note-metadata",
                "identity_status": "unverified", "metadata_status": "unavailable",
                "note_modified_ns": str(path.stat().st_mtime_ns),
                "note_size_bytes": path.stat().st_size,
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
            except (ValueError, UnicodeError, yaml.YAMLError):
                # A note remains a traceable file row; failure never means empty/full-text content.
                pass
            notes.append({"id": "obsidian:" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24], "kind": "library-note", "data": data})
    return {"schema_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
            "vault_label": vault.name, "read_only": True, "body_read": False,
            "collections": collections, "notes": notes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--collection", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    vault = args.vault.resolve(strict=True)
    output = args.output.resolve()
    if output.is_relative_to(vault):
        raise ValueError("Snapshot output must stay outside the vault")
    result = snapshot(vault, args.collection)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"collections": len(result["collections"]), "markdown_notes": len(result["notes"]),
                      "available_metadata": sum(n["data"]["metadata_status"] == "available" for n in result["notes"]),
                      "body_read": False, "vault_written": False}))


if __name__ == "__main__":
    main()
