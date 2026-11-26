from __future__ import annotations

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError
from research_hub.workspace.native_summary import _base as native_base


def test_source_curation_appends_without_mutating_source_revision(tmp_path):
    ws = Workspace(tmp_path)
    project = ws.create_project(id="curation-test", title="Curation Test", archetype="review")
    source = ws.add_record(
        project["id"],
        kind="source",
        data={
            "title": "ReAct: Synergizing Reasoning and Acting",
            "locator": "https://arxiv.org/abs/2210.03629",
            "doi": "10.48550/arXiv.2210.03629",
        },
    )
    revision_before = native_base(source)

    curation = ws.add_record(
        project["id"],
        kind="source_curation",
        data={
            "source_id": source["id"],
            "category": "llm",
            "year": 2023,
            "authors": "Shunyu Yao, Jeffrey Zhao, Dian Yu",
            "venue": "ICLR 2023",
            "relevance": "Core agent benchmark paper.",
            "summary": "Combines reasoning traces and actions.",
            "tags": "agents, reasoning",
        },
    )
    assert curation["kind"] == "source_curation"
    assert curation["data"]["category"] == "llm"
    assert curation["data"]["year"] == "2023"
    assert curation["data"]["authors"] == ["Shunyu Yao", "Jeffrey Zhao", "Dian Yu"]
    assert curation["data"]["tags"] == ["agents", "reasoning"]

    stored_source = next(r for r in ws.records(project["id"]) if r["id"] == source["id"])
    assert native_base(stored_source) == revision_before
    assert stored_source["data"]["identity_status"] == "unverified"


def test_source_curation_rejects_protected_fields_and_unknown_sources(tmp_path):
    ws = Workspace(tmp_path)
    project = ws.create_project(id="curation-guard", title="Guard Test", archetype="review")
    source = ws.add_record(
        project["id"],
        kind="source",
        data={"title": "Test Paper", "locator": "https://example.org/paper"},
    )

    for forbidden in (
        {"source_id": source["id"], "identity_status": "verified"},
        {"source_id": source["id"], "human_acceptance": "accepted"},
        {"source_id": source["id"], "reading_scope": "full-text"},
        {"source_id": source["id"], "title": "Tampered"},
        {"source_id": source["id"], "year": "not-a-year"},
        {"source_id": source["id"], "year": True},
        {"source_id": source["id"], "category": "bad\x00value"},
        {"source_id": "nonexistent-source", "category": "llm"},
    ):
        with pytest.raises(WorkspaceError):
            ws.add_record(project["id"], kind="source_curation", data=forbidden)


def test_add_source_normalizes_optional_authors_and_year(tmp_path):
    ws = Workspace(tmp_path)
    project = ws.create_project(id="source-opt", title="Source Opt", archetype="review")
    source = ws.add_record(
        project["id"],
        kind="source",
        data={
            "title": "RAG Paper",
            "locator": "https://arxiv.org/abs/2005.11401",
            "authors": "Patrick Lewis, Ethan Perez",
            "year": "2020",
            "category": "llm",
            "tags": "#retrieval, benchmark; LLM，#Benchmark",
        },
    )
    assert source["data"]["authors"] == ["Patrick Lewis", "Ethan Perez"]
    assert source["data"]["year"] == "2020"
    assert source["data"]["category"] == "llm"
    assert source["data"]["tags"] == ["retrieval", "benchmark", "LLM"]
    assert source["data"]["identity_status"] == "unverified"

    blank_tags_source = ws.add_record(
        project["id"],
        kind="source",
        data={
            "title": "Blank Tags Paper",
            "locator": "https://example.org/blank-tags",
            "tags": "  ,  ",
        },
    )
    assert "tags" not in blank_tags_source["data"]

    csl_source = ws.add_record(
        project["id"],
        kind="source",
        data={
            "title": "Structured Authors Paper",
            "locator": "https://example.org/csl",
            "authors": [{"family": "Smith", "given": "John"}, {"family": "Doe", "given": "Jane"}],
            "year": 2024,
        },
    )
    assert csl_source["data"]["authors"] == [
        {"family": "Smith", "given": "John"},
        {"family": "Doe", "given": "Jane"},
    ]
    assert csl_source["data"]["year"] == "2024"

    semicolon_curation = ws.add_record(
        project["id"],
        kind="source_curation",
        data={
            "source_id": source["id"],
            "authors": "Smith, John; Doe, Jane",
        },
    )
    assert semicolon_curation["data"]["authors"] == ["Smith, John", "Doe, Jane"]

    for invalid_source in (
        {"title": "Bad Year Bool", "locator": "https://example.org/1", "year": True},
        {"title": "Bad Year Text", "locator": "https://example.org/2", "year": "twenty"},
        {"title": "Bad Authors Num", "locator": "https://example.org/3", "authors": 123},
        {"title": "Bad Authors List", "locator": "https://example.org/4", "authors": [42]},
        {"title": "Bad Tags Num", "locator": "https://example.org/5", "tags": 999},
        {"title": "Bad Scope Control", "locator": "https://example.org/6", "reading_scope": "bad\x00scope"},
        {"title": "Bad Scope Num", "locator": "https://example.org/7", "reading_scope": 123},
    ):
        with pytest.raises(WorkspaceError):
            ws.add_record(project["id"], kind="source", data=invalid_source)


def test_source_curation_supports_doi_and_archive_restore_without_mutating_identity(tmp_path):
    ws = Workspace(tmp_path)
    project = ws.create_project(id="curation-crud", title="CRUD Test", archetype="review")
    source = ws.add_record(
        project["id"],
        kind="source",
        data={
            "title": "Clinical AI Triage Trial",
            "locator": "https://doi.org/10.1038/s41591-025-00001-1",
            "reading_scope": "full-text",
        },
    )
    assert source["data"]["reading_scope"] == "full-text"
    revision_before = native_base(source)

    archived_curation = ws.add_record(
        project["id"],
        kind="source_curation",
        data={
            "source_id": source["id"],
            "doi": "10.1038/s41591-025-00001-1",
            "archived": True,
        },
    )
    assert archived_curation["data"]["doi"] == "10.1038/s41591-025-00001-1"
    assert archived_curation["data"]["archived"] is True

    restored_curation = ws.add_record(
        project["id"],
        kind="source_curation",
        data={
            "source_id": source["id"],
            "archived": False,
        },
    )
    assert restored_curation["data"]["archived"] is False

    stored_source = next(r for r in ws.records(project["id"]) if r["id"] == source["id"])
    assert native_base(stored_source) == revision_before
    assert stored_source["data"]["identity_status"] == "unverified"

    for invalid_curation in (
        {"source_id": source["id"], "archived": "yes"},
        {"source_id": source["id"], "archived": 1},
        {"source_id": source["id"], "archived": None},
        {"source_id": source["id"], "doi": "x" * 201},
    ):
        with pytest.raises(WorkspaceError):
            ws.add_record(project["id"], kind="source_curation", data=invalid_curation)

