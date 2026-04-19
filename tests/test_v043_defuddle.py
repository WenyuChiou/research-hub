"""v0.43 - defuddle URL extraction tests."""
from __future__ import annotations

import subprocess
import sys
import types
from unittest.mock import MagicMock


def test_find_defuddle_binary_returns_none_when_missing(monkeypatch):
    from research_hub import defuddle_extract

    monkeypatch.setattr(defuddle_extract.shutil, "which", lambda name: None)
    assert defuddle_extract.find_defuddle_binary() is None


def test_find_defuddle_binary_returns_first_match(monkeypatch):
    from research_hub import defuddle_extract

    fake_paths = {"defuddle": "/usr/local/bin/defuddle", "defuddle-cli": None}
    monkeypatch.setattr(defuddle_extract.shutil, "which", lambda name: fake_paths.get(name))
    assert defuddle_extract.find_defuddle_binary() == "/usr/local/bin/defuddle"


def test_extract_url_via_defuddle_returns_none_when_binary_missing(monkeypatch):
    from research_hub import defuddle_extract

    monkeypatch.setattr(defuddle_extract, "find_defuddle_binary", lambda: None)
    assert defuddle_extract.extract_url_via_defuddle("https://example.com") is None


def test_extract_url_via_defuddle_success(monkeypatch):
    from research_hub import defuddle_extract

    monkeypatch.setattr(defuddle_extract, "find_defuddle_binary", lambda: "/bin/defuddle")
    fake = MagicMock(returncode=0, stdout="# Title\n\nClean markdown body.\n", stderr="")
    monkeypatch.setattr(defuddle_extract.subprocess, "run", lambda *a, **kw: fake)
    assert "Clean markdown body" in defuddle_extract.extract_url_via_defuddle("https://example.com")


def test_extract_url_via_defuddle_timeout_returns_none(monkeypatch):
    from research_hub import defuddle_extract

    monkeypatch.setattr(defuddle_extract, "find_defuddle_binary", lambda: "/bin/defuddle")

    def _boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="defuddle", timeout=30)

    monkeypatch.setattr(defuddle_extract.subprocess, "run", _boom)
    assert defuddle_extract.extract_url_via_defuddle("https://example.com") is None


def test_extract_url_via_defuddle_nonzero_exit_returns_none(monkeypatch):
    from research_hub import defuddle_extract

    monkeypatch.setattr(defuddle_extract, "find_defuddle_binary", lambda: "/bin/defuddle")
    fake = MagicMock(returncode=1, stdout="", stderr="error")
    monkeypatch.setattr(defuddle_extract.subprocess, "run", lambda *a, **kw: fake)
    assert defuddle_extract.extract_url_via_defuddle("https://example.com") is None


def test_importer_extract_url_uses_defuddle_first(tmp_path, monkeypatch):
    """When defuddle returns text, _extract_url uses it without readability fallback."""
    from research_hub import importer

    url_file = tmp_path / "src.url"
    url_file.write_text("https://example.com/article\n", encoding="utf-8")
    monkeypatch.setattr(
        "research_hub.defuddle_extract.extract_url_via_defuddle",
        lambda url, **kw: "# Article\n\nClean body via defuddle.",
    )

    def _should_not_be_called(*a, **kw):
        raise AssertionError("readability-lxml fallback should not run when defuddle succeeds")

    monkeypatch.setattr("requests.get", _should_not_be_called)

    out = importer._extract_url(url_file)
    assert "defuddle" in out


def test_importer_extract_url_falls_back_to_readability(tmp_path, monkeypatch):
    """When defuddle returns None, readability-lxml is invoked."""
    from research_hub import importer

    url_file = tmp_path / "src.url"
    url_file.write_text("https://example.com/article\n", encoding="utf-8")
    monkeypatch.setattr(
        "research_hub.defuddle_extract.extract_url_via_defuddle",
        lambda url, **kw: None,
    )
    fake_readability = types.SimpleNamespace(
        Document=lambda text: types.SimpleNamespace(summary=lambda: text)
    )
    monkeypatch.setitem(sys.modules, "readability", fake_readability)
    fake_response = MagicMock(text="<html><body><article><p>Fallback body</p></article></body></html>")
    fake_response.raise_for_status = lambda: None
    monkeypatch.setattr("requests.get", lambda url, **kw: fake_response)

    out = importer._extract_url(url_file)
    assert "Fallback body" in out
