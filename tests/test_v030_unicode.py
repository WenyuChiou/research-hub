from __future__ import annotations

import importlib.util

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.paper import _parse_frontmatter


HAS_SECURITY = importlib.util.find_spec("research_hub.security") is not None


def test_cjk_title_in_frontmatter():
    text = (
        "---\n"
        'title: "機器學習與知識圖譜"\n'
        'authors: ["王小明", "李小華"]\n'
        'year: "2024"\n'
        "---\n"
    )
    fm = _parse_frontmatter(text)
    assert fm["title"] == "機器學習與知識圖譜"
    assert fm["authors"] == ["王小明", "李小華"]


def test_rtl_arabic_title():
    text = (
        "---\n"
        'title: "نماذج اللغة في البحث العلمي"\n'
        'authors: ["Ahmad"]\n'
        "---\n"
    )
    fm = _parse_frontmatter(text)
    assert fm["title"] == "نماذج اللغة في البحث العلمي"


def test_emoji_in_cluster_name(tmp_path):
    reg = ClusterRegistry(tmp_path / "clusters.yaml")
    reg.create(query="ai agents", slug="ai-agents", name="🤖 AI Agents")
    cluster = reg.get("ai-agents")
    assert cluster is not None
    assert cluster.name == "🤖 AI Agents"


@pytest.mark.skipif(not HAS_SECURITY, reason="track A not yet shipped: research_hub.security.validate_slug missing")
def test_slug_with_unicode_rejected():
    from research_hub.security import ValidationError, validate_slug

    with pytest.raises(ValidationError):
        validate_slug("研究-代理")


@pytest.mark.skipif(not HAS_SECURITY, reason="track A not yet shipped: research_hub.security.validate_identifier missing")
def test_unicode_doi_normalized():
    from research_hub.security import ValidationError, validate_identifier

    with pytest.raises(ValidationError):
        validate_identifier("１０.１０００/abc")

