"""Tests for NotebookLM client and upload flows without a real browser."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from research_hub.clusters import Cluster, ClusterRegistry
from research_hub.notebooklm.client import (
    NotebookLMClient,
    NotebookLMError,
    _parse_notebook_id,
)
from research_hub.notebooklm.upload import upload_cluster


import re


def _matches(pattern, sample: str) -> bool:
    if pattern is None:
        return True
    if hasattr(pattern, "search"):
        return bool(pattern.search(sample))
    return pattern == sample


class StubLocator:
    def __init__(
        self,
        *,
        count: int = 1,
        click_raises: Exception | None = None,
        text: str = "",
        attr: str = "https://notebooklm.google.com/notebook/xyz",
        on_click=None,
        ancestor: "StubLocator | None" = None,
    ) -> None:
        self._count = count
        self._click_raises = click_raises
        self._text = text
        self._attr = attr
        self._on_click = on_click
        self._ancestor = ancestor
        self.clicked = False
        self.filled_with = None
        self.set_files = None
        self.pressed = None

    def count(self):
        return self._count

    def click(self):
        self.clicked = True
        if self._click_raises:
            raise self._click_raises
        if self._on_click:
            self._on_click()

    def fill(self, text):
        self.filled_with = text

    def press(self, key):
        self.pressed = key

    def set_input_files(self, path):
        self.set_files = path

    @property
    def first(self):
        return self

    def all(self):
        return [self]

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attr

    def locator(self, selector):
        if self._ancestor is not None:
            return self._ancestor
        return StubLocator(count=1)


class StubPage:
    def __init__(self):
        self.url = "https://notebooklm.google.com/"
        self.goto_calls = []
        self.locators = {}
        # role_locators: list of (role, name_pattern_or_str, locator)
        self.role_rules: list = []
        self.placeholder_rules: list = []
        self.wait_for_function_calls = []

    def goto(self, url):
        self.goto_calls.append(url)
        self.url = url

    def wait_for_load_state(self, state):
        return None

    def wait_for_timeout(self, ms):
        return None

    def wait_for_function(self, fn, timeout=None):
        self.wait_for_function_calls.append((fn, timeout))
        return None

    def locator(self, sel):
        return self.locators.get(sel, StubLocator(count=0))

    def set_role(self, role: str, text: str, locator: StubLocator) -> None:
        self.role_rules.append((role, text, locator))

    def set_placeholder(self, text: str, locator: StubLocator) -> None:
        self.placeholder_rules.append((text, locator))

    def get_by_role(self, role, name=None):
        for r, text, loc in self.role_rules:
            if r == role and _matches(name, text):
                return loc
        return StubLocator(count=0)

    def get_by_placeholder(self, text):
        for sample, loc in self.placeholder_rules:
            if _matches(text, sample):
                return loc
        return StubLocator(count=0)


class StubCfg:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.logs = root / "logs"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"


def _write_cluster(cfg: StubCfg, cluster: Cluster) -> None:
    registry = ClusterRegistry(cfg.clusters_file)
    registry.clusters[cluster.slug] = cluster
    registry.save()


def test_upload_cluster_fail_fast_on_expired_session(tmp_path, monkeypatch):
    """Test that upload_cluster fails fast if the Google session is expired."""
    cfg = StubCfg(tmp_path)
    cfg.research_hub_dir.mkdir(parents=True)
    bundle_dir = cfg.research_hub_dir / "bundles" / "alpha-20260411T000000Z"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps(
            {
                "entries": [
                    {"action": "url", "url": "https://example.com"},
                ]
            }
        ),
        encoding="utf-8",
    )
    cluster = Cluster(slug="alpha", name="Alpha", notebooklm_notebook="Alpha Notebook")
    _write_cluster(cfg, cluster)

    # Mock open_cdp_session to return a page that simulates an expired session after goto
    @contextmanager
    def fake_open_cdp_session(session_dir, headless):
        page = StubPage()
        # Ensure headless is passed correctly
        assert headless is True

        # Store original goto to call it
        original_goto = page.goto

        def mock_goto(url):
            original_goto(url) # Simulate navigation to the target URL
            # Simulate redirection to Google sign-in page
            page.url = "https://accounts.google.com/signin/expired"
            page.wait_for_load_state("networkidle")

        page.goto = mock_goto
        yield None, page # Yield a dummy session and the mock page

    monkeypatch.setattr("research_hub.notebooklm.upload.open_cdp_session", fake_open_cdp_session)
    monkeypatch.setattr("research_hub.notebooklm.upload.time.sleep", lambda _: None) # Prevent unnecessary sleeps

    # Assert that NotebookLMError is raised and contains "expired" in the message
    with pytest.raises(NotebookLMError) as excinfo:
        upload_cluster(cluster, cfg, dry_run=False, headless=True)

    assert "expired" in str(excinfo.value)
    assert "https://accounts.google.com/signin/expired" in str(excinfo.value)
    assert excinfo.value.selector == "session-health"


# Existing tests follow...
def test_parse_notebook_id_extracts_uuid():
    assert _parse_notebook_id("https://notebooklm.google.com/notebook/abc-123?x=1") == "abc-123"


def test_create_notebook_happy_path():
    page = StubPage()
    create_button = StubLocator(
        on_click=lambda: setattr(page, "url", "https://notebooklm.google.com/notebook/new-id")
    )
    title_box = StubLocator()
    page.locators["mat-card.create-new-action-button"] = create_button
    page.locators["[contenteditable='true']"] = title_box

    client = NotebookLMClient(page)
    handle = client.create_notebook("Alpha")

    assert create_button.clicked is True
    assert title_box.filled_with == "Alpha"
    assert handle.notebook_id == "new-id"



def test_open_notebook_by_name_raises_on_missing():
    page = StubPage()
    # Any xpath lookup returns an empty locator by default.
    client = NotebookLMClient(page)
    with pytest.raises(NotebookLMError):
        client.open_notebook_by_name("Missing")


def test_upload_pdf_success_records_result(tmp_path):
    page = StubPage()
    add_source = StubLocator()
    file_input = StubLocator()
    page.locators["button.source-stretched-button"] = add_source
    page.locators["input[type='file']"] = file_input

    result = NotebookLMClient(page).upload_pdf(tmp_path / "paper.pdf")

    assert result.success is True
    assert add_source.clicked is True
    assert str(tmp_path / "paper.pdf") == file_input.set_files


def test_upload_pdf_failure_wraps_exception_in_result(tmp_path):
    page = StubPage()
    page.locators["button.source-stretched-button"] = StubLocator(click_raises=RuntimeError("boom"))

    result = NotebookLMClient(page).upload_pdf(tmp_path / "paper.pdf")

    assert result.success is False
    assert "boom" in result.error


def test_upload_url_clicks_website_tab_then_insert():
    page = StubPage()
    add_source = StubLocator()
    website_tab = StubLocator()
    insert_button = StubLocator()
    url_input = StubLocator()
    page.locators["button.source-stretched-button"] = add_source
    page.set_role("tab", "Website", website_tab)
    page.set_role("button", "Insert", insert_button)
    page.set_placeholder("Paste URL", url_input)

    result = NotebookLMClient(page).upload_url("https://example.com")

    assert result.success is True
    assert add_source.clicked is True
    assert website_tab.clicked is True
    assert insert_button.clicked is True
    assert url_input.filled_with == "https://example.com"


def test_upload_url_failure_wraps_exception():
    page = StubPage()
    page.locators["button.source-stretched-button"] = StubLocator(click_raises=RuntimeError("broken"))

    result = NotebookLMClient(page).upload_url("https://example.com")

    assert result.success is False
    assert "broken" in result.error


def test_trigger_briefing_returns_link():
    page = StubPage()
    container = StubLocator()
    briefing = StubLocator(ancestor=container)
    page.set_role("button", "Briefing doc", briefing)
    page.locators["a[href*='/notebook/']"] = StubLocator(
        attr="https://notebooklm.google.com/notebook/briefing"
    )

    url = NotebookLMClient(page).trigger_briefing()

    assert url.endswith("/briefing")


def test_trigger_briefing_raises_on_no_button():
    page = StubPage()
    # No role rules registered — all role lookups return count=0.
    with pytest.raises(NotebookLMError):
        NotebookLMClient(page).trigger_briefing()


def test_trigger_audio_returns_link():
    page = StubPage()
    container = StubLocator()
    audio = StubLocator(ancestor=container)
    page.set_role("button", "Audio Overview", audio)
    page.locators["a[href*='/notebook/']"] = StubLocator(
        attr="https://notebooklm.google.com/notebook/audio"
    )

    url = NotebookLMClient(page).trigger_audio_overview()

    assert url.endswith("/audio")


def test_upload_cluster_dry_run_skips_browser(tmp_path, monkeypatch):
    cfg = StubCfg(tmp_path)
    cfg.research_hub_dir.mkdir(parents=True)
    bundle_dir = cfg.research_hub_dir / "bundles" / "alpha-20260411T000000Z"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps(
            {
                "entries": [
                    {"action": "pdf", "pdf_path": str(tmp_path / "a.pdf"), "doi": "10.1/a"},
                    {"action": "url", "url": "https://example.com"},
                ]
            }
        ),
        encoding="utf-8",
    )
    cluster = Cluster(slug="alpha", name="Alpha")
    _write_cluster(cfg, cluster)

    called = {"open": False}

    @contextmanager
    def fake_open(*args, **kwargs):
        called["open"] = True
        yield None, None

    monkeypatch.setattr("research_hub.notebooklm.upload.open_cdp_session", fake_open)

    report = upload_cluster(cluster, cfg, dry_run=True)

    assert called["open"] is False
    assert report.success_count == 2


def test_upload_cluster_dedup_against_cache(tmp_path, monkeypatch):
    cfg = StubCfg(tmp_path)
    cfg.research_hub_dir.mkdir(parents=True)
    bundle_dir = cfg.research_hub_dir / "bundles" / "alpha-20260411T000000Z"
    bundle_dir.mkdir(parents=True)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    (bundle_dir / "manifest.json").write_text(
        json.dumps(
            {
                "entries": [
                    {"action": "pdf", "pdf_path": str(pdf_path), "doi": "10.1/a"},
                    {"action": "url", "url": "https://example.com"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (cfg.research_hub_dir / "nlm_cache.json").write_text(
        json.dumps({"alpha": {"uploaded_sources": [str(pdf_path)]}}),
        encoding="utf-8",
    )
    cluster = Cluster(slug="alpha", name="Alpha", notebooklm_notebook="Alpha Notebook")
    _write_cluster(cfg, cluster)

    class FakeClient:
        def __init__(self, page):
            self.page = page

        def open_or_create_notebook(self, name):
            return type("Handle", (), {"url": "https://notebooklm.google.com/notebook/abc", "notebook_id": "abc", "name": name})()

        def upload_pdf(self, path):
            raise AssertionError("cached PDF should be skipped")

        def upload_url(self, url):
            from research_hub.notebooklm.client import UploadResult

            return UploadResult(source_kind="url", path_or_url=url, success=True)

    @contextmanager
    def fake_open(*args, **kwargs):
        yield object(), StubPage()

    monkeypatch.setattr("research_hub.notebooklm.upload.open_cdp_session", fake_open)
    monkeypatch.setattr("research_hub.notebooklm.upload.NotebookLMClient", FakeClient)
    monkeypatch.setattr("research_hub.notebooklm.upload.time.sleep", lambda _: None)

    report = upload_cluster(cluster, cfg, dry_run=False)

    assert report.skipped_already_uploaded == 1
    assert report.success_count == 1
