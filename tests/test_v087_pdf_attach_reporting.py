from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import requests  # noqa: F401 — kept for the Zenodo-skip test's monkeypatch target

from research_hub.clusters import ClusterRegistry
from research_hub.zotero.pdf_attach import (
    PdfAttachEntry,
    PdfAttachPlan,
    PdfAttachResults,
    PdfAttachSummary,
    attach_pdfs,
    format_pdf_attach_summary,
    plan_attach_for_items,
    summarize_pdf_attach,
)
from tests.test_pipeline import _configure, _paper


def test_pdf_attach_summary_renders_ok_fail_skip_mix() -> None:
    zot = _zot()
    plans = [
        PdfAttachPlan("S1", "Schuck", "10.1000/s1", "", "https://ok.test/s1.pdf", "openalex-oa"),
        PdfAttachPlan("G1", "Goldshtein", "10.1000/g1", "", "https://ok.test/g1.pdf", "crossref-link"),
        PdfAttachPlan("A1", "Arnold", "10.5281/zenodo.123", "", error="zenodo_dataset"),
        PdfAttachPlan("T1", "Taormina", "10.1000/t1", "", error="no_oa_record"),
        PdfAttachPlan("B1", "Broken", "10.1000/b1", "", "ftp://bad.example/full.pdf", "unpaywall"),
    ]

    results = attach_pdfs(zot, plans, rate_limit_rps=999)
    summary = summarize_pdf_attach(
        plans,
        results,
        slug_by_key={
            "S1": "schuck2026",
            "G1": "goldshtein2025",
            "A1": "arnold2026",
            "T1": "taormina2024",
            "B1": "broken2026",
        },
    )
    text = format_pdf_attach_summary(summary)

    assert summary.ok == 2
    assert summary.fail == 1
    assert summary.skip == 2
    assert "PDF attachment: 2/5 succeeded, 1 failed, 2 skipped" in text
    assert "[OK]   schuck2026" in text
    assert "[SKIP] arnold2026" in text
    assert "zenodo_dataset" in text
    assert "unsafe_url" in text


def test_zenodo_doi_is_skip_not_fail(monkeypatch) -> None:
    monkeypatch.setattr(
        "research_hub.zotero.pdf_attach.requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no network for Zenodo dataset")),
    )
    plans = plan_attach_for_items(
        [{"key": "Z1", "data": {"title": "Dataset", "DOI": "10.5281/zenodo.999"}}],
    )

    results = attach_pdfs(_zot(), plans, rate_limit_rps=999)
    summary = summarize_pdf_attach(plans, results)

    assert plans[0].error == "zenodo_dataset"
    assert summary.skip == 1
    assert summary.fail == 0
    assert summary.entries[0].reason == "zenodo_dataset"


def test_403_404_and_network_errors_are_distinct(monkeypatch) -> None:
    # pdf_attach.py uses httpx.get (since the EZproxy refactor moved off
    # `requests`). httpx's "did the request succeed" attribute is
    # `is_success`, not `ok`.
    def fake_get(url: str, **kwargs):
        if "403" in url:
            return SimpleNamespace(is_success=False, status_code=403, headers={}, content=b"")
        if "404" in url:
            return SimpleNamespace(is_success=False, status_code=404, headers={}, content=b"")
        raise httpx.RequestError("offline")

    monkeypatch.setattr("research_hub.zotero.pdf_attach.httpx.get", fake_get)
    plans = [
        PdfAttachPlan("P403", "Forbidden", "10.1000/403", "", "https://files.example.com/403.pdf", "unpaywall"),
        PdfAttachPlan("P404", "Missing", "10.1000/404", "", "https://files.example.com/404.pdf", "crossref-link"),
        PdfAttachPlan("PNET", "Network", "10.1000/net", "", "https://files.example.com/network.pdf", "openalex-oa"),
    ]

    summary = summarize_pdf_attach(plans, attach_pdfs(_zot(), plans, rate_limit_rps=999))
    reasons = {entry.item_key: entry.reason for entry in summary.entries}

    assert reasons == {
        "P403": "paywall_403",
        "P404": "not_found_404",
        "PNET": "network_error",
    }


def test_pdf_attach_summary_json_shape() -> None:
    summary = PdfAttachSummary(
        [
            PdfAttachEntry(
                item_key="I1",
                slug="paper-one",
                title="Paper One",
                doi="10.1000/one",
                action="OK",
                source="openalex",
                bytes=1234567,
            )
        ]
    )

    payload = summary.to_json()

    assert payload == {
        "total": 1,
        "ok": 1,
        "skip": 0,
        "fail": 0,
        "entries": [
            {
                "slug": "paper-one",
                "action": "OK",
                "source": "openalex",
                "reason": None,
                "bytes": 1234567,
            }
        ],
    }


def test_empty_pdf_attach_input_renders_zero_table() -> None:
    results = attach_pdfs(_zot(), [], rate_limit_rps=999)
    summary = summarize_pdf_attach([], results)

    assert summary.to_json() == {"total": 0, "ok": 0, "skip": 0, "fail": 0, "entries": []}
    assert format_pdf_attach_summary(summary) == "PDF attachment: 0/0 succeeded, 0 failed, 0 skipped"


def test_pipeline_appends_pdf_attach_summary_to_output_json(tmp_path, monkeypatch) -> None:
    from research_hub import config as hub_config
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )
    zot = _zot()
    zot.create_items.side_effect = lambda items: {"successful": {"0": {"key": "Z0"}}}
    zot.item.side_effect = lambda key: {"key": key, "data": {"title": "Paper One", "DOI": "10.1000/one"}}
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="", **kwargs: False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(pipeline, "update_cluster_links", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "_refresh_cluster_base", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "research_hub.zotero.pdf_attach.plan_attach_for_items",
        lambda items, unpaywall_email="": [
            PdfAttachPlan("Z0", "Paper One", "10.1000/one", "", "https://ok.test/paper.pdf", "openalex-oa")
        ],
    )
    monkeypatch.setattr(
        "research_hub.zotero.pdf_attach.attach_pdfs",
        # accept cfg=cfg passed by pipeline.run_pipeline (EZproxy plumbing)
        lambda zot, plans, rate_limit_rps=2.0, cfg=None: PdfAttachResults(
            {"Z0": "ok"},
            PdfAttachSummary(
                [
                    PdfAttachEntry(
                        item_key="Z0",
                        title="Paper One",
                        doi="10.1000/one",
                        action="OK",
                        source="openalex",
                        bytes=1234,
                    )
                ]
            ),
        ),
    )

    try:
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="agents", verify=False, with_pdfs=True) == 0
        output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    finally:
        hub_config._config = None
        hub_config._config_path = None

    assert output["pdf_attach_summary"]["total"] == 1
    assert output["pdf_attach_summary"]["ok"] == 1
    assert output["pdf_attach_summary"]["entries"][0]["slug"] == "paper-one"


def _zot() -> MagicMock:
    zot = MagicMock()
    zot.children.return_value = []
    zot.item_template.side_effect = lambda *args: {"itemType": args[0] if args else "attachment"}
    zot.create_items.return_value = {"successful": {"0": {"key": "ATT1"}}}
    return zot
