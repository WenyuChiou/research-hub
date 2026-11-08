"""Offline regressions for the public native-summary ingest shape at #210.

The text and identifiers below are synthetic. Content presence does not attest
scientific correctness, model generation, full-paper coverage, or human review.
"""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
import yaml

from research_hub.dashboard.markdown_summary import _cluster_stats
from research_hub.dashboard.sections import _summarize_pending_backlog
from research_hub.paper import _parse_frontmatter
from research_hub.paper_summarize import set_frontmatter_fields, summarize_pending
from research_hub.pipeline import _render_obsidian_note
from research_hub.summarize import PaperSummary, _replace_obsidian_block, summarize_cluster
from research_hub.notebooklm.url_quality import _probe_url as _publisher_probe


@pytest.fixture
def supplied_paper():
    return {
        "title": "Synthetic simulation boundary review",
        "authors": [{"creatorType": "author", "firstName": "Test", "lastName": "Reader"}],
        "year": 2026,
        "journal": "Synthetic public-source fixture",
        "doi": "10.0000/synthetic-boundary",
        "abstract": (
            "This synthetic position-paper abstract describes validation boundaries "
            "for social simulation, behavioral heterogeneity, and comparisons with "
            "suitable reference evidence. It is not a human-subject experiment."
        ),
        "summary": "A supplied interpretation distinguishes mean agreement from behavioral heterogeneity.",
        "key_findings": ["Agreement on means alone does not establish individual behavior."],
        "methodology": "A synthetic position-paper review compares validation scope and claim boundaries.",
        "relevance": "A methodological reference for limiting simulation claims to their available evidence.",
        "verified": None,
        "provenance": {
            "research": {
                "summary_origin": "Native source-reading summary; no Hub/provider generation",
                "summary_revision": 2,
                "fulltext_imported_to_vault": False,
                "summary_human_review": "pending",
            },
            "doi_recheck_pending": True,
        },
        "source_records": [{
            "source_id": "synthetic:boundary:v3",
            "work_id": "synthetic:boundary",
            "publication_version": "v3",
            "reading_scope": "Selected sections and one table; appendices not audited",
            "evidence_level": "full-text",
            "raw_sha256": "a" * 64,
        }],
    }


def _render(paper):
    return _render_obsidian_note(paper, "<unconfigured>", "boundary", "simulation boundaries")


def _save(cfg, text, slug="supplied"):
    path = cfg.raw / "boundary" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _cfg(tmp_path):
    return SimpleNamespace(root=tmp_path, raw=tmp_path / "raw", research_hub_dir=tmp_path / ".research_hub")


def _assert_source_metadata(meta, paper):
    assert meta["verified"] is paper["verified"]
    assert meta["status"] == "unread"
    assert meta["provenance"]["research"] == paper["provenance"]["research"]
    assert meta["provenance"]["doi_recheck_pending"] is True
    assert meta["source_records"] == paper["source_records"]
    assert "summarize_source" not in meta
    assert "summarized_at" not in meta


def _yaml_meta(text):
    # The queue's scalar parser intentionally does not decode nested metadata.
    return yaml.safe_load(text.split("---", 2)[1])


@pytest.mark.parametrize("abstract", [None, "", "(no abstract)"])
@pytest.mark.parametrize("verified", [None, False])
def test_supplied_summary_is_done_without_attesting_generation_or_review(supplied_paper, tmp_path, abstract, verified):
    supplied_paper["verified"] = verified
    if abstract is not None:
        supplied_paper["abstract"] = abstract
    text = _render(supplied_paper)
    meta = _parse_frontmatter(text)

    assert meta["summarize_status"] == "done"
    _assert_source_metadata(_yaml_meta(text), supplied_paper)
    cfg = _cfg(tmp_path)
    _save(cfg, text)
    assert _summarize_pending_backlog(str(cfg.root)) == (0, {})
    assert _cluster_stats(cfg.root, "boundary")["pending_summary"] == 0
    assert _cluster_stats(cfg.root, "boundary")["unread"] == 1


@pytest.mark.parametrize("placeholder", ["", "   ", "[TODO: fill from abstract]", "[TODO: extract findings after reading the selected source]"])
def test_empty_or_placeholder_sections_stay_pending(supplied_paper, placeholder):
    supplied_paper.update(summary=placeholder, key_findings=[placeholder], methodology=placeholder, relevance=placeholder)
    assert _parse_frontmatter(_render(supplied_paper))["summarize_status"] == "pending"


