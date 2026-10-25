"""Bounded, local text copies. No fetching, rendering, task creation or execution.

Publication is deliberately unavailable without directory-relative no-follow
stdlib primitives (notably Windows). Existing readers/registration are unchanged.
SQLite commits the linked pair; a crash before commit may leave an orphan copy.
The exact request can reuse it, but no rollback/cleanup deletes a final copy.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from .core import WorkspaceError, digest, encoded, now, safe_path
from .research_draft import MAX_SOURCE_BYTES, read_selected_text
from .tasks import TaskService


def publication_supported() -> bool:
    return (os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")
            and all(fn in os.supports_dir_fd for fn in (os.open, os.mkdir, os.link, os.stat, os.unlink))
            and os.stat in os.supports_follow_symlinks and os.link in os.supports_follow_symlinks)


def capability(workspace) -> dict:
    supported = publication_supported()
    return {"version": 1, "status": "available" if supported else "unavailable",
            "workspace_instance_id": workspace.preparation_namespace(),
            "max_source_bytes": MAX_SOURCE_BYTES, "formats": ["txt", "md"],
            "message": ("Local bounded text copies only; no PDF reading or model execution."
                        if supported else "Safe text publication primitives are unavailable on this platform. Windows text intake is not supported by this implementation.")}


def _supported() -> None:
    if not publication_supported():
        raise WorkspaceError("Safe text publication is unavailable on this platform; Windows intake is not implemented", "unsupported_capability")


@contextmanager
def _directory(root: Path, parts: tuple[str, ...], *, create: bool):
    """Pin every directory without following symlinks, including root ancestors."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root.anchor, flags)
    try:
        for component in root.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        for component in parts:
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            child = os.open(component, flags, dir_fd=descriptor)
            info = os.fstat(child)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                os.close(child)
                raise WorkspaceError("Text-copy directory is not privately owned; existing permissions were preserved", "unsafe_path")
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _read_file(directory: int, name: str) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        # A crash after link publication but before temporary-name cleanup may
        # retain two links to our complete inode. Never write/delete either here;
        # only byte-identical final content may be reused by the same intent.
        if not stat.S_ISREG(info.st_mode):
            raise WorkspaceError("Text-copy target is not a regular file", "unsafe_path")
        return stream.read(MAX_SOURCE_BYTES + 1)


def _verify_location(workspace, parts, directory):
    with _directory(workspace.root, parts, create=False) as current:
        expected, actual = os.fstat(directory), os.fstat(current)
        if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
            raise WorkspaceError("Text-copy directory changed during publication", "unsafe_path")


