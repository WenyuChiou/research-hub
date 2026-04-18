"""v0.35 Connector Protocol and registry tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_protocol_satisfied_by_builtins():
    from research_hub.connectors import Connector
    from research_hub.connectors._notebooklm_adapter import NotebookLMConnector
    from research_hub.connectors.null import NullConnector

    assert isinstance(NullConnector(), Connector)
    assert isinstance(NotebookLMConnector(), Connector)


def test_register_connector_rejects_non_protocol_object():
    from research_hub.connectors import register_connector

    with pytest.raises(TypeError, match="does not satisfy"):
        register_connector(object())


def test_register_connector_rejects_empty_name():
    from research_hub.connectors import register_connector

    class BadConnector:
        name = ""

        def bundle(self, cluster, cfg):
            return None

        def upload(self, cluster, cfg):
            return None

        def generate(self, cluster, cfg, *, artifact_type="brief"):
            return None

        def download(self, cluster, cfg):
            return None

        def check_auth(self, cfg):
            return None

    with pytest.raises(ValueError, match="name must be non-empty"):
        register_connector(BadConnector())


def test_get_connector_unknown_name_raises():
    from research_hub.connectors import get_connector

    with pytest.raises(KeyError, match="not registered"):
        get_connector("nonexistent-connector-xyz")


def test_list_connectors_includes_builtins():
    from research_hub.connectors import list_connectors

    names = list_connectors()
    assert "notebooklm" in names
    assert "null" in names


def test_null_connector_returns_synthetic_reports():
    from research_hub.connectors.null import NullConnector

    connector = NullConnector()
    cluster = MagicMock(slug="test-cluster")

    bundle = connector.bundle(cluster, None)
    upload = connector.upload(cluster, None)
    generated = connector.generate(cluster, None, artifact_type="brief")
    download = connector.download(cluster, None)

    assert bundle.cluster_slug == "test-cluster"
    assert bundle.bundle_dir is None
    assert bundle.source_count == 0
    assert upload.notebook_id == "null-notebook-test-cluster"
    assert generated["ok"] is True
    assert download.preview.startswith("(null connector")


def test_null_connector_check_auth_always_true():
    from research_hub.connectors.null import NullConnector

    assert NullConnector().check_auth(None) is True


def test_notebooklm_adapter_bundle_delegates_to_module(tmp_path):
    from research_hub.connectors._notebooklm_adapter import NotebookLMConnector

    fake_report = MagicMock(bundle_dir=tmp_path / "bundle", pdf_count=2, url_count=3)
    cluster = MagicMock(slug="x-cluster")

    with patch("research_hub.notebooklm.bundle.bundle_cluster", return_value=fake_report) as mock_bundle:
        result = NotebookLMConnector().bundle(cluster, None)

    mock_bundle.assert_called_once_with(cluster, None)
    assert result.cluster_slug == "x-cluster"
    assert result.pdf_count == 2
    assert result.url_count == 3
    assert result.source_count == 5
