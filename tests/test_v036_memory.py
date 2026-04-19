"""v0.36 cluster memory layer tests."""

from __future__ import annotations

import json

import pytest

from tests._persona_factory import make_persona_vault


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch):
    monkeypatch.setattr("research_hub.config._resolve_config_path", lambda: None)


def _seed_vault(tmp_path):
    cfg, meta = make_persona_vault(tmp_path, persona="A")
    return cfg, meta["cluster_slug"]


def _first_paper_slug(cfg, cluster_slug: str) -> str:
    from research_hub.crystal import _read_cluster_papers

    papers = _read_cluster_papers(cfg, cluster_slug)
    assert papers, "persona factory should seed papers"
    return papers[0]["slug"]


def test_emit_memory_prompt_includes_papers(tmp_path):
    from research_hub.memory import emit_memory_prompt

    cfg, cluster_slug = _seed_vault(tmp_path)
    prompt = emit_memory_prompt(cfg, cluster_slug)
    assert "Papers in cluster" in prompt
    assert "entities" in prompt and "claims" in prompt and "methods" in prompt
    assert "JSON" in prompt


def test_emit_memory_prompt_unknown_cluster_raises(tmp_path):
    from research_hub.memory import emit_memory_prompt

    cfg, _cluster_slug = _seed_vault(tmp_path)
    with pytest.raises(ValueError, match="unknown cluster"):
        emit_memory_prompt(cfg, "does-not-exist")


def test_apply_memory_writes_json(tmp_path):
    from research_hub.memory import apply_memory, memory_path

    cfg, cluster_slug = _seed_vault(tmp_path)
    paper_slug = _first_paper_slug(cfg, cluster_slug)
    payload = {
        "generator": "test",
        "entities": [{"slug": "openai", "name": "OpenAI", "type": "org", "papers": [paper_slug]}],
        "claims": [{
            "slug": "rlhf-helps",
            "text": "RLHF helps.",
            "confidence": "high",
            "papers": [paper_slug],
            "related_entities": ["openai"],
        }],
        "methods": [{"slug": "rlhf", "name": "RLHF", "family": "rl", "papers": [paper_slug]}],
    }

    result = apply_memory(cfg, cluster_slug, payload)
    assert result.entity_count == 1
    assert result.claim_count == 1
    assert result.method_count == 1

    written = memory_path(cfg, cluster_slug)
    assert written.exists()
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["entities"][0]["slug"] == "openai"
    assert data["claims"][0]["related_entities"] == ["openai"]


def test_apply_memory_filters_unknown_paper_slugs(tmp_path):
    from research_hub.memory import apply_memory, read_memory

    cfg, cluster_slug = _seed_vault(tmp_path)
    paper_slug = _first_paper_slug(cfg, cluster_slug)
    payload = {
        "generator": "test",
        "entities": [{
            "slug": "openai",
            "name": "OpenAI",
            "type": "org",
            "papers": ["not-in-cluster", paper_slug],
        }],
    }

    apply_memory(cfg, cluster_slug, payload)
    memory = read_memory(cfg, cluster_slug)
    assert memory is not None
    assert memory.entities[0].papers == [paper_slug]


def test_apply_memory_rejects_invalid_slugs(tmp_path):
    from research_hub.memory import apply_memory, read_memory

    cfg, cluster_slug = _seed_vault(tmp_path)
    paper_slug = _first_paper_slug(cfg, cluster_slug)
    payload = {
        "entities": [{"slug": "Open AI", "name": "OpenAI", "type": "org", "papers": [paper_slug]}],
        "claims": [{"slug": "Bad Slug", "text": "Claim text.", "papers": [paper_slug]}],
        "methods": [{"slug": "Method Name", "name": "Method", "family": "other", "papers": [paper_slug]}],
    }

    result = apply_memory(cfg, cluster_slug, payload)
    memory = read_memory(cfg, cluster_slug)
    assert memory is not None
    assert memory.entities == []
    assert memory.claims == []
    assert memory.methods == []
    assert len(result.errors) == 3


def test_apply_memory_dedups_within_each_kind(tmp_path):
    from research_hub.memory import apply_memory, read_memory

    cfg, cluster_slug = _seed_vault(tmp_path)
    paper_slug = _first_paper_slug(cfg, cluster_slug)
    payload = {
        "entities": [
            {"slug": "openai", "name": "OpenAI", "type": "org", "papers": [paper_slug]},
            {"slug": "openai", "name": "OpenAI 2", "type": "org", "papers": [paper_slug]},
        ],
        "claims": [
            {"slug": "claim-one", "text": "Claim one.", "papers": [paper_slug]},
            {"slug": "claim-one", "text": "Claim two.", "papers": [paper_slug]},
        ],
        "methods": [
            {"slug": "rlhf", "name": "RLHF", "family": "rl", "papers": [paper_slug]},
            {"slug": "rlhf", "name": "RLHF 2", "family": "rl", "papers": [paper_slug]},
        ],
    }

    result = apply_memory(cfg, cluster_slug, payload)
    memory = read_memory(cfg, cluster_slug)
    assert memory is not None
    assert [entity.slug for entity in memory.entities] == ["openai"]
    assert [claim.slug for claim in memory.claims] == ["claim-one"]
    assert [method.slug for method in memory.methods] == ["rlhf"]
    assert len(result.errors) == 3


