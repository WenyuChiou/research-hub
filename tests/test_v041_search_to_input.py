from __future__ import annotations

import json
from pathlib import Path

from research_hub.cli import main
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


def test_search_to_papers_input_includes_arxiv_id_and_derived_doi(tmp_path, monkeypatch, capsys):
    cfg = _setup_cfg(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.search.search_papers",
        lambda *args, **kwargs: [
            SearchResult(
                title="Arxiv Only",
                arxiv_id="2604.08224",
                authors=["Jane Doe"],
                year=2026,
                abstract="Abstract",
                venue="arXiv",
                source="arxiv",
            )
        ],
    )

    assert main(["search", "llm", "--to-papers-input", "--cluster", "agents"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["arxiv_id"] == "2604.08224"
    assert payload[0]["doi"] == "10.48550/arxiv.2604.08224"


def test_search_to_papers_input_preserves_real_doi_over_derived(tmp_path, monkeypatch, capsys):
    cfg = _setup_cfg(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.search.search_papers",
        lambda *args, **kwargs: [
            SearchResult(
                title="Arxiv And DOI",
                doi="10.1000/real",
                arxiv_id="2604.08224",
                authors=["Jane Doe"],
                year=2026,
                abstract="Abstract",
                venue="arXiv",
                source="openalex",
            )
        ],
    )

    assert main(["search", "llm", "--to-papers-input"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["arxiv_id"] == "2604.08224"
    assert payload[0]["doi"] == "10.1000/real"


def test_search_to_papers_input_non_arxiv_unchanged(tmp_path, monkeypatch, capsys):
    cfg = _setup_cfg(tmp_path)
    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.search.search_papers",
        lambda *args, **kwargs: [
            SearchResult(
                title="Journal Paper",
                doi="10.1000/example",
                authors=["Jane Doe"],
                year=2025,
                abstract="Abstract",
                venue="Nature",
                source="openalex",
            )
        ],
    )

    assert main(["search", "llm", "--to-papers-input"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert "arxiv_id" not in payload[0]
    assert payload[0]["doi"] == "10.1000/example"
