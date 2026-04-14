from __future__ import annotations

import json

from research_hub.clusters import ClusterRegistry
from tests.stress._helpers import make_stress_cfg


def test_ingest_100_papers_no_duplicates(tmp_path, monkeypatch):
    cfg = make_stress_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="stress", name="Stress", slug="stress")
    papers = [
        {
            "title": f"Stress Paper {i}",
            "doi": f"10.9999/paper-{i}",
            "authors": [{"creatorType": "author", "firstName": "Stress", "lastName": f"Author{i}"}],
            "year": 2024,
            "abstract": f"Synthetic abstract {i} for stress testing the ingest pipeline.",
            "journal": "Stress Journal",
            "slug": f"stress-paper-{i:04d}",
            "sub_category": "stress",
            "summary": "[TODO]",
            "key_findings": ["[TODO]"],
            "methodology": "[TODO]",
            "relevance": "[TODO]",
        }
        for i in range(100)
    ]
    (cfg.root / "papers_input.json").write_text(json.dumps(papers, indent=2), encoding="utf-8")
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.pipeline.time.sleep", lambda _: None)

    from research_hub.pipeline import run_pipeline

    rc = run_pipeline(dry_run=False, cluster_slug="stress", verify=False)

    assert rc == 0

    from research_hub.dedup import DedupIndex

    index = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    assert len(index.doi_to_hits) >= 100
