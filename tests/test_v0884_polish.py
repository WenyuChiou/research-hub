"""v0.88.4 polish — paper retype cleans body too + frontmatter list dedupe."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from research_hub.paper import (
    _render_field,
    _rewrite_paper_body_after_retype,
    retype_paper,
)


# ---------------------------------------------------------------------------
# v0.88.4 #1 — paper retype body cleanup
# ---------------------------------------------------------------------------


def _seed_note_with_body(vault: Path, slug: str, *, zotero_key: str,
                         citation_line: str, footer_key: str) -> Path:
    raw = vault / "raw" / "demo"
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / f"{slug}.md"
    path.write_text(
        f"""---
title: "T"
topic_cluster: "demo"
zotero-key: {zotero_key}
---

# T

**Authors:** Smith
**Year:** 2025
**Citation:** {citation_line}
**DOI:** 10.1061/abc

## Abstract
...

---
*Source: Zotero key `{footer_key}`*
""",
        encoding="utf-8",
    )
    return path


def test_retype_body_cleanup_replaces_citation_and_footer_for_conferencePaper(
    tmp_path: Path,
) -> None:
    note = _seed_note_with_body(
        tmp_path, "goldshtein2025",
        zotero_key="3A5FNAXZ",
        citation_line="arXiv, 921-928",
        footer_key="3A5FNAXZ",
    )
    new_data = {
        "itemType": "conferencePaper",
        "proceedingsTitle": "World Environmental and Water Resources Congress 2025",
        "volume": "",
        "issue": "",
        "pages": "921-928",
        "DOI": "10.1061/9780784486184.086",
    }
    _rewrite_paper_body_after_retype(
        note,
        new_zotero_key="8AVTNDDW",
        old_zotero_key="3A5FNAXZ",
        new_item_data=new_data,
        target_type="conferencePaper",
        target_venue_field="proceedingsTitle",
    )
    text = note.read_text(encoding="utf-8")
    assert "arXiv, 921-928" not in text
    assert "**Citation:** World Environmental and Water Resources Congress 2025, 921-928" in text
    assert "`3A5FNAXZ`" not in text
    assert "`8AVTNDDW`" in text


def test_retype_body_cleanup_dataset_uses_zenodo_marker(tmp_path: Path) -> None:
    note = _seed_note_with_body(
        tmp_path, "arnold2026",
        zotero_key="I92RXW72",
        citation_line="Open MIND",
        footer_key="I92RXW72",
    )
    new_data = {
        "itemType": "dataset",
        "DOI": "10.5281/zenodo.18444869",
        "volume": "",
        "issue": "",
        "pages": "",
    }
    _rewrite_paper_body_after_retype(
        note,
        new_zotero_key="UHI4TD4Z",
        old_zotero_key="I92RXW72",
        new_item_data=new_data,
        target_type="dataset",
        target_venue_field="",
    )
    text = note.read_text(encoding="utf-8")
    assert "Open MIND" not in text
    assert "**Citation:** Dataset (Zenodo)" in text
    assert "`UHI4TD4Z`" in text


def test_retype_body_cleanup_dataset_figshare_marker(tmp_path: Path) -> None:
    note = _seed_note_with_body(
        tmp_path, "demo2025",
        zotero_key="OLD",
        citation_line="Some Journal",
        footer_key="OLD",
    )
    new_data = {
        "itemType": "dataset",
        "DOI": "10.6084/m9.figshare.12345",
    }
    _rewrite_paper_body_after_retype(
        note,
        new_zotero_key="NEW",
        old_zotero_key="OLD",
        new_item_data=new_data,
        target_type="dataset",
        target_venue_field="",
    )
    text = note.read_text(encoding="utf-8")
    assert "**Citation:** Dataset (Figshare)" in text


def test_retype_body_cleanup_dataset_generic_marker_when_no_doi(tmp_path: Path) -> None:
    note = _seed_note_with_body(
        tmp_path, "demo2025",
        zotero_key="OLD",
        citation_line="Some Journal",
        footer_key="OLD",
    )
    new_data = {
        "itemType": "dataset",
        "DOI": "",
    }
    _rewrite_paper_body_after_retype(
        note,
        new_zotero_key="NEW",
        old_zotero_key="OLD",
        new_item_data=new_data,
        target_type="dataset",
        target_venue_field="",
    )
    text = note.read_text(encoding="utf-8")
    assert "**Citation:** Dataset" in text


def test_retype_body_cleanup_skips_if_no_citation_line(tmp_path: Path) -> None:
    """Older notes without a **Citation:** line should be no-op silently
    rather than raising — defensive against schema drift."""
    raw = tmp_path / "raw" / "demo"
    raw.mkdir(parents=True)
    path = raw / "p.md"
    path.write_text(
        "---\ntitle: x\nzotero-key: OLD\n---\n# T\n*Source: Zotero key `OLD`*\n",
        encoding="utf-8",
    )
    _rewrite_paper_body_after_retype(
        path,
        new_zotero_key="NEW",
        old_zotero_key="OLD",
        new_item_data={"itemType": "conferencePaper", "proceedingsTitle": "X"},
        target_type="conferencePaper",
        target_venue_field="proceedingsTitle",
    )
    text = path.read_text(encoding="utf-8")
    # Footer was updated; absence of Citation line didn't crash.
    assert "`NEW`" in text


# ---------------------------------------------------------------------------
# v0.88.4 #2 — _render_field list dedupe
# ---------------------------------------------------------------------------


def test_render_field_dedupes_string_list_order_preserving() -> None:
    """A list with duplicates should render once each, in first-seen order."""
    lines = _render_field("cluster_queries", ["q1", "q2", "q1", "q3", "q2"])
    assert lines == [
        "cluster_queries:",
        "  - q1",
        "  - q2",
        "  - q3",
    ]


def test_render_field_keeps_empty_list_as_inline_marker() -> None:
    assert _render_field("collections", []) == ["collections: []"]


def test_render_field_dedupes_repeated_query_blocks() -> None:
    """The exact arnold/goldshtein bug: 5 queries appended 3 times → 15
    duplicated lines. After dedup the rendered list is 5 unique entries."""
    five_queries = [
        "LLMs and generative AI: water management",
        "hydrology",
        "flood risk",
        "sociohydrology",
        "agent-based modeling",
    ]
    accumulated = five_queries * 3  # 15 lines on disk before v0.88.4
    lines = _render_field("cluster_queries", accumulated)
    # Header line + 5 unique entries (not 15)
    assert len(lines) == 6
    assert lines[0] == "cluster_queries:"
    assert lines[1] == '  - "LLMs and generative AI: water management"'
    assert yaml.safe_load("\n".join(lines)) == {"cluster_queries": five_queries}


# ---------------------------------------------------------------------------
# v0.88.4 #1 — full retype flow exercises body cleanup
# ---------------------------------------------------------------------------


class _FakeZotero:
    def __init__(self, *, item_data: dict, target_template: dict):
        self._item_data = item_data
        self._target_template = target_template
        self.created: list[dict] = []
        self.trashed: list[str] = []

    def item(self, key: str) -> dict:
        return {"data": self._item_data, "key": key}

    def item_template(self, item_type: str) -> dict:
        return dict(self._target_template)

    def create_items(self, batch: list[dict]) -> dict:
        self.created.append(batch[0])
        return {"success": {"0": "NEWKEY01"}}

    def trash_item(self, item: dict) -> bool:
        self.trashed.append(item.get("key", ""))
        return True

    def delete_item(self, item: dict) -> bool:
        self.trashed.append(item.get("key", ""))
        return True


def _cfg(vault: Path) -> SimpleNamespace:
    return SimpleNamespace(
        root=vault,
        raw=vault / "raw",
        hub=vault / "hub",
        research_hub_dir=vault / ".research_hub",
        clusters_file=vault / ".research_hub" / "clusters.yaml",
    )


@pytest.fixture
def fake_zot(monkeypatch):
    def _set_fake(item_data: dict, target_template: dict):
        zot = _FakeZotero(item_data=item_data, target_template=target_template)
        monkeypatch.setattr(
            "research_hub.paper._get_zotero_web_client",
            lambda: zot,
        )
        monkeypatch.setattr(
            "research_hub.paper._trash_zotero_item",
            lambda z, key: (z.trashed.append(key) or True),
        )
        monkeypatch.setattr(
            "research_hub.paper._rebuild_dedup_index",
            lambda cfg: None,
        )
        return zot

    return _set_fake


def test_retype_apply_also_cleans_body_footer(
    tmp_path: Path, fake_zot
) -> None:
    """Full retype apply: body Zotero key footer must point at the NEW
    item, not the old one. Citation line is also rewritten — value may
    coincide with the source venue if Zotero hasn't been hand-fixed yet,
    but the rewrite itself is what we want to verify."""
    note = _seed_note_with_body(
        tmp_path, "p2024-a",
        zotero_key="OLDKEY01",
        citation_line="OLD JOURNAL XYZ",
        footer_key="OLDKEY01",
    )
    fake_zot(
        item_data={
            "itemType": "journalArticle",
            "title": "T",
            "publicationTitle": "OLD JOURNAL XYZ",
            "DOI": "10.1061/abc",
            "volume": "",
            "issue": "",
            "pages": "921-928",
            "tags": [],
            "creators": [],
            "collections": [],
        },
        # Target template has its OWN venue value (would only happen if the
        # user pre-populates the template; in practice it's blank, but this
        # lets us prove the rewrite path is wired up).
        target_template={
            "itemType": "conferencePaper",
            "title": "",
            "proceedingsTitle": "",
            "DOI": "",
            "pages": "",
        },
    )
    cfg = _cfg(tmp_path)
    report = retype_paper(cfg, "p2024-a", target_type="conferencePaper", dry_run=False)
    assert not report["errors"], report
    text = note.read_text(encoding="utf-8")
    # Footer key was updated by v0.88.4 body cleanup
    assert "`OLDKEY01`" not in text
    assert "`NEWKEY01`" in text
    # Citation line rewritten to match new venue field. Source publication
    # title "OLD JOURNAL XYZ" carries over via publicationTitle->proceedingsTitle.
    assert "**Citation:** OLD JOURNAL XYZ, 921-928" in text
