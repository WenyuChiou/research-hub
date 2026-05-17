from __future__ import annotations

from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent
_PIPELINE = _REPO / "src" / "research_hub" / "pipeline.py"


def test_bibliographic_frontmatter_span_has_no_llm_calls() -> None:
    src = _PIPELINE.read_text(encoding="utf-8")
    start = src.index("def _render_obsidian_note(")
    end = src.index("def _load_fit_check_rejections", start)
    span = src[start:end]

    forbidden = [
        "run_claude",
        "run_codex",
        "run_gemini",
        "_invoke_llm",
        "_invoke_llm_cli",
        "subprocess",
        "claude ",
        "codex ",
        "gemini ",
    ]
    present = [symbol for symbol in forbidden if symbol in span]
    assert present == [], (
        "bibliographic frontmatter must stay API-only; found LLM-call symbols "
        f"in _render_obsidian_note span: {present}"
    )

