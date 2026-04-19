from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_hub import crystal
from research_hub.clusters import ClusterRegistry
from research_hub.crystal import CANONICAL_QUESTIONS, CANONICAL_SLUGS, Crystal, CrystalEvidence


class _StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _make_cluster_with_papers(tmp_path: Path, slug: str, papers: list[tuple[str, str, str]]) -> _StubConfig:
    cfg = _StubConfig(tmp_path / "vault")
    ClusterRegistry(cfg.clusters_file).create(query=slug, name=slug.replace("-", " ").title(), slug=slug)
    cluster_dir = cfg.raw / slug
    cluster_dir.mkdir(parents=True, exist_ok=True)
    for paper_slug, title, one_liner in papers:
        (cluster_dir / f"{paper_slug}.md").write_text(
            f"""---
title: "{title}"
authors: "Doe, Jane"
year: "2024"
doi: "10.1/{paper_slug}"
topic_cluster: {slug}
---

## Abstract

Some abstract.

## Summary

{one_liner}
""",
            encoding="utf-8",
        )
    hub_dir = cfg.hub / slug
    hub_dir.mkdir(parents=True, exist_ok=True)
    (hub_dir / "00_overview.md").write_text(
        f"""---
type: topic-overview
cluster: {slug}
---

# {slug}

## TL;DR

This cluster tests the crystal pipeline.
""",
        encoding="utf-8",
    )
    return cfg


def _make_fake_crystals_json(slugs: list[str], generator: str = "test") -> dict:
    return {
        "generator": generator,
        "crystals": [
            {
                "slug": slug,
                "question": next(item["question"] for item in CANONICAL_QUESTIONS if item["slug"] == slug),
                "tldr": f"TLDR for {slug}",
                "gist": f"Gist paragraph for {slug} with [[paper-a]] link.",
                "full": f"Full answer for {slug}. ## Section 1\n\nBlah [[paper-a]] blah.",
                "evidence": [{"claim": f"claim for {slug}", "papers": ["paper-a"]}],
                "confidence": "medium",
            }
            for slug in slugs
        ],
    }


def test_canonical_questions_count_and_slugs():
    assert len(CANONICAL_QUESTIONS) == 10
    assert all("slug" in item and "question" in item for item in CANONICAL_QUESTIONS)
    assert CANONICAL_SLUGS == {item["slug"] for item in CANONICAL_QUESTIONS}


def test_emit_crystal_prompt_includes_all_canonical_questions(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "one line")])
    prompt = crystal.emit_crystal_prompt(cfg, "test")
    for item in CANONICAL_QUESTIONS:
        assert item["slug"] in prompt
        assert item["question"] in prompt


def test_emit_crystal_prompt_includes_cluster_paper_list(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "one line a"), ("paper-b", "Paper B", "one line b")])
    prompt = crystal.emit_crystal_prompt(cfg, "test")
    assert "paper-a" in prompt and "paper-b" in prompt and "Paper A" in prompt


