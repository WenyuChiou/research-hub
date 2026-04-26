"""Install research-hub SKILL.md files into AI coding assistant directories.

v0.53 shipped a skill PACK (multiple SKILL.md files), not just one. v0.66
adds five workspace skills (research-context-compressor, project-orienter,
literature-triage-matrix, paper-memory-builder, notebooklm-brief-verifier)
on top of the original `research-hub` and `research-hub-multi-ai`.

Discovery is dynamic as of v0.66: the installer walks `skills_data/` and
installs every directory that contains a SKILL.md. The hardcoded LEGACY_PACK
below stays as a safety net so older wheels (or empty test environments)
still install the original two skills.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


# Legacy fallback when skills_data/ is missing or empty (e.g. wheel built
# before v0.66 packaging change). Keeps the original two skills installable
# even without the dynamic discovery.
LEGACY_SKILL_PACK: tuple[tuple[str, str], ...] = (
    ("research-hub", "research-hub"),
    ("research-hub-multi-ai", "research-hub-multi-ai"),
)

# Map from on-disk source dir -> install target dir.
# v0.68: source dir renamed `knowledge-base/` -> `research-hub/`; alias
# map is now empty by default but kept as the extension point.
LEGACY_TARGET_ALIASES: dict[str, str] = {}

# v0.68: source-name aliases for backward-compat callers. If external code
# (older user scripts, third-party tooling) calls `get_bundled_skill_path`
# with the pre-rename name, we emit a DeprecationWarning and resolve.
LEGACY_SOURCE_NAME_ALIASES: dict[str, str] = {
    "knowledge-base": "research-hub",
}


def _resolve_skills_data_root() -> Path:
    """Return the directory holding bundled skill subdirectories.

    Order: installed package layout, then editable repo layout.
    """
    pkg = Path(__file__).parent / "skills_data"
    if pkg.exists():
        return pkg
    repo = Path(__file__).resolve().parents[2] / "skills"
    return repo


def _discover_skill_pack() -> tuple[tuple[str, str], ...]:
    """Walk skills_data/ (or skills/ in editable installs) and return
    (install_target_name, source_dir_name) tuples for every directory
    that contains a SKILL.md.

    Falls back to LEGACY_SKILL_PACK when the discovery directory is
    missing or contains no SKILL.md children.
    """
    base = _resolve_skills_data_root()
    if not base.exists():
        return LEGACY_SKILL_PACK
    discovered: list[tuple[str, str]] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        # Skip vendored third-party skills like zotero-skills that ship
        # in the editable repo but aren't part of the research-hub pack.
        if child.name == "zotero-skills":
            continue
        if not (child / "SKILL.md").exists():
            continue
        source_dir = child.name
        target = LEGACY_TARGET_ALIASES.get(source_dir, source_dir)
        # SKILL_PACK historic shape was (source_name, target_name).
        discovered.append((source_dir, target))
    return tuple(discovered) or LEGACY_SKILL_PACK


SKILL_PACK: tuple[tuple[str, str], ...] = _discover_skill_pack()


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


def get_bundled_skill_path(source_name: str = "research-hub") -> Path:
    """Return the path to the SKILL.md bundled with the package for this source.

    Checks the installed-package layout first, then the repo layout (for
    editable installs). Accepts source_name in the discovered SKILL_PACK.

    v0.68: source dir was renamed from `knowledge-base` to `research-hub`.
    Callers passing the pre-rename name still work but emit a one-time
    DeprecationWarning.
    """
    if source_name in LEGACY_SOURCE_NAME_ALIASES:
        import warnings
        new_name = LEGACY_SOURCE_NAME_ALIASES[source_name]
        warnings.warn(
            f"Skill source name {source_name!r} was renamed to {new_name!r} in "
            "research-hub v0.68. Update your code to use the new name; the "
            "alias will be removed in v0.70.",
            DeprecationWarning,
            stacklevel=2,
        )
        source_name = new_name

    pkg_path = Path(__file__).parent / "skills_data" / source_name / "SKILL.md"
    if pkg_path.exists():
        return pkg_path
    # Pre-v0.62 layout: src/research_hub/skill/SKILL.md (singular)
    if source_name == "research-hub":
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
            # core research-hub skill still installs even if multi-ai is
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
    get_bundled_skill_path("research-hub")
    result: list[tuple[str, str, bool]] = []
    for key, cfg in sorted(PLATFORMS.items()):
        all_present = all(cfg.skill_path(target).exists() for _, target in SKILL_PACK)
        result.append((key, cfg.name, all_present))
    return result
