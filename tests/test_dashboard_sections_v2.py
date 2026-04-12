"""Dashboard v0.10.0-C section tests — tabbed audit + locator layout."""

from __future__ import annotations

from research_hub.dashboard.sections import (
    BriefingsSection,
    DEFAULT_SECTIONS,
    DiagnosticsSection,
    HeaderSection,
    LibrarySection,
    ManageSection,
    OverviewSection,
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
        notebooklm_notebook="Agents Notebook",
        notebooklm_notebook_url="https://notebooklm.google.com/cluster",
        zotero_collection_key="ZK1234",
        cluster_bibtex="@article{cluster}",
    )
    for key, value in overrides.items():
        setattr(cluster, key, value)
    return cluster


# --- HeaderSection (tabs + counts + search) -----------------------------


def test_header_section_renders_counts_and_briefings():
    html = HeaderSection().render(
        _data(total_papers=12, total_clusters=3, briefings=[
            BriefingPreview(cluster_slug="x", cluster_name="X", notebook_url="", preview_text="", full_text="", char_count=10)
        ])
    )
    assert "12 papers" in html
    assert "3 clusters" in html
    assert "1 briefings" in html


def test_header_section_renders_tabs():
    html = HeaderSection().render(_data())
    assert 'id="dash-tab-overview"' in html
    assert 'id="dash-tab-library"' in html
    assert 'id="dash-tab-briefings"' in html
    assert 'id="dash-tab-diagnostics"' in html
    assert 'id="dash-tab-manage"' in html
    # First tab is checked by default
    assert 'id="dash-tab-overview" class="dash-tab-radio dash-tab-radio-overview" checked' in html


def test_header_section_renders_search_input():
    html = HeaderSection().render(_data())
    assert 'type="search"' in html
    assert 'id="vault-search"' in html


def test_header_section_renders_no_emoji():
    html = HeaderSection().render(_data(total_papers=5))
    # Common emoji ranges should not appear in any rendered text
    for ch in html:
        assert not (0x1F300 <= ord(ch) <= 0x1FAFF), f"emoji codepoint {hex(ord(ch))} found in header"


# --- OverviewSection (treemap + storage + recent) -----------------------


def test_overview_renders_treemap_with_proportional_flex():
    cluster_a = _cluster(slug="a", name="A", papers=[_paper(slug="a-1")] * 5)
    cluster_b = _cluster(slug="b", name="B", papers=[_paper(slug="b-1")] * 20)
    html = OverviewSection().render(
        _data(clusters=[cluster_a, cluster_b], total_clusters=2, total_papers=25)
    )
    assert 'class="treemap"' in html
    assert 'flex: 5 1 0' in html
    assert 'flex: 20 1 0' in html
    assert 'class="treemap-share">20.0%' in html
    assert 'class="treemap-share">80.0%' in html


def test_overview_storage_map_shows_zotero_obsidian_nlm_columns_for_researcher():
    html = OverviewSection().render(
        _data(clusters=[_cluster()], total_clusters=1, total_papers=1)
    )
    assert "<th scope=\"col\">Zotero</th>" in html
    assert "<th scope=\"col\">Obsidian</th>" in html
    assert "<th scope=\"col\">NotebookLM</th>" in html
    assert "ZK1234" in html
    assert "raw/agents" in html
    assert "https://notebooklm.google.com/cluster" in html


def test_overview_storage_map_hides_zotero_for_analyst():
    html = OverviewSection().render(
        _data(persona="analyst", clusters=[_cluster()], total_clusters=1, total_papers=1)
    )
    assert "<th scope=\"col\">Zotero</th>" not in html
    assert "ZK1234" not in html


def test_overview_recent_additions_shows_latest_first_max_15():
    papers = [
        _paper(slug=f"p{i}", title=f"Paper {i}", ingested_at=f"2026-04-{12 - (i % 12):02d}T10:00:00Z")
        for i in range(20)
    ]
    cluster = _cluster(papers=papers)
    html = OverviewSection().render(_data(clusters=[cluster], total_clusters=1, total_papers=20))
    assert "Recent additions" in html
    # Recent feed list items
    count = html.count('class="recent-item"')
    assert count == 15, f"expected 15 recent items, got {count}"


def test_overview_recent_additions_empty_state():
    html = OverviewSection().render(_data())
    assert "No recent additions" in html


# --- LibrarySection (cluster -> paper rows, no badges) ------------------


