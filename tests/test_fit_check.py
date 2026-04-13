from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    root.mkdir(parents=True)
    hub.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        hub=hub,
        raw=root / "raw",
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _candidate(title: str, doi: str, abstract: str = "Agent systems for software engineering.") -> dict:
    return {
        "title": title,
        "doi": doi,
        "abstract": abstract,
        "year": 2025,
        "authors": ["Jane Doe", "John Roe"],
    }


def test_emit_prompt_includes_cluster_definition():
    from research_hub.fit_check import emit_prompt

    prompt = emit_prompt("agents", [_candidate("Paper", "10.1/a")], definition="Exact cluster definition.")

    assert "## Cluster definition" in prompt
    assert "Exact cluster definition." in prompt


def test_emit_prompt_falls_back_to_overview_definition_section(tmp_path, monkeypatch):
    from research_hub.fit_check import emit_prompt

    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "research_hub.topic.read_overview",
        lambda cfg_arg, cluster_slug: "## Definition\nOverview definition text.\n\n## Scope\nMore",
    )

    prompt = emit_prompt("agents", [_candidate("Paper", "10.1/a")], cfg=cfg)

    assert "Overview definition text." in prompt


def test_emit_prompt_includes_key_terms_list():
    from research_hub.fit_check import emit_prompt

    prompt = emit_prompt(
        "agents",
        [_candidate("Paper", "10.1/a")],
        definition="Benchmarks for LLM agents on software engineering tasks.",
    )

    assert "Key terms:" in prompt
    assert "benchmarks" in prompt
    assert "software" in prompt
    assert "engineering" in prompt


def test_emit_prompt_renders_all_candidates_with_title_doi_abstract():
    from research_hub.fit_check import emit_prompt

    candidates = [
        _candidate("Paper One", "10.1/one"),
        _candidate("Paper Two", "10.1/two"),
        _candidate("Paper Three", "10.1/three"),
    ]

    prompt = emit_prompt("agents", candidates, definition="Definition")

    assert "### 1. Paper One" in prompt
    assert "### 2. Paper Two" in prompt
    assert "### 3. Paper Three" in prompt
    assert "**DOI:** 10.1/three" in prompt


def test_emit_prompt_example_json_output_is_valid():
    from research_hub.fit_check import emit_prompt

    prompt = emit_prompt("agents", [_candidate("Paper", "10.1/a")], definition="Definition")
    json_block = prompt.split("Emit ONE JSON object, nothing else (no prose, no markdown fence):\n\n", 1)[1]
    payload = json.loads(json_block)

    assert "scores" in payload
    assert payload["scores"][0]["score"] == 5


def test_apply_scores_keeps_papers_above_threshold():
    from research_hub.fit_check import apply_scores

    candidates = [_candidate("A", "10.1/a"), _candidate("B", "10.1/b"), _candidate("C", "10.1/c")]
    report = apply_scores(
        "agents",
        candidates,
        {"scores": [
            {"doi": "10.1/a", "score": 5, "reason": "squarely on topic"},
            {"doi": "10.1/b", "score": 4, "reason": "adjacent"},
            {"doi": "10.1/c", "score": 2, "reason": "off topic"},
        ]},
        threshold=3,
    )

    assert [item.doi for item in report.accepted] == ["10.1/a", "10.1/b"]
    assert [item.doi for item in report.rejected] == ["10.1/c"]


def test_apply_scores_rejects_papers_below_threshold():
    from research_hub.fit_check import apply_scores

    report = apply_scores(
        "agents",
        [_candidate("Paper", "10.1/a")],
        [{"doi": "10.1/a", "score": 1, "reason": "not a fit"}],
        threshold=3,
    )

    assert report.accepted == []
    assert report.rejected[0].kept is False


def test_apply_scores_writes_rejected_sidecar_json(tmp_path):
    from research_hub.fit_check import apply_scores

    cfg = _cfg(tmp_path)
    report = apply_scores(
        "agents",
        [_candidate("Paper", "10.1/a")],
        [{"doi": "10.1/a", "score": 1, "reason": "not a fit"}],
        threshold=3,
        cfg=cfg,
    )

    sidecar = cfg.hub / "agents" / ".fit_check_rejected.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))

    assert report.rejected[0].doi == "10.1/a"
    assert payload["rejected"][0]["reason"] == "not a fit"


def test_apply_scores_handles_missing_doi_falls_back_to_title_match():
    from research_hub.fit_check import apply_scores

    report = apply_scores(
        "agents",
        [_candidate("Fallback Title", "")],
        [{"title": "Fallback Title", "score": 4, "reason": "title match"}],
        threshold=3,
    )

    assert report.accepted[0].reason == "title match"


def test_apply_scores_unscored_papers_treated_as_score_zero():
    from research_hub.fit_check import apply_scores

    report = apply_scores("agents", [_candidate("Paper", "10.1/a")], [], threshold=3)

    assert report.rejected[0].score == 0
    assert report.rejected[0].reason == "no score provided"


