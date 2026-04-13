from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.examples import copy_example_as_cluster, list_examples, load_example
from research_hub.onboarding import run_field_wizard


@dataclass
class StubConfig:
    root: Path
    raw: Path
    research_hub_dir: Path
    clusters_file: Path


def make_config(tmp_path: Path) -> StubConfig:
    root = tmp_path / "vault"
    raw = root / "raw"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return StubConfig(
        root=root,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def test_run_field_wizard_non_interactive_creates_cluster(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)

    class State:
        candidate_count = 7

    monkeypatch.setattr("research_hub.discover.discover_new", lambda *args, **kwargs: (State(), "prompt"))

    result = run_field_wizard(
        cfg,
        field="cs",
        cluster_slug="llm-agents",
        cluster_name="LLM Agents",
        query="LLM agent benchmark",
        definition="A cluster for agent benchmarks.",
        non_interactive=True,
    )

    cluster = ClusterRegistry(cfg.clusters_file).get("llm-agents")
    assert cluster is not None
    assert cluster.name == "LLM Agents"
    assert result.candidate_count == 7


def test_run_field_wizard_non_interactive_requires_all_fields(tmp_path):
    cfg = make_config(tmp_path)

    with pytest.raises(ValueError, match="non-interactive mode requires"):
        run_field_wizard(cfg, field="cs", cluster_slug="x", non_interactive=True)


def test_run_field_wizard_unknown_field_raises_valueerror(tmp_path):
    cfg = make_config(tmp_path)

    with pytest.raises(ValueError, match="unknown field"):
        run_field_wizard(
            cfg,
            field="unknown",
            cluster_slug="x",
            cluster_name="X",
            query="test",
            non_interactive=True,
        )


def test_run_field_wizard_uses_default_when_input_blank(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)
    answers = iter(["", "", "LLM agent benchmark", ""])

    class State:
        candidate_count = 2

    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("research_hub.discover.discover_new", lambda *args, **kwargs: (State(), "prompt"))

    result = run_field_wizard(cfg, field="cs")

    assert result.cluster_name == "CS cluster"
    assert result.cluster_slug == "cs-cluster"
    assert result.definition == ""


def test_run_field_wizard_invokes_discover_new(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)
    captured = {}

    class State:
        candidate_count = 4

    def fake_discover_new(cfg_arg, cluster_slug, query, **kwargs):
        captured["cfg"] = cfg_arg
        captured["cluster_slug"] = cluster_slug
        captured["query"] = query
        captured["kwargs"] = kwargs
        return State(), "prompt"

    monkeypatch.setattr("research_hub.discover.discover_new", fake_discover_new)

    run_field_wizard(
        cfg,
        field="bio",
        cluster_slug="protein-folding",
        cluster_name="Protein Folding",
        query="protein structure prediction",
        definition="Protein structures",
        non_interactive=True,
    )

    assert captured["cfg"] == cfg
    assert captured["cluster_slug"] == "protein-folding"
    assert captured["query"] == "protein structure prediction"
    assert captured["kwargs"]["field"] == "bio"


def test_run_field_wizard_returns_next_steps_with_cluster_slug(monkeypatch, tmp_path):
    cfg = make_config(tmp_path)

    class State:
        candidate_count = 5

    monkeypatch.setattr("research_hub.discover.discover_new", lambda *args, **kwargs: (State(), "prompt"))

    result = run_field_wizard(
        cfg,
        field="edu",
        cluster_slug="writing-assessment",
        cluster_name="Writing Assessment",
        query="automated writing assessment llm",
        non_interactive=True,
    )

    assert all("writing-assessment" in step or "scored.json" in step for step in result.next_steps)


def test_examples_list_returns_4_bundled_examples():
    examples = list_examples()

    assert len(examples) == 4
    assert {item["field"] for item in examples} == {"cs", "bio", "social", "edu"}


def test_examples_load_example_unknown_raises_filenotfounderror():
    with pytest.raises(FileNotFoundError, match="unknown example"):
        load_example("missing")


def test_examples_copy_creates_cluster_in_registry(tmp_path):
    cfg = make_config(tmp_path)

    slug = copy_example_as_cluster(cfg, "cs_swe", cluster_slug="test-swe")

    cluster = ClusterRegistry(cfg.clusters_file).get("test-swe")
    assert slug == "test-swe"
    assert cluster is not None
    assert cluster.first_query


def test_examples_copy_existing_cluster_raises_valueerror(tmp_path):
    cfg = make_config(tmp_path)
    copy_example_as_cluster(cfg, "cs_swe", cluster_slug="test-swe")

    with pytest.raises(ValueError, match="already exists"):
        copy_example_as_cluster(cfg, "cs_swe", cluster_slug="test-swe")
