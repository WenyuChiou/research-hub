import argparse
import json

import pytest

from research_hub.workspace import core
from research_hub.workspace.cli import add_workspace_parsers, dispatch_workspace
from research_hub.workspace.core import Workspace, WorkspaceError
from research_hub.workspace.service import call_workspace


def setup_sources(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.create_project(id="selected", title="Synthetic project", archetype="review", goal="Local fixture")
    workspace.create_project(id="other", title="Other fixture", archetype="review", goal="Local fixture")
    source = workspace.add_record("selected", kind="source", data={"title":"Synthetic source", "locator":"https://example.invalid/source", "summary":"Saved prose", "reading_level":"abstract-snippet"})
    second = workspace.add_record("selected", kind="source", data={"title":"Second source", "locator":"https://example.invalid/second"})
    foreign = workspace.add_record("other", kind="source", data={"title":"Other project source", "locator":"https://example.invalid/other"})
    (tmp_path / "report.md").write_text("Synthetic generated report, not primary capture.\n", encoding="utf-8")
    return workspace, source, second, foreign


def test_register_binding_and_formal_preview_preserve_source(tmp_path):
    workspace, source, _, _ = setup_sources(tmp_path)
    before = workspace.records("selected")
    result = call_workspace(tmp_path, "project", "register", {"project_id":"selected", "path":"report.md", "role":"evidence", "source_record_id":source["id"]})
    assert result["ok"]
    artifact = result["artifact"]
    assert artifact["project_id"] == "selected" and artifact["source_record_id"] == source["id"]
    preview = call_workspace(tmp_path, "project", "preview_text", {"project_id":"selected", "artifact_id":artifact["id"]})
    assert preview["ok"] and preview["preview"]["sha256"] == artifact["sha256"]
    assert preview["preview"]["text"].startswith("Synthetic generated report")
    assert workspace.records("selected") == before


@pytest.mark.parametrize("kind", ["missing", "other-project", "non-source", "bad-role"])
def test_reject_invalid_binding_before_file_read(tmp_path, monkeypatch, kind):
    workspace, source, _, foreign = setup_sources(tmp_path)
    record_id = source["id"]
    if kind == "missing": record_id = "missing"
    if kind == "other-project": record_id = foreign["id"]
    if kind == "non-source": record_id = workspace.add_record("selected", kind="question", data={"text":"Synthetic question"})["id"]
    monkeypatch.setattr(core, "file_hash", lambda *_: pytest.fail("Unapproved binding must not read file content"))
    with pytest.raises(WorkspaceError) as error:
        workspace.register_artifact("selected", path="report.md", role="note" if kind == "bad-role" else "evidence", source_record_id=record_id)
    assert error.value.code in {"invalid_source", "invalid_request"}


def test_explicit_binding_is_idempotent_and_cannot_rebind_another_source(tmp_path, monkeypatch):
    workspace, source, second, _ = setup_sources(tmp_path)
    generic = workspace.register_artifact("selected", path="report.md", role="evidence")
    bound = workspace.register_artifact("selected", path="report.md", role="evidence", source_record_id=source["id"])
    again = workspace.register_artifact("selected", path="report.md", role="evidence", source_record_id=source["id"])
    assert generic["id"] == bound["id"] == again["id"]
    before = workspace.artifacts("selected", history=True)
    monkeypatch.setattr(core, "file_hash", lambda *_: pytest.fail("Conflicting ownership must not read content"))
    with pytest.raises(WorkspaceError, match="another source"):
        workspace.register_artifact("selected", path="report.md", role="evidence", source_record_id=second["id"])
    # Read only database metadata because file hashing is deliberately blocked.
    with workspace.db() as db:
        bodies = [json.loads(row[0]) for row in db.execute("SELECT body FROM artifacts WHERE project=?", ("selected",))]
    assert len(bodies) == 1 and bodies[0]["source_record_id"] == source["id"]
    assert len(before) == 1


def test_formal_cli_register_forwards_explicit_binding(tmp_path, capsys):
    _, source, _, _ = setup_sources(tmp_path)
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(["project", "register", "--root", str(tmp_path), "--project", "selected", "--path", "report.md", "--role", "evidence", "--source-record-id", source["id"]])
    assert dispatch_workspace(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["artifact"]["source_record_id"] == source["id"]


@pytest.mark.parametrize("role", ["evidence", "main_manuscript"])
def test_generic_changed_file_or_role_cannot_erase_owner_then_rebind(tmp_path, role):
    workspace, source, second, _ = setup_sources(tmp_path)
    first = workspace.register_artifact("selected", path="report.md", role="evidence", source_record_id=source["id"])
    (tmp_path / "report.md").write_text("Changed owned synthetic bytes.\n", encoding="utf-8")
    replacement = workspace.register_artifact("selected", path="report.md", role=role)
    assert replacement["id"] != first["id"]
    assert replacement["source_record_id"] == source["id"]
    with pytest.raises(WorkspaceError, match="another source"):
        workspace.register_artifact("selected", path="report.md", role="evidence", source_record_id=second["id"])


def test_exclusive_role_superseding_another_path_does_not_release_old_owner(tmp_path):
    workspace, source, second, _ = setup_sources(tmp_path)
    workspace.register_artifact("selected", path="report.md", role="evidence", source_record_id=source["id"])
    workspace.register_artifact("selected", path="report.md", role="main_manuscript")
    (tmp_path / "other.md").write_text("Other synthetic manuscript.\n", encoding="utf-8")
    workspace.register_artifact("selected", path="other.md", role="main_manuscript")
    restored = workspace.register_artifact("selected", path="report.md", role="evidence")
    assert restored["source_record_id"] == source["id"]
    with pytest.raises(WorkspaceError, match="another source"):
        workspace.register_artifact("selected", path="report.md", role="evidence", source_record_id=second["id"])


def test_owner_claimed_during_hashing_is_checked_inside_write_transaction(tmp_path, monkeypatch):
    workspace, source, second, _ = setup_sources(tmp_path)
    (tmp_path / "other.md").write_text("Other synthetic manuscript.\n", encoding="utf-8")
    real_hash = core.file_hash
    interleaved = False

    def hash_with_interleaved_claim(path):
        nonlocal interleaved
        if not interleaved:
            interleaved = True
            workspace.register_artifact("selected", path="report.md", role="evidence", source_record_id=source["id"])
            workspace.register_artifact("selected", path="report.md", role="main_manuscript")
            workspace.register_artifact("selected", path="other.md", role="main_manuscript")
        return real_hash(path)

    monkeypatch.setattr(core, "file_hash", hash_with_interleaved_claim)
    with pytest.raises(WorkspaceError, match="another source"):
        workspace.register_artifact("selected", path="report.md", role="evidence", source_record_id=second["id"])
    with workspace.db() as db:
        owned = [json.loads(row[0]) for row in db.execute("SELECT body FROM artifacts WHERE project=?", ("selected",))]
    assert interleaved
    assert len(owned) == 3
    assert {row["source_record_id"] for row in owned if row["path"] == "report.md"} == {source["id"]}
