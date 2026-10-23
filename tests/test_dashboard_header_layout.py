"""Dashboard reflow contracts; these do not replace real-browser layout checks."""
from __future__ import annotations

from html.parser import HTMLParser
import re

import pytest

from research_hub.dashboard.render import render_dashboard
from research_hub.dashboard.types import DashboardData


def _render(vault_root: str) -> str:
    return render_dashboard(DashboardData(
        vault_root=vault_root,
        generated_at="2026-10-23 00:00 UTC · synthetic acceptance fixture",
        persona="analyst",
        total_papers=0,
        total_clusters=0,
        papers_this_week=0,
    ))


def _rules(css: str, selector: str) -> str:
    return "\n".join(re.findall(re.escape(selector) + r"\s*\{([^{}]*)\}", css))


def test_header_can_reflow_without_clipping_identity_or_timestamp():
    html = _render("synthetic_segment_" * 20)
    css = html.split("<style>", 1)[1].split("</style>", 1)[0]
    assert "flex-wrap: wrap" in _rules(css, ".header-bar")
    item_rules = _rules(css, ".header-bar > *")
    assert "min-width: 0" in item_rules
    assert "max-width: 100%" in item_rules
    assert "overflow-wrap: anywhere" in _rules(css, ".header-meta")
    # Do not trade overflow for hidden/truncated source identity or metadata.
    header_rules = "\n".join(_rules(css, selector) for selector in (
        ".app-header", ".header-bar", ".header-bar > *", ".header-meta",
    ))
    assert not re.search(r"overflow(?:-[xy])?\s*:\s*(?:hidden|clip)", header_rules)
    assert "text-overflow" not in header_rules
    assert "white-space: nowrap" not in header_rules


def test_active_panel_and_overview_card_tracks_can_shrink_without_clipping():
    css = _render("/synthetic-vault").split("<style>", 1)[1].split("</style>", 1)[0]
    for selector in ("main", ".card", ".overview-grid"):
        rules = _rules(css, selector)
        assert "grid-template-columns: minmax(0, 1fr)" in rules
        assert not re.search(r"overflow(?:-[xy])?\s*:\s*(?:hidden|clip)", rules)
    assert "min-width: 0" in _rules(css, "main")
    assert "overflow-wrap: anywhere" in _rules(css, "main")


def test_panel_minimums_are_bounded_by_their_padded_container():
    css = _render("/synthetic-vault").split("<style>", 1)[1].split("</style>", 1)[0]
    for selector, minimum in ((".briefing-grid, .diag-grid", 280),
                              (".manage-filter-bar", 180), (".manage-grid", 320)):
        assert f"minmax(min({minimum}px, 100%), 1fr)" in _rules(css, selector)
    assert "min-width: min(200px, 100%)" in _rules(css, ".treemap-cell")
    for selector in (".manage-filter-bar select", ".manage-form textarea",
                     ".composer-form select"):
        assert "min-width: 0" in _rules(css, selector)
        assert "width: 100%" in _rules(css, selector)
    # Diagnostics has later one/two-column overrides: check those too, not
    # only the earlier declaration shared with Briefings.
    diagnostics = _rules(css, ".diag-grid")
    assert "grid-template-columns: minmax(0, 1fr)" in diagnostics
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in diagnostics
    assert "grid-template-columns: 1fr" not in diagnostics


def test_narrow_overview_reflows_recent_rows_and_keeps_the_storage_table():
    css = _render("/synthetic-vault").split("<style>", 1)[1].split("</style>", 1)[0]
    narrow = css.rsplit("@media (max-width: 720px)", 1)[1]
    assert "grid-template-columns: minmax(0, 1fr)" in _rules(narrow, ".recent-item")
    assert "justify-self: start" in _rules(narrow, ".recent-item > .open-btn")
    assert "table-layout: fixed" in _rules(narrow, ".storage-table")
    assert "padding: var(--space-xs)" in _rules(narrow, ".storage-table tbody td")
    assert "display: none" not in _rules(narrow, ".storage-table")


class _HeaderText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


@pytest.mark.parametrize("vault_root", [
    "fixtures/synthetic-vault/" + "synthetic_segment_" * 20 + "/多語研究-évidence-日本語",
    "C:\\synthetic-vault\\" + "unbroken_segment_" * 20 + "\\多語研究-évidence-日本語",
    "synthetic/<img src=x onerror=alert(1)>/" + "unbroken_" * 20 + "&\"'",
])
def test_header_keeps_complete_escaped_long_path_and_generation_text(vault_root):
    html = _render(vault_root)
    header = html.split('<header class="app-header"', 1)[1].split("</header>", 1)[0]
    parsed = _HeaderText()
    parsed.feed("<header" + header + "</header>")
    text = "".join(parsed.text)
    assert vault_root in text
    assert "Generated 2026-10-23 00:00 UTC · synthetic acceptance fixture · Analyst persona" in text
    assert "img" not in parsed.tags
    assert "script" not in parsed.tags
