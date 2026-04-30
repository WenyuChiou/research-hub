from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from research_hub.auto import auto_pipeline


@pytest.fixture
def mock_deps():
    """Central fixture for mocking all external dependencies of auto_pipeline."""
    with patch("research_hub.auto.get_config") as mock_get_config, \
         patch("research_hub.auto.ClusterRegistry") as mock_cluster_registry, \
         patch("research_hub.auto.run_pipeline") as mock_run_pipeline, \
         patch("research_hub.auto.bundle_cluster") as mock_bundle_cluster, \
         patch("research_hub.auto.upload_cluster") as mock_upload_cluster, \
         patch("research_hub.auto.generate_artifact") as mock_generate_artifact, \
         patch("research_hub.auto.download_briefing_for_cluster") as mock_download, \
         patch("research_hub.auto._run_search") as mock_run_search:

        mock_cfg = MagicMock()
        mock_cfg.root = MagicMock()
        (mock_cfg.root / "papers_input.json").write_text = MagicMock()
        mock_get_config.return_value = mock_cfg

        mock_registry_instance = MagicMock()
        mock_cluster_registry.return_value = mock_registry_instance

        mock_run_pipeline.return_value = 0
        mock_run_search.return_value = [{"title": "Mock Paper 1"}]

        yield {
            "get_config": mock_get_config,
            "ClusterRegistry": mock_cluster_registry,
            "registry_instance": mock_registry_instance,
            "run_pipeline": mock_run_pipeline,
            "bundle_cluster": mock_bundle_cluster,
            "upload_cluster": mock_upload_cluster,
            "generate_artifact": mock_generate_artifact,
            "download_briefing": mock_download,
            "run_search": mock_run_search,
            "cfg": mock_cfg,
        }


def test_auto_pipeline_dry_run_new_cluster(mock_deps):
    mock_deps["registry_instance"].get.return_value = None  # Cluster does not exist

    report = auto_pipeline(
        topic="test topic",
        dry_run=True,
        print_progress=False,
    )

    assert report.ok
    assert report.cluster_slug == "test-topic"
    assert not report.cluster_created
    assert len(report.steps) == 1
    assert report.steps[0].name == "cluster"
    assert report.steps[0].detail.startswith("would create")

    mock_deps["registry_instance"].create.assert_not_called()
    mock_deps["run_search"].assert_not_called()


def test_auto_pipeline_dry_run_existing_cluster(mock_deps):
    mock_cluster = MagicMock()
    mock_deps["registry_instance"].get.return_value = mock_cluster

    report = auto_pipeline(
        topic="test topic",
        cluster_slug="existing-slug",
        dry_run=True,
        print_progress=False,
    )

    assert report.ok
    assert report.cluster_slug == "existing-slug"
    assert not report.cluster_created
    assert report.steps[0].name == "cluster"
    assert "existing" in report.steps[0].detail
    mock_deps["registry_instance"].create.assert_not_called()


def test_auto_pipeline_full_run_new_cluster(mock_deps):
    mock_deps["registry_instance"].get.return_value = None
    mock_created_cluster = MagicMock(slug="new-topic")
    mock_deps["registry_instance"].create.return_value = mock_created_cluster
    mock_deps["registry_instance"].get.side_effect = [None, mock_created_cluster] # first get fails, second (after create) succeeds

    report = auto_pipeline(
        topic="New Topic",
        max_papers=5,
        do_nlm=True,
        print_progress=False,
    )

    assert report.ok
    assert report.cluster_slug == "new-topic"
    assert report.cluster_created
    mock_deps["registry_instance"].create.assert_called_with(
        query="New Topic", slug="new-topic", name="New Topic"
    )
    mock_deps["run_search"].assert_called_with("New Topic", max_papers=5, cluster_slug="new-topic")
    # v0.73.0: zotero_batch_size=50 added to run_pipeline signature.
    mock_deps["run_pipeline"].assert_called_with(
        dry_run=False, cluster_slug="new-topic", query="New Topic", verify=False,
        zotero_batch_size=50,
    )
    mock_deps["bundle_cluster"].assert_called()
    mock_deps["upload_cluster"].assert_called()
    mock_deps["generate_artifact"].assert_called()
    mock_deps["download_briefing"].assert_called()