def test_apply_memory_skips_claims_with_no_supporting_papers(tmp_path):
    from research_hub.memory import apply_memory, read_memory

    cfg, cluster_slug = _seed_vault(tmp_path)
    payload = {
        "claims": [{
            "slug": "unsupported-claim",
            "text": "This is unsupported.",
            "papers": ["not-in-cluster"],
        }]
    }

    result = apply_memory(cfg, cluster_slug, payload)
    memory = read_memory(cfg, cluster_slug)
    assert memory is not None
    assert memory.claims == []
    assert any("no valid supporting papers" in error for error in result.errors)


def test_apply_memory_normalizes_invalid_confidence(tmp_path):
    from research_hub.memory import apply_memory, read_memory

    cfg, cluster_slug = _seed_vault(tmp_path)
    paper_slug = _first_paper_slug(cfg, cluster_slug)
    payload = {
        "claims": [{
            "slug": "rlhf-helps",
            "text": "RLHF helps.",
            "confidence": "banana",
            "papers": [paper_slug],
        }]
    }

    apply_memory(cfg, cluster_slug, payload)
    memory = read_memory(cfg, cluster_slug)
    assert memory is not None
    assert memory.claims[0].confidence == "medium"


def test_read_memory_round_trips(tmp_path):
    from research_hub.memory import apply_memory, read_memory

    cfg, cluster_slug = _seed_vault(tmp_path)
    paper_slug = _first_paper_slug(cfg, cluster_slug)
    payload = {
        "generator": "test-model",
        "entities": [{"slug": "openai", "name": "OpenAI", "type": "org", "papers": [paper_slug]}],
        "claims": [{
            "slug": "rlhf-helps",
            "text": "RLHF helps.",
            "confidence": "high",
            "papers": [paper_slug],
            "related_entities": ["openai"],
        }],
        "methods": [{
            "slug": "rlhf",
            "name": "Reinforcement Learning from Human Feedback",
            "family": "rl",
            "papers": [paper_slug],
            "description": "Reward model plus PPO.",
        }],
    }

    apply_memory(cfg, cluster_slug, payload)
    memory = read_memory(cfg, cluster_slug)
    assert memory is not None
    assert len(memory.entities) == 1
    assert len(memory.claims) == 1
    assert len(memory.methods) == 1
    assert memory.generator == "test-model"
    assert memory.based_on_paper_count == 3


def test_read_memory_returns_none_when_missing(tmp_path):
    from research_hub.memory import read_memory

    cfg, cluster_slug = _seed_vault(tmp_path)
    (cfg.hub / cluster_slug / "memory.json").unlink()
    assert read_memory(cfg, cluster_slug) is None


def test_list_entities_claims_methods_helpers(tmp_path):
    from research_hub.memory import apply_memory, list_claims, list_entities, list_methods

    cfg, cluster_slug = _seed_vault(tmp_path)
    paper_slug = _first_paper_slug(cfg, cluster_slug)
    payload = {
        "entities": [{"slug": "openai", "name": "OpenAI", "type": "org", "papers": [paper_slug]}],
        "claims": [{"slug": "rlhf-helps", "text": "RLHF helps.", "papers": [paper_slug]}],
        "methods": [{"slug": "rlhf", "name": "RLHF", "family": "rl", "papers": [paper_slug]}],
    }

    apply_memory(cfg, cluster_slug, payload)
    assert len(list_entities(cfg, cluster_slug)) == 1
    assert len(list_claims(cfg, cluster_slug)) == 1
    assert len(list_methods(cfg, cluster_slug)) == 1


def test_apply_memory_handles_empty_payload(tmp_path):
    from research_hub.memory import apply_memory, read_memory

    cfg, cluster_slug = _seed_vault(tmp_path)
    result = apply_memory(cfg, cluster_slug, {})
    memory = read_memory(cfg, cluster_slug)
    assert memory is not None
    assert result.entity_count == 0
    assert result.claim_count == 0
    assert result.method_count == 0
    assert memory.entities == []
    assert memory.claims == []
    assert memory.methods == []
