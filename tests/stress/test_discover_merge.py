from __future__ import annotations

import time


def test_merge_results_500_candidates_5_backends():
    from research_hub.search._rank import merge_results
    from research_hub.search.base import SearchResult

    def gen_results(backend: str, offset: int, count: int = 100) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"Paper {i + offset}",
                doi=f"10.9999/paper-{i + offset}",
                year=2024,
                source=backend,
                citation_count=i,
            )
            for i in range(count)
        ]

    per_backend = {
        "openalex": gen_results("openalex", 0),
        "crossref": gen_results("crossref", 40),
        "arxiv": gen_results("arxiv", 80),
        "semantic-scholar": gen_results("semantic-scholar", 120),
        "dblp": gen_results("dblp", 160),
    }

    start = time.perf_counter()
    merged = merge_results(per_backend)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0
    seen = set()
    for result in merged:
        assert result.doi not in seen
        seen.add(result.doi)
    multi_backend = [result for result in merged if len(result.found_in) > 1]
    assert len(multi_backend) > 20
