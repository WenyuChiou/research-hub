"""Explicit local working prose; not source verification or human acceptance."""
from __future__ import annotations

import json
import re

from .core import WorkspaceError, digest, encoded, now
from .research_draft import read_selected_text

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_FIELDS = {"text", "artifact_id", "artifact_sha256", "source_revision", "previous_revision", "saved_at"}
_DISCLAIMER = "Evidence level: generated-summary. This is report-derived prose, NOT an original abstract or publisher capture."


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 40_000:
        raise WorkspaceError("Working summary requires nonempty text of at most 40000 characters")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise WorkspaceError("Working summary requires valid UTF-8 text") from exc
    return value.replace("\r\n", "\n").strip()


def _saved(data):
    value = data.get("working_summary")
    if value is None:
        return None
    from .task_summary import valid_provenance
    common = {"text", "source_revision", "previous_revision", "saved_at"}
    legacy = (isinstance(value, dict) and set(value) == _FIELDS
              and isinstance(value.get("artifact_id"), str) and bool(value["artifact_id"])
              and isinstance(value.get("artifact_sha256"), str) and _SHA.fullmatch(value["artifact_sha256"]))
    task = (isinstance(value, dict) and set(value) == common | {"provenance"}
            and valid_provenance(value.get("provenance")))
    if (not (legacy or task) or not isinstance(value.get("text"), str) or not value["text"].strip()
            or not all(isinstance(value.get(k), str) and _SHA.fullmatch(value[k])
                       for k in ("source_revision", "previous_revision"))
            or not isinstance(value.get("saved_at"), str)):
        raise WorkspaceError("Existing working summary requires review; it was not overwritten", "invalid_source")
    return value


def _base(record):
    return digest({**record, "data": {k: v for k, v in record["data"].items() if k != "working_summary"}})


def _selection(workspace, db, project_id, source_record_id, artifact_id, expected_sha=None):
    if not all(isinstance(v, str) and v for v in (project_id, source_record_id, artifact_id)):
        raise WorkspaceError("Select a project source and its generated draft", "invalid_source")
    row = db.execute("SELECT kind,body FROM records WHERE project=? AND id=?", (project_id, source_record_id)).fetchone()
    if row is None or row["kind"] != "source":
        raise WorkspaceError("Selected project source is unavailable", "invalid_source")
    record = {"id": source_record_id, "kind": "source", "data": json.loads(row["body"])}
    data = record["data"]
    if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not data["id"].strip():
        raise WorkspaceError("Selected source identity is unavailable", "invalid_source")
    _saved(data)
    row = db.execute("SELECT body FROM artifacts WHERE project=? AND id=?", (project_id, artifact_id)).fetchone()
    artifact = json.loads(row["body"]) if row else {}
    checksum, path = artifact.get("sha256"), artifact.get("path")
    if (artifact.get("id") != artifact_id or artifact.get("project_id") != project_id
            or artifact.get("source_record_id") != source_record_id or artifact.get("role") != "evidence"
            or artifact.get("superseded_by") or not isinstance(checksum, str) or not _SHA.fullmatch(checksum)
            or not isinstance(path, str) or not path):
        raise WorkspaceError("Generated draft is not bound to this source", "invalid_source")
    if expected_sha is not None and checksum != expected_sha:
        raise WorkspaceError("Selected generated draft changed; reload before saving", "stale_input")
    observations = data.get("source_records")
    observations = observations if isinstance(observations, list) else []
    ids = [v.get("observation_id") for v in observations if isinstance(v, dict)]
    matches = [v for v in observations if isinstance(v, dict)
               and isinstance(v.get("observation_id"), str) and v["observation_id"].strip()
               and ids.count(v["observation_id"]) == 1
               and isinstance(v.get("work_id"), str) and v["work_id"].strip()
               and isinstance(v.get("source_id"), str) and v["source_id"] in (source_record_id, data["id"])
               and v.get("evidence_level") == "generated-summary" and v.get("status") == "available"
               and v.get("text_path") == path and v.get("text_sha256") == checksum]
    if len(matches) != 1 or not isinstance(data.get("id"), str) or not data["id"].strip():
        raise WorkspaceError("Select one uniquely bound generated observation", "invalid_source")
    preview = read_selected_text(workspace, project_id, artifact_id, source_record_id=source_record_id)
    lines = preview["text"].replace("\r\n", "\n").split("\n")
    heading = f"# Generated summary observation: {data['id']}"
    anchor = "## Supplied generated summary"
    roles = [i for i, line in enumerate(lines) if line.startswith("Role candidate (not human acceptance):")]
    if (not lines or lines[0] != heading or sum(s.startswith("# Generated summary observation:") for s in lines) != 1
            or lines.count(_DISCLAIMER) != 1 or lines.count(anchor) != 1 or len(roles) != 1
            or not lines.index(_DISCLAIMER) < lines.index(anchor) < roles[0]):
        raise WorkspaceError("Generated report format is unavailable for review", "invalid_source")
    prose = _text("\n".join(lines[lines.index(anchor) + 1:roles[0]]))
    return record, artifact, prose


