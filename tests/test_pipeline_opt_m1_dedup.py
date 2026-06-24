"""M1 (pipeline-opt): ``auto._run_search`` dedups against the persistent
DedupIndex so refreshing a standing cluster only surfaces NEW papers, and
honours ``skip_dedup`` for ``force=overwrite`` re-ingests (where the notes were
just cleared but the DedupIndex still holds the DOIs).
"""
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch, MagicMock

import research_hub.auto as auto


@dataclass
class _Result:
    doi: str | None = None
    title: str = "Some Paper"


def _run(skip_dedup, ingested_dois):
    results = [_Result(doi="10.1/old", title="Old"), _Result(doi="10.2/new", title="New")]
    cfg = MagicMock(research_hub_dir=Path("."))
    idx = MagicMock()
    idx.doi_to_hits = {d: [object()] for d in ingested_dois}
    with patch("research_hub.search.search_papers", return_value=results), \
         patch("research_hub.dedup.DedupIndex.load", return_value=idx), \
         patch("research_hub.auto._to_papers_input", side_effect=lambda dicts, slug: dicts):
        return auto._run_search(
            "topic", max_papers=5, cluster_slug="c",
            cfg=cfg, skip_dedup=skip_dedup,
        )


def test_run_search_drops_already_ingested_doi():
    out = _run(skip_dedup=False, ingested_dois=["10.1/old"])
    dois = [d.get("doi") for d in out]
    assert "10.2/new" in dois          # new paper kept
    assert "10.1/old" not in dois      # already-ingested dropped


def test_skip_dedup_keeps_all_for_overwrite():
    # force=overwrite cleared the notes but the DedupIndex still has the DOIs;
    # skip_dedup must keep everything so the re-ingest is not silently emptied.
    out = _run(skip_dedup=True, ingested_dois=["10.1/old"])
    dois = [d.get("doi") for d in out]
    assert "10.1/old" in dois and "10.2/new" in dois


def test_no_cfg_keeps_all():
    # Without cfg there is no index to dedup against — fail open (keep all).
    results = [_Result(doi="10.1/old"), _Result(doi="10.2/new")]
    with patch("research_hub.search.search_papers", return_value=results), \
         patch("research_hub.auto._to_papers_input", side_effect=lambda dicts, slug: dicts):
        out = auto._run_search("topic", max_papers=5, cluster_slug="c")
    assert len(out) == 2
