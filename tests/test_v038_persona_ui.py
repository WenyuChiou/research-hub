"""v0.38 persona-aware information architecture tests."""
from __future__ import annotations

import pytest

from research_hub.dashboard.terminology import (
    ALL_PERSONAS,
    get_label,
    is_section_visible,
    label_capitalize,
    visible_tabs,
)
from tests._persona_factory import make_persona_vault


@pytest.mark.parametrize(
    "persona,expected",
    [
        ("researcher", "Cluster"),
        ("analyst", "Topic"),
        ("humanities", "Theme"),
        ("internal", "Project area"),
    ],
)
def test_get_label_cluster_per_persona(persona, expected):
    assert get_label("cluster", persona) == expected


def test_get_label_unknown_key_returns_key():
    assert get_label("totally-made-up-xyz", "researcher") == "totally-made-up-xyz"


def test_get_label_unknown_persona_falls_back_to_researcher():
    assert get_label("cluster", "alien-persona") == "Cluster"


def test_label_capitalize_passthrough():
    assert label_capitalize("cluster", "internal") == "Project area"


def test_all_personas_have_all_labels():
    from research_hub.dashboard.terminology import _LABELS

    for key, by_persona in _LABELS.items():
        for persona in ALL_PERSONAS:
            assert persona in by_persona, f"{key!r} missing {persona!r}"


@pytest.mark.parametrize(
    "persona,expected_tabs",
    [
        ("researcher", {"overview", "library", "briefings", "writing", "diagnostics", "manage"}),
        ("humanities", {"overview", "library", "briefings", "writing", "diagnostics", "manage"}),
        ("analyst", {"overview", "library", "briefings", "writing", "manage"}),
        ("internal", {"overview", "library", "briefings", "writing", "manage"}),
    ],
)
def test_visible_tabs_per_persona(persona, expected_tabs):
    assert visible_tabs(persona) == expected_tabs


def test_diagnostics_hidden_for_analyst_and_internal():
    assert "diagnostics" not in visible_tabs("analyst")
    assert "diagnostics" not in visible_tabs("internal")
    assert "diagnostics" in visible_tabs("researcher")
    assert "diagnostics" in visible_tabs("humanities")


def test_visible_tabs_unknown_persona_falls_back_to_researcher():
    assert visible_tabs("unknown") == visible_tabs("researcher")


def test_bind_zotero_hidden_for_no_zotero_personas():
    assert not is_section_visible("manage_bind_zotero", "analyst")
    assert not is_section_visible("manage_bind_zotero", "internal")
    assert is_section_visible("manage_bind_zotero", "researcher")
    assert is_section_visible("manage_bind_zotero", "humanities")


def test_compose_draft_hidden_for_no_zotero_personas():
    assert not is_section_visible("writing_compose_draft", "analyst")
    assert not is_section_visible("writing_compose_draft", "internal")
    assert is_section_visible("writing_compose_draft", "researcher")


def test_zotero_column_hidden_for_no_zotero_personas():
    assert not is_section_visible("library_zotero_column", "analyst")
    assert not is_section_visible("library_zotero_column", "internal")


def test_unknown_section_defaults_visible():
    assert is_section_visible("brand-new-feature", "researcher") is True


def test_persona_detection_explicit_humanities(tmp_path, monkeypatch):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr(cfg, "persona", "humanities", raising=False)
    from research_hub.dashboard.data import _detect_persona

    assert _detect_persona(cfg, None) == "humanities"


def test_persona_detection_explicit_internal(tmp_path, monkeypatch):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr(cfg, "persona", "internal", raising=False)
    from research_hub.dashboard.data import _detect_persona

    assert _detect_persona(cfg, None) == "internal"


def test_persona_env_var_overrides_default(tmp_path, monkeypatch):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setenv("RESEARCH_HUB_PERSONA", "humanities")
    monkeypatch.setattr(cfg, "persona", "", raising=False)
    from research_hub.dashboard.data import _detect_persona

    assert _detect_persona(cfg, None) == "humanities"


def test_persona_legacy_no_zotero_still_returns_analyst(tmp_path, monkeypatch):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr(cfg, "persona", "", raising=False)
    monkeypatch.setattr(cfg, "no_zotero", True, raising=False)
    monkeypatch.delenv("RESEARCH_HUB_PERSONA", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    from research_hub.dashboard.data import _detect_persona

    assert _detect_persona(cfg, None) == "analyst"


@pytest.mark.parametrize(
    "persona,expected_label",
    [
        ("researcher", "Cluster"),
        ("analyst", "Topic"),
        ("humanities", "Theme"),
        ("internal", "Project area"),
    ],
)
def test_dashboard_renders_with_persona_label(tmp_path, monkeypatch, persona, expected_label):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr(cfg, "persona", persona, raising=False)
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    from research_hub.dashboard.render import render_dashboard_from_config

    html = render_dashboard_from_config(cfg)
    assert expected_label in html


def test_analyst_dashboard_omits_diagnostics_radio(tmp_path, monkeypatch):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr(cfg, "persona", "analyst", raising=False)
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    from research_hub.dashboard.render import render_dashboard_from_config

    html = render_dashboard_from_config(cfg)
    assert 'id="dash-tab-diagnostics"' not in html
    assert 'id="tab-diagnostics"' not in html


def test_researcher_dashboard_includes_diagnostics_radio(tmp_path, monkeypatch):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr(cfg, "persona", "researcher", raising=False)
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    from research_hub.dashboard.render import render_dashboard_from_config

    html = render_dashboard_from_config(cfg)
    assert "dash-tab-radio-diagnostics" in html


def test_preservation_ids_intact_across_all_personas(tmp_path, monkeypatch):
    from research_hub.dashboard.render import render_dashboard_from_config

    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    for persona in ALL_PERSONAS:
        cfg, _ = make_persona_vault(tmp_path / persona, persona="A")
        monkeypatch.setattr(cfg, "persona", persona, raising=False)
        html = render_dashboard_from_config(cfg)
        for marker in (
            "vault-search",
            "live-pill",
            "csrf-token",
            "data-jump-tab",
            "data-cluster",
            "tab-overview",
            "manage-build-btn",
        ):
            assert marker in html, f"{persona}: missing preserved marker: {marker}"
