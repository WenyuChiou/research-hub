from __future__ import annotations

from pathlib import Path

from research_hub.dashboard.executor import ALLOWED_ACTIONS, _build_command_args
from research_hub.dashboard.manage_commands import build_manage_command
from research_hub.dashboard.sections import BriefingsSection, ManageSection
from research_hub.dashboard.types import BriefingPreview, ClusterCard, DashboardData, NLMArtifactRecord


def _data(**overrides) -> DashboardData:
    base = DashboardData(
        vault_root="/vault",
        generated_at="2026-04-19T12:00:00Z",
        persona="researcher",
        total_papers=0,
        total_clusters=0,
        papers_this_week=0,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _cluster(**overrides) -> ClusterCard:
    cluster = ClusterCard(
        slug="harness",
        name="Harness",
        notebooklm_notebook_url="https://notebooklm.google.com/notebook/harness",
    )
    for key, value in overrides.items():
        setattr(cluster, key, value)
    return cluster


def test_executor_whitelist_includes_v042_v043_actions():
    assert "notebooklm-ask" in ALLOWED_ACTIONS
    assert "vault-polish-markdown" in ALLOWED_ACTIONS
    assert "bases-emit" in ALLOWED_ACTIONS
    assert "notebooklm-bundle" in ALLOWED_ACTIONS
    assert "notebooklm-upload" in ALLOWED_ACTIONS


def test_build_notebooklm_bundle():
    assert build_manage_command("notebooklm-bundle", "harness") == (
        "research-hub notebooklm bundle --cluster harness"
    )


def test_build_notebooklm_upload_visible():
    cmd = build_manage_command("notebooklm-upload", "harness", visible=True)
    assert "--visible" in cmd
    assert "--cluster harness" in cmd


def test_build_notebooklm_upload_default_headless():
    cmd = build_manage_command("notebooklm-upload", "harness")
    assert "--headless" in cmd
    assert "--visible" not in cmd


def test_build_notebooklm_generate_brief():
    cmd = build_manage_command("notebooklm-generate", "harness", kind="brief")
    assert "--type brief" in cmd


def test_build_notebooklm_generate_invalid_kind_returns_none():
    assert build_manage_command("notebooklm-generate", "harness", kind="bogus") is None


def test_build_notebooklm_ask_requires_question():
    assert build_manage_command("notebooklm-ask", "harness", question="") is None
    assert build_manage_command("notebooklm-ask", "harness", question="   ") is None


def test_build_notebooklm_ask_with_timeout():
    cmd = build_manage_command(
        "notebooklm-ask",
        "harness",
        question="What is X?",
        timeout="60",
    )
    assert "--question" in cmd
    assert '"What is X?"' in cmd
    assert "--timeout 60" in cmd


def test_build_vault_polish_markdown_default_and_apply():
    assert "--apply" not in build_manage_command("vault-polish-markdown", "harness")
    assert "--apply" in build_manage_command("vault-polish-markdown", "harness", apply=True)


def test_build_bases_emit_default_and_force():
    assert build_manage_command("bases-emit", "harness") == "research-hub bases emit --cluster harness"
    assert "--force" in build_manage_command("bases-emit", "harness", force=True)


def test_executor_builds_new_manage_actions_from_builder():
    args = _build_command_args("notebooklm-ask", "harness", {"question": "Why?", "timeout": "90"})
    assert args[:3]
    assert args[-4:] == ["--cluster", "harness", "--question", "Why?"] or "--question" in args
    assert "--timeout" in args


def test_sections_render_v042_v043_buttons():
    html = ManageSection().render(_data(clusters=[_cluster()], total_clusters=1))
    for action in (
        "notebooklm-bundle",
        "notebooklm-upload",
        "notebooklm-generate",
        "notebooklm-download",
        "notebooklm-ask",
        "vault-polish-markdown",
        "bases-emit",
    ):
        assert f'data-action="{action}"' in html


def test_script_js_has_new_manage_actions():
    text = Path("src/research_hub/dashboard/script.js").read_text(encoding="utf-8")
    for action in (
        "notebooklm-bundle",
        "notebooklm-upload",
        "notebooklm-generate",
        "notebooklm-download",
        "notebooklm-ask",
        "vault-polish-markdown",
        "bases-emit",
    ):
        assert f'case "{action}"' in text


def test_briefings_artifact_tile_renders_single_artifact():
    briefing = BriefingPreview(
        cluster_slug="harness",
        cluster_name="Harness",
        notebook_url="https://notebooklm.google.com/notebook/harness",
        preview_text="Preview",
        full_text="Full text",
        char_count=1243,
        downloaded_at="2026-04-19T12:00:00Z",
    )
    cluster = _cluster(
        briefing=briefing,
        nlm_artifacts=[
            NLMArtifactRecord(
                kind="brief",
                # Use a per-OS absolute path so Path.as_uri() works on
                # Linux + macOS as well as Windows.
                path=("C:/tmp/brief.txt" if __import__("sys").platform == "win32" else "/tmp/brief.txt"),
                downloaded_at="2026-04-19T12:00:00Z",
                char_count=1243,
                notebook_url="https://notebooklm.google.com/notebook/harness",
            )
        ],
    )
    html = BriefingsSection().render(_data(clusters=[cluster], total_clusters=1, briefings=[briefing]))
    assert "NotebookLM artifacts" in html
    assert "brief" in html
    assert "2026-04-19" in html
    assert "1,243" in html
    assert "open in NLM" in html
    assert "open .txt" in html


def test_briefings_artifact_tile_renders_download_button_when_empty():
    html = BriefingsSection().render(_data(clusters=[_cluster()], total_clusters=1))
    assert "No downloaded artifacts yet." in html
    assert 'data-action="notebooklm-download"' in html
    assert "Download brief" in html


def test_briefings_artifact_tile_renders_multiple_artifacts():
    cluster = _cluster(
        nlm_artifacts=[
            NLMArtifactRecord(kind="brief", downloaded_at="2026-04-19T12:00:00Z", char_count=111),
            NLMArtifactRecord(kind="audio", notebook_url="https://notebooklm.google.com/notebook/harness/audio"),
            NLMArtifactRecord(kind="mind_map", notebook_url="https://notebooklm.google.com/notebook/harness/map"),
        ]
    )
    html = BriefingsSection().render(_data(clusters=[cluster], total_clusters=1))
    assert "audio" in html
    assert "mind map" in html
    assert html.count("<tr>") >= 3