def test_library_section_empty_state():
    html = LibrarySection().render(_data())
    assert "No clusters yet" in html


def test_library_section_renders_papers_without_status_badges():
    html = LibrarySection().render(
        _data(clusters=[_cluster()], total_clusters=1, total_papers=1)
    )
    assert "Paper One" in html
    assert "Doe, J.; Roe, A." in html
    assert "Download cluster .bib" in html
    # No reading status pill, no Z/O/N badge
    assert 'reading-status' not in html
    assert 'class="status-badge' not in html
    assert 'title="Zotero"' not in html


def test_library_section_renders_binding_links_per_cluster():
    html = LibrarySection().render(
        _data(clusters=[_cluster()], total_clusters=1, total_papers=1)
    )
    assert "Zotero · " in html
    assert "ZK1234" in html
    assert "Obsidian · " in html
    assert "raw/agents" in html
    assert "NotebookLM · " in html
    assert "Agents Notebook" in html


def test_library_section_hides_zotero_for_analyst():
    html = LibrarySection().render(
        _data(persona="analyst", clusters=[_cluster()], total_clusters=1, total_papers=1)
    )
    assert "Zotero · " not in html
    assert ">Cite<" not in html
    assert "Download cluster .bib" not in html


def test_library_section_renders_cite_button_for_researcher():
    html = LibrarySection().render(
        _data(clusters=[_cluster()], total_clusters=1, total_papers=1)
    )
    assert 'class="cite-btn"' in html
    assert 'data-bibtex="@article{paper-one}"' in html


def test_library_section_escapes_html_in_abstract():
    html = LibrarySection().render(
        _data(
            clusters=[_cluster(papers=[_paper(abstract="<script>alert(1)</script> abstract")])],
            total_clusters=1,
            total_papers=1,
        )
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; abstract" in html


# --- BriefingsSection ---------------------------------------------------


def test_briefings_renders_inline_preview():
    briefing = BriefingPreview(
        cluster_slug="agents",
        cluster_name="Agents",
        notebook_url="https://notebooklm.google.com/brief",
        preview_text="Preview body",
        full_text="Full briefing body",
        char_count=240,
        downloaded_at="2026-04-12T09:00:00Z",
    )
    html = BriefingsSection().render(_data(briefings=[briefing]))
    assert 'class="briefing-card"' in html
    assert "Show preview" in html
    assert "Preview body" in html
    assert "Copy full text" in html
    assert "↗ Open in NotebookLM" in html


def test_briefings_empty_state():
    html = BriefingsSection().render(_data())
    assert "No briefings downloaded yet" in html
    assert "research-hub notebooklm download" in html


# --- DiagnosticsSection -------------------------------------------------


def test_diagnostics_renders_health_and_drift():
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
    assert "zotero" in html
    assert "OK" in html
    assert "indexed" in html
    assert "Duplicate DOI" in html
    assert "research-hub dedup fix" in html


def test_diagnostics_empty_state_for_clean_vault():
    html = DiagnosticsSection().render(_data())
    assert "No drift detected" in html


# --- ManageSection ------------------------------------------------------


def test_manage_section_renders_form_per_cluster():
    html = ManageSection().render(
        _data(clusters=[_cluster()], total_clusters=1, total_papers=1)
    )
    assert 'class="manage-card"' in html
    # Six manage forms per cluster
    assert html.count('class="manage-form"') == 6
    assert 'data-action="rename"' in html
    assert 'data-action="merge"' in html
    assert 'data-action="split"' in html
    assert 'data-action="bind-zotero"' in html
    assert 'data-action="bind-nlm"' in html
    assert 'data-action="delete"' in html


def test_manage_section_includes_other_clusters_in_merge_dropdown():
    a = _cluster(slug="a", name="Alpha")
    b = _cluster(slug="b", name="Beta")
    html = ManageSection().render(_data(clusters=[a, b], total_clusters=2, total_papers=2))
    # Both clusters appear as options in the merge select for each card
    assert html.count('<option value="a">Alpha</option>') == 2
    assert html.count('<option value="b">Beta</option>') == 2


def test_manage_section_empty_state():
    html = ManageSection().render(_data())
    assert "No clusters to manage" in html


# --- DEFAULT_SECTIONS ---------------------------------------------------


def test_default_sections_in_correct_order():
    ids = [s.id for s in DEFAULT_SECTIONS]
    assert ids == ["header", "overview", "library", "briefings", "diagnostics", "manage"]