def test_metadata_only_without_abstract_keeps_failure_status(supplied_paper):
    supplied_paper.update(abstract="", summary="", key_findings=[], methodology="", relevance="")
    assert _parse_frontmatter(_render(supplied_paper))["summarize_status"] == "failed_no_abstract"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_cluster_apply_updates_content_status_and_preserves_provenance(supplied_paper, newline):
    original = deepcopy(supplied_paper)
    original.update(summary="", key_findings=[], methodology="", relevance="")
    text = _render(original).replace("\n", newline)
    summary = PaperSummary(
        paper_slug="supplied", summary=supplied_paper["summary"],
        key_findings=supplied_paper["key_findings"], methodology=supplied_paper["methodology"],
        relevance=supplied_paper["relevance"],
    )
    updated = _replace_obsidian_block(text, summary)

    assert _parse_frontmatter(updated)["summarize_status"] == "done"
    _assert_source_metadata(_yaml_meta(updated), supplied_paper)
    assert updated.split(newline + "---" + newline, 1)[0] == text.split(newline + "---" + newline, 1)[0].replace("summarize_status: pending", "summarize_status: done")


@pytest.mark.parametrize("status", ["pending", "failed_no_abstract"])
def test_pending_worker_preserves_substantive_summary_despite_stale_status(supplied_paper, tmp_path, monkeypatch, status):
    cfg = _cfg(tmp_path)
    text = set_frontmatter_fields(_render(supplied_paper), {"summarize_status": status})
    path = _save(cfg, text)
    calls = []
    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", lambda *args: calls.append(args) or "bad response")

    results = summarize_pending(cfg, backend="codex")

    assert calls == []
    assert results == []
    assert path.read_bytes() == text.encode("utf-8")


