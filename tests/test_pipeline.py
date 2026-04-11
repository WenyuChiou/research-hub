"""Tests for research_hub.pipeline.run_pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_config(tmp_path: Path, *, default_collection: str | None) -> Path:
    root = tmp_path / "kb"
    root.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    zotero = {
        "library_id": "99999",
        "library_type": "user",
        "collections": {
            "ABCD1234": {
                "name": "Survey Papers",
                "parent": None,
                "section": "survey",
            }
        },
    }
    if default_collection is not None:
        zotero["default_collection"] = default_collection
    config_path.write_text(
        json.dumps(
            {
                "knowledge_base": {
                    "root": str(root),
                    "raw": str(root / "raw"),
                    "hub": str(root / "hub"),
                    "projects": str(root / "projects"),
                    "logs": str(root / "logs"),
                    "obsidian_graph": str(root / ".obsidian" / "graph.json"),
                },
                "zotero": zotero,
            }
        ),
        encoding="utf-8",
    )
    return config_path


def _configure(monkeypatch, tmp_path: Path, *, default_collection: str | None):
    from research_hub import config as hub_config

    cfg_file = _write_config(tmp_path, default_collection=default_collection)
    hub_config._config = None
    monkeypatch.setattr(hub_config, "CONFIG_PATH", cfg_file)
    return hub_config.get_config()


def _paper(title: str, slug: str, doi: str) -> dict:
    return {
        "title": title,
        "authors": [{"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}],
        "authors_str": "Doe, Jane",
        "year": "2024",
        "doi": doi,
        "url": f"https://example.com/{slug}",
        "journal": "Journal of Testing",
        "abstract": "Abstract text",
        "tags": ["flood risk", "PMT"],
        "summary": "Summary text",
        "key_findings": ["Finding one"],
        "methodology": "Survey",
        "relevance": "Relevant",
        "sub_category": "survey",
        "slug": slug,
        "category": "behavioral",
        "method_type": "qualitative",
        "citations": 3,
        "pdf_url": "",
    }


def test_run_pipeline_missing_default_collection(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub.pipeline import run_pipeline

    _configure(monkeypatch, tmp_path, default_collection=None)

    with pytest.raises(RuntimeError, match="RESEARCH_HUB_DEFAULT_COLLECTION"):
        run_pipeline()

    hub_config._config = None


def test_run_pipeline_dry_run_allows_missing_default_collection(tmp_path, monkeypatch):
    """dry_run=True must work without a configured default_collection so
    verify_setup.py succeeds on a fresh install before config.json is edited."""
    from research_hub import config as hub_config
    from research_hub.pipeline import run_pipeline

    _configure(monkeypatch, tmp_path, default_collection=None)

    result = run_pipeline(dry_run=True)
    assert result == 0

    hub_config._config = None


def test_run_pipeline_dry_run_no_papers_json(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub.pipeline import run_pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")

    result = run_pipeline(dry_run=True)

    assert result == 0
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "DRY RUN MODE" in log_text
    assert "DRY RUN: Config and imports OK. Ready to run. Exiting." in log_text

    hub_config._config = None


def test_run_pipeline_dry_run_with_papers(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub import pipeline
    from research_hub.zotero import client as zotero_client

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    papers_path = cfg.root / "papers_input.json"
    papers_path.write_text(
        json.dumps(
            [
                _paper("Paper One", "paper-one", "10.1000/one"),
                _paper("Paper Two", "paper-two", "10.1000/two"),
            ]
        ),
        encoding="utf-8",
    )

    def fail_get_client():
        raise AssertionError("Zotero client should not be created during dry run")

    monkeypatch.setattr(zotero_client, "get_client", fail_get_client)
    monkeypatch.setattr(pipeline, "get_client", fail_get_client)

    result = pipeline.run_pipeline(dry_run=True)

    assert result == 0
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "would process 2 papers" in log_text

    hub_config._config = None


def test_run_pipeline_writes_error_log_on_zotero_failure(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper Error", "paper-error", "10.1000/error")]),
        encoding="utf-8",
    )

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            raise RuntimeError("create failed")

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="": False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline()

    assert result == 0
    error_logs = list(cfg.logs.glob("pipeline_errors_*.jsonl"))
    assert len(error_logs) == 1
    contents = error_logs[0].read_text(encoding="utf-8")
    assert "Paper Error" in contents
    assert "create failed" in contents

    hub_config._config = None


def test_run_pipeline_skips_duplicate(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Existing Paper", "existing-paper", "10.1000/existing")]),
        encoding="utf-8",
    )

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            raise AssertionError("Duplicate papers should not be created in Zotero")

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="": True)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline()

    assert result == 0
    output = json.loads((cfg.root / "pipeline_test_output.json").read_text(encoding="utf-8"))
    assert output["zotero_results"] == [
        {"title": "Existing Paper", "status": "SKIPPED_DUPLICATE", "key": ""}
    ]

    hub_config._config = None