def test_emit_crystal_prompt_custom_question_subset(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    prompt = crystal.emit_crystal_prompt(cfg, "test", question_slugs=["what-is-this-field", "key-concepts"])
    assert "what-is-this-field" in prompt and "key-concepts" in prompt and "common-pitfalls" not in prompt


def test_emit_crystal_prompt_rejects_unknown_slug(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    with pytest.raises(ValueError):
        crystal.emit_crystal_prompt(cfg, "test", question_slugs=["nonexistent"])


def test_apply_crystals_writes_all_requested_files(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    result = crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field", "key-concepts"]))
    assert set(result.written) == {"what-is-this-field", "key-concepts"}
    assert (cfg.hub / "test" / "crystals" / "what-is-this-field.md").exists()


def test_apply_crystals_is_idempotent(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    scored = _make_fake_crystals_json(["what-is-this-field"])
    crystal.apply_crystals(cfg, "test", scored)
    second = crystal.apply_crystals(cfg, "test", scored)
    assert "what-is-this-field" in second.replaced and len(second.written) == 0


def test_apply_crystals_skips_unknown_slugs(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    result = crystal.apply_crystals(cfg, "test", {"generator": "test", "crystals": [{"slug": "nonexistent", "question": "?", "tldr": "x", "gist": "x", "full": "x"}]})
    assert any("nonexistent" in item for item in result.skipped)


def test_apply_crystals_captures_current_papers_in_frontmatter(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", ""), ("paper-b", "Paper B", "")])
    crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field"]))
    loaded = crystal.read_crystal(cfg, "test", "what-is-this-field")
    assert loaded is not None
    assert set(loaded.based_on_papers) == {"paper-a", "paper-b"}
    assert loaded.based_on_paper_count == 2


def test_crystal_to_markdown_roundtrip():
    loaded = Crystal.from_markdown(
        Crystal(
            cluster_slug="test",
            question_slug="what-is-this-field",
            question="What is this research area about?",
            tldr="Short answer",
            gist="Medium answer",
            full="Long answer",
            evidence=[CrystalEvidence(claim="Claim", papers=["paper-a"])],
            based_on_papers=["paper-a"],
            based_on_paper_count=1,
            last_generated="2026-04-15T00:00:00Z",
            generator="test",
            confidence="medium",
            see_also=["key-concepts"],
        ).to_markdown()
    )
    assert loaded.question_slug == "what-is-this-field"
    assert loaded.tldr == "Short answer"
    assert loaded.evidence[0].papers == ["paper-a"]
    assert loaded.see_also == ["key-concepts"]


def test_list_crystals_returns_empty_when_none_written(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    assert crystal.list_crystals(cfg, "test") == []


def test_list_crystals_returns_all_written(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field", "key-concepts", "main-threads"]))
    assert {item.question_slug for item in crystal.list_crystals(cfg, "test")} == {"what-is-this-field", "key-concepts", "main-threads"}


def test_read_crystal_missing_returns_none(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    assert crystal.read_crystal(cfg, "test", "what-is-this-field") is None


def test_check_staleness_empty_when_no_crystals(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    assert crystal.check_staleness(cfg, "test") == {}


def test_check_staleness_fresh_after_generation(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field"]))
    assert crystal.check_staleness(cfg, "test")["what-is-this-field"].delta_ratio == 0.0


def test_check_staleness_detects_added_paper(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field"]))
    for index in range(5):
        (cfg.raw / "test" / f"paper-new-{index}.md").write_text(
            f"---\ntitle: \"New {index}\"\ndoi: \"10.1/n{index}\"\ntopic_cluster: test\n---\n\n## Abstract\n\n## Summary\nx\n",
            encoding="utf-8",
        )
    staleness = crystal.check_staleness(cfg, "test")["what-is-this-field"]
    assert staleness.stale is True and len(staleness.added_papers) == 5


def test_check_staleness_detects_removed_paper(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", ""), ("paper-b", "Paper B", ""), ("paper-c", "Paper C", "")])
    crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field"]))
    (cfg.raw / "test" / "paper-a.md").unlink()
    assert "paper-a" in crystal.check_staleness(cfg, "test")["what-is-this-field"].removed_papers


def test_crystal_see_also_populated_with_sibling_slugs(tmp_path):
    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "")])
    crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field", "key-concepts"]))
    assert "key-concepts" in crystal.read_crystal(cfg, "test", "what-is-this-field").see_also


def test_emit_prompt_handles_missing_overview_gracefully(tmp_path):
    cfg = _StubConfig(tmp_path / "vault")
    ClusterRegistry(cfg.clusters_file).create(query="test", name="Test", slug="test")
    (cfg.hub / "test" / "00_overview.md").unlink()
    (cfg.raw / "test").mkdir(parents=True)
    (cfg.raw / "test" / "paper-a.md").write_text("---\ntitle: \"A\"\ndoi: \"10.1/a\"\ntopic_cluster: test\n---\n\n## Summary\nx\n", encoding="utf-8")
    assert "(no definition" in crystal.emit_crystal_prompt(cfg, "test")


def test_cli_crystal_emit_writes_prompt_file(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "one line")])
    out = tmp_path / "crystal_prompt.md"
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    assert cli.main(["crystal", "emit", "--cluster", "test", "--out", str(out)]) == 0
    assert "what-is-this-field" in out.read_text(encoding="utf-8")


def test_cli_crystal_apply_writes_files(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "one line")])
    scored_path = tmp_path / "crystals.json"
    scored_path.write_text(json.dumps(_make_fake_crystals_json(["what-is-this-field"])), encoding="utf-8")
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    assert cli.main(["crystal", "apply", "--cluster", "test", "--scored", str(scored_path)]) == 0


def test_cli_crystal_list_empty_cluster(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "one line")])
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    assert cli.main(["crystal", "list", "--cluster", "test"]) == 0
    assert "(no crystals yet" in capsys.readouterr().out


def test_cli_crystal_read_gist(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "one line")])
    crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field"]))
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    assert cli.main(["crystal", "read", "--cluster", "test", "--slug", "what-is-this-field"]) == 0
    assert "Gist paragraph for what-is-this-field" in capsys.readouterr().out


def test_mcp_list_crystals_returns_summary(tmp_path, monkeypatch):
    from research_hub.mcp_server import mcp
    from tests._mcp_helpers import _get_mcp_tool

    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "one line")])
    crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field"]))
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp, "list_crystals").fn("test")
    assert result["cluster"] == "test" and result["crystals"][0]["slug"] == "what-is-this-field"


def test_mcp_read_crystal_returns_requested_level(tmp_path, monkeypatch):
    from research_hub.mcp_server import mcp
    from tests._mcp_helpers import _get_mcp_tool

    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "one line")])
    crystal.apply_crystals(cfg, "test", _make_fake_crystals_json(["what-is-this-field"]))
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp, "read_crystal").fn("test", "what-is-this-field", "tldr")
    assert result["status"] == "ok" and result["answer"] == "TLDR for what-is-this-field"


def test_mcp_emit_and_check_crystals(tmp_path, monkeypatch):
    from research_hub.mcp_server import mcp
    from tests._mcp_helpers import _get_mcp_tool

    cfg = _make_cluster_with_papers(tmp_path, "test", [("paper-a", "Paper A", "one line")])
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    emitted = _get_mcp_tool(mcp, "emit_crystal_prompt").fn("test", ["what-is-this-field"])
    _get_mcp_tool(mcp, "apply_crystals").fn("test", _make_fake_crystals_json(["what-is-this-field"]))
    checked = _get_mcp_tool(mcp, "check_crystal_staleness").fn("test")
    assert "what-is-this-field" in emitted["prompt"] and checked["crystals"]["what-is-this-field"]["stale"] is False
