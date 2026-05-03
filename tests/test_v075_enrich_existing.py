from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from research_hub.clusters import ClusterRegistry
from research_hub.search.base import SearchResult
from research_hub.zotero.enrich import EnrichPlan, apply_enrichment, plan_enrichment


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    rh = root / ".research_hub"
    raw.mkdir(parents=True)
    rh.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=root / "hub",
        research_hub_dir=rh,
        clusters_file=rh / "clusters.yaml",
    )


def _item(doi: str = "10.1000/one", **data) -> dict:
    payload = {"DOI": doi, "title": "Example", "volume": "", "issue": "", "pages": "", "url": "", "abstractNote": ""}
    payload.update(data)
    return {"key": "ITEM1", "data": payload}


def test_plan_enrichment_fills_fields_from_crossref(monkeypatch):
    monkeypatch.setattr(
        "research_hub.search.crossref.CrossrefBackend.get_paper",
        lambda self, doi: SearchResult(
            title="Example",
            doi=doi,
            abstract="Abstract",
            url="https://doi.org/10.1000/one",
            volume="12",
            issue="4",
            pages="10-20",
        ),
    )
    monkeypatch.setattr("research_hub.search.openalex.OpenAlexBackend.get_paper", lambda self, doi: None)

    plans = plan_enrichment([_item()])

    assert len(plans) == 1
    assert plans[0].fields_to_fill["volume"] == "12"
    assert plans[0].fields_to_fill["abstractNote"] == "Abstract"


def test_plan_enrichment_uses_openalex_as_fallback(monkeypatch):
    monkeypatch.setattr(
        "research_hub.search.crossref.CrossrefBackend.get_paper",
        lambda self, doi: SearchResult(title="Example", doi=doi),
    )
    monkeypatch.setattr(
        "research_hub.search.openalex.OpenAlexBackend.get_paper",
        lambda self, doi: SearchResult(
            title="Example",
            doi=doi,
            url="https://openalex.org/example",
            pages="1-2",
        ),
    )

    plans = plan_enrichment([_item()])

    assert plans[0].fields_to_fill["url"] == "https://openalex.org/example"
    assert plans[0].fields_to_fill["pages"] == "1-2"


def test_plan_enrichment_skips_items_without_doi(monkeypatch):
    monkeypatch.setattr("research_hub.search.crossref.CrossrefBackend.get_paper", lambda self, doi: None)
    monkeypatch.setattr("research_hub.search.openalex.OpenAlexBackend.get_paper", lambda self, doi: None)

    assert plan_enrichment([_item(doi="")]) == []


def test_apply_enrichment_only_fills_empty_fields():
    class _Zot:
        def __init__(self) -> None:
            self.updated: list[dict] = []

        def item(self, key: str) -> dict:
            return {
                "data": {
                    "key": key,
                    "volume": "",
                    "issue": "existing-issue",
                    "pages": "",
                }
            }

        def update_item(self, data: dict) -> dict:
            self.updated.append(data.copy())
            return {}

    zot = _Zot()
    results = apply_enrichment(
        zot,
        [
            EnrichPlan(
                item_key="ITEM1",
                title="Example",
                doi="10.1000/one",
                fields_to_fill={"volume": "12", "issue": "9", "pages": "10-20"},
            )
        ],
        rate_limit_rps=999.0,
    )

    assert results == {"ITEM1": "ok"}
    assert zot.updated[0]["volume"] == "12"
    assert zot.updated[0]["issue"] == "existing-issue"
    assert zot.updated[0]["pages"] == "10-20"


def test_cli_paper_enrich_existing_writes_manifest_entries(tmp_path, monkeypatch):
    from research_hub import cli
    from research_hub.manifest import Manifest

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Agents", slug="agents")
    registry.bind("agents", zotero_collection_key="COLL1", sync_zotero=False)
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: object())
    monkeypatch.setattr(
        "research_hub.vault.sync.list_zotero_collection_items",
        lambda zot, key: [{"key": "ITEM1", "data": {"DOI": "10.1000/one", "title": "Example"}}],
    )
    monkeypatch.setattr(
        "research_hub.zotero.enrich.plan_enrichment",
        lambda items: [
            EnrichPlan(
                item_key="ITEM1",
                title="Example",
                doi="10.1000/one",
                fields_to_fill={"volume": "12"},
            )
        ],
    )
    monkeypatch.setattr(
        "research_hub.zotero.enrich.apply_enrichment",
        lambda zot, plans, rate_limit_rps=2.0: {"ITEM1": "ok"},
    )

    rc = cli.main(["paper", "enrich-existing", "--cluster", "agents", "--apply"])

    assert rc == 0
    entries = Manifest(cfg.research_hub_dir / "manifest.jsonl").read_all()
    assert entries[-1].action == "enrich-existing"
    assert entries[-1].zotero_key == "ITEM1"
