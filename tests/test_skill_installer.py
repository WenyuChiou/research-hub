from __future__ import annotations

from pathlib import Path

import pytest

from research_hub import skill_installer


def _patch_platform_paths(monkeypatch, home: Path) -> None:
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "claude-code",
        skill_installer.PlatformConfig(
            name="Claude Code",
            skill_dir=home / ".claude" / "skills" / "research-hub",
        ),
    )
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "codex",
        skill_installer.PlatformConfig(
            name="Codex (OpenAI)",
            skill_dir=home / ".codex" / "skills" / "research-hub",
        ),
    )
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "cursor",
        skill_installer.PlatformConfig(
            name="Cursor",
            skill_dir=home / ".cursor" / "skills" / "research-hub",
        ),
    )
    monkeypatch.setitem(
        skill_installer.PLATFORMS,
        "gemini",
        skill_installer.PlatformConfig(
            name="Gemini CLI",
            skill_dir=home / ".gemini" / "skills" / "research-hub",
        ),
    )


def test_install_skill_creates_directory(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)

    installed = Path(skill_installer.install_skill("claude-code"))

    assert installed == tmp_path / ".claude" / "skills" / "research-hub" / "SKILL.md"
    assert installed.is_file()


def test_install_skill_content_matches_source(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)

    installed = Path(skill_installer.install_skill("claude-code"))
    source = skill_installer.get_bundled_skill_path()

    assert installed.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_install_unknown_platform_raises():
    with pytest.raises(ValueError, match="Unknown platform"):
        skill_installer.install_skill("unknown")


def test_list_platforms_shows_all():
    platforms = skill_installer.list_platforms()

    assert len(platforms) == 4
    assert [key for key, _, _ in platforms] == ["claude-code", "codex", "cursor", "gemini"]


def test_install_idempotent(tmp_path, monkeypatch):
    _patch_platform_paths(monkeypatch, tmp_path)

    first = Path(skill_installer.install_skill("claude-code"))
    second = Path(skill_installer.install_skill("claude-code"))
    source = skill_installer.get_bundled_skill_path()

    assert first == second
    assert second.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
