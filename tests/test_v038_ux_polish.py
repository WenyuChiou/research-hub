"""v0.38 UX polish: collapsed health badge + font scale + recent feed."""

from __future__ import annotations

import re

from tests._persona_factory import make_persona_vault


def _render_dashboard(cfg, with_warnings: bool = False):
    """Render the dashboard HTML and return as string."""
    from research_hub.dashboard.render import render_dashboard_from_config

    if with_warnings:
        orphan = cfg.raw / "stranded-folder"
        orphan.mkdir(exist_ok=True)
        (orphan / "x.md").write_text("---\ntitle: x\n---\nbody", encoding="utf-8")
    return render_dashboard_from_config(cfg)


def test_health_badge_renders_when_warnings_exist(tmp_path):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    html = _render_dashboard(cfg, with_warnings=True)
    assert "health-badge" in html
    assert "<details" in html


def test_health_badge_does_not_render_when_clean(tmp_path, monkeypatch):
    """Persona A factory creates a vault that should be doctor-clean."""
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    import research_hub.dashboard.render as render_mod

    original_collect = render_mod.collect_dashboard_data

    def _collect_clean(*args, **kwargs):
        data = original_collect(*args, **kwargs)
        data.health_badges = []
        return data

    monkeypatch.setattr(render_mod, "collect_dashboard_data", _collect_clean)
    html = _render_dashboard(cfg, with_warnings=False)
    assert '<details class="health-badge"' not in html
    assert "debug-banner is-visible" not in html


def test_health_badge_uses_data_status_attribute(tmp_path):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    html = _render_dashboard(cfg, with_warnings=True)
    assert re.search(r'data-status="(fail|warn)"', html)


def test_health_badge_has_summary_with_count(tmp_path):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    html = _render_dashboard(cfg, with_warnings=True)
    assert "click to expand" in html
    # v0.38.1: chip now breaks down "N error(s), N warning(s)" instead of opaque "N issues"
    assert re.search(r"\d+ (error|warning)", html)


def test_font_scale_tokens_present(tmp_path):
    """style.css served inline must include the new font tokens."""
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    html = _render_dashboard(cfg)
    assert "--text-sm: 0.9375rem" in html
    assert "--text-md: 1.0625rem" in html


def test_recent_additions_uses_increased_title_font(tmp_path):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    html = _render_dashboard(cfg)
    assert ".recent-title" in html
    assert re.search(r"\.recent-title\s*\{[^}]*font-size:\s*var\(--text-md\)", html)


def test_all_six_tabs_still_present(tmp_path):
    """Regression guard: A's CSS-only changes don't break the tab system."""
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    html = _render_dashboard(cfg)
    for tab_id in (
        "dash-tab-overview",
        "dash-tab-library",
        "dash-tab-briefings",
        "dash-tab-writing",
        "dash-tab-diagnostics",
        "dash-tab-manage",
    ):
        assert tab_id in html, f"missing tab id: {tab_id}"


def test_preservation_ids_intact_after_polish(tmp_path):
    """All v0.34-locked element IDs and data-attrs must still be present."""
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    html = _render_dashboard(cfg)
    for marker in (
        "vault-search",
        "live-pill",
        "csrf-token",
        "data-jump-tab",
        "data-cluster",
        "tab-overview",
        "manage-build-btn",
    ):
        assert marker in html, f"missing preserved marker: {marker}"
