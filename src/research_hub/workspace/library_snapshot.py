"""Read one startup-selected historical metadata file; no vault/config discovery."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from .obsidian_validation import _lexical, _metadata

MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
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
