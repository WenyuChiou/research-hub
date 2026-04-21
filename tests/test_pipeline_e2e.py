from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.clusters import ClusterRegistry, slugify
from research_hub.search.base import SearchResult

from tests._pipeline_fixtures import (
    BRIEF_TEXT,
    FakeNotebookLMClient,
    FakeResponse,
    PDF_BLOB,
    backend_response,
    fake_cdp_session,
    paper_input,
    write_note,
)


@pytest.fixture
def pipeline_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    logs = root / "logs"
    research_hub_dir = root / ".research_hub"
    for path in (raw, hub, logs, research_hub_dir):
        path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "knowledge_base": {
                    "root": str(root),
                    "raw": str(raw),
                    "hub": str(hub),
                    "logs": str(logs),
                },
                "clusters_file": str(research_hub_dir / "clusters.yaml"),
                "zotero": {
                    "library_id": "123",
                    "library_type": "user",
                    "default_collection": "DEFAULT",
                    "collections": {"DEFAULT": {"name": "Default"}},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(config_path))
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(root))
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)

    import research_hub.config as cfg_mod

    cfg_mod._config = None
    cfg_mod._config_path = None
    cfg = cfg_mod.get_config()
    (cfg.research_hub_dir / "dedup_index.json").write_text("{}", encoding="utf-8")
    (cfg.research_hub_dir / "manifest.jsonl").write_text("", encoding="utf-8")
    (cfg.research_hub_dir / "nlm_cache.json").write_text("{}", encoding="utf-8")
    return cfg


def _cluster(cfg, slug: str = "llm-agents-for-abm"):
    registry = ClusterRegistry(cfg.clusters_file)
    return registry.create(
        query="LLM agents for ABM",
        name="LLM Agents for ABM",
        slug=slug,
        zotero_collection_key="COLL1",
    )


def _fake_dedup():
    return SimpleNamespace(
        doi_to_hits={},
        title_to_hits={},
        check=lambda payload: (False, []),
        add=lambda hit: None,
        save=lambda path: None,
    )


class _FakeZotero:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def item_template(self, kind: str) -> dict:
        return {"itemType": kind}

    def create_items(self, items):
        self.created.extend(items)
        return {"successful": {"0": {"key": f"ITEM{len(self.created):02d}"}}}


def test_stage_1_slugify_and_cluster_create_or_reuse(pipeline_cfg):
    assert slugify("LLM agents for ABM") == "llm-agents-abm"
    registry = ClusterRegistry(pipeline_cfg.clusters_file)
    first = registry.create(query="LLM agents for ABM", slug="llm-agents-for-abm", name="Agents")
    second = registry.create(query="Different", slug="llm-agents-for-abm", name="Overwrite")

    assert first is second
    assert ClusterRegistry(pipeline_cfg.clusters_file).get("llm-agents-for-abm").name == "Agents"


def test_stage_2_zotero_collection_auto_create_and_failure_is_best_effort(pipeline_cfg, monkeypatch):
    from research_hub import auto as auto_mod

    registry = ClusterRegistry(pipeline_cfg.clusters_file)
    cluster = registry.create(query="LLM agents for ABM", slug="llm-agents-for-abm", name="Agents")
    report = auto_mod.AutoReport(cluster_slug=cluster.slug, cluster_created=True)
    monkeypatch.setattr(
        "research_hub.zotero.client.get_client",
        lambda: SimpleNamespace(create_collections=lambda payload: {"successful": {"0": {"key": "ABCD1234"}}}),
    )

    auto_mod._ensure_zotero_collection(registry, cluster, cluster.slug, report, False)
    assert ClusterRegistry(pipeline_cfg.clusters_file).get(cluster.slug).zotero_collection_key == "ABCD1234"

    report = auto_mod.AutoReport(cluster_slug=cluster.slug, cluster_created=False)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    auto_mod._ensure_zotero_collection(registry, cluster, cluster.slug, report, False)
    assert report.steps[-1].ok is False
    assert "could not load Zotero client" in report.steps[-1].detail


