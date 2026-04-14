from __future__ import annotations

import time

import pytest

from tests.stress._helpers import build_synthetic_vault


@pytest.mark.parametrize("paper_count", [100, 500, 2000, 5000])
def test_dashboard_render_under_time_budget(paper_count, tmp_path, monkeypatch):
    cfg = build_synthetic_vault(tmp_path, clusters=5, papers_per_cluster=paper_count // 5)
    monkeypatch.setattr("research_hub.dashboard.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    monkeypatch.setattr("research_hub.dashboard.data.load_all_quotes", lambda cfg: [], raising=False)

    from research_hub.dashboard import generate_dashboard

    start = time.perf_counter()
    out_path = generate_dashboard()
    elapsed = time.perf_counter() - start
    budget = 2.0 + 0.003 * paper_count

    assert out_path.exists()
    assert elapsed < budget, f"{paper_count} papers: {elapsed:.2f}s > budget {budget:.2f}s"
