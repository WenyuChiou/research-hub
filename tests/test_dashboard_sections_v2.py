"""Dashboard v0.10.0-C section tests — tabbed audit + locator layout."""

from __future__ import annotations

from research_hub.dashboard.sections import (
    BriefingsSection,
    DEFAULT_SECTIONS,
    DebugSection,
    DiagnosticsSection,
    HeaderSection,
    LibrarySection,
    ManageSection,
    OverviewSection,
    WritingSection,
    _render_archived_section,
    _render_cross_cluster_labels,
    _render_label_breakdown,
)
from research_hub.dashboard.types import (
    BriefingPreview,
    ClusterCard,
    DashboardData,
    DriftAlert,
    HealthBadge,
    PaperRow,
    Quote,
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
    assert 'id="dash-tab-writing"' in html
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
    """Treemap uses sqrt(count) for flex weights so tiny clusters
    stay readable next to giant ones — but the displayed share
    percentage is still computed from the raw counts."""
    cluster_a = _cluster(slug="a", name="A", papers=[_paper(slug="a-1")] * 4)
    cluster_b = _cluster(slug="b", name="B", papers=[_paper(slug="b-1")] * 16)
    html = OverviewSection().render(
        _data(clusters=[cluster_a, cluster_b], total_clusters=2, total_papers=20)
    )
    assert 'class="treemap"' in html
    # sqrt(4) = 2.0, sqrt(16) = 4.0
    assert 'flex: 2.0 1 0' in html
    assert 'flex: 4.0 1 0' in html
    # Share is raw percentage — 4/20 = 20%, 16/20 = 80%
    assert 'class="treemap-share">20.0% of vault' in html
    assert 'class="treemap-share">80.0% of vault' in html
    # Jump target is the library tab (no hash anchors for file:// safety)
    assert 'data-jump-tab="library"' in html
    assert 'href="#tab-library"' not in html


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


def test_paper_row_has_quote_button():
    html = LibrarySection().render(
        _data(clusters=[_cluster()], total_clusters=1, total_papers=1)
    )
    assert 'class="quote-btn"' in html
    assert 'data-slug="paper-one"' in html


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


def test_render_label_breakdown_makes_chips_clickable():
    html = _render_label_breakdown({"seed": 2, "core": 1}, 0, "agents")
    assert 'class="cluster-label"' in html
    assert 'data-label="seed"' in html
    assert 'data-cluster="agents"' in html
    assert "<a " in html


def test_render_label_breakdown_active_class_when_matching_filter():
    html = _render_label_breakdown({"seed": 2}, 0, "agents", active_label="seed")
    assert 'cluster-label cluster-label--active' in html


def test_render_archived_section_hidden_when_no_archived_papers():
    html = _render_archived_section(_cluster(archived_papers=[]))
    assert html == ""


def test_render_archived_section_shows_unarchive_command():
    html = _render_archived_section(
        _cluster(
            archived_papers=[{"slug": "old-paper", "title": "Old Paper", "labels": ["deprecated"], "fit_reason": "", "fit_score": "1"}]
        )
    )
    assert "research-hub paper unarchive --cluster agents --slug old-paper" in html
    assert "unarchive cmd" in html


def test_render_archived_section_shows_fit_reason():
    html = _render_archived_section(
        _cluster(
            archived_papers=[{"slug": "old-paper", "title": "Old Paper", "labels": ["deprecated"], "fit_reason": "off topic", "fit_score": "1"}]
        )
    )
    assert "off topic" in html


def test_render_cross_cluster_labels_empty_when_no_labels():
    assert _render_cross_cluster_labels({}) == ""


def test_render_cross_cluster_labels_groups_by_canonical_order():
    html = _render_cross_cluster_labels(
        {
            "benchmark": [("agents", "paper-b", "Benchmark Paper")],
            "seed": [("agents", "paper-a", "Seed Paper")],
        }
    )
    assert html.index("seed (1)") < html.index("benchmark (1)")


def test_render_cross_cluster_labels_per_paper_links_to_obsidian():
    html = _render_cross_cluster_labels({"seed": [("agents", "paper-a", "Seed Paper")]})
    assert 'obsidian://open?path=raw/agents/paper-a.md' in html
    assert "Seed Paper" in html


def test_paper_row_includes_label_chips_when_labels_set():
    html = LibrarySection().render(
        _data(clusters=[_cluster(papers=[_paper(labels=["seed", "benchmark"])])], total_clusters=1, total_papers=1)
    )
    assert 'class="paper-row-labels"' in html
    assert 'class="paper-label-chip">seed<' in html
    assert 'class="paper-label-chip">benchmark<' in html


def test_paper_row_has_data_labels_attribute_for_filter_js():
    html = LibrarySection().render(
        _data(clusters=[_cluster(papers=[_paper(labels=["seed", "core"])])], total_clusters=1, total_papers=1)
    )
    assert 'data-labels="seed,core"' in html


def test_paper_row_data_cluster_row_attribute():
    html = LibrarySection().render(_data(clusters=[_cluster()], total_clusters=1, total_papers=1))
    assert 'data-cluster-row="agents"' in html


def test_library_section_renders_cross_cluster_label_view():
    html = LibrarySection().render(
        _data(
            clusters=[_cluster()],
            labels_across_clusters={"seed": [("agents", "paper-one", "Paper One")]},
            total_clusters=1,
            total_papers=1,
        )
    )
    assert "Papers by label (across all clusters)" in html
    assert "seed (1)" in html


def test_cluster_card_label_chips_match_clicker_js_selector():
    html = LibrarySection().render(
        _data(clusters=[_cluster(label_counts={"seed": 2})], total_clusters=1, total_papers=1)
    )
    assert 'class="cluster-label"' in html
    assert 'data-label="seed"' in html


def test_label_breakdown_skips_zero_count_labels():
    html = _render_label_breakdown({"seed": 0, "core": 1}, 0, "agents")
    assert "seed:" not in html
    assert "core: 1" in html


def test_label_breakdown_includes_archived_chip_when_count_gt_0():
    html = _render_label_breakdown({}, 3, "agents")
    assert 'data-archived="1"' in html
    assert "archived: 3" in html


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
    assert "Open in NotebookLM" in html


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
    # Original six forms plus seven v0.42/v0.43 action forms
    assert html.count('class="manage-form"') == 13
    assert 'data-action="rename"' in html
    assert 'data-action="merge"' in html
    assert 'data-action="split"' in html
    assert 'data-action="bind-zotero"' in html
    assert 'data-action="bind-nlm"' in html
    assert 'data-action="delete"' in html
    assert 'data-action="notebooklm-ask"' in html
    assert 'data-action="vault-polish-markdown"' in html
    assert 'data-action="bases-emit"' in html


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


# --- WritingSection -----------------------------------------------------


def _quote(**overrides) -> Quote:
    quote = Quote(
        slug="paper-one",
        doi="10.1000/one",
        title="Paper One",
        authors="Doe, J.; Roe, A.",
        year="2025",
        cluster_slug="agents",
        cluster_name="Agents",
        page="12",
        text="Quoted passage about coordination.",
        captured_at="2026-04-12T12:00:00Z",
        context_note="Section 3.2",
    )
    for key, value in overrides.items():
        setattr(quote, key, value)
    return quote


def test_writing_section_empty_state():
    html = WritingSection().render(_data())
    assert "No captured quotes yet" in html
    assert "marked cited" in html


def test_writing_section_renders_quote_cards():
    html = WritingSection().render(_data(quotes=[_quote()]))
    assert 'class="writing-quote-card quote-card"' in html
    assert "Quoted passage about coordination." in html
    assert "Copy as markdown" in html
    assert "Copy inline" in html


def test_writing_section_renders_label_filter_chips():
    html = WritingSection().render(_data(quotes=[_quote(paper_labels=["seed", "benchmark"])]))
    assert 'class="quote-filter-chip active"' in html
    assert 'data-label="seed"' in html
    assert 'data-label="benchmark"' in html


def test_writing_section_quote_card_has_data_paper_labels():
    html = WritingSection().render(_data(quotes=[_quote(paper_labels=["seed", "benchmark"])]))
    assert 'class="writing-quote-card quote-card"' in html
    assert 'data-paper-labels="seed,benchmark"' in html


def test_writing_section_filter_bar_lists_all_distinct_labels():
    html = WritingSection().render(
        _data(
            quotes=[
                _quote(paper_labels=["seed", "benchmark"]),
                _quote(slug="paper-two", paper_labels=["seed", "core"]),
            ]
        )
    )
    assert html.count('data-label="seed"') == 1
    assert 'data-label="core"' in html
    assert 'data-label="benchmark"' in html


def test_writing_section_groups_quotes_by_cluster():
    html = WritingSection().render(
        _data(quotes=[_quote(cluster_name="Agents"), _quote(slug="paper-two", cluster_name="Policy")])
    )
    assert "Agents" in html
    assert "Policy" in html


def test_writing_section_renders_cited_papers():
    cited = _cluster(papers=[_paper(status="cited")])
    html = WritingSection().render(_data(clusters=[cited], total_clusters=1, total_papers=1))
    assert "Cited papers" in html
    assert "Marked cited" in html
    assert "Copy citation" in html


def test_writing_section_hides_cited_when_none():
    html = WritingSection().render(_data(quotes=[_quote()]))
    assert "No papers are marked" in html


def test_writing_section_renders_composer_panel():
    html = WritingSection().render(
        _data(
            clusters=[_cluster()],
            quotes=[_quote()],
            total_clusters=1,
            total_papers=1,
        )
    )
    assert 'class="composer-panel"' in html
    assert 'name="cluster"' in html
    assert 'name="outline"' in html
    assert "Build draft command" in html


def test_writing_section_composer_has_style_radios():
    html = WritingSection().render(
        _data(
            clusters=[_cluster()],
            quotes=[_quote()],
            total_clusters=1,
            total_papers=1,
        )
    )
    assert 'type="radio" name="style" value="apa" checked' in html
    assert 'type="radio" name="style" value="chicago"' in html
    assert 'type="radio" name="style" value="mla"' in html
    assert 'type="radio" name="style" value="latex"' in html


def test_writing_section_composer_lists_all_quotes_as_checkboxes():
    html = WritingSection().render(
        _data(
            clusters=[_cluster()],
            quotes=[_quote(), _quote(slug="paper-two", title="Paper Two")],
            total_clusters=1,
            total_papers=2,
        )
    )
    assert html.count('class="composer-quote-option"') == 2
    assert 'data-select-id="paper-one"' in html
    assert 'data-select-id="paper-two"' in html
    assert 'data-slug="paper-one"' in html
    assert 'data-slug="paper-two"' in html


def test_header_section_includes_writing_tab_radio():
    html = HeaderSection().render(_data())
    assert 'class="dash-tab-radio dash-tab-radio-writing"' in html


# --- DEFAULT_SECTIONS ---------------------------------------------------


def test_default_sections_in_correct_order():
    ids = [s.id for s in DEFAULT_SECTIONS]
    assert ids == ["header", "overview", "library", "briefings", "writing", "diagnostics", "manage", "debug"]


def test_debug_section_renders_snapshot_with_vault_metadata():
    html = DebugSection().render(
        _data(
            total_papers=42,
            total_clusters=2,
            clusters=[_cluster(slug="a", name="A"), _cluster(slug="b", name="B")],
            health_badges=[HealthBadge(subsystem="zotero", status="FAIL", summary="No API key")],
        )
    )
    assert 'id="debug-section"' in html
    assert "Spot a bug" in html
    assert "Copy snapshot" in html
    # Snapshot includes vault summary + cluster slugs
    assert "vault_root: /vault" in html
    assert "total_papers: 42" in html
    assert "slug=&#39;a&#39;" in html
    assert "zotero: FAIL" in html


def test_overview_health_banner_when_check_fails():
    badge = HealthBadge(
        subsystem="zotero",
        status="FAIL",
        summary="No API key",
        items=[{"name": "zotero_key", "status": "FAIL", "message": "No Zotero API key found", "remedy": "Set ZOTERO_API_KEY"}],
    )
    html = OverviewSection().render(_data(health_badges=[badge]))
    assert 'class="health-badge"' in html
    assert '<details class="health-badge" data-status="fail">' in html
    assert "click to expand" in html
    assert "zotero_key:" in html
    assert "No Zotero API key" in html


def test_overview_health_banner_hidden_when_clean():
    html = OverviewSection().render(_data())
    assert "health-badge" not in html
