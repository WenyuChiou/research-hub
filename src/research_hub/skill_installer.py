"""Install research-hub SKILL.md into AI coding assistant directories."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlatformConfig:
    name: str
    skill_dir: Path

    @property
    def skill_path(self) -> Path:
        return self.skill_dir / "SKILL.md"


PLATFORMS: dict[str, PlatformConfig] = {
    "claude-code": PlatformConfig(
        name="Claude Code",
        skill_dir=Path.home() / ".claude" / "skills" / "research-hub",
    ),
    "codex": PlatformConfig(
        name="Codex (OpenAI)",
        skill_dir=Path.home() / ".codex" / "skills" / "research-hub",
    ),
    "cursor": PlatformConfig(
        name="Cursor",
        skill_dir=Path.home() / ".cursor" / "skills" / "research-hub",
    ),
    "gemini": PlatformConfig(
        name="Gemini CLI",
        skill_dir=Path.home() / ".gemini" / "skills" / "research-hub",
    ),
}


def get_bundled_skill_path() -> Path:
    """Return the path to the SKILL.md bundled with the package."""
    pkg_skill = Path(__file__).parent / "skill" / "SKILL.md"
    if pkg_skill.exists():
        return pkg_skill

    repo_skill = Path(__file__).resolve().parents[2] / "skills" / "knowledge-base" / "SKILL.md"
    if repo_skill.exists():
        return repo_skill

    raise FileNotFoundError(
        "Could not find bundled SKILL.md. "
        "Reinstall the package: pip install research-hub-pipeline"
    )


def install_skill(platform: str) -> str:
    """Install SKILL.md for the given platform. Returns the installed path."""
    if platform not in PLATFORMS:
        raise ValueError(
            f"Unknown platform '{platform}'. "
            f"Supported: {', '.join(sorted(PLATFORMS))}"
        )

    config = PLATFORMS[platform]
    source = get_bundled_skill_path()
    config.skill_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, config.skill_path)
    return str(config.skill_path)


def list_platforms() -> list[tuple[str, str, bool]]:
    """Return (key, display_name, already_installed) for each platform."""
    get_bundled_skill_path()
    result: list[tuple[str, str, bool]] = []
    for key, cfg in sorted(PLATFORMS.items()):
        result.append((key, cfg.name, cfg.skill_path.exists()))
    return result
