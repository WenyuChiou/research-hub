"""Read one startup-selected historical metadata file; no vault/config discovery."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import yaml

from .obsidian_validation import _UniqueLoader, _lexical, _metadata

MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_FRONTMATTER_BYTES = 64 * 1024
MAX_VAULT_NOTES = 1000
MAX_VAULT_CLUSTERS = 128
TEXT_FIELDS = {"title", "year", "record_type", "note_path", "category", "collection_id",
               "collection_name", "reading_level", "identity_status", "metadata_status",
               "note_modified_ns", "saved_reading_status", "abstract", "doi", "zotero_key",
               "locator", "frontmatter_sha256"}


def unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate snapshot field")
        result[key] = value
    return result


def projection(value):
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int or value.get("schema_version") != 1 or
            value.get("read_only") is not True or value.get("body_read") is not False):
        raise ValueError("Invalid snapshot")
    timestamp = datetime.fromisoformat(value["captured_at"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None or not isinstance(value.get("vault_label"), str):
        raise ValueError("Invalid snapshot metadata")
    collections, notes = value["collections"], value["notes"]
    if not isinstance(collections, list) or len(collections) > 128 or not isinstance(notes, list) or len(notes) > 1000:
        raise ValueError("Invalid snapshot size")
    clean_collections = []
    for item in collections:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str) or
                not isinstance(item.get("name"), str) or type(item.get("note_count")) is not int or item["note_count"] < 0):
            raise ValueError("Invalid collection")
        clean_collections.append({key: item[key] for key in ("id", "name", "note_count")})
    clean_notes = []
    seen = set()
    for note in notes:
        if (not isinstance(note, dict) or not isinstance(note.get("id"), str) or
                not re.fullmatch(r"obsidian:[a-f0-9]{24}", note["id"]) or note["id"] in seen or
                note.get("kind") != "library-note" or not isinstance(note.get("data"), dict)):
            raise ValueError("Invalid note")
        seen.add(note["id"])
        data = note["data"]
        if (data.get("origin") != "obsidian" or data.get("read_only") is not True or
                data.get("reading_level") != "note-metadata" or data.get("identity_status") != "unverified" or
                data.get("record_type", "markdown-note") != "markdown-note" or
                data.get("metadata_status") not in {"available", "unavailable"}):
            raise ValueError("Invalid note scope")
        clean = {"origin": "obsidian", "read_only": True}
        for key in TEXT_FIELDS & data.keys():
            if not isinstance(data[key], str) or len(data[key]) > 12000:
                raise ValueError("Invalid metadata")
            clean[key] = data[key]
        path = clean.get("note_path", "")
        if not path or PurePosixPath(path).is_absolute() or any(part in {".", ".."} or ":" in part or "\\" in part for part in path.split("/")):
            raise ValueError("Invalid note reference")
        for key in {"authors", "labels", "tags"} & data.keys():
            items = data[key]
            if not isinstance(items, list) or len(items) > 100 or any(not isinstance(item, str) or len(item) > 200 for item in items):
                raise ValueError("Invalid metadata terms")
            clean[key] = items
        if "note_size_bytes" in data:
            if type(data["note_size_bytes"]) is not int or data["note_size_bytes"] < 0:
                raise ValueError("Invalid note size")
            clean["note_size_bytes"] = data["note_size_bytes"]
        clean_notes.append({"id": note["id"], "kind": "library-note", "data": clean})
    return {"schema_version": 1, "read_only": True, "body_read": False,
            "captured_at": value["captured_at"], "vault_label": value["vault_label"],
            "collections": clean_collections, "notes": clean_notes}


class LibrarySnapshot:
    def __init__(self, path: str | Path | None = None):
        self.path = _lexical(path) if path is not None else None

    def read(self):
        unavailable = {"ok": False, "code": "library_snapshot_unavailable", "status": "unknown",
                       "error": "No readable startup-selected Library snapshot is available."}
        if self.path is None:
            return unavailable
        try:
            before = _metadata(self.path)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_SNAPSHOT_BYTES:
                return unavailable
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            fd = os.open(self.path, flags)
            try:
                opened = os.fstat(fd)
                identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)
                if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
                    return unavailable
                raw = bytearray()
                while len(raw) <= MAX_SNAPSHOT_BYTES:
                    part = os.read(fd, min(65536, MAX_SNAPSHOT_BYTES + 1 - len(raw)))
                    if not part:
                        break
                    raw.extend(part)
                if len(raw) != opened.st_size or identity(os.fstat(fd)) != identity(opened) or identity(_metadata(self.path)) != identity(opened):
                    return unavailable
            finally:
                os.close(fd)
            return projection(json.loads(raw, object_pairs_hook=unique_mapping))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            # Never echo selected paths, source text or raw parse errors.
            return unavailable


def _safe_open_read_bounded(path: Path, *, max_bytes: int) -> tuple[bytes, os.stat_result]:
    before = _metadata(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("Unsafe note file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)
        if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
            raise ValueError("File changed during open")
        limit = min(max_bytes, opened.st_size)
        raw = bytearray()
        while len(raw) < limit:
            chunk = os.read(fd, min(16384, limit - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        return bytes(raw), opened
    finally:
        os.close(fd)


def _extract_frontmatter_only(head_bytes: bytes) -> tuple[dict | None, str]:
    text = head_bytes.decode("utf-8", errors="replace")
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return None, ""
    end_idx = normalized.find("\n---\n", 4)
    if end_idx == -1:
        if normalized.endswith("\n---"):
            end_idx = len(normalized) - 4
        else:
            return None, ""
    fm_text = normalized[4:end_idx]
    fm_bytes = fm_text.encode("utf-8")
    digest_hex = hashlib.sha256(fm_bytes).hexdigest()
    loaded = yaml.load(fm_bytes, Loader=_UniqueLoader)
    if not isinstance(loaded, dict):
        return None, digest_hex
    return loaded, digest_hex


def _clean_terms(value: object, *, limit: int = 100) -> list[str]:
    if isinstance(value, str):
        raw_items = [part.strip() for part in re.split(r"[,;|\n]+", value) if part.strip()]
    elif isinstance(value, list):
        raw_items = []
        for item in value:
            if isinstance(item, (str, int, float)) and str(item).strip():
                raw_items.append(str(item).strip())
            elif isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if not name:
                    last = str(item.get("lastName") or item.get("family") or "").strip()
                    first = str(item.get("firstName") or item.get("given") or "").strip()
                    name = f"{last}, {first}".strip(", ") if (last or first) else ""
                if name:
                    raw_items.append(name)
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        trimmed = item.lstrip("#").strip()[:200]
        if not trimmed or trimmed.casefold() in seen:
            continue
        seen.add(trimmed.casefold())
        result.append(trimmed)
        if len(result) >= limit:
            break
    return result


def _clean_str(value: object, *, limit: int = 12000) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)[:limit]
    if isinstance(value, str):
        return value.strip()[:limit]
    return ""


def read_vault_snapshot(vault_root: str | Path | None) -> dict:
    """Build a strictly read-only YAML frontmatter projection directly from an authorized vault."""
    unavailable = {
        "ok": False,
        "code": "library_snapshot_unavailable",
        "status": "unknown",
        "error": "No readable startup-selected Library snapshot is available.",
    }
    if vault_root is None:
        return unavailable
    try:
        root = _lexical(vault_root)
        info = _metadata(root)
        if not stat.S_ISDIR(info.st_mode):
            return unavailable

        cluster_names: dict[str, str] = {}
        cluster_subfolders: dict[str, str] = {}
        active_slugs: list[str] = []
        reg_path = _lexical(root / ".research_hub" / "clusters.yaml")
        if reg_path.exists():
            raw_reg, _ = _safe_open_read_bounded(reg_path, max_bytes=2 * 1024 * 1024)
            reg_doc = yaml.load(raw_reg, Loader=_UniqueLoader)
            if isinstance(reg_doc, dict) and isinstance(reg_doc.get("clusters"), dict):
                for slug, entry in reg_doc["clusters"].items():
                    if not isinstance(slug, str) or not isinstance(entry, dict):
                        continue
                    if entry.get("status", "active") != "active":
                        continue
                    cluster_names[slug] = _clean_str(entry.get("name"), limit=200) or slug
                    sub = _clean_str(entry.get("obsidian_subfolder"), limit=200) or slug
                    cluster_subfolders[slug] = sub
                    active_slugs.append(slug)

        raw_dir = _lexical(root / "raw")
        if not active_slugs and raw_dir.exists() and stat.S_ISDIR(_metadata(raw_dir).st_mode):
            for child in sorted(raw_dir.iterdir(), key=lambda p: p.name):
                if child.name.startswith((".", "_")) or not child.is_dir():
                    continue
                try:
                    cinfo = _metadata(child)
                except (OSError, ValueError):
                    continue
                if stat.S_ISDIR(cinfo.st_mode):
                    active_slugs.append(child.name)
                    cluster_names.setdefault(child.name, child.name)
                    cluster_subfolders.setdefault(child.name, child.name)

        collections: list[dict] = []
        notes: list[dict] = []

        for slug in active_slugs[:MAX_VAULT_CLUSTERS]:
            subfolder = cluster_subfolders.get(slug, slug)
            if any(part in {".", ".."} or "/" in part or "\\" in part or ":" in part for part in (slug, subfolder)):
                continue
            cluster_dir = root / "raw" / subfolder
            if not cluster_dir.exists():
                continue
            try:
                cluster_dir_lex = _lexical(cluster_dir)
                if not stat.S_ISDIR(_metadata(cluster_dir_lex).st_mode):
                    continue
            except (OSError, ValueError):
                continue

            scan_dirs: list[tuple[Path, str]] = [(cluster_dir_lex, f"raw/{subfolder}")]
            notes_sub = cluster_dir_lex / "notes"
            if notes_sub.exists():
                try:
                    notes_sub_lex = _lexical(notes_sub)
                    if stat.S_ISDIR(_metadata(notes_sub_lex).st_mode):
                        scan_dirs.append((notes_sub_lex, f"raw/{subfolder}/notes"))
                except (OSError, ValueError):
                    pass

            cluster_note_count = 0
            seen_rel_paths: set[str] = set()
            for scan_dir, rel_prefix in scan_dirs:
                for note_file in sorted(scan_dir.iterdir(), key=lambda p: p.name):
                    if len(notes) >= MAX_VAULT_NOTES:
                        break
                    if note_file.suffix.lower() != ".md" or not note_file.is_file():
                        continue
                    rel_posix = f"{rel_prefix}/{note_file.name}"
                    if rel_posix in seen_rel_paths:
                        continue
                    seen_rel_paths.add(rel_posix)
                    try:
                        note_lex = _lexical(note_file)
                        head_bytes, opened = _safe_open_read_bounded(note_lex, max_bytes=MAX_FRONTMATTER_BYTES)
                        fm, fm_sha = _extract_frontmatter_only(head_bytes)
                    except (OSError, ValueError, yaml.YAMLError, RecursionError):
                        continue

                    note_id = f"obsidian:{hashlib.sha256(rel_posix.encode('utf-8')).hexdigest()[:24]}"
                    data: dict = {
                        "origin": "obsidian",
                        "read_only": True,
                        "reading_level": "note-metadata",
                        "identity_status": "unverified",
                        "record_type": "markdown-note",
                        "metadata_status": "available" if isinstance(fm, dict) else "unavailable",
                        "note_path": rel_posix,
                        "collection_id": slug,
                        "collection_name": cluster_names.get(slug, slug),
                        "note_modified_ns": str(opened.st_mtime_ns),
                        "note_size_bytes": int(opened.st_size),
                    }
                    if fm_sha:
                        data["frontmatter_sha256"] = fm_sha

                    if isinstance(fm, dict):
                        title = _clean_str(fm.get("title"), limit=1000) or note_file.stem
                        data["title"] = title
                        raw_year = _clean_str(fm.get("year"), limit=32)
                        year_match = re.search(r"(19|20)\d{2}", raw_year)
                        if year_match:
                            data["year"] = year_match.group(0)
                        category = _clean_str(fm.get("category") or fm.get("topic_cluster"), limit=200)
                        if category:
                            data["category"] = category
                        abstract = _clean_str(fm.get("abstract") or fm.get("summary"), limit=12000)
                        if abstract:
                            data["abstract"] = abstract
                        doi = _clean_str(fm.get("doi"), limit=300)
                        if doi:
                            data["doi"] = doi
                        zot_key = _clean_str(fm.get("zotero_key") or fm.get("zotero-key"), limit=128)
                        if zot_key:
                            data["zotero_key"] = zot_key
                        locator = _clean_str(fm.get("url") or fm.get("locator"), limit=1000)
                        if locator:
                            data["locator"] = locator
                        reading_status = _clean_str(
                            fm.get("reading_status") or fm.get("saved_reading_status") or fm.get("status"), limit=128
                        )
                        if reading_status:
                            data["saved_reading_status"] = reading_status
                        authors = _clean_terms(fm.get("authors"))
                        if authors:
                            data["authors"] = authors
                        labels = _clean_terms(fm.get("labels"))
                        if labels:
                            data["labels"] = labels
                        tags = _clean_terms(fm.get("tags"))
                        if tags:
                            data["tags"] = tags
                    else:
                        data["title"] = note_file.stem

                    notes.append({"id": note_id, "kind": "library-note", "data": data})
                    cluster_note_count += 1

            collections.append({
                "id": slug,
                "name": cluster_names.get(slug, slug),
                "note_count": cluster_note_count,
            })

        captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return projection({
            "schema_version": 1,
            "read_only": True,
            "body_read": False,
            "captured_at": captured_at,
            "vault_label": root.name or "vault",
            "collections": collections,
            "notes": notes,
        })
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, yaml.YAMLError):
        return unavailable
