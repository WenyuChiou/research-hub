"""Phase B / v1.1 — command palette + _HOME wayfinding contract tests.

Locks the palette↔command-surface contract so a future CLI
subcommand or ALLOWED_ACTION can't silently desync from the ⌘K
palette (same contract-lock philosophy as test_release_gate.py),
and asserts the _HOME "Start here" block is prepend-only +
idempotent.
"""

from __future__ import annotations

import re

import pytest

from research_hub.dashboard.executor import ALLOWED_ACTIONS
from research_hub.dashboard.palette import build_palette_manifest
from research_hub.vault import hub_overview as ho


# --- palette manifest ↔ command surface (no drift) ----------------------

@pytest.fixture(scope="module")
def manifest() -> dict:
    return build_palette_manifest()


def test_palette_actions_exactly_equal_allowed_actions(manifest: dict) -> None:
    """Every ALLOWED_ACTION appears exactly once as a palette
    action, and nothing else. Adding/removing an action without it
    surfacing in the palette fails here."""
    ids = [a["id"] for a in manifest["actions"]]
    assert sorted(ids) == sorted(ALLOWED_ACTIONS)
    assert len(ids) == len(set(ids)), "duplicate action ids"
    assert all(a["kind"] == "action" for a in manifest["actions"])


def test_palette_subcommands_match_describe(manifest: dict) -> None:
    """The cli entries are exactly the describe subcommand list —
    no parallel/hand-maintained command list."""
    from research_hub.describe import build_manifest

    describe_names = {
        str(e.get("name", "")).strip()
        for e in build_manifest().get("subcommands", [])
        if str(e.get("name", "")).strip()
    }
    palette_names = {e["label"] for e in manifest["subcommands"]}
    assert palette_names == describe_names
    assert all(e["kind"] == "cli" for e in manifest["subcommands"])
    assert all(e["id"] == f"cli:{e['label']}" for e in manifest["subcommands"])


def test_palette_nonempty(manifest: dict) -> None:
    assert manifest["actions"], "actions empty"
    assert len(manifest["subcommands"]) > 10, "describe subcommands missing"


def test_api_palette_route_registered() -> None:
    """The /api/palette GET route exists in the dashboard server."""
    import research_hub.dashboard.http_server as h
    from pathlib import Path

    src = Path(h.__file__).read_text(encoding="utf-8")
    assert '"/api/palette"' in src
    assert "build_palette_manifest" in src


# --- template + assets carry the palette (no-LLM static checks) ---------

def test_template_has_palette_dialog() -> None:
    from pathlib import Path
    from research_hub.dashboard import render

    tpl = Path(render._TEMPLATE_PATH).read_text(encoding="utf-8")
    assert 'id="cmdk"' in tpl and 'id="cmdk-input"' in tpl
    assert 'aria-modal="true"' in tpl


def test_script_has_palette_module_and_keybinding() -> None:
    from pathlib import Path
    from research_hub.dashboard import render

    js = Path(render._SCRIPT_PATH).read_text(encoding="utf-8")
    assert "initCommandPalette" in js
    assert 'fetch("/api/palette")' in js
    assert "metaKey || ev.ctrlKey" in js  # ⌘/Ctrl+K


def test_style_has_mobile_breakpoint_and_palette() -> None:
    from pathlib import Path
    from research_hub.dashboard import render

    css = Path(render._STYLE_PATH).read_text(encoding="utf-8")
    assert "@media (max-width: 720px)" in css
    assert ".cmdk" in css
    # desktop tokens untouched: :root still present, dark-mode media intact
    assert ":root" in css
    assert "@media (prefers-color-scheme: dark)" in css


# --- _HOME "Start here": prepend-only + idempotent ----------------------

_SECTIONS = {
    "Start here": "SH",
    "Clusters": "C",
    "Reading queue": "RQ",
    "Recent NotebookLM briefs": "B",
    "Dashboard": "D",
}


def test_home_from_scratch_start_here_is_first() -> None:
    out = ho._build_home_from_scratch(_SECTIONS)
    assert "## Start here" in out
    assert out.index("## Start here") < out.index("## Clusters")


def test_home_refresh_injects_start_here_when_missing() -> None:
    legacy = (
        "---\ntype: home\n---\n\n# Research Hub\n\n"
        "## Clusters\nold-c\n\n## Dashboard\nold-d\n"
    )
    r = ho._refresh_home_sections(legacy, _SECTIONS)
    assert "## Start here" in r
    assert r.index("## Start here") < r.index("## Clusters")
    # existing sections refreshed, not dropped
    assert "old-c" not in r and "## Dashboard" in r


def test_home_refresh_is_idempotent() -> None:
    legacy = "# Research Hub\n\n## Clusters\nc\n\n## Dashboard\nd\n"
    once = ho._refresh_home_sections(legacy, _SECTIONS)
    twice = ho._refresh_home_sections(once, dict(_SECTIONS, **{"Start here": "SH2"}))
    assert twice.count("## Start here") == 1
    assert "SH2" in twice  # in-place refresh works after injection


def test_home_section_regex_recognizes_start_here() -> None:
    assert "Start here" in ho._HOME_SECTION_RE.pattern


def test_home_refresh_no_h1_does_not_corrupt_frontmatter() -> None:
    """P2 regression: a hand-edited _HOME with frontmatter but NO
    `# ` H1 must get Start here AFTER the closing `---`, never
    above it (prepending above frontmatter breaks Obsidian YAML)."""
    legacy = "---\ntype: home\n---\n\n## Clusters\nc\n\n## Dashboard\nd\n"
    r = ho._refresh_home_sections(legacy, _SECTIONS)
    assert r.startswith("---\n"), "frontmatter must remain the first thing"
    fm_end = r.index("---\n", 4) + len("---\n")
    assert r.index("## Start here") > fm_end, "Start here injected above frontmatter"
    assert "## Clusters" in r and "## Dashboard" in r


def test_home_refresh_no_frontmatter_no_h1_prepends_top() -> None:
    legacy = "## Clusters\nc\n\n## Dashboard\nd\n"
    r = ho._refresh_home_sections(legacy, _SECTIONS)
    assert r.startswith("## Start here")
    assert "## Clusters" in r
