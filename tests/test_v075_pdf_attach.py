from __future__ import annotations

import json
from unittest.mock import MagicMock

from research_hub.clusters import ClusterRegistry
from research_hub.zotero.pdf_attach import (
    PdfAttachPlan,
    _extract_arxiv_id,
    attach_pdfs,
    find_pdf_url,
    plan_attach_for_items,
)
from tests.test_pipeline import _configure, _paper


def test_extract_arxiv_id_from_doi():
    assert _extract_arxiv_id({"DOI": "10.48550/arXiv.2604.08224"}) == "2604.08224"


def test_extract_arxiv_id_from_url():
    assert _extract_arxiv_id({"url": "https://arxiv.org/abs/2604.08224"}) == "2604.08224"


def test_find_pdf_url_prefers_arxiv_without_network(monkeypatch):
    monkeypatch.setattr("research_hub.zotero.pdf_attach.requests.get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no network")))

    pdf_url, source = find_pdf_url(arxiv_id="2604.08224")

    assert pdf_url == "https://arxiv.org/pdf/2604.08224.pdf"
    assert source == "arxiv"


def test_find_pdf_url_uses_unpaywall_when_email_is_available(monkeypatch):
    class _Resp:
        ok = True

        @staticmethod
        def json():
            return {"best_oa_location": {"url_for_pdf": "https://example.test/full.pdf"}}

    monkeypatch.setattr("research_hub.zotero.pdf_attach.requests.get", lambda *args, **kwargs: _Resp())

    pdf_url, source = find_pdf_url(doi="10.1000/one", unpaywall_email="user@example.com")

    assert pdf_url == "https://example.test/full.pdf"
    assert source == "unpaywall"


def test_plan_attach_for_items_builds_source_and_pdf_url(monkeypatch):
    monkeypatch.setattr(
        "research_hub.zotero.pdf_attach.find_pdf_url",
        lambda doi="", arxiv_id="", unpaywall_email="": ("https://arxiv.org/pdf/2604.08224.pdf", "arxiv"),
    )

    plans = plan_attach_for_items(
        [
            {
                "key": "ITEM1",
                "data": {
                    "title": "Paper",
                    "DOI": "10.48550/arXiv.2604.08224",
                    "url": "https://arxiv.org/abs/2604.08224",
                },
            }
        ]
    )

    assert plans[0].item_key == "ITEM1"
    assert plans[0].source == "arxiv"
    assert plans[0].pdf_url.endswith("2604.08224.pdf")


def test_attach_pdfs_creates_imported_url_attachment():
    zot = MagicMock()
    zot.item_template.side_effect = lambda *args: {"itemType": "attachment"}

    results = attach_pdfs(
        zot,
        [
            PdfAttachPlan(item_key="ITEM0", title="Missing", doi="", arxiv_id=""),
            PdfAttachPlan(
                item_key="ITEM1",
                title="Paper",
                doi="10.1000/one",
                arxiv_id="",
                pdf_url="https://example.test/full.pdf",
                source="unpaywall",
            )
        ],
        rate_limit_rps=999.0,
    )

    assert results == {"ITEM0": "skip:no-source", "ITEM1": "ok"}
    payload = zot.create_items.call_args.args[0][0]
    assert payload["parentItem"] == "ITEM1"
    assert payload["contentType"] == "application/pdf"


def test_run_pipeline_with_pdfs_invokes_attach_helpers(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub import pipeline
    from research_hub.manifest import Manifest

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Agents", slug="agents")
    registry.bind("agents", zotero_collection_key="CLUSTER123", sync_zotero=False)
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    zot = MagicMock()
    zot.item_template.side_effect = lambda item_type: {"itemType": item_type}
    zot.create_items.side_effect = lambda items: {"successful": {"0": {"key": "Z0"}}}
    zot.item.side_effect = lambda key: {"key": key, "data": {"key": key, "title": "Paper One", "DOI": "10.1000/one"}}
    monkeypatch.setattr(pipeline, "get_client", lambda: zot)
    monkeypatch.setattr(pipeline, "check_duplicate", lambda zot, title, doi="", **kwargs: False)
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(pipeline, "update_cluster_links", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "_refresh_cluster_base", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "research_hub.zotero.pdf_attach.plan_attach_for_items",
        lambda items, unpaywall_email="": [
            PdfAttachPlan(
                item_key="Z0",
                title="Paper One",
                doi="10.1000/one",
                arxiv_id="2604.08224",
                pdf_url="https://arxiv.org/pdf/2604.08224.pdf",
                source="arxiv",
            )
        ],
    )
    monkeypatch.setattr(
        "research_hub.zotero.pdf_attach.attach_pdfs",
        lambda zot, plans, rate_limit_rps=2.0: {"Z0": "ok"},
    )

    try:
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="agents", verify=False, with_pdfs=True) == 0
        entries = Manifest(cfg.research_hub_dir / "manifest.jsonl").read_all()
        assert any(entry.action == "pdf-attach" and entry.zotero_key == "Z0" for entry in entries)
    finally:
        hub_config._config = None
        hub_config._config_path = None
