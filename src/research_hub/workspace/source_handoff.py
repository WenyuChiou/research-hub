"""No-write handoff preview; only bundled schema, never caller files or services."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from itertools import islice
import json
from pathlib import Path
import re

from .core import RECORD_FIELDS, WorkspaceError, encoded


MAX_PREVIEW_BYTES = 4 * 1024 * 1024
MAX_PREVIEW_ITEMS = 10_000
# Caller data keeps its original budget. Internal copies must also fit the
# bounded fields added by core: identity default, longest UTC clock, UUID hex,
# source kind and the maximum valid project ID. No source content is exempt.
_IDENTITY_BYTES = len(encoded({"identity_status": "unverified"}).encode("utf-8")) - 1
_CLOCK_BYTES = len(encoded({"recorded_at": "2000-01-01T00:00:00.000000Z"}).encode("utf-8")) - 1
_WRAPPER_BYTES = len(encoded({"id": "f" * 32, "kind": "source", "project_id": "p" * 63, "data": {}}).encode("utf-8")) - 2
MAX_SOURCE_RECORD_BYTES = MAX_PREVIEW_BYTES + _IDENTITY_BYTES + _CLOCK_BYTES
MAX_SOURCE_BATCH_BYTES = MAX_PREVIEW_BYTES + MAX_PREVIEW_ITEMS * _IDENTITY_BYTES
MAX_SOURCE_SNAPSHOT_BYTES = MAX_SOURCE_BATCH_BYTES + MAX_PREVIEW_ITEMS * (_CLOCK_BYTES + _WRAPPER_BYTES)
_PAPER_FIELDS = (
    "id", "title", "year", "url", "relevance", "reading_level",
    "reading_level_note", "category",
)


def source_record_arguments(
    paper: Mapping, *, batch_id: str, prior_batch_matches: Sequence[Mapping] = (),
) -> dict:
    """Project the existing quick-list metadata into source record arguments.

    Upstream data.id is retained. A real, separately authorized add_record call
    owns the outer Hub ID/timestamp; this function never makes that call.
    """
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise WorkspaceError("batch_id must be nonempty text")
    if not isinstance(paper, Mapping):
        raise WorkspaceError("Paper metadata must be an object")
    for key in ("id", "title", "url"):
        if not isinstance(paper.get(key), str) or not paper[key].strip():
            raise WorkspaceError(f"{key} must be nonempty text")
    level = paper.get("reading_level")
    if not isinstance(level, str) or level not in {"abstract", "abstract-snippet"}:
        raise WorkspaceError("Unsupported quick-list reading level")
    data = {key: deepcopy(paper[key]) for key in _PAPER_FIELDS if key in paper}
    data.update(
        locator=paper["url"], batch_id=batch_id,
        prior_batch_matches=deepcopy(list(prior_batch_matches)),
        reading_scope=level,
        identity_status="unverified", human_acceptance="pending",
    )
    return {"kind": "source", "data": data}


def _decode_source_json(raw: str, expected):
    """Shared strict decoder; caller and selected-payload entrypoints bound bytes."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result

    try:
        if not isinstance(raw, str):
            raise ValueError("Wrong JSON type")
        data = json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite")))
        if not isinstance(data, expected):
            raise ValueError("Wrong JSON shape")
        if expected is list and len(data) > MAX_PREVIEW_ITEMS:
            raise ValueError("Too many entries")
        encoded(data).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WorkspaceError("Source preview requires bounded valid JSON with the requested shape") from exc
    return data


def _parse_preview_json(raw: str, expected, *, max_bytes=MAX_PREVIEW_BYTES):
    try:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > max_bytes:
            raise ValueError("Too large")
    except (ValueError, UnicodeError) as exc:
        raise WorkspaceError("Source preview requires bounded valid JSON with the requested shape") from exc
    return _decode_source_json(raw, expected)


