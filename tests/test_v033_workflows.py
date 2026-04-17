"""v0.33 Track A: task-level workflow wrapper tests.

All underlying functions are mocked. These tests verify the WRAPPER dispatch
logic, not the underlying implementations (which have their own tests).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_cached_modules(monkeypatch):
    """Force re-import of research_hub.{crystal,topic,fit_check,doctor,operations,importer}
    before each test so other tests' mocks don't leak.

    v0.33 workflows do late imports — some earlier test (e.g. discover / pipeline)
    may have monkey-patched attrs at module level and not cleaned up.
    """
    import sys
    for name in (
        "research_hub.workflows",
        "research_hub.crystal",
        "research_hub.topic",
        "research_hub.fit_check",
        "research_hub.doctor",
        "research_hub.operations",
        "research_hub.importer",
        "research_hub.notebooklm.upload",
        "research_hub.notebooklm.bundle",
        "research_hub.clusters",
    ):
        sys.modules.pop(name, None)


def _make_cfg(tmp_path):
    """Minimal HubConfig pointing at tmp vault."""
    os.environ["RESEARCH_HUB_ROOT"] = str(tmp_path)
    os.environ["RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"] = "1"
    import research_hub.config as cfg_mod
    cfg_mod._config = None
    cfg_mod._config_path = None
    return cfg_mod.HubConfig()


def _fake_crystal(slug, question, tldr="T", gist="G", full="F", confidence="medium"):
    c = MagicMock()
    c.question_slug = slug
    c.question = question
    c.tldr = tldr
    c.gist = gist
    c.full = full
    c.confidence = confidence
    c.based_on_papers = []
    return c


# ---------------------------------------------------------------------------
# ask_cluster
# ---------------------------------------------------------------------------


def test_ask_cluster_hits_crystal_when_question_matches(tmp_path):
    from research_hub.workflows import ask_cluster
    cfg = _make_cfg(tmp_path)

    crystal = _fake_crystal(
        "sota-and-open-problems",
        "What is the current state of the art and what remains unsolved?",
        gist="SOTA moved from 1% to 33% on SWE-bench.",
    )

    with patch("research_hub.crystal.list_crystals", return_value=[crystal]), \
         patch("research_hub.crystal.check_staleness", return_value={}):
        result = ask_cluster(
            cfg, "test-cluster",
            question="what's the state of the art", detail="gist",
        )

    assert result["ok"] is True
    assert result["source"] == "crystal"
    assert result["crystal_slug"] == "sota-and-open-problems"
    assert "SOTA" in result["answer"]


def test_ask_cluster_falls_back_to_digest_when_no_crystal_match(tmp_path):
    from research_hub.workflows import ask_cluster
    cfg = _make_cfg(tmp_path)

    fake_digest = MagicMock()
    fake_digest.paper_count = 20
    fake_digest.papers = []

    with patch("research_hub.crystal.list_crystals", return_value=[]), \
         patch("research_hub.topic.get_topic_digest", return_value=fake_digest), \
         patch("research_hub.topic.read_overview", return_value="overview text"):
        result = ask_cluster(cfg, "empty-cluster", question="something")

    assert result["ok"] is True
    assert result["source"] == "digest"
    assert result["suggest_regenerate"] is True  # no crystals
    assert "research-hub crystal emit" in result["hint"]


def test_ask_cluster_rejects_invalid_detail(tmp_path):
    from research_hub.workflows import ask_cluster
    cfg = _make_cfg(tmp_path)
    result = ask_cluster(cfg, "test-cluster", detail="huge")
    assert result["ok"] is False
    assert "detail" in result["error"].lower()


def test_ask_cluster_validates_slug(tmp_path):
    from research_hub.workflows import ask_cluster
    cfg = _make_cfg(tmp_path)
    result = ask_cluster(cfg, "../../etc", question="x")
    assert result["ok"] is False
    assert "cluster_slug" in result["error"]


# ---------------------------------------------------------------------------
# brief_cluster
# ---------------------------------------------------------------------------


def test_brief_cluster_chains_bundle_upload_generate_download(tmp_path):
    from research_hub.workflows import brief_cluster
    cfg = _make_cfg(tmp_path)

    fake_cluster = MagicMock()
    fake_cluster.notebooklm_notebook_id = None  # force upload + generate

    fake_bundle = MagicMock()
    fake_bundle.bundle_dir = tmp_path / "bundle"
    fake_bundle.source_count = 5

    fake_download = MagicMock()
    fake_download.artifact_path = tmp_path / "brief.txt"

    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_cluster

    with patch("research_hub.clusters.ClusterRegistry", return_value=fake_registry), \
         patch("research_hub.notebooklm.bundle.bundle_cluster", return_value=fake_bundle), \
         patch("research_hub.notebooklm.upload.upload_cluster") as mock_upload, \
         patch("research_hub.notebooklm.upload.generate_artifact") as mock_generate, \
         patch("research_hub.notebooklm.upload.download_briefing_for_cluster", return_value=fake_download):
        result = brief_cluster(cfg, "some-cluster", force_regenerate=True)

    assert result["ok"] is True
    assert "bundle" in result["steps_completed"]
    assert "upload" in result["steps_completed"]
    assert "generate" in result["steps_completed"]
    mock_upload.assert_called_once()
    mock_generate.assert_called_once()


def test_brief_cluster_handles_missing_cluster(tmp_path):
    from research_hub.workflows import brief_cluster
    cfg = _make_cfg(tmp_path)

    fake_registry = MagicMock()
    fake_registry.get.return_value = None

    with patch("research_hub.clusters.ClusterRegistry", return_value=fake_registry):
        result = brief_cluster(cfg, "nonexistent")

    assert result["ok"] is False
    assert "cluster not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# sync_cluster
# ---------------------------------------------------------------------------


def test_sync_cluster_aggregates_staleness_and_recommendations(tmp_path):
    from research_hub.workflows import sync_cluster
    cfg = _make_cfg(tmp_path)

    c1 = _fake_crystal("what-is-this-field", "Q1")
    c2 = _fake_crystal("sota", "Q2")

    stale_entry1 = MagicMock()
    stale_entry1.stale = False
    stale_entry2 = MagicMock()
    stale_entry2.stale = True

    with patch("research_hub.crystal.list_crystals", return_value=[c1, c2]), \
         patch("research_hub.crystal.check_staleness",
               return_value={"what-is-this-field": stale_entry1, "sota": stale_entry2}), \
         patch("research_hub.fit_check.drift_check", return_value={"score": 1}), \
         patch("research_hub.doctor.run_doctor", return_value=[]):
        result = sync_cluster(cfg, "test-cluster")

    assert result["ok"] is True
    assert "sota" in result["stale_crystals"]
    assert any("crystal emit" in r for r in result["recommendations"])
    assert result["drift_score"] == 1


def test_sync_cluster_flags_empty_crystals(tmp_path):
    from research_hub.workflows import sync_cluster
    cfg = _make_cfg(tmp_path)

    with patch("research_hub.crystal.list_crystals", return_value=[]), \
         patch("research_hub.fit_check.drift_check", return_value={"score": 0}), \
         patch("research_hub.doctor.run_doctor", return_value=[]):
        result = sync_cluster(cfg, "fresh-cluster")

    assert result["ok"] is True
    assert result["crystal_count"] == 0
    assert any("no crystals yet" in r for r in result["recommendations"])


# ---------------------------------------------------------------------------
# compose_brief
# ---------------------------------------------------------------------------


def test_compose_brief_default_outline_uses_overview_plus_tldrs(tmp_path):
    """When outline is None, default is built from overview + crystal TLDRs."""
    from research_hub import workflows
    cfg = _make_cfg(tmp_path)

    crystal = _fake_crystal("what-is-this-field", "What is this?", tldr="Field overview text.")

    captured = {}
    def fake_compose(cfg_, **kwargs):
        captured["outline"] = kwargs.get("outline", "")
        return {"draft_path": str(tmp_path / "draft.md")}

    with patch("research_hub.topic.read_overview", return_value="Some cluster overview."), \
         patch("research_hub.crystal.list_crystals", return_value=[crystal]), \
         patch.object(workflows, "_err", side_effect=workflows._err) as _:
        import sys
        fake_mod = MagicMock()
        fake_mod.compose_draft = fake_compose
        with patch.dict(sys.modules, {"research_hub.operations": fake_mod}):
            result = workflows.compose_brief(cfg, "test-cluster")

    assert result["ok"] is True
    assert "Background" in result["outline_used"]
    assert "Key questions" in result["outline_used"]
    assert "Field overview text" in result["outline_used"]


# ---------------------------------------------------------------------------
# collect_to_cluster
# ---------------------------------------------------------------------------


def test_collect_to_cluster_routes_doi_to_add_paper(tmp_path):
    from research_hub import workflows
    cfg = _make_cfg(tmp_path)

    fake_add = MagicMock(return_value=0)
    import sys
    fake_ops = MagicMock()
    fake_ops.add_paper = fake_add

    with patch.dict(sys.modules, {"research_hub.operations": fake_ops}):
        result = workflows.collect_to_cluster(
            cfg, "10.48550/arxiv.2310.06770", cluster_slug="test-cluster",
        )

    assert result["ok"] is True
    assert result["source_kind"] == "paper"
    fake_add.assert_called_once()


def test_collect_to_cluster_routes_folder_to_import_folder(tmp_path):
    from research_hub import workflows
    cfg = _make_cfg(tmp_path)

    test_folder = tmp_path / "src"
    test_folder.mkdir()

    fake_report = MagicMock()
    fake_report.imported_count = 2
    fake_report.skipped_count = 0
    fake_report.failed_count = 0
    fake_report.entries = []

    import sys
    fake_importer = MagicMock()
    fake_importer.import_folder = MagicMock(return_value=fake_report)

    with patch.dict(sys.modules, {"research_hub.importer": fake_importer}):
        result = workflows.collect_to_cluster(
            cfg, str(test_folder), cluster_slug="test-cluster",
        )

    assert result["ok"] is True
    assert result["source_kind"] == "folder"
    assert result["imported"] == 2


def test_collect_to_cluster_rejects_unknown_source(tmp_path):
    from research_hub.workflows import collect_to_cluster
    cfg = _make_cfg(tmp_path)
    result = collect_to_cluster(cfg, "not-a-doi-or-url", cluster_slug="test")
    assert result["ok"] is False
    assert "source kind" in result["error"].lower()
