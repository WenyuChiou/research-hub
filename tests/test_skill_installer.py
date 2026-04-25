from __future__ import annotations

from pathlib import Path

import pytest

from research_hub import skill_installer


def _patch_platform_paths(monkeypatch, home: Path) -> None:
    """v0.53: PlatformConfig now takes `skills_root` (shared dir for all skills
    in the pack) instead of `skill_dir` (one dir per skill)."""
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "claude-code",
        skill_installer.PlatformConfig(
            name="Claude Code",
            skills_root=home / ".claude" / "skills",
        ),
    )
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "codex",
        skill_installer.PlatformConfig(
            name="Codex (OpenAI)",
            skills_root=home / ".codex" / "skills",
        ),
    )
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "cursor",
        skill_installer.PlatformConfig(
            name="Cursor",
            skills_root=home / ".cursor" / "skills",
        ),
    )
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "gemini",
        skill_installer.PlatformConfig(
            name="Gemini CLI",
            skills_root=home / ".gemini" / "skills",
        ),
    )


def test_install_skill_pack_writes_every_pack_member(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)

    installed = skill_installer.install_skill("claude-code")

    # v0.53: returns a list (one entry per skill in SKILL_PACK)
    assert isinstance(installed, list)
    assert len(installed) == len(skill_installer.SKILL_PACK)
    # Each target dir was created with SKILL.md inside
    for _source, target in skill_installer.SKILL_PACK:
        dest = tmp_path / ".claude" / "skills" / target / "SKILL.md"
        assert dest.is_file(), f"missing skill at {dest}"


def test_install_skill_content_matches_source(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)

    skill_installer.install_skill("claude-code")

    for source_name, target_name in skill_installer.SKILL_PACK:
        source = skill_installer.get_bundled_skill_path(source_name)
        dest = tmp_path / ".claude" / "skills" / target_name / "SKILL.md"
        assert dest.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_install_unknown_platform_raises():
    with pytest.raises(ValueError, match="Unknown platform"):
        skill_installer.install_skill("unknown")


def test_list_platforms_shows_all():
    platforms = skill_installer.list_platforms()

    assert len(platforms) == 4
    assert [key for key, _, _ in platforms] == ["claude-code", "codex", "cursor", "gemini"]


def test_install_idempotent(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)

    first = skill_installer.install_skill("claude-code")
    second = skill_installer.install_skill("claude-code")

    assert first == second
    for path in second:
        dest = Path(path)
        assert dest.is_file()


def test_list_platforms_reports_true_after_full_pack_install(tmp_path, monkeypatch):
    """v0.53 regression: list_platforms only reports 'installed' when ALL
    skills in the pack are present, not just the legacy knowledge-base one."""
    _patch_platform_paths(monkeypatch, tmp_path)

    before = dict((k, ok) for k, _, ok in skill_installer.list_platforms())
    assert before["claude-code"] is False

    skill_installer.install_skill("claude-code")

    after = dict((k, ok) for k, _, ok in skill_installer.list_platforms())
    assert after["claude-code"] is True


def test_multi_ai_skill_is_discoverable():
    """The v0.53 multi-AI skill must be findable from the bundled source."""
    path = skill_installer.get_bundled_skill_path("research-hub-multi-ai")
    text = path.read_text(encoding="utf-8")
    assert "research-hub-multi-ai" in text
    # Spot-check that the skill mentions the three executors
    for name in ("Claude", "Codex", "Gemini"):
        assert name in text


def test_bundled_skills_use_current_public_positioning():
    """Packaged skills are what `research-hub install` copies for users."""
    bad_fragments = ("??", "蝜", "銝", "", "撟")
    for source_name, _target in skill_installer.SKILL_PACK:
        text = skill_installer.get_bundled_skill_path(source_name).read_text(encoding="utf-8")
        for fragment in bad_fragments:
            assert fragment not in text
        for fragment in ("Zotero", "Obsidian", "NotebookLM"):
            assert fragment in text
    core = skill_installer.get_bundled_skill_path("knowledge-base").read_text(encoding="utf-8")
    assert "AI-operable" in core
    assert "--preset" not in core
    assert "notebooklm generate --cluster project-topic --type brief" in core


def test_ai_integration_docs_use_current_notebooklm_generate_flag():
    for path in (Path("docs/ai-integrations.md"), Path("docs/zh/ai-integrations.md")):
        text = path.read_text(encoding="utf-8")
        assert "--preset" not in text
        assert "notebooklm generate --cluster my-topic --type brief" in text
