"""v0.32 Track A: dashboard screenshot CLI tests. All Playwright mocked."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_cfg(tmp_path):
    import os

    os.environ["RESEARCH_HUB_ROOT"] = str(tmp_path)
    os.environ["RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"] = "1"
    import research_hub.config as cfg_mod

    cfg_mod._config = None
    cfg_mod._config_path = None
    return cfg_mod.HubConfig()


def test_screenshot_validates_tab_name(tmp_path):
    from research_hub.dashboard.screenshot import screenshot_dashboard

    cfg = _make_cfg(tmp_path)
    with pytest.raises(ValueError, match="tab="):
        screenshot_dashboard(cfg, tab="bogus-tab", out=tmp_path / "x.png")


def test_screenshot_handles_missing_playwright(tmp_path, monkeypatch):
    from research_hub.dashboard import screenshot as ss_mod

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    cfg = _make_cfg(tmp_path)
    with pytest.raises(ss_mod.PlaywrightNotInstalled, match="Install"):
        ss_mod.screenshot_dashboard(cfg, tab="overview", out=tmp_path / "x.png")


def test_screenshot_writes_output_with_correct_args(tmp_path, monkeypatch):
    from research_hub.dashboard import screenshot as ss_mod

    cfg = _make_cfg(tmp_path)
    captured = {}

    class FakePage:
        def goto(self, url, **kw):
            captured["goto"] = url

        def click(self, sel, **kw):
            captured["click"] = sel

        def wait_for_timeout(self, n):
            captured["wait"] = n

        def screenshot(self, path, **kw):
            captured["screenshot_path"] = path
            captured["screenshot_kw"] = kw

    class FakeContext:
        def new_page(self):
            return FakePage()

    class FakeBrowser:
        def new_context(self, **kw):
            captured["context_kw"] = kw
            return FakeContext()

        def close(self):
            captured["closed"] = True

    class FakeChromium:
        def launch(self, **kw):
            captured["launch_kw"] = kw
            return FakeBrowser()

    class FakePW:
        def __init__(self):
            self.chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_sync_api = types.ModuleType("playwright.sync_api")
    fake_sync_api.sync_playwright = lambda: FakePW()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)

    dashboard_html = tmp_path / "dashboard.html"
    dashboard_html.write_text("<html></html>", encoding="utf-8")
    with patch.object(ss_mod, "generate_dashboard", return_value=dashboard_html):
        out = ss_mod.screenshot_dashboard(
            cfg,
            tab="library",
            out=tmp_path / "out.png",
            scale=2.5,
            viewport_width=1600,
            viewport_height=1000,
        )

    assert out == tmp_path / "out.png"
    assert captured["context_kw"]["device_scale_factor"] == 2.5
    assert captured["context_kw"]["viewport"]["width"] == 1600
    assert captured["context_kw"]["viewport"]["height"] == 1000
    assert captured["screenshot_path"] == str(tmp_path / "out.png")
    assert captured["screenshot_kw"]["full_page"] is False
    assert captured["click"] == "label[for='dash-tab-library']"
    assert captured["goto"].startswith("file:///")


def test_screenshot_all_writes_one_per_tab(tmp_path):
    from research_hub.dashboard import screenshot as ss_mod

    cfg = _make_cfg(tmp_path)
    calls = []

    def fake_one(cfg_, *, tab, out, **kw):
        calls.append(tab)
        out = Path(out)
        out.write_bytes(b"fake")
        return out

    with patch.object(ss_mod, "screenshot_dashboard", side_effect=fake_one):
        paths = ss_mod.screenshot_all(cfg, out_dir=tmp_path / "shots")

    assert calls == ["overview", "library", "briefings", "writing", "diagnostics", "manage"]
    assert all(p.exists() for p in paths)


def test_cli_screenshot_requires_out_for_single_tab(tmp_path, capsys):
    import os

    os.environ["RESEARCH_HUB_ROOT"] = str(tmp_path)
    os.environ["RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"] = "1"
    import research_hub.config as cfg_mod

    cfg_mod._config = None
    cfg_mod._config_path = None

    from research_hub.cli import main

    rc = main(["dashboard", "--screenshot", "overview"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "--out required" in captured.err
