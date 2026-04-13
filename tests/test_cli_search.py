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
    assert payload["papers"][0]["sub_category"] == "foo-bar"
    assert payload["papers"][0]["slug"]


def test_cli_search_year_range_parses_2024_2025():
    assert _parse_year_range("2024-2025") == (2024, 2025)


def test_cli_search_year_range_parses_open_ended():
    assert _parse_year_range("2024-") == (2024, None)
    assert _parse_year_range("-2024") == (None, 2024)
    assert _parse_year_range("2024") == (2024, 2024)


def test_cli_search_year_range_invalid_raises_systemexit():
    with pytest.raises(SystemExit):
        _parse_year_range("2024-2025-2026")


def test_cli_search_backend_flag_splits_comma_list(monkeypatch):
    captured = {}

    def fake_search(query, limit, verify=False, **kwargs):
        captured["query"] = query
        captured["backends"] = kwargs["backends"]
        return 0

    monkeypatch.setattr("research_hub.cli._search", fake_search)

    assert main(["search", "llm", "--backend", "openalex,arxiv"]) == 0
    assert captured["query"] == "llm"
    assert captured["backends"] == ("openalex", "arxiv")
