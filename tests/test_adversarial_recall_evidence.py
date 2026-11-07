"""Offline regressions: returned-result counts do not establish literature recall.

The production orchestrator and Crossref backend run; only query expansion and
HTTP responses are controlled. These tests are not live searches or a scientific
assessment of closest/contrary-work coverage.
"""

import json

import pytest
import requests
import responses

from research_hub.audit import audit_command
from research_hub.search.fallback import adversarial_search


_URL = "https://api.crossref.org/works"
_WORK = {"DOI": "10.1234/fixture", "title": ["Synthetic test paper"]}


def _payload(items):
    return {"message": {"total-results": 100, "items": items}}


@responses.activate
@pytest.mark.parametrize("audit_enabled", [False, True])
@pytest.mark.parametrize("later", ["rate_limit", "timeout", "invalid_json", "empty", "same_top_result"])
def test_late_query_yield_never_establishes_recall(monkeypatch, tmp_path, later, audit_enabled):
    monkeypatch.setattr(
        "research_hub.search.query_expansion.expand_query",
        lambda *args, **kwargs: ["original wording", "alternative wording"],
    )
    responses.get(_URL, json=_payload([_WORK]))
    if later == "rate_limit":
        responses.get(_URL, status=429, json={"message": "rate limited"})
    elif later == "timeout":
        responses.get(_URL, body=requests.Timeout("synthetic timeout"))
    elif later == "invalid_json":
        responses.get(_URL, body="not JSON", content_type="application/json")
    else:
        responses.get(_URL, json=_payload([_WORK] if later == "same_top_result" else []))

    audit_dir = tmp_path / "audit" if audit_enabled else None
    with audit_command(audit_dir, ["search", "synthetic question"]) as command:
        results, report = adversarial_search(
            "synthetic question", limit=1, per_query_limit=1,
            per_backend_limit=1, backends=("crossref",),
        )
        command.exit_code = 0

    assert len(responses.calls) == 2  # The real search path attempted both requests.
    assert [result.doi for result in results] == ["10.1234/fixture"]
    assert report.variants == ["original wording", "alternative wording"]
    assert report.new_per_query == [1, 0]
    assert report.total_unique == 1
    assert report.confidence == "unassessed"
    assert report.saturated is False
    if audit_enabled:
        # Preserve actual HTTP/parse distinctions instead of reclassifying errors
        # as a successful empty search. An audit proves execution, not recall.
        events = [json.loads(line) for line in (audit_dir / "events.jsonl").read_text().splitlines()]
        backend_outcomes = [
            event["outcome"] for event in events
            if event["event"] == "finished" and event["operation"] == "backend-search"
        ]
        expected = {
            "rate_limit": "rate_limited", "timeout": "timeout",
            "invalid_json": "parse_error", "empty": "success_empty",
            "same_top_result": "success",
        }
        assert backend_outcomes == ["success", expected[later]]


@responses.activate
@pytest.mark.parametrize("audit_enabled", [False, True])
def test_cli_preserves_results_and_discloses_unassessed_recall(
    monkeypatch, tmp_path, capsys, audit_enabled
):
    from research_hub.cli import main
    from research_hub.dedup import DedupIndex

    class Config:
        research_hub_dir = tmp_path / "workspace"

    Config.research_hub_dir.mkdir()
    DedupIndex().save(Config.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr("research_hub.cli.get_config", lambda: Config())
    monkeypatch.setattr(
        "research_hub.search.query_expansion.expand_query",
        lambda *args, **kwargs: ["original wording", "alternative wording"],
    )
    responses.get(_URL, json=_payload([_WORK]))
    responses.get(_URL, status=429, json={"message": "rate limited"})
    args = ["search", "synthetic question", "--backend", "crossref", "--adversarial", "--json"]
    if audit_enabled:
        args.extend(["--audit-output", str(tmp_path / "audit")])
    assert main(args) == 0  # Partial-result CLI behavior is unchanged.
    captured = capsys.readouterr()
    assert [row["doi"] for row in json.loads(captured.out)] == ["10.1234/fixture"]
    assert "2 query phrasings attempted" in captured.err
    assert "1 unique returned papers" in captured.err
    assert "new_per_query=[1, 0]" in captured.err
    assert "confidence=unassessed" in captured.err
    assert "literature coverage not verified" in captured.err
    assert "saturated" not in captured.err
    assert len(responses.calls) == 2


def test_gap_skill_mirrors_keep_recall_evidence_boundary():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = root / "skills" / "gap-to-topic"
    packaged = root / "src" / "research_hub" / "skills_data" / "gap-to-topic"
    for relative in ("SKILL.md", "evals/evals.json"):
        assert (source / relative).read_bytes() == (packaged / relative).read_bytes()
    skill = (source / "SKILL.md").read_text(encoding="utf-8")
    assert "recall explicitly `unassessed`" in skill
    assert "these counts do not establish saturation" in skill
    assert "recall-confidence verdict" not in skill
    evals = json.loads((source / "evals/evals.json").read_text(encoding="utf-8"))
    case = next(case for case in evals["evals"] if case["prompt"] == "Has someone already done this idea?")
    assert "unassessed recall" in case["expected_behavior"]
    assert "closest and contrary work" in case["expected_behavior"]
