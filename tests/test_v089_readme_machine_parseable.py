from __future__ import annotations

from pathlib import Path
import hashlib


def _readme_text() -> str:
    return (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_readme_env_var_table_is_machine_parseable_and_version_drift_free():
    text = _readme_text()
    start_marker = "<!-- env-vars-table-start -->"
    end_marker = "<!-- env-vars-table-end -->"

    assert start_marker in text
    assert end_marker in text

    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker)
    table_lines = [line.strip() for line in text[start:end].splitlines() if line.strip()]

    assert table_lines[0] == "| Name | Required | Purpose |"
    assert table_lines[1] == "|---|---|---|"

    rows = [line for line in table_lines[2:] if line.startswith("|")]
    assert len(rows) >= 5
    assert any("`ZOTERO_API_KEY`" in row for row in rows)

    assert "v0.81.0" not in text
    assert "v0.68.3" not in text


def test_researcher_first_visuals_and_preview_install_are_bilingual():
    root = Path(__file__).resolve().parents[1]
    for readme, locale in (("README.md", "en"), ("README.zh-TW.md", "zh-TW")):
        text = (root / readme).read_text(encoding="utf-8")
        lifecycle = f"docs/images/workspace-lifecycle.{locale}.png"
        screenshot = f"docs/images/workspace-ui.{locale}.png"
        writing = f"docs/images/workspace-writing.{locale}.png"
        assert lifecycle in text[:2500]
        assert text.index(lifecycle) < text.index(screenshot) < text.index(writing)
        assert "git clone -b codex/researcher-workspace" in text
        assert "research-hub project demo --root ./workspace-demo --json" in text
        assert "docs/workspace-architecture.md" in text
        for relative in (lifecycle, screenshot, writing):
            assert (root / relative).is_file()


def test_legacy_cover_remains_available_and_unchanged():
    root = Path(__file__).resolve().parents[1]
    asset = root / "docs/images/research-hub-cover.png"
    assert asset.stat().st_size > 1_000_000
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == (
        "f77e8c9b933007132747f8a85c58d8fc7feeeddce30a9453541a3f92326abe91"
    )