def stored_source_identity(raw: str) -> tuple[str, str] | None:
    """Inspect existing ordinary metadata, not a new batch payload.

    Ordinary add_record has no batch byte budget. Oversized rows are decoded
    strictly only to establish exact top-level identity, then discarded. This
    never admits their body to the bounded batch or snapshot. Use Python's same
    decoder rather than lossy SQLite JSON paths for NUL/escaped identities.
    """
    data = _decode_source_json(raw, dict)
    if "batch_id" not in data:
        return None  # Unbatched ordinary sources may still have a legacy id.
    for name in ("batch_id", "id"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise WorkspaceError("Stored batch source identity is unavailable", "conflict")
    return data["batch_id"], data["id"]


def parse_preview_data(raw: str) -> dict:
    return _parse_preview_json(raw, dict)


def parse_preview_array(raw: str) -> list:
    return _parse_preview_json(raw, list)


def parse_preview_snapshot(raw: str) -> list:
    return _parse_preview_json(raw, list, max_bytes=MAX_SOURCE_SNAPSHOT_BYTES)


def parse_stored_source_data(raw: str) -> dict:
    return _parse_preview_json(raw, dict, max_bytes=MAX_SOURCE_RECORD_BYTES)


def preview_source_record(project_id: str, *, kind: str, data: dict) -> dict:
    """Validate an in-memory proposal, without looking up the declared project."""
    if kind != "source":
        raise WorkspaceError("Record dry-run supports source metadata only")
    if not isinstance(project_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", project_id):
        raise WorkspaceError("Source preview requires a valid declared project ID")
    if not isinstance(data, dict):
        raise WorkspaceError("Source metadata must be an object")
    try:
        raw = encoded(data).encode("utf-8")
        if len(raw) > MAX_PREVIEW_BYTES:
            raise ValueError("Too large")
        proposal = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WorkspaceError("Source preview requires bounded finite JSON metadata") from exc
    for field in RECORD_FIELDS["source"]:
        if not isinstance(proposal.get(field), str) or not proposal[field].strip():
            raise WorkspaceError(f"source requires nonempty {field}")
    # Local quick-list preview policy, not a core Workspace source-record schema.
    if "reading_level" in proposal or "reading_scope" in proposal:
        level, scope = proposal.get("reading_level"), proposal.get("reading_scope")
        if not isinstance(level, str) or level not in {"abstract", "abstract-snippet"} or scope != level:
            raise WorkspaceError("Quick-list reading level and scope must match without promotion")
    proposal.update(identity_status="unverified", human_acceptance="pending")
    missing = [field for field in ("authors", "abstract", "summary")
               if not proposal.get(field) or isinstance(proposal[field], str) and not proposal[field].strip()]
    return {"ok": True, "preview": {
        "project_id": project_id, "project_verified": False,
        "kind": kind, "data": proposal, "record_id": None,
        "persisted": False, "execution_authorized": False,
        "missing_fields": missing, "ingest_readiness": "not-assessed",
        "limits": [
            "Metadata is caller supplied; reading, identity and scientific roles are not verified.",
            "No project lookup, record creation, summary generation or integration action occurred.",
            "This preview is not discovery observation validation, a saved handoff or Stage1 completion.",
        ],
    }}


def _preview_audit_items(records) -> dict:
    """Check existing audit-item compatibility, not generic source_records validity."""
    report = {
        "scope": "research-source-audit/1.0 observation items only",
        "status": "not-supplied", "item_count": len(records) if isinstance(records, list) else None,
        "findings": [], "findings_truncated": False,
        "packet_binding": "not-performed", "artifact_binding": "not-performed",
        "version_identity_scientific_checks": "not-performed",
        "persisted": False, "execution_authorized": False,
    }
    if isinstance(records, list) and not records:
        return report
    from jsonschema import Draft202012Validator

    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas" /
                         "research-source-audit-1.0.json").read_text(encoding="utf-8"))
    observation_schema = schema["properties"]["observations"]
    known_fields = observation_schema["items"]["properties"]
    findings = report["findings"]
    for error in islice(Draft202012Validator(observation_schema).iter_errors(records), 101):
        if len(findings) == 100:
            report["findings_truncated"] = True
            break
        path = list(error.absolute_path)
        findings.append({
            "item_index": path[0] if path and isinstance(path[0], int) else None,
            "field": path[1] if len(path) > 1 and path[1] in known_fields else None,
            "code": str(error.validator),
        })  # Never include jsonschema's content-bearing error.message.
    if isinstance(records, list):
        seen = set()
        for index, item in enumerate(records):
            oid = item.get("observation_id") if isinstance(item, dict) else None
            if not isinstance(oid, str):
                continue
            if oid in seen:
                if len(findings) == 100:
                    report["findings_truncated"] = True
                    break
                findings.append({"item_index": index, "field": "observation_id",
                                 "code": "duplicate-observation-id"})
            seen.add(oid)
    report["status"] = "rejected" if findings else "valid"
    return report


