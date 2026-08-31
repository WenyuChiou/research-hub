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


def test_image2_cover_is_shared_by_bilingual_readmes_and_hash_locked():
    root = Path(__file__).resolve().parents[1]
    relative = "docs/images/research-hub-cover.png"
    for readme in ("README.md", "README.zh-TW.md"):
        text = (root / readme).read_text(encoding="utf-8")
        assert relative in text[:2500]
        assert "dashboard-walkthrough.gif" in text[:3000]
        assert text.index(relative) < text.index("dashboard-walkthrough.gif")

    english = (root / "README.md").read_text(encoding="utf-8")
    traditional_chinese = (root / "README.zh-TW.md").read_text(encoding="utf-8")
    assert "How research-hub MCP works" in english[:2500]
    assert "ordinary research tools can read or mutate truth stores directly" in english[:2500]
    assert "workflow-managed path" in english[:2500]
    assert "reconcile-required blocker" in english[:2500]
    assert "research-hub MCP 運作邏輯" in traditional_chinese[:2500]
    assert "一般 research tools 可直接讀取或修改 truth stores" in traditional_chinese[:2500]
    assert "workflow-managed path" in traditional_chinese[:2500]
    assert "reconcile-required 阻擋狀態" in traditional_chinese[:2500]

    asset = root / relative
    assert asset.stat().st_size > 1_000_000
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == (
        "f77e8c9b933007132747f8a85c58d8fc7feeeddce30a9453541a3f92326abe91"
    )
