"""Offline guidance/CLI contract, not host execution or research acceptance."""
from pathlib import Path
import os
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_selected_hub_entry_resolves_and_preserves_scope():
    for base in (ROOT / 'skills', ROOT / 'src/research_hub/skills_data'):
        entry = (base / 'paper-summarize/SKILL.md').read_text(encoding='utf-8')
        guide = (base / 'paper-summarize/references/fulltext-summary.md').read_text(encoding='utf-8')
        assert 'references/fulltext-summary.md#optional-selected-hub-handoff' in entry
        section = ' '.join(guide.split('## Optional selected Hub handoff', 1)[1].split())
        for clause in ('authorized the relevant local writes',
                       'do not silently install or upgrade',
                       'The agent prepares the seven-section authored envelope, not the researcher',
                       'human_acceptance: pending', 'semantic_support: not_assessed',
                       'without enabling BLOB storage or a path fallback'):
            assert clause in section


@pytest.mark.parametrize('operation', ['context', 'import', 'read', 'export'])
def test_documented_selected_hub_commands_exist_without_opening_workspace(operation, tmp_path):
    import research_hub
    env = {**os.environ, 'PYTHONPATH': str(Path(research_hub.__file__).resolve().parent.parent)}
    before = list(tmp_path.iterdir())
    result = subprocess.run([sys.executable, '-m', 'research_hub', 'project',
                             'native-summary-' + operation, '--help'],
                            cwd=tmp_path, env=env, capture_output=True, text=True,
                            encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stderr
    assert '--root' in result.stdout and '--project' in result.stdout
    assert list(tmp_path.iterdir()) == before
