from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_hub.security import ValidationError
from tests.test_pipeline import _configure, _paper


def _create_cluster(cfg, slug: str, zotero_collection_key: str | None = None) -> None:
    lines = [
        "clusters:",
        f"  {slug}:",
        f"    name: {slug}",
        "    seed_keywords:",
        "      - llm",
        "      - agents",
        f"    obsidian_subfolder: {slug}",
    ]
    if zotero_collection_key:
        lines.append(f"    zotero_collection_key: {zotero_collection_key}")
    cfg.clusters_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_pipeline_routes_to_cluster_collection_when_bound(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "cluster-a", "CLUSTER999")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            seen["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda zot, title, doi="", collection_key=None, **kwargs: (
            seen.setdefault("duplicate_collection", collection_key) and False
        ),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline(cluster_slug="cluster-a")

    assert result == 0
    assert seen["duplicate_collection"] == "CLUSTER999"
    assert seen["collections"] == ["CLUSTER999"]
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "Routing to collection: CLUSTER999 (cluster=cluster-a)" in log_text


def test_pipeline_falls_back_to_default_when_cluster_unbound(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "cluster-a")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            seen["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda zot, title, doi="", collection_key=None, **kwargs: (
            seen.setdefault("duplicate_collection", collection_key) and False
        ),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline(cluster_slug="cluster-a")

    assert result == 0
    assert seen["duplicate_collection"] is None
    assert seen["collections"] == ["ABCD1234"]
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "Routing to collection: ABCD1234 (cluster=cluster-a)" in log_text


def test_pipeline_falls_back_to_default_when_no_cluster_slug(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            seen["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda zot, title, doi="", collection_key=None, **kwargs: (
            seen.setdefault("duplicate_collection", collection_key) and False
        ),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline()

    assert result == 0
    assert seen["duplicate_collection"] is None
    assert seen["collections"] == ["ABCD1234"]
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "Routing to collection: ABCD1234 (cluster=none)" in log_text


def test_validate_slug_accepts_normal_slug():
    from research_hub.security import validate_slug

    assert validate_slug("llm_agents-2025") == "llm_agents-2025"


def test_validate_slug_rejects_dotdot():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("..")


def test_validate_slug_rejects_absolute_path():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("/etc/passwd")


def test_validate_slug_rejects_uppercase():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("Topic-A")


def test_validate_slug_rejects_long_input():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("a" * 65)


def test_validate_slug_rejects_shell_metacharacters():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("topic;rm-rf")


def test_validate_identifier_accepts_doi():
    from research_hub.security import validate_identifier

    assert validate_identifier("10.1234/example-doi") == "10.1234/example-doi"


def test_validate_identifier_accepts_arxiv_id():
    from research_hub.security import validate_identifier

    assert validate_identifier("2502.10978v1") == "2502.10978v1"


def test_validate_identifier_rejects_semicolon():
    from research_hub.security import validate_identifier

    with pytest.raises(ValidationError):
        validate_identifier("10.1234/x; rm -rf /")


def test_validate_identifier_rejects_newline():
    from research_hub.security import validate_identifier

    with pytest.raises(ValidationError):
        validate_identifier("10.1234/x\nsecond-line")


def test_safe_join_blocks_traversal(tmp_path):
    from research_hub.security import safe_join

    with pytest.raises(ValidationError):
        safe_join(tmp_path, "..")


def test_safe_join_blocks_absolute_segment(tmp_path):
    from research_hub.security import safe_join

    with pytest.raises(ValidationError):
        safe_join(tmp_path, "/etc")


def test_safe_join_allows_valid_subpath(tmp_path):
    from research_hub.security import safe_join

    assert safe_join(tmp_path, "cluster-a", "crystals") == Path(tmp_path).resolve() / "cluster-a" / "crystals"


def test_mcp_read_crystal_blocks_traversal_slug():
    from research_hub.mcp_server import read_crystal

    with pytest.raises(ValidationError):
        read_crystal.fn("../../etc", "what-is-this-field")


def test_mcp_add_paper_blocks_injection_identifier():
    from research_hub.mcp_server import add_paper

    with pytest.raises(ValidationError):
        add_paper.fn("10.1234/x; rm -rf /")