def test_term_overlap_detects_cluster_keywords_case_insensitive():
    from research_hub.fit_check import term_overlap

    overlap = term_overlap("This AGENT benchmark studies Software Engineering workflows.", ["agent", "software"])

    assert overlap == 1.0


def test_term_overlap_returns_zero_when_abstract_empty():
    from research_hub.fit_check import term_overlap

    assert term_overlap("", ["agent"]) == 0.0


def test_term_overlap_word_boundary_not_substring():
    from research_hub.fit_check import term_overlap

    assert term_overlap("Management systems only.", ["agent"]) == 0.0


def test_parse_nlm_off_topic_extracts_bulleted_list():
    from research_hub.fit_check import parse_nlm_off_topic

    briefing = "### Off-topic papers\n- Paper One — wrong cluster\n- Paper Two — unrelated\n"

    assert parse_nlm_off_topic(briefing) == ["Paper One", "Paper Two"]


def test_parse_nlm_off_topic_returns_empty_when_none():
    from research_hub.fit_check import parse_nlm_off_topic

    assert parse_nlm_off_topic("### Off-topic papers\nnone\n") == []


def test_parse_nlm_off_topic_returns_empty_when_missing_section():
    from research_hub.fit_check import parse_nlm_off_topic

    assert parse_nlm_off_topic("# Briefing\nNo audit section here.\n") == []


def test_parse_nlm_off_topic_tolerates_whitespace_and_dash_variants():
    from research_hub.fit_check import parse_nlm_off_topic

    briefing = "### Off-topic papers\n\n - Paper One -- wrong fit\n* Paper Two – tangential\n"

    assert parse_nlm_off_topic(briefing) == ["Paper One", "Paper Two"]


def test_drift_check_returns_prompt_for_ingested_papers(tmp_path, monkeypatch):
    from research_hub.fit_check import drift_check

    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "research_hub.topic.get_topic_digest",
        lambda cfg_arg, cluster_slug: SimpleNamespace(
            papers=[
                SimpleNamespace(title="Paper One", doi="10.1/one", abstract="A1", year=2024, authors=["Doe"]),
                SimpleNamespace(title="Paper Two", doi="10.1/two", abstract="A2", year=2024, authors=["Doe"]),
                SimpleNamespace(title="Paper Three", doi="10.1/three", abstract="A3", year=2024, authors=["Doe"]),
            ]
        ),
    )
    monkeypatch.setattr(
        "research_hub.topic.read_overview",
        lambda cfg_arg, cluster_slug: "## Definition\nSoftware engineering agents.\n",
    )

    result = drift_check(cfg, "agents", threshold=3)

    assert result["paper_count"] == 3
    assert "### 1. Paper One" in result["prompt"]
    assert "### 3. Paper Three" in result["prompt"]


def test_cli_fit_check_apply_respects_threshold_flag(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    candidates_path = tmp_path / "candidates.json"
    scored_path = tmp_path / "scored.json"
    candidates_path.write_text(json.dumps([_candidate("Paper", "10.1/a")]), encoding="utf-8")
    scored_path.write_text(
        json.dumps({"scores": [{"doi": "10.1/a", "score": 3, "reason": "borderline"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    rc = cli.main(
        [
            "fit-check",
            "apply",
            "--cluster",
            "agents",
            "--candidates",
            str(candidates_path),
            "--scored",
            str(scored_path),
            "--threshold",
            "4",
        ]
    )

    stdout = capsys.readouterr().out
    assert rc == 0
    assert stdout.strip() == "[]"


def test_cli_fit_check_apply_auto_threshold_flag(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    candidates_path = tmp_path / "candidates.json"
    scored_path = tmp_path / "scored.json"
    candidates_path.write_text(json.dumps([_candidate("Paper", "10.1/a")]), encoding="utf-8")
    scored_path.write_text(
        json.dumps({"scores": [{"doi": "10.1/a", "score": 3, "reason": "borderline"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    rc = cli.main(
        [
            "fit-check",
            "apply",
            "--cluster",
            "agents",
            "--candidates",
            str(candidates_path),
            "--scored",
            str(scored_path),
            "--threshold",
            "5",
            "--auto-threshold",
        ]
    )

    stdout = capsys.readouterr().out
    assert rc == 0
    assert '"score": 3' in stdout


def test_cli_fit_check_audit_exits_1_when_flags_present(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.notebooklm.upload.read_latest_briefing",
        lambda cluster_slug, cfg_arg: "### Off-topic papers\n- Paper One — unrelated\n",
    )

    rc = cli.main(["fit-check", "audit", "--cluster", "agents"])
    sidecar = cfg.hub / "agents" / ".fit_check_nlm_flags.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))

    assert rc == 1
    assert payload["flagged"] == ["Paper One"]
