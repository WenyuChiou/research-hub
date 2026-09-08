from importlib import metadata

from research_hub import __version__
from research_hub.doctor import check_config_secrets, check_installation_version


def test_secret_diagnostic_preserves_input_and_never_exposes_key():
    config = {"zotero": {"api_key": "private-value"}}
    result = check_config_secrets(config)
    assert result.status == "WARN"
    assert config["zotero"]["api_key"] == "private-value"
    assert "private-value" not in str(result)
    assert "config encrypt-secrets" in result.remedy


def test_installation_metadata_drift_is_not_pass(monkeypatch):
    monkeypatch.setattr(metadata, "version", lambda name: "0.0.0")
    result = check_installation_version()
    assert result.status == "WARN"
    assert __version__ in result.message and "0.0.0" in result.message


def test_matching_distribution_version(monkeypatch):
    monkeypatch.setattr(metadata, "version", lambda name: __version__)
    assert check_installation_version().status == "OK"


def test_source_checkout_is_not_installation_proof(monkeypatch):
    def missing(name):
        raise metadata.PackageNotFoundError(name)
    monkeypatch.setattr(metadata, "version", missing)
    assert check_installation_version().status == "WARN"