class WorkingSummary:
    def __init__(self, workspace):
        self.workspace = workspace

    def _select(self, db, project_id, source_record_id, artifact_id, task_id, expected_sha=None):
        if task_id is not None:
            if artifact_id is not None:
                raise WorkspaceError("Select exactly one draft provenance", "invalid_source")
            from .task_summary import selection
            record, provenance, prose = selection(self.workspace, db, project_id, source_record_id, task_id)
            _saved(record["data"])
            return record, {"provenance": provenance}, prose
        record, artifact, prose = _selection(self.workspace, db, project_id, source_record_id, artifact_id, expected_sha)
        return record, {"artifact_id": artifact["id"], "artifact_sha256": artifact["sha256"]}, prose

    def context(self, project_id, *, source_record_id, artifact_id=None, task_id=None):
        with self.workspace.db() as db:
            record, binding, prose = self._select(db, project_id, source_record_id, artifact_id, task_id)
        return {"ok": True, "context": {"source_record_id": record["id"], **binding,
                "revision": digest(record), "draft_text": prose, "working_summary": _saved(record["data"])}}

    def save(self, project_id, *, source_record_id, expected_revision, text,
             artifact_id=None, artifact_sha256=None, task_id=None, provenance=None):
        text = _text(text)
        if not isinstance(expected_revision, str) or not _SHA.fullmatch(expected_revision):
            raise WorkspaceError("Select the exact reviewed draft and source revision")
        if task_id is None:
            if provenance is not None or not isinstance(artifact_sha256, str) or not _SHA.fullmatch(artifact_sha256):
                raise WorkspaceError("Select the exact reviewed draft and source revision")
        else:
            from .task_summary import valid_provenance
            if artifact_sha256 is not None or not valid_provenance(provenance):
                raise WorkspaceError("Select the exact task draft provenance")
        # Source compare-and-save and task ledger reads share BEGIN IMMEDIATE.
        # The source is the only write; task/candidate/human decisions are untouched.
        with self.workspace.db(write=True) as db:
            record, binding, _ = self._select(db, project_id, source_record_id, artifact_id, task_id, artifact_sha256)
            if task_id is not None and binding["provenance"] != provenance:
                raise WorkspaceError("Task candidate changed; reload before saving", "stale_input")
            data = record["data"]
            previous = _saved(data)
            if (previous and previous["previous_revision"] == expected_revision
                    and previous["source_revision"] == _base(record) and previous["text"] == text
                    and all(previous.get(k) == v for k, v in binding.items())):
                return {"ok": True, "record": record, "reused": True}
            if digest(record) != expected_revision:
                raise WorkspaceError("Source or working summary changed; reload before saving", "stale_input")
            if previous:
                history = data.get("working_summary_history", [])
                if not isinstance(history, list):
                    raise WorkspaceError("Existing working summary history was not overwritten", "invalid_source")
                data["working_summary_history"] = [*history, previous]
            data["working_summary"] = {"text": text, **binding, "source_revision": _base(record),
                                       "previous_revision": expected_revision, "saved_at": now()}
            db.execute("UPDATE records SET body=? WHERE project=? AND id=? AND kind='source'",
                       (encoded(data), project_id, source_record_id))
        return {"ok": True, "record": record, "reused": False}
