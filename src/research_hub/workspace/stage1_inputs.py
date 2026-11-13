"""Prepare a private, source-bound input bundle from explicitly selected tasks.

This is not a native Core handoff, Stage 1 completion, or Stage 2 admission.
Inputs are read-only; no source discovery, model execution, or acceptance occurs.
See export() and the bundle guide for output-platform and path-race limitations.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import zipfile

from .batch_audit import _ReadOnlyWorkspace, _json, audit_entry, validate_manifest
from .core import WorkspaceError, safe_path
from .task_summary import selection

CORE_REQUIREMENTS = (
    "original_core_manifest_and_trusted_hash",
    "native_stage1_handoff_and_trusted_hash",
    "same_run_confirmed_research_brief",
    "original_claim_history_screening_and_coverage",
    "same_version_relevance_and_identity_reviews",
)

# Capture the host capability before tests or callers wrap os.open. The legacy
# path on other non-Windows hosts is unchanged; it has no parent-race guard.
_WINDOWS_EXPORT_SUPPORTED = os.name == "nt"
_DIRECTORY_EXPORT_SUPPORTED = (
    os.name == "posix" and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY") and os.open in os.supports_dir_fd
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _capture(entry, audited):
    """Revalidate and retain only the selected abstract and resolved draft."""
    workspace = _ReadOnlyWorkspace(entry["workspace_root"])
    with workspace.db() as db:
        _, provenance, _ = selection(workspace, db, entry["project_id"],
                                     entry["source_record_id"], entry["task_id"])
        if any(provenance[key] != audited[key] for key in ("input_hash", "action_hash", "draft_sha256")):
            raise WorkspaceError("Task changed during preparation", "stale_input")
        saved = db.execute("SELECT body FROM tasks WHERE project=? AND id=?",
                           (entry["project_id"], entry["task_id"])).fetchone()
        task = _json(saved[0])
        pack = task["request"]["research_draft"]["source_pack"]
        source = pack["text"].encode("utf-8")
        if (pack["source_sha256"] != entry["expected_source_sha256"]
                or _sha(source) != entry["expected_selected_sha256"]):
            raise WorkspaceError("Selected source changed", "stale_input")
        item = next(row for row in task["result"]["artifacts"]
                    if row["path"].endswith("/draft-response.json"))
        path = safe_path(workspace.root, item["path"], exists=True)
        with path.open("rb") as stream:
            draft = stream.read(200_001)
        if len(draft) > 200_000 or _sha(draft) != item["sha256"]:
            raise WorkspaceError("Draft changed during preparation", "stale_input")
        # All source extras, instructions, raw provider output and private root
        # paths are not added. Selected metadata itself may still be private.
        # These are observations, not approvals.
        metadata = {key: pack[key] for key in (
            "source_sha256", "start", "end", "text_sha256", "source", "scope", "scope_basis")}
    workspace.unchanged()
    return provenance, metadata, source, draft


def prepare(value):
    """Return a snapshot manifest and selected bytes; never mutate a workspace.

    Each source is verified independently. This is not an atomic snapshot of
    multiple running projects and does not admit an external Core consumer.
    """
    entries = validate_manifest(value)
    rows, files = [], {}
    for entry in entries:
        audited = audit_entry(entry)
        row = {"article_id": entry["article_id"], "status": audited["status"],
               "diagnostic": audited["diagnostic"], "files": [],
               "human_acceptance": "pending" if audited["status"] == "binding_pass" else "unknown",
               "scientific_acceptance": "not_assessed", "provider_execution": "not_verified"}
        if "declared_status" in entry:
            row.update(declared_source_status=entry["declared_status"], reason_codes=list(entry["reason_codes"]))
        if audited["status"] == "binding_pass":
            try:
                provenance, metadata, source, draft = _capture(entry, audited)
            except (WorkspaceError, OSError, sqlite3.Error, ValueError, KeyError,
                    TypeError, AttributeError, StopIteration, RecursionError):
                row.update(status="blocked", diagnostic="changed_or_unavailable_during_capture",
                           human_acceptance="unknown")
            else:
                row.update(status="prepared", diagnostic="verified_selected_abstract_snapshot",
                           provenance=provenance, source_selection=metadata,
                           recorded_execution_mode=audited["recorded_execution_mode"],
                           source_bound_statements=audited["source_bound_statements"])
                for name, raw in (("selected-source.txt", source), ("draft-response.json", draft)):
                    relative = entry["article_id"] + "/" + name
                    files[relative] = raw
                    row["files"].append({"path": relative, "sha256": _sha(raw), "bytes": len(raw)})
        rows.append(row)
    return ({"kind": "ResearchHubStage1InputBundle", "version": 1,
             "scope": "explicit_existing_selected_abstract_tasks",
             "native_core_handoff": False, "core_admission": "not_assessed",
             "stage1_completion": "not_assessed", "stage2_execution_authorized": False,
             "scientific_acceptance": "not_assessed",
             "requires_separate_core_evidence": list(CORE_REQUIREMENTS),
             "counts": {state: sum(row["status"] == state for row in rows)
                        for state in ("prepared", "unprepared", "missing", "blocked")},
             "entries": rows}, files)


@contextmanager
def _stream_from_descriptor(descriptor):
    """Transfer ownership to a stream, closing the descriptor if transfer fails."""
    try:
        stream = os.fdopen(descriptor, "wb")
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
        yield stream


@contextmanager
def _destination_stream(destination, *, workspace_roots=()):
    """Create under a no-follow, pinned parent where the host supports it.

    This stops symlink redirection, not relocation of a pinned real directory.
    Windows uses pinned native handles, without a path-based fallback.
    """
    if _WINDOWS_EXPORT_SUPPORTED:
        from ._windows_export import destination_stream
        with destination_stream(destination, workspace_roots=workspace_roots) as stream:
            yield stream
        return

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    if not _DIRECTORY_EXPORT_SUPPORTED:
        with _stream_from_descriptor(os.open(destination, flags, 0o600)) as stream:
            yield stream
        return

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(destination.anchor, directory_flags)
    try:
        for component in destination.parent.parts[1:]:
            child = os.open(component, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        with _stream_from_descriptor(os.open(
                destination.name, flags | os.O_NOFOLLOW, 0o600,
                dir_fd=directory)) as stream:
            yield stream
    finally:
        os.close(directory)


def export(value, destination):
    """Write one new private ZIP outside every selected workspace.

    All archive writes use the same exclusive-created descriptor, never output
    child paths. A renamed/replaced output is refused before reporting success.
    An interrupted/unverified output is never overwritten or deleted implicitly.
    POSIX no-follow directory handles prevent parent-symlink redirection, not
    hostile relocation. Windows uses exclusive, handle-relative creation with
    pinned ancestors and selected-root identity exclusion; native validation
    remains a separate acceptance gate. See the guide for platform limits.
    """
    entries = validate_manifest(value)
    destination = Path(destination).absolute()
    if _WINDOWS_EXPORT_SUPPORTED:
        from ._windows_export import _parts
        _parts(destination)
    safe_path(Path(destination.anchor), destination)
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Select a new bundle file under an existing parent")
    for entry in entries:
        if "workspace_root" in entry and destination.is_relative_to(Path(entry["workspace_root"]).resolve()):
            raise ValueError("Bundle must be outside selected workspaces")
    report, files = prepare(value)
    safe_path(Path(destination.anchor), destination)
    with _destination_stream(destination, workspace_roots=tuple(
            entry["workspace_root"] for entry in entries if "workspace_root" in entry)) as stream:
        identity = os.fstat(stream.fileno())

        def unchanged():
            safe_path(Path(destination.anchor), destination)
            current = destination.stat()
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise ValueError("Bundle destination changed")

        unchanged()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for relative, raw in files.items():
                archive.writestr(zipfile.ZipInfo(relative), raw)
            raw = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
            archive.writestr(zipfile.ZipInfo("manifest.json"), raw)
        stream.flush()
        unchanged()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Explicit task bindings, as used by batch_audit")
    parser.add_argument("destination", type=Path, help="New private ZIP file outside selected workspaces")
    args = parser.parse_args(argv)
    try:
        with args.manifest.open("rb") as stream:
            raw = stream.read(256_001)
        if len(raw) > 256_000:
            raise ValueError("Manifest too large")
        report = export(_json(raw), args.destination)
        # Do not print source text, draft prose, metadata, IDs, or private paths.
        print(json.dumps({"counts": report["counts"], "native_core_handoff": False,
                          "core_admission": "not_assessed", "stage2_execution_authorized": False}))
        return 0 if report["counts"]["prepared"] == len(report["entries"]) else 1
    except (OSError, ValueError, TypeError, RecursionError, WorkspaceError):
        print("Input preparation failed; no verified bundle completed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
