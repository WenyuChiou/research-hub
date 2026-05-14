from __future__ import annotations

from pathlib import Path


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