def preview_source_handoff(project_id: str, *, kind: str, data: dict) -> dict:
    """Keep record acceptance/exit semantics while reporting append compatibility."""
    try:
        result = preview_source_record(project_id, kind=kind, data=data)
    except WorkspaceError as exc:
        result = {"ok": False, "error": str(exc), "code": exc.code}
    # Only already-bounded, well-formed JSON is eligible for the independent report.
    if kind == "source" and isinstance(data, dict) and isinstance(project_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", project_id):
        try:
            proposal = parse_preview_data(encoded(data))
        except (WorkspaceError, TypeError, ValueError, RecursionError):
            return result
        if "source_records" in proposal:
            result["record_preview_status"] = "metadata-valid" if result["ok"] else "rejected"
            result["record_preview_contract"] = "local-quick-list-metadata-policy"
            result["core_record_validity"] = "not-assessed"
            result["source_audit_item_preview"] = _preview_audit_items(proposal["source_records"])
    return result


def _batch_copy(value, *, max_bytes=MAX_PREVIEW_BYTES) -> list:
    try:
        return _parse_preview_json(encoded(value), list, max_bytes=max_bytes)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise WorkspaceError("Batch preview requires a bounded finite JSON array") from exc


def _source_key(data: dict) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise WorkspaceError("Batch source data must be an object")
    for field in (*RECORD_FIELDS["source"], "batch_id", "id"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise WorkspaceError("Batch source requires nonempty title, locator, batch_id and id")
    return data["batch_id"], data["id"]


def preview_source_batch(project_id: str, *, kind: str, data: list, existing_records=None) -> dict:
    """Plan exact-key reuse/conflicts from caller data; no lookup or reservation.

    Generic batch validation uses core's required source fields, not the narrower
    quick-list level/scope policy. Every supplied field remains byte-equivalent
    under canonical JSON, including manual prose and historical declarations.
    """
    if kind != "source" or not isinstance(project_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", project_id):
        raise WorkspaceError("Batch preview requires source kind and a valid declared project")
    incoming = _batch_copy(data)
    supplied = existing_records is not None
    snapshot = _batch_copy(existing_records, max_bytes=MAX_SOURCE_SNAPSHOT_BYTES) if supplied else []
    return _plan_source_batch(project_id, incoming, snapshot, supplied=supplied)


def _plan_source_batch(project_id, incoming, snapshot, *, supplied):
    """Compare already bounded copies; neither public nor stored sizes are skipped."""
    if not isinstance(project_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", project_id):
        raise WorkspaceError("Batch preview requires source kind and a valid declared project")
    kind = "source"
    incoming_by_key, existing_by_key, outer_ids = {}, {}, set()
    for index, proposal in enumerate(incoming):
        incoming_by_key.setdefault(_source_key(proposal), []).append(index)
    for index, record in enumerate(snapshot):
        if (not isinstance(record, dict) or record.get("project_id") != project_id
                or record.get("kind") != "source" or not isinstance(record.get("id"), str)
                or not record["id"].strip() or record["id"] in outer_ids):
            raise WorkspaceError("Existing source snapshot has malformed, unbound or cross-project records")
        outer_ids.add(record["id"])
        existing_by_key.setdefault(_source_key(record.get("data")), []).append(index)
    conflicts, decisions = [], {}
    for key, indexes in incoming_by_key.items():
        matches = existing_by_key.get(key, [])
        reason = ("duplicate-incoming-key" if len(indexes) > 1 else
                  "ambiguous-snapshot-key" if len(matches) > 1 else
                  "changed-data" if matches and encoded(incoming[indexes[0]]) != encoded(snapshot[matches[0]]["data"]) else None)
        if reason:
            decisions[key] = ("conflict", None, len(conflicts))
            # Grouped references avoid quadratic copies for duplicate-key input.
            conflicts.append({"key": {"batch_id": key[0], "source_id": key[1]}, "reason": reason,
                              "incoming_indices": indexes, "existing_record_indices": matches})
        elif matches:
            decisions[key] = ("exact-reuse", snapshot[matches[0]]["id"], None)
        else:
            decisions[key] = ("create", None, None)
    counts = {"create": 0, "exact-reuse": 0, "conflict": 0}
    plans = []
    for index, proposal in enumerate(incoming):
        key = _source_key(proposal)
        disposition, record_id, conflict_index = decisions[key]
        counts[disposition] += 1
        plans.append({"index": index, "key": {"batch_id": key[0], "source_id": key[1]},
                      "disposition": disposition, "record_id": record_id,
                      "data": proposal, "conflict_index": conflict_index})
    return {"ok": True, "preview": {
        "project_id": project_id, "kind": kind, "project_verified": False,
        "snapshot_supplied": supplied, "snapshot_verified": False,
        "persisted": False, "execution_authorized": False, "atomic_reservation": False,
        "counts": counts, "plans": plans, "conflicts": conflicts, "existing_records": snapshot,
        "destination_writes": {name: "not-performed" for name in ("research-hub", "zotero", "obsidian", "notebooklm")},
        "limits": [
            "Exact keys and canonical data are compared only against the caller-supplied snapshot, not live storage.",
            "Create is a proposal; exact-reuse is a caller-snapshot match, not a verified current Hub binding.",
            "No source, version, reading, summary, classification, receipt or destination claim is verified.",
            "No lookup, file read, model, provider, record creation or atomic reservation occurred.",
        ],
    }}


class SourceBatchConflict(WorkspaceError):
    """Carry a plan through the existing transaction's rollback boundary."""
    def __init__(self, plan):
        super().__init__("Source batch has conflicts; no source records were written", "conflict")
        self.plan = plan


def prepare_source_batch_write(project_id: str, *, kind: str, data: list) -> list:
    """Validate before opening storage; only core-owned identity is projected."""
    if kind != "source" or not isinstance(project_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", project_id):
        raise WorkspaceError("Batch save requires source kind and a valid declared project")
    incoming = _batch_copy(data)
    for item in incoming:
        _source_key(item)
        if "recorded_at" in item:
            raise WorkspaceError("Batch save reserves recorded_at for the storage clock")
        if item.get("identity_status") not in (None, "unverified") or item.get("human_acceptance") not in (None, "pending"):
            raise WorkspaceError("Native source batch cannot assert verification or human acceptance")
        item["identity_status"] = "unverified"  # Same rule as ordinary add_record.
    return incoming


def plan_stored_source_batch(project_id: str, incoming: list, records: list) -> dict:
    """Storage-aware comparison; original stored rows remain untouched.

    Only the core's recorded_at field is omitted from comparison. Invalid or
    missing storage clocks remain explicit conflicts, never inferred replays.
    """
    incoming = _batch_copy(incoming, max_bytes=MAX_SOURCE_BATCH_BYTES)
    snapshot = _batch_copy(records, max_bytes=MAX_SOURCE_SNAPSHOT_BYTES)
    bad = {}
    for index, record in enumerate(snapshot):
        data = record.get("data")
        try:
            key = _source_key(data)
        except WorkspaceError as exc:
            raise WorkspaceError("Stored batch source metadata is malformed", "conflict") from exc
        stamp = data.pop("recorded_at", None)
        try:
            valid = (isinstance(stamp, str)
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?Z", stamp) is not None
                and datetime.fromisoformat(stamp[:-1] + "+00:00").isoformat().replace("+00:00", "Z") == stamp)
        except (ValueError, OverflowError):
            valid = False
        if not valid:
            bad.setdefault(key, []).append(index)
    result = _plan_source_batch(project_id, incoming, snapshot, supplied=True)
    view = result["preview"]
    for key, existing_indices in bad.items():
        matched = [p for p in view["plans"] if (p["key"]["batch_id"], p["key"]["source_id"]) == key]
        if not matched:
            continue
        conflict_index = len(view["conflicts"])
        view["conflicts"].append({"key": matched[0]["key"], "reason": "unknown-storage-metadata",
            "incoming_indices": [p["index"] for p in matched], "existing_record_indices": existing_indices})
        for plan in matched:
            plan.update(disposition="conflict", record_id=None, conflict_index=conflict_index)
    view["counts"] = {name: sum(p["disposition"] == name for p in view["plans"])
                      for name in ("create", "exact-reuse", "conflict")}
    view["existing_records"] = deepcopy(records)
    view["comparison"] = "core-storage-projection; recorded_at only; no scientific verification"
    return result
