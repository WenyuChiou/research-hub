"""Install research-hub SKILL.md files into AI coding assistant directories.

v0.53 ships a skill PACK (multiple SKILL.md files), not just one. The
existing `research-hub` skill gives generic pipeline guidance; the new
`research-hub-multi-ai` skill teaches Claude how to delegate crystal
generation and long work to Codex/Gemini CLIs when they're on PATH.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


# A skill in the pack: bundled source name -> install target subdir name.
# Each platform directory ends up with one subdir per skill, each containing
# SKILL.md — matches Claude Code's standard `~/.claude/skills/<name>/SKILL.md`.
SKILL_PACK: tuple[tuple[str, str], ...] = (
    ("knowledge-base", "research-hub"),             # legacy name -> legacy dir
    ("research-hub-multi-ai", "research-hub-multi-ai"),
)


@dataclass
class PlatformConfig:
    name: str
    skills_root: Path

    def skill_dir(self, target_name: str) -> Path:
        return self.skills_root / target_name

    def skill_path(self, target_name: str) -> Path:
        return self.skill_dir(target_name) / "SKILL.md"


PLATFORMS: dict[str, PlatformConfig] = {
    "claude-code": PlatformConfig(
        name="Claude Code",
        skills_root=Path.home() / ".claude" / "skills",
    ),
    "codex": PlatformConfig(
        name="Codex (OpenAI)",
        skills_root=Path.home() / ".codex" / "skills",
    ),
    "cursor": PlatformConfig(
        name="Cursor",
        skills_root=Path.home() / ".cursor" / "skills",
    ),
    "gemini": PlatformConfig(
        name="Gemini CLI",
        skills_root=Path.home() / ".gemini" / "skills",
    ),
}


def get_bundled_skill_path(source_name: str = "knowledge-base") -> Path:
    """Return the path to the SKILL.md bundled with the package for this source.

    Checks the installed-package layout first, then the repo layout (for
    editable installs). Accepts source_name ∈ SKILL_PACK first column.
    """
    pkg_path = Path(__file__).parent / "skills_data" / source_name / "SKILL.md"
    if pkg_path.exists():
        return pkg_path
    # Backward-compat: old layout had knowledge-base at src/research_hub/skill/SKILL.md
    if source_name == "knowledge-base":
        legacy_pkg = Path(__file__).parent / "skill" / "SKILL.md"
        if legacy_pkg.exists():
            return legacy_pkg

    repo_path = Path(__file__).resolve().parents[2] / "skills" / source_name / "SKILL.md"
    if repo_path.exists():
        return repo_path

    raise FileNotFoundError(
        f"Could not find bundled SKILL.md for skill {source_name!r}. "
        "Reinstall the package: pip install research-hub-pipeline"
    )


def install_skill(platform: str) -> list[str]:
    """Install the skill PACK for the given platform.

    Returns a list of installed SKILL.md paths (one per skill in the pack).
    """
    if platform not in PLATFORMS:
        raise ValueError(
            f"Unknown platform '{platform}'. "
            f"Supported: {', '.join(sorted(PLATFORMS))}"
        )

    config = PLATFORMS[platform]
    installed: list[str] = []
    for source_name, target_name in SKILL_PACK:
        try:
            source = get_bundled_skill_path(source_name)
        except FileNotFoundError:
            # Skip optional skills gracefully if the source is missing, so the
            # core knowledge-base skill still installs even if multi-ai is
            # absent from a partial install.
            continue
        skill_dir = config.skill_dir(target_name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        dest = skill_dir / "SKILL.md"
        shutil.copy2(source, dest)
        installed.append(str(dest))
    return installed


def list_platforms() -> list[tuple[str, str, bool]]:
    """Return (key, display_name, all_skills_installed) for each platform.

    A platform is marked installed only when every skill in SKILL_PACK is
    present. This way `research-hub install --list` highlights partial
    installs that need re-running after a package upgrade.
    """
    # Ensure at least the core skill is findable — fail loudly if not.
    get_bundled_skill_path("knowledge-base")
    result: list[tuple[str, str, bool]] = []
    for key, cfg in sorted(PLATFORMS.items()):
        all_present = all(cfg.skill_path(target).exists() for _, target in SKILL_PACK)
        result.append((key, cfg.name, all_present))
    return result
