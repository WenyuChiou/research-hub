from __future__ import annotations

from research_hub.dashboard.sections import (
    BriefingShelfSection,
    ClusterListSection,
    DiagnosticsSection,
    HeaderSection,
)
from research_hub.dashboard.types import (
    BriefingPreview,
    ClusterCard,
    DashboardData,
    DriftAlert,
    HealthBadge,
    PaperRow,
)


def _data(**overrides) -> DashboardData:
    base = DashboardData(
        vault_root="/vault",
        generated_at="2026-04-12T12:00:00Z",
        persona="researcher",
        total_papers=0,
        total_clusters=0,
        papers_this_week=0,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _paper(**overrides) -> PaperRow:
    paper = PaperRow(
        slug="paper-one",
        title="Paper One",
        authors="Doe, J.; Roe, A.",
        year="2025",
        abstract="A compact abstract about methods and results.",
        doi="10.1000/one",
        tags=["agents", "memory"],
        status="reading",
        ingested_at="2026-04-11T12:00:00Z",
        obsidian_path="raw/agents/paper-one.md",
        zotero_key="ABC123",
        in_zotero=True,
        in_obsidian=True,
        in_nlm=False,
        bibtex="@article{paper-one}",
    )
    for key, value in overrides.items():
        setattr(paper, key, value)
    return paper


def _cluster(**overrides) -> ClusterCard:
    cluster = ClusterCard(
        slug="agents",
        name="Agents",
        papers=[_paper()],
        zotero_count=1,
        obsidian_count=1,
        nlm_count=0,
        last_activity="2026-04-12T10:00:00Z",
        notebooklm_notebook_url="https://notebooklm.google.com/cluster",
        cluster_bibtex="@article{cluster}",
    )
    for key, value in overrides.items():
        setattr(cluster, key, value)
    return cluster


def test_header_section_renders_counts():
    html = HeaderSection().render(_data(total_papers=12, total_clusters=3, papers_this_week=5))
    assert "12 papers" in html
    assert "3 clusters" in html
    assert "+5 this week" in html


def test_header_section_renders_search_input():
    html = HeaderSection().render(_data())
    assert 'type="search"' in html
    assert 'id="vault-search"' in html
    assert "Search clusters, titles, or tags" in html


def test_cluster_list_section_empty_state():
    html = ClusterListSection().render(_data())
    assert "No clusters yet" in html
    assert "research-hub clusters new" in html


def test_cluster_list_section_renders_papers():
    html = ClusterListSection().render(_data(clusters=[_cluster()], total_clusters=1, total_papers=1))
    assert "Paper One" in html
    assert "Doe, J.; Roe, A." in html
    assert "Download cluster .bib" in html
    assert 'data-title="paper one"' in html


def test_cluster_list_section_first_active_cluster_is_open():
    older = _cluster(slug="older", name="Older", papers=[_paper(slug="older-paper")], last_activity="2026-04-12T08:00:00Z")
    newer = _cluster(
        slug="newer",
        name="Newer",
        papers=[_paper(slug="newer-paper", ingested_at="2026-04-12T11:30:00Z")],
        last_activity="2026-04-12T11:30:00Z",
    )
    html = ClusterListSection().render(_data(clusters=[older, newer], total_clusters=2, total_papers=2))
    assert '<details class="cluster-card" data-cluster="newer" open>' in html
    assert '<details class="cluster-card" data-cluster="older">' in html


def test_cluster_list_section_hides_zotero_for_analyst():
    html = ClusterListSection().render(_data(persona="analyst", clusters=[_cluster()], total_clusters=1, total_papers=1))
    assert "Z 1" not in html
    assert ">Cite<" not in html
    assert "Download cluster .bib" not in html


def test_cluster_list_section_renders_cite_button_for_researcher():
    html = ClusterListSection().render(_data(clusters=[_cluster()], total_clusters=1, total_papers=1))
    assert 'class="cite-btn"' in html
    assert 'data-bibtex="@article{paper-one}"' in html


def test_briefing_shelf_renders_inline_preview():
    briefing = BriefingPreview(
        cluster_slug="agents",
        cluster_name="Agents",
        notebook_url="https://notebooklm.google.com/brief",
        preview_text="Preview body",
        full_text="Full briefing body",
        char_count=240,
        downloaded_at="2026-04-12T09:00:00Z",
    )
    html = BriefingShelfSection().render(_data(briefings=[briefing]))
    assert "AI Briefings" in html
    assert "Show preview" in html
    assert "Preview body" in html
    assert "Copy full text" in html


def test_briefing_shelf_empty_state():
    html = BriefingShelfSection().render(_data())
    assert "No briefings downloaded yet" in html
    assert "research-hub notebooklm download" in html


def test_diagnostics_section_collapsed_by_default():
    html = DiagnosticsSection().render(_data())
    assert '<section id="diagnostics">' in html
    assert "<details>" in html
    assert "<details open>" not in html


def test_paper_row_escapes_html_in_abstract():
    html = ClusterListSection().render(
        _data(
            clusters=[_cluster(papers=[_paper(abstract="<script>alert(1)</script> abstract")])],
            total_clusters=1,
            total_papers=1,
        )
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; abstract" in html


def test_diagnostics_section_renders_health_and_drift():
    html = DiagnosticsSection().render(
        _data(
            health_badges=[HealthBadge(subsystem="zotero", status="OK", summary="indexed")],
            drift_alerts=[
                DriftAlert(
                    kind="duplicate_doi",
                    severity="WARN",
                    title="Duplicate DOI",
                    description="Multiple notes share one DOI.",
                    sample_paths=["raw/agents/a.md"],
                    fix_command="research-hub dedup fix",
                )
            ],
        )
    )
    assert "zotero OK indexed" in html
    assert "Duplicate DOI" in html
    assert "research-hub dedup fix" in html