def test_default_cluster_summary_preserves_existing_content(supplied_paper, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    text = set_frontmatter_fields(_render(supplied_paper), {"summarize_status": "pending"})
    path = _save(cfg, text)
    calls = []
    monkeypatch.setattr("research_hub.llm_cli.invoke_llm_cli", lambda *args: calls.append(args) or "bad response")

    report = summarize_cluster(cfg, "boundary", llm_cli="codex", apply=True, write_zotero=False)

    assert calls == []
    assert report.ok is True
    assert report.apply_result is not None
    assert report.apply_result.applied == []
    assert path.read_bytes() == text.encode("utf-8")


def test_explicit_resummarization_still_selects_existing_content(supplied_paper, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _save(cfg, _render(supplied_paper))
    prompts = []
    monkeypatch.setattr("research_hub.llm_cli.invoke_llm_cli", lambda cli, prompt: prompts.append(prompt) or '{"summaries": []}')

    report = summarize_cluster(cfg, "boundary", llm_cli="codex", skip_existing=False)

    assert report.ok is True
    assert len(prompts) == 1
    assert supplied_paper["title"] in prompts[0]


def test_mixed_cluster_only_prompts_for_missing_sections(supplied_paper, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _save(cfg, set_frontmatter_fields(_render(supplied_paper), {"summarize_status": "pending"}))
    missing = deepcopy(supplied_paper)
    missing.update(title="Synthetic metadata-only paper", summary="", key_findings=[], methodology="", relevance="")
    _save(cfg, _render(missing), "missing")
    prompts = []
    monkeypatch.setattr("research_hub.llm_cli.invoke_llm_cli", lambda cli, prompt: prompts.append(prompt) or '{"summaries": []}')

    report = summarize_cluster(cfg, "boundary", llm_cli="codex")

    assert report.ok is True
    assert len(prompts) == 1
    assert supplied_paper["title"] not in prompts[0]
    assert missing["title"] in prompts[0]


def test_default_apply_rejects_unsolicited_existing_paper(supplied_paper, tmp_path, monkeypatch):
    from research_hub.summarize import _PerPaperOutcome

    cfg = _cfg(tmp_path)
    text = set_frontmatter_fields(_render(supplied_paper), {"summarize_status": "pending"})
    path = _save(cfg, text)
    missing = deepcopy(supplied_paper)
    missing.update(title="Synthetic metadata-only paper", summary="", key_findings=[], methodology="", relevance="")
    _save(cfg, _render(missing), "missing")
    # A backend response cannot expand the set selected for default autofill.
    unsolicited = {
        "paper_slug": "supplied", "summary": "An unwanted replacement summary.",
        "key_findings": ["An unwanted replacement finding."],
        "methodology": "An unwanted replacement methodology.",
        "relevance": "An unwanted replacement relevance.",
    }
    monkeypatch.setattr("research_hub.llm_cli.invoke_llm_cli", lambda *args: json.dumps({"summaries": [unsolicited]}))
    dispatches = []

    def record_dispatch(cfg, paper, summary, *args, **kwargs):
        dispatches.append(summary.paper_slug)
        return _PerPaperOutcome(slug=summary.paper_slug, applied=True)

    monkeypatch.setattr("research_hub.summary_apply_journal.apply_entry", record_dispatch)

    report = summarize_cluster(cfg, "boundary", llm_cli="codex", apply=True, write_zotero=False)

    assert dispatches == []
    assert path.read_bytes() == text.encode("utf-8")
    assert report.apply_result.applied == []
    assert len(report.apply_result.skipped) == 1
    assert "supplied" in report.apply_result.skipped[0]


def test_placeholder_apply_does_not_claim_content_done(supplied_paper):
    supplied_paper.update(summary="", key_findings=[], methodology="", relevance="")
    updated = _replace_obsidian_block(_render(supplied_paper), PaperSummary(
        paper_slug="supplied", key_findings=["[abstract too thin to extract findings]"],
        methodology="[TODO: check methods after reading the source]",
        relevance="[PDF needed to establish cluster relevance]",
    ))
    assert _parse_frontmatter(updated)["summarize_status"] == "pending"


def _publisher_skeleton_bundle(supplied_paper, tmp_path, monkeypatch, abstract, *, polish=False):
    from research_hub.clusters import Cluster
    from research_hub.notebooklm.bundle import bundle_cluster

    cfg = _cfg(tmp_path)
    cfg.clusters_file = cfg.research_hub_dir / "clusters.yaml"
    supplied_paper["abstract"] = abstract
    original = _render(supplied_paper)
    if polish:
        from research_hub.markdown_conventions import upgrade_paper_body
        original = upgrade_paper_body(original)
    path = _save(cfg, original)
    cluster = Cluster(slug="boundary", name="Boundary", obsidian_subfolder="boundary")
    # Real probe parsing sees an HTTP-200 publisher shell containing an article
    # element, but the response has no paper text or new acquisition evidence.
    shell = b"<html><body><article>Subscription access options only.</article></body></html>"
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: SimpleNamespace(
        status_code=200, headers={}, url="https://publisher.example.test/paper",
        iter_content=lambda chunk_size: iter([shell]),
    ))
    # The shared fixture stubs this probe by default. Exercise the real parser
    # with our mocked HTTP response while retaining the external socket fence.
    monkeypatch.setattr("research_hub.notebooklm.url_quality._probe_url", _publisher_probe)
    assert _publisher_probe("https://publisher.example.test/paper").reason == "probe_ok"
    report = bundle_cluster(cluster, cfg, download_pdfs=False)
    return cfg, cluster, path, original, report


@pytest.mark.parametrize("abstract", ["", "Short abstract.", "This abstract has some reference metadata but fewer than one hundred characters."])
def test_supplied_summary_without_abstract_keeps_url_guard(supplied_paper, tmp_path, monkeypatch, abstract):
    from research_hub.notebooklm.url_quality import classify_url_source

    cfg, cluster, path, original, report = _publisher_skeleton_bundle(
        supplied_paper, tmp_path, monkeypatch, abstract,
    )
    entry = report.entries[0]
    legacy = classify_url_source("https://doi.org/10.0000/synthetic-boundary", "failed_no_abstract")

    assert _yaml_meta(original)["summarize_status"] == "done"
    assert legacy.quality == "likely_error_page"
    assert entry.url_quality == legacy.quality
    assert entry.pdf_path == ""
    assert path.read_bytes() == original.encode("utf-8")
    _assert_source_metadata(_yaml_meta(path.read_text(encoding="utf-8")), supplied_paper)


@pytest.mark.parametrize("include_suspect_urls", [False, True])
@pytest.mark.parametrize("abstract_style", ["plain-empty", "polished-short"])
def test_supplied_summary_publisher_shell_is_filtered_before_upload(supplied_paper, tmp_path, monkeypatch, include_suspect_urls, abstract_style):
    from unittest.mock import Mock
    from research_hub.clusters import ClusterRegistry
    from research_hub.notebooklm.upload import upload_cluster

    cfg, cluster, path, original, bundle = _publisher_skeleton_bundle(
        supplied_paper, tmp_path, monkeypatch,
        "Short abstract." if abstract_style == "polished-short" else "",
        polish=abstract_style == "polished-short",
    )
    registry = ClusterRegistry(cfg.clusters_file)
    registry.clusters[cluster.slug] = cluster
    registry.save()
    client = SimpleNamespace(close=lambda: None)
    handle = SimpleNamespace(notebook_id="synthetic-notebook", url="https://example.test/notebook", name="Boundary")
    monkeypatch.setattr("research_hub.notebooklm.upload._make_client", lambda *args, **kwargs: client)
    monkeypatch.setattr("research_hub.notebooklm.upload._find_or_create_notebook", lambda *args: handle)
    monkeypatch.setattr("research_hub.notebooklm.upload._set_active_notebook", lambda *args: None)
    dispatch = Mock(return_value=(None, None, []))
    monkeypatch.setattr("research_hub.notebooklm.upload._attempt_versioned_upload", dispatch)
    monkeypatch.setattr("research_hub.notebooklm.upload.validate_uploaded_sources", lambda *args, **kwargs: SimpleNamespace(warning_text=lambda: ""))

    result = upload_cluster(cluster, cfg, include_suspect_urls=include_suspect_urls)

    if include_suspect_urls:
        dispatch.assert_called_once()
        expected = "pre_upload_likely_error_page_warning"
    else:
        dispatch.assert_not_called()
        expected = "pre_upload_likely_error_page"
    assert any(error["error"] == expected for error in result.errors)
    assert path.read_bytes() == original.encode("utf-8")
    assert _yaml_meta(original)["summarize_status"] == "done"


SHORT_SCIENTIFIC_ABSTRACT = (
    "This variance remains low; n=21; p<0.05; x^2 and CO2 retain their source values."
)


@pytest.mark.parametrize("style", ["plain", "callout", "polished", "plain-id"])
def test_short_abstract_markup_cannot_expand_url_eligibility(supplied_paper, tmp_path, monkeypatch, style):
    from research_hub.markdown_conventions import wrap_callout

    content = SHORT_SCIENTIFIC_ABSTRACT
    assert len(content) == 80
    if style == "callout":
        abstract = wrap_callout("abstract", content, block_id="summary")
    elif style == "plain-id":
        abstract = content + "\n^long-abstract-source-anchor"
    else:
        abstract = content
    cfg, cluster, path, original, report = _publisher_skeleton_bundle(
        supplied_paper, tmp_path, monkeypatch, abstract, polish=style == "polished",
    )

    assert report.entries[0].url_quality == "likely_error_page"
    assert report.entries[0].action == "text"
    assert report.entries[0].text.endswith("Abstract\n" + content)
    assert report.entries[0].pdf_path == ""
    assert path.read_bytes() == original.encode("utf-8")
    assert _yaml_meta(original)["summarize_status"] == "done"
    _assert_source_metadata(_yaml_meta(original), supplied_paper)
    if style in {"callout", "polished"}:
        assert "> [!abstract]\n> " + content + "\n^summary" in original


@pytest.mark.parametrize("style", ["plain", "callout", "polished"])
def test_tiny_abstract_markup_cannot_create_text_fallback(supplied_paper, tmp_path, monkeypatch, style):
    from research_hub.markdown_conventions import wrap_callout

    content = "Short abstract."
    abstract = wrap_callout("abstract", content, block_id="summary") if style == "callout" else content
    cfg, cluster, path, original, report = _publisher_skeleton_bundle(
        supplied_paper, tmp_path, monkeypatch, abstract, polish=style == "polished",
    )

    entry = report.entries[0]
    assert entry.url_quality == "likely_error_page"
    assert entry.action == "url"
    assert entry.text == ""
    assert path.read_bytes() == original.encode("utf-8")


@pytest.mark.parametrize("style", ["plain", "callout", "polished"])
def test_substantive_abstract_content_survives_callout_normalization(supplied_paper, tmp_path, monkeypatch, style):
    from research_hub.markdown_conventions import wrap_callout
    from research_hub.notebooklm.url_quality import classify_url_source

    content = SHORT_SCIENTIFIC_ABSTRACT + "\nThe source also records Δσ²=0.2 without extending these claims to individual trajectories."
    abstract = wrap_callout("abstract", content, block_id="summary") if style == "callout" else content
    cfg, cluster, path, original, report = _publisher_skeleton_bundle(
        supplied_paper, tmp_path, monkeypatch, abstract, polish=style == "polished",
    )

    assert report.entries[0].url_quality == "ok"
    assert report.entries[0].url_quality_reason == "probe_ok"
    assert "p<0.05; x^2 and CO2" in original
    assert "Δσ²=0.2" in original
    assert path.read_bytes() == original.encode("utf-8")
    _assert_source_metadata(_yaml_meta(original), supplied_paper)
    # A substantive abstract still cannot clear a legacy access-quality prior.
    legacy = classify_url_source("https://doi.org/10.0000/synthetic-boundary", "failed_no_abstract", abstract_usable=True)
    assert legacy.quality == "likely_error_page"
    assert legacy.reason == "probe_cleared_failed_no_abstract"
