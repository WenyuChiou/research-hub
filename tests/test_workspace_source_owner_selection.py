"""Source-owner selection contract on synthetic workspace files only."""
import pytest

from research_hub.workspace import research_draft
from research_hub.workspace.core import Workspace, WorkspaceError


@pytest.fixture
def owned(tmp_path):
    ws = Workspace(tmp_path)
    ws.create_project(id="selected", title="Synthetic ownership")
    a = ws.add_record("selected", kind="source", data={"title": "Source A", "locator": "https://example.invalid/a"})
    b = ws.add_record("selected", kind="source", data={"title": "Source B", "locator": "https://example.invalid/b"})
    text = "Synthetic report belonging to source A."
    (tmp_path / "owned.md").write_text(text, encoding="utf-8")
    artifact = ws.register_artifact("selected", path="owned.md", role="evidence", source_record_id=a["id"])
    return ws, a, b, artifact, text


def selection(artifact, source, text):
    return {"artifact_id": artifact["id"], "source_record_id": source["id"], "start": 0, "end": len(text)}


def test_owned_file_cannot_be_attributed_to_another_source(owned):
    ws, _, b, artifact, text = owned
    with pytest.raises(WorkspaceError) as error:
        research_draft.read_selection(ws, "selected", selection(artifact, b, text))
    assert error.value.code == "invalid_source"


def test_wrong_owner_is_rejected_before_filesystem_probe(owned, monkeypatch):
    ws, _, b, artifact, text = owned
    monkeypatch.setattr(research_draft, "safe_path", lambda *_a, **_kw: pytest.fail("Wrong source must not probe/read evidence"))
    with pytest.raises(WorkspaceError) as error:
        research_draft.read_selection(ws, "selected", selection(artifact, b, text))
    assert error.value.code == "invalid_source"


def test_correct_owner_preserves_original_text_and_source_identity(owned):
    ws, a, _, artifact, text = owned
    before = ws.records("selected")
    pack = research_draft.read_selection(ws, "selected", selection(artifact, a, text))
    assert pack["text"] == text
    assert pack["source_record_id"] == a["id"]
    assert pack["source"]["locator"] == a["data"]["locator"]
    assert pack["source"]["identity_status"] == "unverified"
    assert ws.records("selected") == before


def test_genuinely_unbound_legacy_file_remains_selectable(owned):
    ws, _, b, _, text = owned
    (ws.root / "legacy.md").write_text(text, encoding="utf-8")
    legacy = ws.register_artifact("selected", path="legacy.md", role="evidence")
    assert "source_record_id" not in legacy
    pack = research_draft.read_selection(ws, "selected", selection(legacy, b, text))
    assert pack["source_record_id"] == b["id"] and pack["text"] == text


@pytest.mark.parametrize("owner", [None, "", 0, {}, " different-source "])
def test_malformed_owner_never_becomes_legacy_unbound(owned, monkeypatch, owner):
    ws, a, _, artifact, text = owned
    monkeypatch.setattr(research_draft, "selected_artifact", lambda *_: {**artifact, "source_record_id": owner})
    monkeypatch.setattr(research_draft, "safe_path", lambda *_a, **_kw: pytest.fail("Invalid owner must not probe/read evidence"))
    with pytest.raises(WorkspaceError) as error:
        research_draft.read_selection(ws, "selected", selection(artifact, a, text))
    assert error.value.code == "invalid_source"