def test_auto_pipeline_no_nlm(mock_deps):
    mock_deps["registry_instance"].get.return_value = MagicMock()
    
    report = auto_pipeline(
        topic="No NLM Topic",
        do_nlm=False,
        print_progress=False,
    )

    assert report.ok
    assert report.cluster_slug == "no-nlm-topic"
    mock_deps["run_pipeline"].assert_called()
    mock_deps["bundle_cluster"].assert_not_called()
    mock_deps["upload_cluster"].assert_not_called()


def test_auto_pipeline_search_fails(mock_deps):
    mock_deps["registry_instance"].get.return_value = MagicMock()
    mock_deps["run_search"].side_effect = ValueError("API limit reached")

    report = auto_pipeline(topic="Search Fail Topic", print_progress=False)

    assert not report.ok
    assert report.error == "search failed: API limit reached"
    assert report.steps[-1].name == "search"
    assert not report.steps[-1].ok
    mock_deps["run_pipeline"].assert_not_called()


def test_auto_pipeline_ingest_fails(mock_deps):
    mock_deps["registry_instance"].get.return_value = MagicMock()
    mock_deps["run_pipeline"].return_value = 1  # Non-zero exit code

    report = auto_pipeline(topic="Ingest Fail Topic", print_progress=False)

    assert not report.ok
    assert "ingest failed" in report.error
    assert report.steps[-1].name == "ingest"
    assert not report.steps[-1].ok
    mock_deps["bundle_cluster"].assert_not_called()


def test_auto_pipeline_nlm_step_fails(mock_deps):
    mock_deps["registry_instance"].get.return_value = MagicMock()
    mock_deps["upload_cluster"].side_effect = RuntimeError("Invalid credentials")

    report = auto_pipeline(topic="NLM Fail Topic", do_nlm=True, print_progress=False)

    assert report.ok
    assert report.nlm_deferred is True
    assert "nlm.upload: Invalid credentials" == report.nlm_error
    assert report.steps[-1].name == "nlm.upload"
    assert not report.steps[-1].ok
    mock_deps["bundle_cluster"].assert_called() # bundle runs before upload
    mock_deps["generate_artifact"].assert_not_called() # generate is after upload


def test_auto_nlm_failure_does_not_abort_pipeline(mock_deps, capsys):
    mock_deps["registry_instance"].get.return_value = MagicMock()
    mock_deps["upload_cluster"].side_effect = RuntimeError("login expired")

    with patch("research_hub.auto._run_crystal_step") as mock_crystals:
        report = auto_pipeline(
            topic="NLM Deferred Topic",
            do_nlm=True,
            do_crystals=True,
            print_progress=True,
        )

    out = capsys.readouterr().out
    assert report.ok is True
    assert report.nlm_deferred is True
    assert report.nlm_error == "nlm.upload: login expired"
    mock_crystals.assert_called_once()
    assert "[NLM] skipped (check: research-hub notebooklm login). Resume with:" in out
    assert "research-hub notebooklm bundle   --cluster nlm-deferred-topic" in out
    assert "research-hub notebooklm upload   --cluster nlm-deferred-topic" in out
    assert "research-hub notebooklm generate --cluster nlm-deferred-topic --type brief" in out
    assert "research-hub notebooklm download --cluster nlm-deferred-topic --type brief" in out


def test_auto_pipeline_search_returns_no_papers(mock_deps):
    mock_deps["registry_instance"].get.return_value = MagicMock()
    mock_deps["run_search"].return_value = []

    report = auto_pipeline(topic="No Results Topic", print_progress=False)

    assert not report.ok
    assert report.error == "Search returned 0 papers ??try a different topic or backend"
    mock_deps["run_pipeline"].assert_not_called()
