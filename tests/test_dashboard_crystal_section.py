from __future__ import annotations

from dataclasses import dataclass

from research_hub.dashboard.sections import CrystalSection
from research_hub.dashboard.types import CrystalSummary


@dataclass
class _FakeCluster:
    slug: str = ""
    name: str = ""
    last_activity: str = ""


@dataclass
class _FakeData:
    clusters: list
    crystal_summary_by_cluster: dict
    vault_root: str = ""


def test_crystal_section_empty_state_when_no_clusters():
    section = CrystalSection()
    data = _FakeData(clusters=[], crystal_summary_by_cluster={})
    html = section.render(data)
    assert html == ""


def test_crystal_section_empty_state_when_no_crystals():
    section = CrystalSection()
    cluster = _FakeCluster(slug="test", name="Test")
    summary = CrystalSummary(
        cluster_slug="test",
        total_canonical=10,
        generated_count=0,
        stale_count=0,
        last_generated="",
        crystals=[],
    )
    data = _FakeData(clusters=[cluster], crystal_summary_by_cluster={"test": summary})
    html = section.render(data)
    assert "No crystals generated yet" in html
    assert "research-hub crystal emit" in html


def test_crystal_section_renders_completion_ratio():
    section = CrystalSection()
    cluster = _FakeCluster(slug="test", name="Test")
    summary = CrystalSummary(
        cluster_slug="test",
        total_canonical=10,
        generated_count=7,
        stale_count=0,
        last_generated="2026-04-15T12:00:00Z",
        crystals=[
            {"slug": "what-is-this-field", "question": "?", "tldr": "ok", "confidence": "high", "stale": False},
        ],
    )
    data = _FakeData(clusters=[cluster], crystal_summary_by_cluster={"test": summary})
    html = section.render(data)
    assert "7/10" in html
    assert "what-is-this-field" in html


def test_crystal_section_renders_stale_badge():
    section = CrystalSection()
    cluster = _FakeCluster(slug="test", name="Test")
    summary = CrystalSummary(
        cluster_slug="test",
        total_canonical=10,
        generated_count=10,
        stale_count=3,
        last_generated="2026-04-10T12:00:00Z",
        crystals=[
            {"slug": "what-is-this-field", "question": "?", "tldr": "ok", "confidence": "medium", "stale": True},
        ],
    )
    data = _FakeData(clusters=[cluster], crystal_summary_by_cluster={"test": summary})
    html = section.render(data)
    assert "3 stale" in html
    assert "STALE" in html


def test_crystal_section_uses_absolute_obsidian_path():
    section = CrystalSection()
    cluster = _FakeCluster(slug="test", name="Test")
    summary = CrystalSummary(
        cluster_slug="test",
        total_canonical=10,
        generated_count=1,
        stale_count=0,
        last_generated="2026-04-15T12:00:00Z",
        crystals=[
            {"slug": "what-is-this-field", "question": "?", "tldr": "ok", "confidence": "high", "stale": False},
        ],
    )
    data = _FakeData(
        clusters=[cluster],
        crystal_summary_by_cluster={"test": summary},
        vault_root="C:/Users/wenyu/knowledge-base",
    )
    html = section.render(data)
    assert "C:/Users/wenyu/knowledge-base" in html or "obsidian://open?path=C" in html


def test_crystal_section_regenerate_command_available():
    section = CrystalSection()
    cluster = _FakeCluster(slug="my-cluster", name="My")
    summary = CrystalSummary(
        cluster_slug="my-cluster",
        total_canonical=10,
        generated_count=5,
        stale_count=1,
        last_generated="2026-04-15T12:00:00Z",
        crystals=[
            {"slug": "what-is-this-field", "question": "?", "tldr": "ok", "confidence": "high", "stale": False},
        ],
    )
    data = _FakeData(clusters=[cluster], crystal_summary_by_cluster={"my-cluster": summary})
    html = section.render(data)
    assert "research-hub crystal emit --cluster my-cluster" in html
    assert "copy-cmd-btn" in html
