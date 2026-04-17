from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_hub.cli import _parse_year_range, main
from research_hub.dedup import DedupIndex
from research_hub.search import SearchResult


class _Cfg:
    def __init__(self, root: Path) -> None:
        self.research_hub_dir = root / ".research_hub"
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _setup_cfg(tmp_path: Path) -> _Cfg:
    cfg = _Cfg(tmp_path)
    DedupIndex().save(cfg.research_hub_dir / "dedup_index.json")
    return cfg


def test_cli_search_json_flag_emits_valid_json(tmp_path, monkeypatch, capsys):
    cfg = _setup_cfg(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.search.search_papers",
        lambda *args, **kwargs: [
            SearchResult(title="Paper 1", doi="10.1/a", source="openalex"),
            SearchResult(title="Paper 2", arxiv_id="2411.12345", source="arxiv"),
        ],
    )

    assert main(["search", "llm", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 2


def test_cli_search_to_papers_input_produces_ingest_ready_shape(tmp_path, monkeypatch, capsys):
    cfg = _setup_cfg(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.search.search_papers",
        lambda *args, **kwargs: [
            SearchResult(
                title="Paper 1",
                doi="10.1/a",
                authors=["Jane Doe"],
                year=2024,
                abstract="Abstract",
                venue="Venue",
                source="openalex",
            )
        ],
    )

    assert main(["search", "llm", "--to-papers-input", "--cluster", "foo-bar"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert payload[0]["sub_category"] == "foo-bar"
    assert payload[0]["slug"]
    assert payload[0]["authors"][0]["lastName"] == "Doe"
    assert payload[0]["summary"].startswith("[TODO]")


def test_cli_search_year_range_parses_2024_2025():
    assert _parse_year_range("2024-2025") == (2024, 2025)


def test_cli_search_year_range_parses_open_ended():
    assert _parse_year_range("2024-") == (2024, None)
    assert _parse_year_range("-2024") == (None, 2024)
    assert _parse_year_range("2024") == (2024, 2024)


def test_cli_search_year_range_invalid_raises_systemexit():
    with pytest.raises(SystemExit):
        _parse_year_range("2024-2025-2026")


def test_cli_search_backend_flag_splits_comma_list(monkeypatch, mock_require_config):
    captured = {}

    def fake_search(query, limit, verify=False, **kwargs):
        captured["query"] = query
        captured["backends"] = kwargs["backends"]
        return 0

    monkeypatch.setattr("research_hub.cli._search", fake_search)

    assert main(["search", "llm", "--backend", "openalex,arxiv"]) == 0
    assert captured["query"] == "llm"
    assert captured["backends"] == ("openalex", "arxiv")


def test_cli_search_field_flag_uses_preset(monkeypatch, mock_require_config):
    captured = {}

    def fake_search(query, limit, verify=False, **kwargs):
        captured["backends"] = kwargs["backends"]
        return 0

    monkeypatch.setattr("research_hub.cli._search", fake_search)

    assert main(["search", "llm", "--field", "bio"]) == 0
    assert captured["backends"] == ("openalex", "pubmed", "biorxiv", "crossref", "semantic-scholar")


def test_cli_search_region_flag_uses_preset(monkeypatch):
    captured = {}

    def fake_search(query, limit, verify=False, **kwargs):
        captured["backends"] = kwargs["backends"]
        return 0

    monkeypatch.setattr("research_hub.cli._search", fake_search)

    assert main(["search", "llm", "--region", "jp"]) == 0
    assert captured["backends"] == ("openalex", "cinii", "crossref")


def test_cli_search_field_and_backend_mutually_exclusive():
    with pytest.raises(SystemExit):
        main(["search", "llm", "--backend", "openalex", "--field", "bio"])


def test_cli_search_region_field_backend_mutex():
    for argv in (
        ["search", "llm", "--region", "jp", "--field", "bio"],
        ["search", "llm", "--region", "jp", "--backend", "openalex"],
    ):
        with pytest.raises(SystemExit):
            main(argv)


def test_cli_search_forwards_new_filter_and_rank_flags(monkeypatch):
    captured = {}

    def fake_search(query, limit, verify=False, **kwargs):
        captured["exclude_types"] = kwargs["exclude_types"]
        captured["exclude_terms"] = kwargs["exclude_terms"]
        captured["min_confidence"] = kwargs["min_confidence"]
        captured["rank_by"] = kwargs["rank_by"]
        captured["backend_trace"] = kwargs["backend_trace"]
        return 0

    monkeypatch.setattr("research_hub.cli._search", fake_search)

    assert main(
        [
            "search",
            "llm",
            "--exclude-type",
            "report,book-chapter",
            "--exclude",
            "ipcc lancet",
            "--min-confidence",
            "0.75",
            "--rank-by",
            "year",
            "--backend-trace",
        ]
    ) == 0

    assert captured["exclude_types"] == ("report", "book-chapter")
    assert captured["exclude_terms"] == ("ipcc", "lancet")
    assert captured["min_confidence"] == 0.75
    assert captured["rank_by"] == "year"
    assert captured["backend_trace"] is True