def _publish_copy(workspace, relative: str, raw: bytes) -> None:
    """Complete, fsynced, no-replace publication; identical orphan reuse is safe.

Do not remove final copies on DB failure: commit uncertainty and external edits
make retaining bounded evidence safer than a compensating destructive action.
Only this invocation's temporary name/inode is cleaned up on ordinary exit.
"""
    safe_path(workspace.root, relative)
    parts = Path(relative).parts
    with _directory(workspace.root, parts[:-1], create=True) as directory:
        name = parts[-1]
        try:
            existing = _read_file(directory, name)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != raw:
                raise WorkspaceError("Text-copy target already contains different bytes; nothing was overwritten", "file_conflict")
            _verify_location(workspace, parts[:-1], directory)
            return
        temporary = ".intake-" + uuid.uuid4().hex + ".tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        identity = os.fstat(descriptor)
        linked = False
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                linked = True
            except FileExistsError:
                if _read_file(directory, name) != raw:
                    raise WorkspaceError("Text-copy target changed; nothing was overwritten", "file_conflict")
            os.fsync(directory)
        finally:
            try:
                current = os.stat(temporary, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                    os.unlink(temporary, dir_fd=directory)
                    os.fsync(directory)
            except FileNotFoundError:
                pass
        # A no-follow link can itself link a substituted symlink inode. Verify
        # publication, not merely the temporary bytes written before the link.
        final = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if linked and (final.st_dev, final.st_ino) != (identity.st_dev, identity.st_ino):
            raise WorkspaceError("Text-copy publication identity changed; no source was saved", "unsafe_path")
        if _read_file(directory, name) != raw:
            raise WorkspaceError("Text-copy bytes changed before registration", "file_conflict")
        _verify_location(workspace, parts[:-1], directory)


class TextIntake:
    _blob_storage = False

    def _check_capability(self):
        _supported()

    def __init__(self, workspace):
        self.workspace = workspace

    def _identity(self, project_id, workspace_instance_id, key):
        TaskService._request_uuid(workspace_instance_id)
        TaskService._request_uuid(key)
        if workspace_instance_id != self.workspace.preparation_namespace():
            raise WorkspaceError("Text intake belongs to a different workspace instance", "workspace_mismatch")
        self.workspace.project(project_id)
        namespace = uuid.UUID(workspace_instance_id)
        scope = {"project": project_id, "key": key, "version": 1}
        return (uuid.uuid5(namespace, encoded({**scope, "kind": "source-text"})).hex,
                uuid.uuid5(namespace, encoded({**scope, "kind": "source-text-artifact"})).hex)

    def _lookup(self, db, project_id, record_id, artifact_id, key):
        row = db.execute("SELECT project,kind,body FROM records WHERE id=?", (record_id,)).fetchone()
        if row is None:
            if db.execute("SELECT 1 FROM artifacts WHERE id=?", (artifact_id,)).fetchone():
                raise WorkspaceError("Text-intake artifact remains but its source linkage is unavailable", "ledger_unavailable")
            from ._source_storage import has_table
            if has_table(db) and db.execute("SELECT 1 FROM source_text_blobs WHERE artifact_id=?", (artifact_id,)).fetchone():
                raise WorkspaceError("Saved-text bytes remain without source linkage", "ledger_unavailable")
            return None
        data = json.loads(row[2])
        if not isinstance(data, dict):
            raise WorkspaceError("Text-intake source record is malformed", "ledger_unavailable")
        intake = data.get("intake", {})
        if (row[0] != project_id or row[1] != "source" or not isinstance(intake, dict)
                or intake.get("version") != 1 or intake.get("key") != key or intake.get("artifact_id") != artifact_id):
            raise WorkspaceError("Text-intake source identity is inconsistent", "ledger_unavailable")
        stored = db.execute("SELECT project,body FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if stored is None or stored[0] != project_id:
            raise WorkspaceError("Text-intake artifact linkage is unavailable", "ledger_unavailable")
        artifact = json.loads(stored[1])
        payload_hash = intake.get("payload_digest")
        source_format = intake.get("format")
        if (not isinstance(payload_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", payload_hash)
                or source_format not in ("md", "txt") or not isinstance(artifact, dict)
                or ("storage" not in artifact and artifact.get("path") != f"hub-sources/{project_id}/{record_id}/{payload_hash}.{source_format}")
                or artifact.get("source_record_id") != record_id or artifact.get("id") != artifact_id
                or artifact.get("project_id") != project_id or artifact.get("origin") != "hub-text-intake"
                or artifact.get("role") != "evidence" or artifact.get("sha256") != intake.get("sha256")):
            raise WorkspaceError("Text-intake artifact linkage is inconsistent", "ledger_unavailable")
        if "storage" in artifact:
            from ._source_storage import row as storage_row
            storage_row(db, artifact)
        return {"id": record_id, "kind": "source", "data": data}, artifact

    def _result(self, pair, key, **state):
        record, artifact = pair
        preview = None
        try:
            preview = read_selected_text(self.workspace, artifact["project_id"], artifact["id"])
            preview_status = "available"
        except WorkspaceError as error:
            preview_status = "stale" if error.code == "stale_input" else "unavailable"
        except (OSError, ValueError, TypeError, KeyError):
            preview_status = "unavailable"
        return {"ok": True, "intake": {"version": 1, "key": key, **state}, "record": record,
                "artifact": {**artifact, "current": preview is not None}, "preview": preview,
                "preview_status": preview_status}

    def lookup(self, project_id: str, *, workspace_instance_id, key):
        record_id, artifact_id = self._identity(project_id, workspace_instance_id, key)
        with self.workspace.db() as db:
            pair = self._lookup(db, project_id, record_id, artifact_id, key)
        if pair is None:
            return {"ok": True, "intake": {"version": 1, "key": key, "state": "not_observed"}}
        return self._result(pair, key, state="found")

    def save(self, project_id: str, *, intake_request, title, reading_scope, input_kind,
             format, content_base64, locator=""):
        self._check_capability()
        if (not isinstance(intake_request, dict) or set(intake_request) != {"version", "workspace_instance_id", "key"}
                or type(intake_request["version"]) is not int or intake_request["version"] != 1):
            raise WorkspaceError("Unsupported text-intake identity envelope")
        key = intake_request["key"]
        record_id, artifact_id = self._identity(project_id, intake_request["workspace_instance_id"], key)
        if not isinstance(title, str) or not title.strip() or len(title) > 2000 or not isinstance(locator, str) or len(locator) > 2000:
            raise WorkspaceError("Text intake requires a title and optional locator of at most 2000 characters")
        if reading_scope not in ("abstract", "unknown") or input_kind not in ("paste", "file") or format not in ("txt", "md") or (input_kind == "paste" and format != "txt"):
            raise WorkspaceError("Unsupported text-intake scope or format", "unsupported_source")
        if not isinstance(content_base64, str) or not 0 < len(content_base64) <= 53336:
            raise WorkspaceError("Text intake requires at most 40000 UTF-8 bytes", "context_limit")
        try:
            raw = base64.b64decode(content_base64, validate=True)
            text = raw.decode("utf-8")
            if base64.b64encode(raw).decode("ascii") != content_base64:
                raise ValueError("Noncanonical encoding")
        except (UnicodeError, binascii.Error, ValueError) as error:
            raise WorkspaceError("Text intake requires strict UTF-8 and canonical base64", "invalid_source") from error
        if not 0 < len(raw) <= MAX_SOURCE_BYTES:
            raise WorkspaceError("Text intake requires at most 40000 UTF-8 bytes", "context_limit")
        if not text.lstrip("\ufeff").strip() or "\x00" in text:
            raise WorkspaceError("Text intake requires nonempty text without NUL bytes", "invalid_source")
        title, locator = title.strip(), locator.strip()
        # Metadata must also be valid UTF-8, not a JSON unpaired-surrogate escape.
        try:
            title.encode("utf-8")
            locator.encode("utf-8")
        except UnicodeError as error:
            raise WorkspaceError("Text-intake metadata must be valid Unicode", "invalid_source") from error
        sha256 = hashlib.sha256(raw).hexdigest()
        payload_hash = digest({"version": 1, "project": project_id, "title": title, "locator": locator,
                               "reading_scope": reading_scope, "input_kind": input_kind, "format": format, "sha256": sha256})
        try:
            with self.workspace.db(write=True) as db:
                if self._blob_storage:
                    from ._source_storage import initialize
                    initialize(db)
                pair = self._lookup(db, project_id, record_id, artifact_id, key)
                if pair:
                    if pair[0]["data"]["intake"].get("payload_digest") != payload_hash:
                        raise WorkspaceError("Text-intake key already belongs to different input", "request_key_conflict")
                    disposition = "existing"
                else:
                    relative = f"hub-sources/{project_id}/{record_id}/{payload_hash}.{format}"
                    if not self._blob_storage:
                        _publish_copy(self.workspace, relative, raw)
                    timestamp = now()
                    artifact = {"id": artifact_id, "project_id": project_id, "path": relative, "role": "evidence",
                                "sha256": sha256, "registered_at": timestamp, "source_record_id": record_id,
                                "origin": "hub-text-intake"}
                    data = {"title": title, "locator": locator or f"hub-source:{record_id}",
                            "locator_kind": "provided" if locator else "local-copy", "identity_status": "unverified",
                            "publication_version": "unknown", "human_acceptance": "pending", "reading_scope": reading_scope,
                            "scope_basis": "operator-declared, not independently verified", "recorded_at": timestamp,
                            "intake": {"version": 1, "key": key, "payload_digest": payload_hash, "artifact_id": artifact_id,
                                       "sha256": sha256, "input_kind": input_kind, "format": format}}
                    if self._blob_storage:
                        artifact.pop("path")
                        artifact.update(storage={"kind": "workspace_blob", "version": 1, "blob_id": artifact_id},
                                        format=format, byte_length=len(raw))
                    db.execute("INSERT INTO artifacts VALUES (?,?,?)", (artifact_id, project_id, encoded(artifact)))
                    db.execute("INSERT INTO records VALUES (?,?,?,?)", (record_id, project_id, "source", encoded(data)))
                    if self._blob_storage:
                        db.execute("INSERT INTO source_text_blobs VALUES (?,?,?,?,?,?,?,?)",
                                   (artifact_id, project_id, record_id, 1, format, sha256, len(raw), raw))
                    pair = {"id": record_id, "kind": "source", "data": data}, artifact
                    disposition = "created"
        except OSError as error:
            raise WorkspaceError("Text-copy storage is unavailable; no overwrite or cleanup was attempted on existing evidence. An interrupted copy may remain.", "storage_unavailable") from error
        return self._result(pair, key, disposition=disposition)
