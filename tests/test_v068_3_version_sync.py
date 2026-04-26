"""v0.68.3 — guard rails to prevent regressions that would break
downstream consumers (especially the WenyuChiou/ai-research-skills
catalog which links into our `skills/<name>/` paths).

Two invariants enforced:

1. `research_hub.__version__` MUST match `pyproject.toml [project].version`.
   The hardcoded string drift bug (0.64.2 in __init__.py while pyproject
   said 0.68.2) shipped to PyPI for 4 releases before the v0.68.2 interop
   test caught it.

2. The set of source-dir names under `skills/` MUST NOT shrink across
   releases. Each name is pinned in EXPECTED_SKILL_DIR_NAMES below.
   Adding a new skill: add its name here. Renaming/removing a skill:
   you must coordinate with the catalog maintainer FIRST (see
   CONTRIBUTING.md) and explicitly remove the name here in the same
   commit that renames the dir. Forces a deliberate decision.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / "skills"

# Source dirs the catalog (and any other downstream consumer) may link to.
# Excludes `zotero-skills` which is a vendored third-party clone.
EXPECTED_SKILL_DIR_NAMES = frozenset({
    "research-hub",
    "research-hub-multi-ai",
    "research-context-compressor",
    "research-project-orienter",
    "literature-triage-matrix",
    "paper-memory-builder",
    "notebooklm-brief-verifier",
    "zotero-library-curator",
    "research-design-helper",
})


def test_init_version_matches_pyproject_version():
    """Catches the drift bug that shipped 0.64.2 in __init__.py while
    pyproject.toml said 0.65/0.66/0.67/0.68.2 across 4 PyPI releases."""
    init_text = (REPO_ROOT / "src" / "research_hub" / "__init__.py").read_text(encoding="utf-8")
    init_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_text)
    assert init_match, "__version__ not found in src/research_hub/__init__.py"
    init_version = init_match.group(1)

    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    py_match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', pyproject, re.MULTILINE)
    assert py_match, "version not found in pyproject.toml"
    py_version = py_match.group(1)

    assert init_version == py_version, (
        f"Version drift detected — bump both:\n"
        f"  src/research_hub/__init__.py: {init_version}\n"
        f"  pyproject.toml:               {py_version}"
    )


def test_skill_source_dirs_match_expected_set():
    """Adding a skill requires extending EXPECTED_SKILL_DIR_NAMES.
    Removing or renaming a skill requires explicit catalog coordination
    (see CONTRIBUTING.md) AND an update here in the same commit. This
    forces deliberate decisions about downstream link stability."""
    actual = {
        child.name for child in SKILLS_ROOT.iterdir()
        if child.is_dir() and child.name != "zotero-skills"
    }

    missing = EXPECTED_SKILL_DIR_NAMES - actual
    extra = actual - EXPECTED_SKILL_DIR_NAMES

    msg_parts = []
    if missing:
        msg_parts.append(
            f"Missing skill source dirs that the catalog may link to: "
            f"{sorted(missing)}. If you renamed/removed one of these, "
            "coordinate with the catalog maintainer FIRST (see CONTRIBUTING.md), "
            "then remove the name from EXPECTED_SKILL_DIR_NAMES in the same commit."
        )
    if extra:
        msg_parts.append(
            f"New skill source dirs not pinned in EXPECTED_SKILL_DIR_NAMES: "
            f"{sorted(extra)}. Add them here so future renames trigger this guard."
        )
    assert not (missing or extra), "\n\n".join(msg_parts)


def test_skill_data_mirror_dirs_match_expected_set():
    """Same invariant applied to the packaged mirror under
    src/research_hub/skills_data/. The wheel installs from this path."""
    mirror_root = REPO_ROOT / "src" / "research_hub" / "skills_data"
    actual = {
        child.name for child in mirror_root.iterdir()
        if child.is_dir() and child.name != "zotero-skills"
    }
    missing = EXPECTED_SKILL_DIR_NAMES - actual
    extra = actual - EXPECTED_SKILL_DIR_NAMES
    assert not (missing or extra), (
        f"skills_data/ mirror drift — missing={sorted(missing)} extra={sorted(extra)}"
    )
