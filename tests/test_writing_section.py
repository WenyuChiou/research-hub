from __future__ import annotations

from research_hub.dashboard.sections import HeaderSection, LibrarySection
from research_hub.dashboard.types import ClusterCard, DashboardData, PaperRow, Quote
from research_hub.dashboard.writing_section import WritingSection


def _data(**overrides) -> DashboardData:
    data = DashboardData(
        vault_root="/vault",
        generated_at="2026-04-12T12:00:00Z",
        persona="researcher",
        total_papers=0,
        total_clusters=0,
        papers_this_week=0,
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


def _paper(**overrides) -> PaperRow:
    paper = PaperRow(
        slug="paper-one",
        title="Paper One",
        authors="Doe, Jane",
        year="2025",
        abstract="Abstract",
        doi="10.1000/one",
        status="reading",
        bibtex="@article{paper-one}",
    )
    for key, value in overrides.items():
        setattr(paper, key, value)
    return paper


def _cluster(**overrides) -> ClusterCard:
    cluster = ClusterCard(slug="agents", name="Agents", papers=[_paper(status="cited")])
    for key, value in overrides.items():
        setattr(cluster, key, value)
    return cluster


def _quote(**overrides) -> Quote:
    quote = Quote(
        slug="paper-one",
        doi="10.1000/one",
        title="Paper One",
        authors="Doe, Jane",
        year="2025",
        cluster_slug="agents",
        cluster_name="Agents",
        page="12",
        text="Quoted passage",
        captured_at="2026-04-12T12:00:00Z",
    )
    for key, value in overrides.items():
        setattr(quote, key, value)
    return quote


def test_writing_section_empty_state():
    html = WritingSection().render(_data())
    assert "No captured quotes yet" in html


def test_writing_section_renders_quote_cards():
    html = WritingSection().render(_data(quotes=[_quote()]))
    assert 'class="writing-quote-card"' in html
    assert "Quoted passage" in html


def test_writing_section_groups_quotes_by_cluster():
    html = WritingSection().render(_data(quotes=[_quote(), _quote(slug="paper-two", cluster_name="Policy")]))
    assert "Agents" in html
    assert "Policy" in html


def test_writing_section_renders_cited_papers():
    html = WritingSection().render(_data(clusters=[_cluster()], total_clusters=1, total_papers=1))
    assert "Marked cited" in html
    assert "Copy citation" in html


def test_writing_section_hides_cited_when_none():
    html = WritingSection().render(_data(quotes=[_quote()]))
    assert "No papers are marked" in html


def test_paper_row_has_quote_button():
    html = LibrarySection().render(_data(clusters=[_cluster()], total_clusters=1, total_papers=1))
    assert 'class="quote-btn"' in html


def test_header_section_includes_writing_tab_radio():
    html = HeaderSection().render(_data())
    assert 'dash-tab-radio-writing' in html