@pytest.mark.parametrize(
    ("backend", "patch_module", "expected_id"),
    [
        ("arxiv", "research_hub.search.arxiv_backend.requests.get", "2604.08224"),
        ("semantic-scholar", "research_hub.search.semantic_scholar.requests.get", "10.1000/s2"),
        ("openalex", "research_hub.search.openalex.requests.get", "10.1000/openalex"),
        ("crossref", "research_hub.search.crossref.requests.get", "10.1000/crossref"),
        ("pubmed", "research_hub.search.pubmed.requests.get", "10.1000/pubmed"),
        ("biorxiv", "research_hub.search.biorxiv.requests.get", "10.1101/2021.01.01.1"),
        ("dblp", "research_hub.search.dblp.requests.get", "10.1000/dblp"),
        ("websearch", "research_hub.search.websearch.requests.post", "web"),
    ],
)
def test_stage_3_search_backend_canned_responses(monkeypatch, backend, patch_module, expected_id):
    from research_hub.search.fallback import search_papers

    monkeypatch.setenv("TAVILY_API_KEY", "fake")

    def fake_request(url, **kwargs):
        del kwargs
        return backend_response(backend, url)

    monkeypatch.setattr(patch_module, fake_request)
    results = search_papers("pipeline agents", backends=[backend], limit=5)

    assert len(results) == 1
    result = results[0]
    assert result.title
    assert result.year is None or int(result.year) > 1900
    assert result.authors or backend == "websearch"
    assert result.source in {backend, "web"}
    if expected_id == "2604.08224":
        assert result.arxiv_id == expected_id
    elif expected_id == "web":
        assert result.url.startswith("https://")
    else:
        assert result.doi == expected_id


def test_stage_3_cross_backend_rate_limit_and_empty(monkeypatch):
    from research_hub.search.fallback import search_papers

    monkeypatch.setattr(
        "research_hub.search.semantic_scholar.requests.get",
        lambda *a, **k: FakeResponse(status_code=429),
    )
    monkeypatch.setattr("research_hub.search.semantic_scholar.time.sleep", lambda seconds: None)
    monkeypatch.setattr(
        "research_hub.search.openalex.requests.get",
        lambda url, **k: backend_response("openalex", url),
    )
    results = search_papers("pipeline agents", backends=["semantic-scholar", "openalex"], limit=5)
    assert [result.source for result in results] == ["openalex"]

    monkeypatch.setattr("research_hub.search.openalex.requests.get", lambda *a, **k: FakeResponse(payload={"results": []}))
    assert search_papers("none", backends=["semantic-scholar", "openalex"], limit=5) == []


def test_stage_4_to_papers_input_mapping():
    from research_hub.discover import _to_papers_input

    mapped = _to_papers_input(
        [
            asdict(SearchResult(title="Arxiv Only", arxiv_id="2604.08224", authors=["Jane Doe"], year=2026)),
            asdict(SearchResult(title="Real DOI", doi="10.1000/real", arxiv_id="2604.08225", authors=["Jane Doe"], year=2026)),
            asdict(SearchResult(title="No DOI", authors=["Jane Doe"], year=2026)),
        ],
        "llm-agents-for-abm",
    )

    assert mapped[0]["doi"] == "10.48550/arxiv.2604.08224"
    assert mapped[1]["doi"] == "10.1000/real"
    assert mapped[2]["doi"] == ""


