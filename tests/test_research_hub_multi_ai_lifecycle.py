"""Lifecycle guards for delegate names embedded in the multi-AI router."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-hub-multi-ai"


def test_router_does_not_depend_on_archived_gemini_delegate():
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(SKILL.rglob("*")) if path.is_file()
    )
    assert "gemini-delegate" not in text
    assert "antigravity-delegate" in text


def test_router_declares_heterogeneous_result_artifacts():
    template = (SKILL / "references" / "multi_ai_plan_template.md").read_text(
        encoding="utf-8"
    )
    assert "result_artifact:" in template
    assert "result_contract:" in template
    assert "codex_result_json_v1" in template
    assert "agy_markdown_v1" in template
    assert "result.json" in template
    assert "agy_result" in template
