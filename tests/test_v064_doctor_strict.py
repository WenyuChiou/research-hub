"""v0.64.2: doctor's frontmatter_completeness check downgrades known legacy
gaps to a single INFO line by default; --strict still surfaces every WARN."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from research_hub.doctor import check_frontmatter_completeness


def _write_legacy_note(path: Path, *, missing_doi: bool = True, empty_section: bool = True) -> None:
    fm = "---\n"
    fm += 'title: "Legacy Paper"\n'
    if not missing_doi:
        fm += 'doi: "10.1/x"\n'
    else:
        fm += 'doi: ""\n'
    fm += 'authors: "Smith, J"\nyear: 2020\ntopic_cluster: "legacy-cluster"\n'
    fm += 'status: unread\ningested_at: "2024-01-01T00:00:00Z"\n'
    fm += 'ingestion_source: "pre-v0.3.0-migration"\n'
    fm += "---\n\n"
    body = "# Legacy Paper\n\n"
    if not empty_section:
        body += "## Summary\n\nNon-empty.\n\n## Key Findings\n\nA.\n\n## Methodology\n\nB.\n\n## Relevance\n\nC.\n"
    path.write_text(fm + body, encoding="utf-8")


def test_doctor_default_downgrades_legacy_gaps_to_info(tmp_path):
    raw = tmp_path / "raw" / "legacy-cluster"
    raw.mkdir(parents=True)
    _write_legacy_note(raw / "p1.md", missing_doi=True, empty_section=True)
    _write_legacy_note(raw / "p2.md", missing_doi=False, empty_section=True)
    cfg = SimpleNamespace(raw=tmp_path / "raw")

    result = check_frontmatter_completeness(cfg, strict=False)

    assert result.status == "INFO"
    assert "legacy notes have known gaps" in result.message
    assert "--strict" in result.message


def test_doctor_strict_surfaces_individual_warns(tmp_path):
    raw = tmp_path / "raw" / "legacy-cluster"
    raw.mkdir(parents=True)
    _write_legacy_note(raw / "p1.md", missing_doi=True, empty_section=True)
    cfg = SimpleNamespace(raw=tmp_path / "raw")

    result = check_frontmatter_completeness(cfg, strict=True)

    assert result.status == "WARN"
    assert ("WARN" in result.message) or ("missing" in result.message.lower())


def test_doctor_no_legacy_returns_ok(tmp_path):
    raw = tmp_path / "raw" / "clean-cluster"
    raw.mkdir(parents=True)
    _write_legacy_note(raw / "p.md", missing_doi=False, empty_section=False)
    cfg = SimpleNamespace(raw=tmp_path / "raw")

    result = check_frontmatter_completeness(cfg, strict=False)

    assert result.status == "OK"
