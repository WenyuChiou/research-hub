import json
import re
from pathlib import Path

import pytest

from research_hub.fit_check import emit_prompt, term_overlap


def _seed_keywords() -> list[str]:
    path = Path("src/research_hub/examples/cs_swe.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["query"].lower().split()


def _extract_abstract_block(prompt: str, title: str) -> str:
    pattern = re.compile(
        rf"### \d+\. {re.escape(title)}\n.*?\n\*\*Abstract:\*\*\n(.*?)(?:\n### \d+\. |\n## Your output)",
        re.DOTALL,
    )
    match = pattern.search(prompt)
    if match is None:
        raise AssertionError(f"abstract block for {title!r} not found")
    return match.group(1).strip()


@pytest.mark.evals
def test_term_overlap_correlates_with_acceptance(live_cluster_sidecars, metrics_collector):
    """Accepted papers should have higher mean term_overlap than rejected."""
    key_terms = _seed_keywords()
    accepted_entries = live_cluster_sidecars["accepted"].get("accepted", [])
    rejected_entries = live_cluster_sidecars["rejected"].get("rejected", [])
    if not accepted_entries or not rejected_entries:
        pytest.skip("need both accepted and rejected sidecars to compare overlap")

    accepted_scores = [term_overlap(entry.get("reason", ""), key_terms) for entry in accepted_entries]
    rejected_scores = [term_overlap(entry.get("reason", ""), key_terms) for entry in rejected_entries]
    accepted_mean = sum(accepted_scores) / len(accepted_scores)
    rejected_mean = sum(rejected_scores) / len(rejected_scores)
    metrics_collector.record("term_overlap_mean", "accepted", accepted_mean)
    metrics_collector.record("term_overlap_mean", "rejected", rejected_mean)
    assert accepted_mean > rejected_mean


@pytest.mark.evals
def test_abstract_length_not_silent_truncated():
    """emit_prompt should not truncate abstracts mid-sentence."""
    papers = [
        {"title": "Short Paper", "abstract": "A short abstract.", "year": 2024, "doi": "10.1/short"},
        {"title": "Medium Paper", "abstract": "Sentence one. " * 35, "year": 2024, "doi": "10.1/medium"},
        {"title": "Long Paper", "abstract": "Long sentence. " * 140, "year": 2024, "doi": "10.1/long"},
    ]
    prompt = emit_prompt("llm-agents-software-engineering", papers, definition="Software engineering agents.")
    for paper in papers:
        abstract = _extract_abstract_block(prompt, paper["title"])
        assert abstract == paper["abstract"].strip()
        assert abstract.endswith((".", "!", "?"))


@pytest.mark.evals
def test_empty_abstract_handled_gracefully():
    """Paper with empty abstract should render (no abstract) marker."""
    prompt = emit_prompt(
        "llm-agents-software-engineering",
        [{"title": "No Abstract", "abstract": "", "year": 2024, "doi": "10.1/none"}],
        definition="Software engineering agents.",
    )
    assert "**Abstract:**" in prompt
    assert "(no abstract)" in prompt
