"""Artifact reflow/semantic contracts, not a substitute for browser geometry QA."""
from __future__ import annotations

import re
from urllib.parse import quote
from xml.etree import ElementTree as ET

from research_hub.dashboard.render import render_dashboard
from research_hub.dashboard.sections import BriefingsSection
from research_hub.dashboard.types import ClusterCard, DashboardData, NLMArtifactRecord


LABELS = ("Artifact", "Downloaded", "Char count", "Open")
LONG_DATE = "syntheticdate" * 12


def _cluster():
    return ClusterCard(slug="synthetic", name="Synthetic artifacts", nlm_artifacts=[
        NLMArtifactRecord(kind="brief", downloaded_at="2026-10-23T00:00:00Z", char_count=12345),
        NLMArtifactRecord(kind="audio", downloaded_at=LONG_DATE, char_count=9876543210123456789,
                          path="synthetic/" + "segment" * 40 + ".txt",
                          notebook_url="https://example.invalid/synthetic"),
        NLMArtifactRecord(kind="mind_map", char_count=0),
        NLMArtifactRecord(kind="video", downloaded_at="synthetic é 日本語 合成", char_count=987),
    ])


def _html():
    return render_dashboard(DashboardData(
        vault_root="/synthetic-vault", generated_at="synthetic fixture", persona="researcher",
        total_papers=0, total_clusters=1, papers_this_week=0, clusters=[_cluster()],
    ))


def _rules(css, selector):
    return "\n".join(re.findall(re.escape(selector) + r"\s*\{([^{}]*)\}", css))


def test_artifact_table_keeps_roles_headers_and_full_labelled_values():
    tile = ET.fromstring(BriefingsSection()._artifact_tile(_cluster()))
    table = tile.find("table")
    assert table is not None
    assert table.attrib == {"class": "briefing-artifact-table", "role": "table",
                            "aria-label": "NotebookLM artifacts"}
    for group in (table.find("thead"), table.find("tbody")):
        assert group is not None and group.get("role") == "rowgroup"
        assert all(row.get("role") == "row" for row in group)
    headers = table.findall("./thead/tr/th")
    assert tuple(h.text for h in headers) == LABELS
    assert all(h.get("scope") == "col" and h.get("role") == "columnheader" for h in headers)
    rows = table.findall("./tbody/tr")
    assert len(rows) == 4
    values = []
    for row in rows:
        assert len(row) == 4
        value_row = []
        for cell, label in zip(row, LABELS):
            assert cell.tag == "td" and cell.get("role") == "cell"
            visual_label, value = list(cell)
            assert visual_label.attrib == {"class": "briefing-artifact-label", "aria-hidden": "true"}
            assert visual_label.text == label
            assert value.get("class") == "briefing-artifact-value"
            value_row.append("".join(value.itertext()))
        values.append(value_row)
    assert [r[0] for r in values] == ["brief", "audio", "mind map", "video"]
    assert values[1][1] == LONG_DATE
    assert values[1][2] == "9,876,543,210,123,456,789"
    assert values[3][1] == "synthetic é 日本語 合成"
    # Full controls/targets survive; no click or operation is executed here.
    open_cell = rows[1][3]
    links = open_cell.findall("./span/a")
    assert [a.text for a in links] == ["open in NLM", "open .txt"]
    assert links[1].get("href") == "/artifact?path=" + quote(_cluster().nlm_artifacts[1].path, safe="")
    button = open_cell.find("./span/button")
    assert button is not None and button.get("type") == "button"
    assert button.get("data-action") == "delete-artifact"


def test_artifact_renderer_preserves_escaped_content_and_control_payloads():
    cluster = _cluster()
    artifact = cluster.nlm_artifacts[1]
    artifact.downloaded_at = '<img src=x onerror="bad()"> & 日本語'
    artifact.path = 'synthetic/<img>&".txt'
    artifact.notebook_url = 'https://example.invalid/?q="<&'
    tile = ET.fromstring(BriefingsSection()._artifact_tile(cluster))
    assert not list(tile.iter("img"))
    row = tile.findall("./table/tbody/tr")[1]
    assert row[1].find("span[@class='briefing-artifact-value']").text == artifact.downloaded_at
    assert row[3].find("./span/a").get("href") == artifact.notebook_url
    assert row[3].find("./span/button").get("data-path") == quote(artifact.path, safe="")


def test_real_dashboard_includes_artifact_table_and_repeated_visual_labels():
    html = _html()
    assert '<table class="briefing-artifact-table" role="table"' in html
    assert html.count('class="briefing-artifact-label" aria-hidden="true"') == 16


def test_narrow_artifact_values_stack_without_clipping_or_changing_wide_table():
    html = _html()
    css = html.split("<style>", 1)[1].split("</style>", 1)[0]
    wide, narrow = css.rsplit("@media (max-width: 720px)", 1)
    assert not _rules(wide, ".briefing-artifact-table")
    assert "display: none" in _rules(wide, ".briefing-artifact-label")
    # v2 squeezed four columns into 20/24px. Each value now occupies its own
    # full-width block; no guessed numeric pixel measurement is asserted here.
    for selector in (".briefing-artifact-table", ".briefing-artifact-table tbody",
                     ".briefing-artifact-table tbody tr", ".briefing-artifact-table td",
                     ".briefing-artifact-label", ".briefing-artifact-value"):
        assert "display: block" in _rules(narrow, selector)
    assert "width: 100%" in _rules(narrow, ".briefing-artifact-table")
    assert "overflow-wrap: anywhere" in _rules(wide, ".briefing-artifact-value")
    # Only duplicated visual column headings are clipped, never actual data.
    headings = _rules(narrow, ".briefing-artifact-table thead")
    assert "position: absolute" in headings and "clip-path: inset(50%)" in headings
    assert "display: none" not in headings and "visibility: hidden" not in headings
    for selector in (".briefing-artifact-table", ".briefing-artifact-table tbody",
                     ".briefing-artifact-table tbody tr", ".briefing-artifact-table td",
                     ".briefing-artifact-value"):
        rules = _rules(css, selector)
        assert not re.search(r"overflow(?:-[xy])?\s*:\s*(?:hidden|clip)", rules)
        assert "text-overflow" not in rules and "white-space: nowrap" not in rules
    controls = _rules(narrow, ".briefing-artifact-table td:last-child .briefing-artifact-value")
    assert "display: flex" in controls and "flex-wrap: wrap" in controls
