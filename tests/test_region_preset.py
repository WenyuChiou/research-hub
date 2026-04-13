from __future__ import annotations

from research_hub.search.fallback import resolve_backends_for_region


def test_resolve_region_jp_includes_cinii():
    assert resolve_backends_for_region("jp") == ("openalex", "cinii", "crossref")


def test_resolve_region_cjk_includes_both_cinii_and_kci():
    assert resolve_backends_for_region("cjk") == ("openalex", "cinii", "kci", "crossref")