def test_stage_5_run_pipeline_ingests_valid_papers_and_rejects_no_doi(pipeline_cfg, monkeypatch):
    from research_hub import pipeline

    _cluster(pipeline_cfg)
    papers = [
        paper_input("Arxiv Only", "arxiv-only", "10.48550/arxiv.2604.08224", arxiv_id="2604.08224"),
        paper_input("Real DOI", "real-doi", "10.1000/real"),
        paper_input("Missing DOI", "missing-doi", ""),
    ]
    (pipeline_cfg.root / "papers_input.json").write_text(json.dumps({"papers": papers}), encoding="utf-8")
    fake_zotero = _FakeZotero()
    monkeypatch.setattr(pipeline, "get_config", lambda: pipeline_cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: fake_zotero)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: _fake_dedup())
    monkeypatch.setattr(pipeline, "check_duplicate", lambda *a, **k: False)
    monkeypatch.setattr(pipeline, "add_note", lambda *a, **k: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    assert pipeline.run_pipeline(cluster_slug="llm-agents-for-abm", query="LLM agents for ABM", verify=False) == 0

    notes = sorted((pipeline_cfg.raw / "llm-agents-for-abm").glob("*.md"))
    assert [note.stem for note in notes] == ["arxiv-only", "real-doi"]
    assert len(fake_zotero.created) == 2
    text = notes[0].read_text(encoding="utf-8")
    assert 'title: "Arxiv Only"' in text
    assert 'doi: "10.48550/arxiv.2604.08224"' in text
    assert "topic_cluster:" in text
    assert "llm-agents-for-abm" in text
    log_text = (pipeline_cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "SKIPPED invalid input" in log_text
    assert "missing required field 'doi'" in log_text


def test_stage_6_bundle_downloads_pdfs_and_reports_failures(pipeline_cfg, monkeypatch):
    from research_hub.notebooklm import pdf_fetcher
    from research_hub.notebooklm.bundle import bundle_cluster

    cluster = _cluster(pipeline_cfg)
    for idx in range(3):
        write_note(
            pipeline_cfg.raw / cluster.slug / f"paper-{idx}.md",
            title=f"Paper {idx}",
            doi=f"10.48550/arxiv.2604.0822{idx}",
            arxiv_id=f"2604.0822{idx}",
        )

    def fake_fetch(doi, slug, pdfs_dir):
        if doi.endswith("2"):
            return SimpleNamespace(ok=False, path=None, source="", error="404")
        path = pdfs_dir / f"{slug}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PDF_BLOB)
        return SimpleNamespace(ok=True, path=path, source="arxiv", error="")

    monkeypatch.setattr(pdf_fetcher, "fetch_paper_pdf", fake_fetch)
    report = bundle_cluster(cluster, pipeline_cfg, download_pdfs=True)

    assert report.pdf_count == 2
    assert report.url_count == 1
    assert len(list((report.bundle_dir / "pdfs").glob("*.pdf"))) == 2
    assert any(entry.skip_reason == "no OA; url fallback used" for entry in report.entries)


def _write_bundle(cfg, cluster, count: int = 3) -> Path:
    bundle_dir = cfg.research_hub_dir / "bundles" / f"{cluster.slug}-20260420T000000Z"
    pdf_dir = bundle_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for idx in range(count):
        pdf_path = pdf_dir / f"paper-{idx}.pdf"
        pdf_path.write_bytes(PDF_BLOB)
        entries.append({"action": "pdf", "pdf_path": str(pdf_path), "doi": f"10.1000/{idx}", "title": f"Paper {idx}"})
    (bundle_dir / "manifest.json").write_text(
        json.dumps({"entries": entries, "pdf_count": count}, indent=2),
        encoding="utf-8",
    )
    return bundle_dir


def test_stage_7_nlm_upload_records_uploads_and_binds_cluster(pipeline_cfg, monkeypatch):
    from research_hub.notebooklm import upload as upload_mod

    cluster = _cluster(pipeline_cfg)
    _write_bundle(pipeline_cfg, cluster, 3)
    FakeNotebookLMClient.uploaded = []
    monkeypatch.setattr(upload_mod, "open_cdp_session", fake_cdp_session)
    monkeypatch.setattr(upload_mod, "NotebookLMClient", FakeNotebookLMClient)
    monkeypatch.setattr(upload_mod, "_check_session_health", lambda page: (True, page.url))
    monkeypatch.setattr(upload_mod.time, "sleep", lambda seconds: None)

    report = upload_mod.upload_cluster(cluster, pipeline_cfg, headless=True)

    assert report.success_count == 3
    assert len(FakeNotebookLMClient.uploaded) == 3
    saved = ClusterRegistry(pipeline_cfg.clusters_file).get(cluster.slug)
    assert saved.notebooklm_notebook_url == "https://notebooklm.google.com/notebook/fixture"


def test_stage_8_nlm_generate_success_and_missing_button(pipeline_cfg, monkeypatch):
    from research_hub.notebooklm import upload as upload_mod
    from research_hub.notebooklm.client import NotebookLMError

    cluster = _cluster(pipeline_cfg)
    monkeypatch.setattr(upload_mod, "open_cdp_session", fake_cdp_session)
    monkeypatch.setattr(upload_mod, "NotebookLMClient", FakeNotebookLMClient)
    monkeypatch.setattr(upload_mod, "_check_session_health", lambda page: (True, page.url))

    FakeNotebookLMClient.trigger_returns_none = False
    assert upload_mod.generate_artifact(cluster, pipeline_cfg, kind="brief", headless=True).endswith("/fixture")

    FakeNotebookLMClient.trigger_returns_none = True
    with pytest.raises(NotebookLMError, match="Generation button not found"):
        upload_mod.generate_artifact(cluster, pipeline_cfg, kind="brief", headless=True)
    FakeNotebookLMClient.trigger_returns_none = False


def test_stage_9_nlm_download_writes_brief(pipeline_cfg, monkeypatch):
    from research_hub.notebooklm import upload as upload_mod

    cluster = _cluster(pipeline_cfg)
    monkeypatch.setattr(upload_mod, "open_cdp_session", fake_cdp_session)
    monkeypatch.setattr(upload_mod, "NotebookLMClient", FakeNotebookLMClient)
    monkeypatch.setattr(upload_mod, "_check_session_health", lambda page: (True, page.url))

    report = upload_mod.download_briefing_for_cluster(cluster, pipeline_cfg, headless=True)

    assert report.char_count == len(BRIEF_TEXT)
    assert BRIEF_TEXT in report.artifact_path.read_text(encoding="utf-8")


def test_stage_10_crystal_emit_cli_and_apply(pipeline_cfg, monkeypatch):
    from research_hub import auto as auto_mod
    from research_hub.crystal import CANONICAL_QUESTIONS, emit_crystal_prompt

    cluster = _cluster(pipeline_cfg)
    for idx in range(3):
        write_note(
            pipeline_cfg.raw / cluster.slug / f"paper-{idx}.md",
            title=f"Paper {idx}",
            doi=f"10.1000/{idx}",
        )

    prompt = emit_crystal_prompt(pipeline_cfg, cluster.slug)
    assert all(f"`paper-{idx}`" in prompt for idx in range(3))
    assert all(question["slug"] in prompt for question in CANONICAL_QUESTIONS)
    assert "Output JSON schema" in prompt

    monkeypatch.setattr(auto_mod, "detect_llm_cli", lambda: "claude")
    monkeypatch.setattr(
        auto_mod,
        "_invoke_llm_cli",
        lambda cli, p: json.dumps(
            {
                "generator": "fixture",
                "crystals": [
                    {
                        "slug": "what-is-this-field",
                        "tldr": "x",
                        "gist": "g",
                        "full": "f",
                        "evidence": [{"claim": "c", "papers": ["paper-0"]}],
                        "confidence": "medium",
                    }
                ],
            }
        ),
    )
    report = auto_mod.AutoReport(cluster_slug=cluster.slug, cluster_created=False)
    auto_mod._run_crystal_step(pipeline_cfg, cluster.slug, None, report, 0.0, False)

    assert (pipeline_cfg.hub / cluster.slug / "crystals" / "what-is-this-field.md").exists()
    assert report.steps[-1].ok is True


def test_cross_stage_arxiv_round_trip_to_obsidian_frontmatter(pipeline_cfg, monkeypatch):
    from research_hub import pipeline
    from research_hub.discover import _to_papers_input
    from research_hub.search.fallback import search_papers

    _cluster(pipeline_cfg)
    monkeypatch.setattr("research_hub.search.arxiv_backend.requests.get", lambda url, **k: backend_response("arxiv", url))
    results = search_papers("pipeline agents", backends=["arxiv"], limit=1)
    papers = _to_papers_input([asdict(result) for result in results], "llm-agents-for-abm")
    (pipeline_cfg.root / "papers_input.json").write_text(json.dumps({"papers": papers}), encoding="utf-8")
    monkeypatch.setattr(pipeline, "get_config", lambda: pipeline_cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: _FakeZotero())
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: _fake_dedup())
    monkeypatch.setattr(pipeline, "check_duplicate", lambda *a, **k: False)
    monkeypatch.setattr(pipeline, "add_note", lambda *a, **k: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    assert pipeline.run_pipeline(cluster_slug="llm-agents-for-abm", query="pipeline agents", verify=False) == 0
    note = next((pipeline_cfg.raw / "llm-agents-for-abm").glob("*.md"))
    text = note.read_text(encoding="utf-8")
    assert "Arxiv Pipeline Agents" in text
    assert 'doi: "10.48550/arxiv.2604.08224"' in text
    assert "year: 2026" in text


def test_cross_stage_auto_reuses_cluster_and_adds_papers(pipeline_cfg, monkeypatch):
    from research_hub import auto as auto_mod

    created_inputs: list[list[dict]] = []

    def fake_run_pipeline(**kwargs):
        payload = json.loads((pipeline_cfg.root / "papers_input.json").read_text(encoding="utf-8"))["papers"]
        created_inputs.append(payload)
        for paper in payload:
            write_note(
                pipeline_cfg.raw / kwargs["cluster_slug"] / f"{paper['slug']}.md",
                title=paper["title"],
                doi=paper["doi"],
            )
        return 0

    calls = {"n": 0}

    def fake_search(topic, **kwargs):
        calls["n"] += 1
        start = (calls["n"] - 1) * 3
        return [paper_input(f"Paper {start + idx}", f"paper-{start + idx}", f"10.1000/{start + idx}") for idx in range(3)]

    monkeypatch.setattr(auto_mod, "get_config", lambda: pipeline_cfg)
    monkeypatch.setattr(auto_mod, "_ensure_zotero_collection", lambda *a, **k: None)
    monkeypatch.setattr(auto_mod, "_run_search", fake_search)
    monkeypatch.setattr(auto_mod, "run_pipeline", fake_run_pipeline)

    first = auto_mod.auto_pipeline("LLM agents for ABM", do_nlm=False, print_progress=False)
    second = auto_mod.auto_pipeline("LLM agents for ABM", do_nlm=False, print_progress=False)

    assert first.ok and second.ok
    assert len(ClusterRegistry(pipeline_cfg.clusters_file).list()) == 1
    assert len(list((pipeline_cfg.raw / "llm-agents-abm").glob("*.md"))) == 6


def test_cross_stage_search_zero_auto_exits_cleanly(pipeline_cfg, monkeypatch):
    from research_hub import auto as auto_mod

    monkeypatch.setattr(auto_mod, "get_config", lambda: pipeline_cfg)
    monkeypatch.setattr(auto_mod, "_ensure_zotero_collection", lambda *a, **k: None)
    monkeypatch.setattr(auto_mod, "_run_search", lambda *a, **k: [])

    report = auto_mod.auto_pipeline("LLM agents for ABM", do_nlm=False, print_progress=False)

    assert report.ok is False
    assert "Search returned 0 papers" in report.error


def test_cross_stage_auto_with_crystals_no_cli_is_best_effort(pipeline_cfg, monkeypatch):
    from research_hub import auto as auto_mod

    def fake_run_pipeline(**kwargs):
        write_note(pipeline_cfg.raw / kwargs["cluster_slug"] / "paper-0.md", title="Paper 0", doi="10.1000/0")
        return 0

    monkeypatch.setattr(auto_mod, "get_config", lambda: pipeline_cfg)
    monkeypatch.setattr(auto_mod, "_ensure_zotero_collection", lambda *a, **k: None)
    monkeypatch.setattr(auto_mod, "_run_search", lambda *a, **k: [paper_input("Paper 0", "paper-0", "10.1000/0")])
    monkeypatch.setattr(auto_mod, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(auto_mod, "detect_llm_cli", lambda: None)

    report = auto_mod.auto_pipeline("LLM agents for ABM", do_nlm=False, do_crystals=True, print_progress=False)

    assert report.ok is True
    crystal_step = next(step for step in report.steps if step.name == "crystals")
    assert crystal_step.ok is False
    assert "no LLM CLI on PATH" in crystal_step.detail
    assert (pipeline_cfg.research_hub_dir / "artifacts" / "llm-agents-abm" / "crystal-prompt.md").exists()
