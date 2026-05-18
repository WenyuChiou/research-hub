from __future__ import annotations

import xml.etree.ElementTree as ET
from types import SimpleNamespace

from research_hub.search._rank import apply_filters
from research_hub.search.arxiv_backend import ArxivBackend
from research_hub.search.base import SearchResult
from research_hub.search.fallback import GRAY_DOC_TYPES, apply_peer_reviewed


def test_arxiv_parse_entry_marks_preprint():
    xml = """
    <entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <id>http://arxiv.org/abs/2411.12345v1</id>
      <published>2024-01-02T00:00:00Z</published>
      <title>LLM agent benchmark</title>
      <summary>Evaluation of agent systems</summary>
      <author><name>Jane Doe</name></author>
    </entry>
    """
    entry = ET.fromstring(xml)

    result = ArxivBackend(delay_seconds=0)._parse_entry(entry)

    assert result is not None
    assert result.doc_type == "preprint"


def test_apply_peer_reviewed_drops_preprint_backends_and_hardens_filters():
    backends, exclude_types, min_confidence = apply_peer_reviewed(
        ("arxiv", "openalex", "crossref"),
        (),
        0.0,
    )

    assert set(backends).isdisjoint({"arxiv", "biorxiv", "chemrxiv", "medrxiv"})
    assert set(GRAY_DOC_TYPES).issubset(set(exclude_types))
    assert min_confidence == 0.5


def test_apply_peer_reviewed_keeps_original_when_all_backends_would_drop():
    backends, exclude_types, min_confidence = apply_peer_reviewed(("arxiv",), (), 0.0)

    assert backends == ("arxiv",)
    assert set(GRAY_DOC_TYPES).issubset(set(exclude_types))
    assert min_confidence == 0.5


def test_apply_filters_drops_arxiv_preprint_when_excluded():
    result = SearchResult(
        title="Arxiv preprint",
        arxiv_id="2411.12345",
        source="arxiv",
        doc_type="preprint",
    )

    assert apply_filters([result], exclude_types=("preprint",)) == []


def test_cli_search_peer_reviewed_hardens_dispatch(monkeypatch):
    from research_hub.cli import main

    captured = {}

    def fake_search(query, limit, verify=False, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("research_hub.cli.get_config", lambda: object())
    monkeypatch.setattr("research_hub.cli._search", fake_search)

    assert main(["search", "llm", "--backend", "arxiv,openalex", "--peer-reviewed"]) == 0

    assert captured["backends"] == ("openalex",)
    assert "preprint" in captured["exclude_types"]
    assert captured["min_confidence"] == 0.5


def test_auto_peer_reviewed_dry_run_plan_shows_hardened_backends(
    monkeypatch,
    tmp_path,
    capsys,
):
    from research_hub import auto as auto_mod

    cfg = SimpleNamespace(
        clusters_file=tmp_path / "clusters.json",
        research_hub_dir=tmp_path / ".research_hub",
    )
    cfg.research_hub_dir.mkdir()
    registry = SimpleNamespace(get=lambda _slug: None)

    monkeypatch.setattr(auto_mod, "get_config", lambda: cfg)
    monkeypatch.setattr(auto_mod, "ClusterRegistry", lambda _path: registry)
    monkeypatch.setattr(auto_mod, "detect_llm_cli", lambda: "claude")

    report = auto_mod.auto_pipeline(
        "llm agents",
        dry_run=True,
        peer_reviewed=True,
        print_progress=True,
        do_nlm=False,
    )

    assert report.ok
    output = capsys.readouterr().out
    assert "backends=semantic-scholar+openalex+crossref" in output
    assert "arxiv+semantic-scholar" not in output
