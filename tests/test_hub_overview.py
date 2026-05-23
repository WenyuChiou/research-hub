from __future__ import annotations

import json
from pathlib import Path

from research_hub.vault.hub_overview import populate_overview


def _write_cluster_query(root: Path, slug: str, query: str) -> None:
    cluster_dir = root / ".research_hub" / "clusters"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / f"{slug}.json").write_text(
        json.dumps({"cluster_queries": [query]}),
        encoding="utf-8",
    )


def _write_paper(root: Path, slug: str, stem: str, *, title: str, year: int, authors: str) -> None:
    raw_dir = root / "raw" / slug
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{stem}.md").write_text(
        f"""---
title: "{title}"
authors: "{authors}"
year: {year}
doi: "10.123/{stem}"
---

# {title}
""",
        encoding="utf-8",
    )


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.index(marker) + len(marker)
    next_heading = text.find("\n## ", start)
    end = next_heading if next_heading != -1 else len(text)
    return text[start:end].strip()


def test_populate_overview_fills_papers_section_from_raw_md(tmp_path):
    slug = "alpha"
    _write_cluster_query(tmp_path, slug, "LLM water systems")
    _write_paper(tmp_path, slug, "baker2024", title="Older Paper", year=2024, authors="Baker, B.")
    _write_paper(tmp_path, slug, "adams2026", title="Newer Paper", year=2026, authors="Adams, A.")

    path = populate_overview(cluster_slug=slug, vault_root=tmp_path)

    text = path.read_text(encoding="utf-8")
    papers = _section(text, "Papers in this cluster")
    assert "- [[adams2026]]: *Newer Paper*" in papers
    assert "- [[baker2024]]: *Older Paper*" in papers
    assert papers.index("[[adams2026]]") < papers.index("[[baker2024]]")


def test_populate_overview_is_idempotent(tmp_path):
    slug = "alpha"
    _write_cluster_query(tmp_path, slug, "LLM water systems")
    _write_paper(tmp_path, slug, "adams2026", title="Newer Paper", year=2026, authors="Adams, A.")

    path = populate_overview(cluster_slug=slug, vault_root=tmp_path)
    first = path.read_bytes()
    populate_overview(cluster_slug=slug, vault_root=tmp_path)

    assert path.read_bytes() == first


def test_populate_overview_preserves_user_edits_to_tldr(tmp_path):
    slug = "alpha"
    _write_cluster_query(tmp_path, slug, "Fallback query")
    _write_paper(tmp_path, slug, "adams2026", title="Newer Paper", year=2026, authors="Adams, A.")
    overview_dir = tmp_path / "hub" / slug
    overview_dir.mkdir(parents=True)
    (overview_dir / "00_overview.md").write_text(
        """---
type: topic-overview
cluster: alpha
---

# Alpha

## TL;DR

User-written synthesis stays here.
""",
        encoding="utf-8",
    )

    path = populate_overview(cluster_slug=slug, vault_root=tmp_path)

    assert "User-written synthesis stays here." in path.read_text(encoding="utf-8")
    assert "Fallback query" not in _section(path.read_text(encoding="utf-8"), "TL;DR")


def test_populate_overview_refreshes_fresh_chinese_scaffold(tmp_path):
    """Regression: the Chinese opening that topic.py writes for a brand-new
    cluster ("一到兩句話說清楚...") must be recognised as scaffold, not as
    user-curated content. Otherwise populate_overview leaves the TL;DR
    stuck at the empty placeholder forever (00_overview is "極大缺失")."""
    slug = "alpha"
    _write_cluster_query(tmp_path, slug, "Fallback query")
    _write_paper(tmp_path, slug, "adams2026", title="Newer Paper", year=2026, authors="Adams, A.")
    overview_dir = tmp_path / "hub" / slug
    overview_dir.mkdir(parents=True)
    (overview_dir / "00_overview.md").write_text(
        """---
type: topic-overview
cluster: alpha
---

# Alpha

## TL;DR

> [!abstract]
> 一到兩句話說清楚這個 cluster 在研究什麼、解決什麼問題。
^tldr
""",
        encoding="utf-8",
    )

    path = populate_overview(cluster_slug=slug, vault_root=tmp_path)
    written = path.read_text(encoding="utf-8")

    # Scaffold placeholder was replaced (the fallback query / paper-derived
    # summary now occupies the TL;DR).
    assert "一到兩句話" not in written, (
        "fresh Chinese scaffold must be replaced; if this fails, "
        "_SCAFFOLD_MARKERS in vault/hub_overview.py has drifted out of "
        "sync with topic.py's template"
    )


def test_populate_overview_handles_missing_brief_gracefully(tmp_path):
    slug = "alpha"
    _write_cluster_query(tmp_path, slug, "Fallback cluster query")
    _write_paper(tmp_path, slug, "adams2026", title="Newer Paper", year=2026, authors="Adams, A.")

    path = populate_overview(
        cluster_slug=slug,
        vault_root=tmp_path,
        brief_md_path=tmp_path / "hub" / slug / "missing.md",
    )

    text = path.read_text(encoding="utf-8")
    assert "Fallback cluster query" in text
    assert "## NotebookLM brief" not in text


def test_paper_bullet_sorts_by_year_desc_then_author_asc(tmp_path):
    slug = "alpha"
    _write_cluster_query(tmp_path, slug, "Fallback cluster query")
    _write_paper(tmp_path, slug, "baker2026", title="Baker Paper", year=2026, authors="Baker, B.")
    _write_paper(tmp_path, slug, "adams2026", title="Adams Paper", year=2026, authors="Adams, A.")
    _write_paper(tmp_path, slug, "clark2025", title="Clark Paper", year=2025, authors="Clark, C.")

    path = populate_overview(cluster_slug=slug, vault_root=tmp_path)

    # v0.88 #8: section now starts with a `> [!info] Auto-generated ...`
    # callout (visual fence to discourage edits). Drop it and the blank line
    # that follows so the bullet-list assertion still works.
    bullets = [
        line for line in _section(path.read_text(encoding="utf-8"), "Papers in this cluster").splitlines()
        if line and not line.startswith("> [!info]")
    ]
    assert bullets == [
        "- [[adams2026]]: *Adams Paper*",
        "- [[baker2026]]: *Baker Paper*",
        "- [[clark2025]]: *Clark Paper*",
    ]
