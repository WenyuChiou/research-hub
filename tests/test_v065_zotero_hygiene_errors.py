"""v0.65 Track D1: zotero_hygiene now logs file/parse failures instead of silently swallowing."""

from __future__ import annotations

import logging

import pytest

from research_hub.zotero_hygiene import _frontmatter_payload


def test_unreadable_file_logs_warning(tmp_path, caplog):
    """OSError on file read used to silently return {}; v0.65 logs WARN."""
    nonexistent = tmp_path / "missing.md"
    with caplog.at_level(logging.WARNING, logger="research_hub.zotero_hygiene"):
        result = _frontmatter_payload(nonexistent)
    assert result == {}
    assert any("could not read" in rec.message for rec in caplog.records), (
        f"Expected file-read WARN, got: {[r.message for r in caplog.records]}"
    )


def test_yaml_parse_failure_logs_warning(tmp_path, caplog, monkeypatch):
    """YAML parse failure used to silently fall back; v0.65 logs WARN
    and still falls back so a single bad note doesn't break the scan."""
    bad = tmp_path / "bad.md"
    bad.write_text("---\ntitle: \"unbalanced\nstatus: ok\n---\nbody\n", encoding="utf-8")

    # Force yaml import to raise so the except branch fires deterministically
    import research_hub.zotero_hygiene as zh

    real_get_text = bad.read_text
    # Monkeypatch yaml.safe_load to always raise so we don't depend on
    # a specific malformed input being unparsable across yaml versions.
    import yaml

    def _raise(*_args, **_kwargs):
        raise yaml.YAMLError("synthetic parse error")

    monkeypatch.setattr(yaml, "safe_load", _raise)

    with caplog.at_level(logging.WARNING, logger="research_hub.zotero_hygiene"):
        result = _frontmatter_payload(bad)
    assert isinstance(result, dict)  # fallback parser returned something
    assert any("YAML parse failed" in rec.message for rec in caplog.records), (
        f"Expected YAML-parse WARN, got: {[r.message for r in caplog.records]}"
    )
