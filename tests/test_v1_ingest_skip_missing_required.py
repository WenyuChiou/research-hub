"""PR-C: ingest skips a paper missing one or more REQUIRED_FIELDS_CORE
(title/authors/year) instead of aborting the whole batch.

Pre-PR-C the pipeline already skipped papers whose ONLY error was a
missing DOI; this PR generalises that escape to every required core
field. Real-world trigger: a CrossRef record returned with an empty
``authors: []`` (editorial materials / metadata not yet author-registered)
would otherwise fail-fast the entire `auto` run, even when the rest of
the candidates are valid.

The escape is strictly real-run -- dry-run still surfaces every
validation issue so the operator sees the full picture.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub import pipeline
from research_hub.clusters import ClusterRegistry
from research_hub.pipeline import (
    _only_missing_required_field_errors,
    _validate_paper_input,
    run_pipeline,
)


# --- unit: predicate ---


def test_only_missing_required_field_errors_empty_returns_false():
    """No errors means no classification (the caller's `paper_errors`
    truthiness check fires first; this predicate only meaningful for a
    populated list)."""
    assert _only_missing_required_field_errors([]) is False


def test_only_missing_required_field_errors_single_match_returns_true():
    assert _only_missing_required_field_errors(
        ["Paper 0: missing required field 'authors' - add 'authors: <value>' ..."]
    ) is True


def test_only_missing_required_field_errors_multiple_all_match_returns_true():
    """A paper missing title AND authors AND year is still all-classifiable
    as missing-required — skip it cleanly."""
    assert _only_missing_required_field_errors(
        [
            "Paper 3: missing required field 'title' - ...",
            "Paper 3: missing required field 'authors' - ...",
            "Paper 3: missing required field 'year' - ...",
        ]
    ) is True


def test_only_missing_required_field_errors_mixed_returns_false():
    """If even one error is a non-missing-required (e.g., a dict-author
    shape error), the paper should NOT be silently skipped — the
    operator needs to see it as fatal."""
    assert _only_missing_required_field_errors(
        [
            "Paper 0: missing required field 'authors' - ...",
            "Paper 0, author 0: dict authors must have 'creatorType' ...",
        ]
    ) is False


def test_only_missing_required_field_errors_non_required_only_returns_false():
    assert _only_missing_required_field_errors(
        ["Paper 0: 'authors' must be a list"]
    ) is False


# --- composition: real _validate_paper_input output flows into the predicate ---


def test_validator_for_empty_paper_yields_mixed_errors_predicate_false():
    """Anti-overreach guard: an empty paper dict produces missing-required
    errors for the 3 core fields PLUS "missing field '...'" errors for
    non-required-but-still-validated fields (methodology/summary/...).
    The mixed error set must NOT classify as "skippable as a whole" —
    the operator needs to see the fatal validation failure."""
    errors = _validate_paper_input({}, 0)
    assert any("missing required field 'title'" in e for e in errors)
    assert any("missing required field 'authors'" in e for e in errors)
    assert any("missing required field 'year'" in e for e in errors)
    has_non_required = any(
        "missing field '" in e and "missing required field" not in e
        for e in errors
    )
    assert has_non_required, "empty dict should also trip non-required-field checks"
    # Predicate returns False because non-required errors are mixed in.
    assert _only_missing_required_field_errors(errors) is False


def test_validator_for_empty_authors_list_yields_missing_required_authors():
    """A real-world CrossRef return: every required field present except
    authors=[]. The validator must report ONLY missing-authors so the
    predicate skips it cleanly (no surprise extra errors that would
    make it fatal)."""
    paper = {
        "title": "Paper",
        "doi": "10.1/x",
        "authors": [],          # empty list -> treated as missing
        "year": 2025,
        "abstract": "Abstract",
        "journal": "Journal",
        "summary": "Summary",
        "key_findings": ["One"],
        "methodology": "Method",
        "relevance": "Relevant",
    }
    errors = _validate_paper_input(paper, 0)
    # filter to just the required-core errors:
    core_errors = [e for e in errors if "missing required field" in e]
    assert any("'authors'" in e for e in core_errors)
    # The whole error set must be all-missing-required for the skip
    # path to fire (any other error class would mark it fatal).
    assert _only_missing_required_field_errors(errors) is True


# --- integration: mixed batch with 1 valid + 1 missing-authors paper ---


def _cfg(tmp_path: Path, *, default_collection: str | None = "DEFAULT") -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    logs = root / "logs"
    hub = root / ".research_hub"
    raw.mkdir(parents=True)
    logs.mkdir(parents=True)
    hub.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        logs=logs,
        research_hub_dir=hub,
        clusters_file=hub / "clusters.yaml",
        zotero_default_collection=default_collection,
        zotero_collections={},
        zotero_library_id="123",
    )


def _valid_paper(idx: int) -> dict:
    return {
        "title": f"Valid Paper {idx}",
        "doi": f"10.1000/valid-{idx}",
        "authors": [{"creatorType": "author", "lastName": "Doe", "firstName": "Jane"}],
        "year": 2026,
        "abstract": "Abstract",
        "journal": "Journal",
        "summary": "Summary",
        "key_findings": ["Finding"],
        "methodology": "Method",
        "relevance": "Relevant",
        "slug": f"doe2026-valid-paper-{idx}",
        "sub_category": "agents",
        "citation_count": 1,
    }


def _no_authors_paper() -> dict:
    return {
        "title": "Missing Authors Paper",
        "doi": "10.31673/2412-9070.2026.028906",  # the real culprit from the LLM-reservoir run
        "authors": [],
        "year": 2026,
        "abstract": "Abstract",
        "journal": "Connectivity",
        "summary": "Summary",
        "key_findings": ["Finding"],
        "methodology": "Method",
        "relevance": "Relevant",
        "slug": "unknown2026-missing-authors-paper",
        "sub_category": "agents",
        "citation_count": 1,
    }


class _FastZotero:
    def __init__(self) -> None:
        self.created: list[list[dict]] = []

    def item_template(self, item_type: str) -> dict:
        return {"itemType": item_type}

    def create_items(self, items):  # type: ignore[no-untyped-def]
        self.created.append(items)
        return {
            "successful": {
                str(idx): {"key": f"K{idx}"} for idx, _item in enumerate(items)
            }
        }


def _mock_zotero(monkeypatch: pytest.MonkeyPatch) -> _FastZotero:
    z = _FastZotero()
    monkeypatch.setattr(pipeline, "get_client", lambda: z)
    monkeypatch.setattr(
        pipeline, "check_duplicate",
        lambda zot, title, doi="", **kwargs: False,
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(
        pipeline, "_load_or_build_dedup",
        lambda *args, **kwargs: SimpleNamespace(
            doi_to_hits={},
            title_to_hits={},
            check=lambda payload: (False, []),
            add=lambda hit: None,
            save=lambda path: None,
        ),
    )
    monkeypatch.setattr("research_hub.pipeline.time.sleep", lambda seconds: None)
    monkeypatch.setattr(
        "research_hub.pipeline.update_cluster_links",
        lambda *args, **kwargs: None,
    )
    return z


def test_mixed_batch_skips_no_authors_paper_and_ingests_valid_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CrossRef-no-authors paper is skipped; the valid paper still
    writes to Zotero. Without PR-C the run aborts with exit code 1
    and 0 papers ingested."""
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents",
        zotero_collection_key="DEFAULT",
    )
    payload = {"papers": [_valid_paper(1), _no_authors_paper(), _valid_paper(2)]}
    (cfg.root / "papers_input.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    z = _mock_zotero(monkeypatch)

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)

    # PR-C: batch must NOT abort with the no-authors paper; the 2 valid
    # papers are passed to Zotero.
    assert rc == 0
    # Zotero received some items (the 2 valid papers).
    assert z.created, "expected at least one create_items call for valid papers"
    created_titles = {
        item.get("title") for batch in z.created for item in batch
        if isinstance(item, dict)
    }
    assert "Valid Paper 1" in created_titles
    assert "Valid Paper 2" in created_titles
    # The no-authors paper must NOT have been created.
    assert "Missing Authors Paper" not in created_titles
    # The SKIP message must appear in pipeline_log.txt.
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "SKIPPED invalid input" in log_text
    assert "Missing Authors Paper" in log_text


def test_pure_valid_batch_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a fully-valid batch keeps the existing happy path
    (no spurious skips logged)."""
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents",
        zotero_collection_key="DEFAULT",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps({"papers": [_valid_paper(1)]}), encoding="utf-8",
    )
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    _mock_zotero(monkeypatch)

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)

    assert rc == 0
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "INPUT VALIDATION FAILED" not in log_text
    assert "SKIPPED invalid input" not in log_text


def test_dry_run_does_not_skip_missing_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PR-C escape is real-run only. In dry-run, every validation
    issue must surface so the operator sees the full picture."""
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents",
        zotero_collection_key="DEFAULT",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps({"papers": [_valid_paper(1), _no_authors_paper()]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    _mock_zotero(monkeypatch)

    rc = run_pipeline(dry_run=True, cluster_slug="agents", verify=False)

    # Dry-run still surfaces the validation failure as a non-zero exit
    # (existing strict behaviour preserved).
    assert rc == 1
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "INPUT VALIDATION FAILED" in log_text or "missing required field" in log_text
