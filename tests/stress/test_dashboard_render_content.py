from __future__ import annotations

from research_hub.dashboard.render import render_dashboard
from research_hub.dashboard.types import ClusterCard, DashboardData, PaperRow


def test_dashboard_render_large_label_markup_present():
    papers = [
        PaperRow(
            slug=f"paper-{i:03d}",
            title=f"Paper {i}",
            authors="Stress, Test",
            year="2024",
            abstract="Synthetic abstract",
            doi=f"10.9999/paper-{i}",
            labels=["seed"] if i % 2 == 0 else ["core"],
            obsidian_path=f"raw/stress/paper-{i:03d}.md",
        )
        for i in range(300)
    ]
    data = DashboardData(
        vault_root="/vault",
        generated_at="2026-04-13 00:00 UTC",
        persona="researcher",
        total_papers=len(papers),
        total_clusters=1,
        papers_this_week=0,
        clusters=[
            ClusterCard(
                slug="stress",
                name="Stress",
                papers=papers,
                label_counts={"seed": 150, "core": 150},
                archived_count=25,
            )
        ],
        labels_across_clusters={
            "seed": [("stress", paper.slug, paper.title) for paper in papers[:150]],
            "core": [("stress", paper.slug, paper.title) for paper in papers[150:]],
        },
    )

    html = render_dashboard(data)

    assert 'data-label="seed"' in html
    assert 'data-archived="1"' in html
    assert 'data-labels="seed"' in html
    assert "Papers by label (across all clusters)" in html
