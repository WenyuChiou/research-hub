from __future__ import annotations

import random
import time

from tests.stress._helpers import build_synthetic_cluster, make_stress_cfg


def test_topic_build_30_subtopics_100_papers(tmp_path):
    cfg = make_stress_cfg(tmp_path)
    build_synthetic_cluster(cfg, "stress", 100)

    from research_hub.topic import apply_assignments, build_subtopic_notes

    random.seed(42)
    subtopic_pool = [f"subtopic-{i:02d}" for i in range(30)]
    assignments = {}
    for i in range(100):
        slug = f"stress-stress-{i:04d}"
        chosen = random.sample(subtopic_pool, random.randint(1, 3))
        assignments[slug] = chosen
    apply_assignments(cfg, "stress", assignments)

    start = time.perf_counter()
    written = build_subtopic_notes(cfg, "stress")
    elapsed = time.perf_counter() - start

    assert len(written) == 30
    assert elapsed < 15.0
