"""Explicitly scoped, metadata-only Obsidian validation. No config discovery."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import stat

import yaml

MAX_REGISTRY_BYTES = 128 * 1024
MAX_COLLECTIONS = 128


def _lexical(value: str | Path) -> Path:
    text = str(value)
    if not text or text != text.strip() or "\x00" in text or text.startswith(("\\\\", "//")):
        raise ValueError("An explicit local absolute path is required")
    path = Path(text)
    if not path.is_absolute() or path == Path(path.anchor):
        raise ValueError("An explicit vault directory is required")
    parts = re.split(r"[\\/]", text[len(path.anchor):])
    if any(part in {".", ".."} or ":" in part or part.endswith((".", " ")) for part in parts if part):
        raise ValueError("Ambiguous path")
    return Path(os.path.normcase(os.path.normpath(text)))


def _metadata(path: Path):
    # Check every ancestor before resolving anything. Never follow aliases.
    if os.name == "nt":
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) not in {2, 3, 6}:
            raise ValueError("Only local drives are supported")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        info = current.lstat()
        if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
                or getattr(info, "st_reparse_tag", 0)):
            raise ValueError("Linked paths are not supported")
        if current != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError("Invalid path ancestor")
    return info


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError("Invalid registry mapping")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _registry(path: Path) -> dict:
    before = _metadata(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_REGISTRY_BYTES:
        raise ValueError("Invalid registry file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or
                (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) !=
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)):
            raise ValueError("Registry changed during open")
        _metadata(path)
        raw = bytearray()
        while len(raw) <= MAX_REGISTRY_BYTES:
            chunk = os.read(fd, MAX_REGISTRY_BYTES + 1 - len(raw))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        if (len(raw) > MAX_REGISTRY_BYTES or len(raw) != opened.st_size or
                (after.st_size, after.st_mtime_ns, after.st_nlink) !=
                (opened.st_size, opened.st_mtime_ns, 1)):
            raise ValueError("Registry changed during read")
    finally:
        os.close(fd)
    payload = yaml.load(bytes(raw), Loader=_UniqueLoader)
    if not isinstance(payload, dict) or str(payload.get("schema_version", "1.0")) != "1.0":
        raise ValueError("Unsupported registry")
    return payload


class ObsidianValidation:
    def __init__(self, authorized_vault: str | Path | None = None):
        self.scope = _lexical(authorized_vault) if authorized_vault is not None else None

    def assert_storage_outside(self, workspace_root: str | Path) -> None:
        if self.scope is None:
            return
        try:
            _metadata(self.scope)
        except FileNotFoundError:
            # Existing ancestors have already been checked; no directory is created.
            pass
        # Resolve only the trusted startup paths, after rejecting scope aliases.
        vault_identity = self.scope.resolve()
        workspace_identity = Path(workspace_root).expanduser().resolve()
        if workspace_identity.is_relative_to(vault_identity):
            raise ValueError("Workspace storage must be outside the read-only Obsidian vault")

    def capability(self) -> dict:
        result = {"status": "available" if self.scope else "unavailable", "read_only": True,
                  "scope": "startup_selected_exact_vault", "version": 1}
        if self.scope:
            result["authorized_vault"] = str(self.scope)
        return result

    def validate(self, requested: object) -> dict:
        # Out-of-scope requests stop before any filesystem operation.
        if self.scope is None:
            return {"ok": False, "code": "vault_validation_unavailable", "error": "No startup-authorized vault is configured."}
        try:
            selected = _lexical(requested) if isinstance(requested, str) and len(requested) <= 4096 else None
        except ValueError:
            selected = None
        if selected != self.scope:
            return {"ok": False, "code": "vault_scope_denied", "error": "Only the startup-authorized vault may be validated."}
        result = {"ok": True, "status": "unknown", "read_only": True, "saved": False,
                  "note_bodies_read": False, "observed_at": datetime.now(timezone.utc).isoformat(),
                  "root_readable": False, "obsidian_marker": False, "library_layout": False}
        # Use only the saved trusted scope, never the request's path spelling.
        root = self.scope
        try:
            info = _metadata(root)
            if not stat.S_ISDIR(info.st_mode):
                return {**result, "status": "not_directory"}
            if not os.access(root, os.R_OK | os.X_OK):
                return {**result, "status": "unreadable"}
            result["root_readable"] = True
            try:
                result["obsidian_marker"] = stat.S_ISDIR(_metadata(root / ".obsidian").st_mode)
            except FileNotFoundError:
                pass
            try:
                raw_exists = stat.S_ISDIR(_metadata(root / "raw").st_mode)
            except FileNotFoundError:
                raw_exists = False
            try:
                payload = _registry(root / ".research_hub" / "clusters.yaml")
            except FileNotFoundError:
                return {**result, "status": "registry_missing" if result["obsidian_marker"] else "not_vault"}
            except (ValueError, yaml.YAMLError, UnicodeError, RecursionError):
                return {**result, "status": "invalid_registry"}
            clusters = payload.get("clusters")
            if isinstance(clusters, list):
                entries = [(item.get("slug"), item) for item in clusters if isinstance(item, dict)]
                if len(entries) != len(clusters):
                    return {**result, "status": "invalid_registry"}
            elif isinstance(clusters, dict):
                entries = list(clusters.items())
            else:
                return {**result, "status": "invalid_registry"}
            if not raw_exists or len(entries) > MAX_COLLECTIONS:
                return {**result, "status": "registry_mismatch"}
            seen = set()
            active = 0
            for slug, data in entries:
                if (not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", slug)
                        or slug in seen or not isinstance(data, dict)):
                    return {**result, "status": "invalid_registry"}
                seen.add(slug)
                if data.get("obsidian_subfolder", "") not in {"", slug}:
                    return {**result, "status": "registry_mismatch"}
                if data.get("status", "active") != "active":
                    continue
                try:
                    collection_exists = stat.S_ISDIR(_metadata(root / "raw" / slug).st_mode)
                except FileNotFoundError:
                    collection_exists = False
                if not collection_exists:
                    return {**result, "status": "registry_mismatch"}
                active += 1
            return {**result, "status": "valid", "library_layout": True, "collection_count": active}
        except FileNotFoundError:
            return {**result, "status": "not_found"}
        except PermissionError:
            return {**result, "status": "unreadable"}
        except (ValueError, OSError, TypeError, RecursionError):
            return {**result, "status": "unsafe_path"}
