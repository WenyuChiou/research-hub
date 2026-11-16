"""Instruction routing consistency, not live model or scientific acceptance."""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('tree', ['skills', 'src/research_hub/skills_data'])
def test_cited_paper_route_does_not_enter_manuscript_memory(tree):
    text = (ROOT / tree / 'literature-triage-matrix/SKILL.md').read_text(encoding='utf-8')
    exclusions = text.split('Not for:', 1)[1].split('## Evidence contract', 1)[0]
    assert 'Single cited-paper deep dive — use `paper-summarize`' in exclusions
    assert "`paper-memory-builder` for the researcher's own manuscript claims and figures" in exclusions
    assert 'Single-paper deep dive — use `paper-memory-builder`' not in exclusions
    assert 'per-cited-paper Key Findings → `paper-summarize`' in text
