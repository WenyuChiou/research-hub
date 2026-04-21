from __future__ import annotations

from types import SimpleNamespace

from research_hub.dashboard import executor
from research_hub.dashboard.sections import LibrarySection


def _paper():
    return SimpleNamespace(
        slug="paper-one",
        title="Paper One",
        authors="Doe, Jane",
        year="2026",
        abstract="Abstract.",
        doi="10.1000/one",
        zotero_key="ABC123",
        obsidian_path="raw/alpha/paper-one.md",
        tags=["agents"],
        labels=["seed"],
        bibtex="@article{one}",
    )


def test_paper_row_renders_action_menu_forms():
    html = LibrarySection()._paper_row("alpha", _paper(), show_zotero=True)

    assert 'class="paper-action-menu"' in html
    assert 'data-action="move"' in html
    assert 'name="target_cluster"' in html
    assert 'data-action="label"' in html
    assert 'name="label"' in html
    assert 'data-action="mark"' in html
    assert 'value="read"' in html
    assert 'value="reading"' in html
    assert 'value="archived"' in html
    assert 'data-action="remove"' in html
    assert 'name="apply"' in html


def test_paper_row_action_forms_use_paper_slug():
    html = LibrarySection()._paper_row("alpha", _paper(), show_zotero=True)

    assert html.count('data-slug="paper-one"') >= 5


def test_paper_row_hides_zotero_cite_when_persona_gated():
    html = LibrarySection()._paper_row("alpha", _paper(), show_zotero=False)

    assert 'class="cite-btn"' not in html
    assert 'class="open-btn"' in html


def test_move_action_builds_api_exec_command_payload():
    args = executor._build_command_args("move", "paper-one", {"target_cluster": "beta"})

    assert args[-4:] == ["move", "paper-one", "--to", "beta"]


def test_label_action_builds_api_exec_command_payload():
    args = executor._build_command_args("label", "paper-one", {"label": "core"})

    assert args[-4:] == ["label", "paper-one", "--set", "core"]


def test_mark_read_action_builds_api_exec_command_payload():
    args = executor._build_command_args("mark", "paper-one", {"status": "read"})

    assert args[-4:] == ["mark", "paper-one", "--status", "read"]


def test_mark_reading_action_builds_api_exec_command_payload():
    args = executor._build_command_args("mark", "paper-one", {"status": "reading"})

    assert args[-4:] == ["mark", "paper-one", "--status", "reading"]


def test_mark_archived_action_builds_api_exec_command_payload():
    args = executor._build_command_args("mark", "paper-one", {"status": "archived"})

    assert args[-4:] == ["mark", "paper-one", "--status", "archived"]


def test_remove_preview_action_builds_dry_run_payload():
    args = executor._build_command_args("remove", "paper-one", {"dry_run": True})

    assert args[-3:] == ["remove", "paper-one", "--dry-run"]


def test_remove_apply_action_omits_dry_run_flag():
    args = executor._build_command_args("remove", "paper-one", {"dry_run": False})

    assert args[-2:] == ["remove", "paper-one"]
    assert "--dry-run" not in args
