"""Synthetic real CLI subprocesses, not native AI or browser acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from tests.test_workspace_native_summary import setup, envelope, POSIX

@pytest.mark.skipif(not POSIX, reason='Pinned POSIX source-file reads')
def test_cli_import_survives_process_exit_and_source_recovery(setup, tmp_path):
    w, record, artifact, original_text = setup
    _, value = envelope(setup)
    (w.root / 'authored.json').write_text(json.dumps(value), encoding='utf-8')
    import research_hub
    env = {**os.environ, 'PYTHONPATH': str(Path(research_hub.__file__).resolve().parent.parent)}
    child_cwd = tmp_path / 'outside-checkout'
    child_cwd.mkdir()
    def cli(operation, *extra):
        result = subprocess.run([sys.executable, '-m', 'research_hub', 'project', operation,
            '--root', str(w.root), '--project', 'p', *extra], cwd=child_cwd, env=env,
            text=True, encoding='utf-8', capture_output=True, timeout=15)
        return result.returncode, json.loads(result.stdout)
    code, imported = cli('native-summary-import', '--path', 'authored.json')
    assert code == 0 and imported['ok']
    saved = imported['native_summary']
    before = w.db_path.read_bytes()
    source_args = ('--source-record-id', record['id'])
    code, read = cli('native-summary-read', *source_args)
    assert code == 0 and read['native_summary'] == saved
    code, exported = cli('native-summary-export', *source_args, '--json')
    assert code == 0 and exported['markdown']
    assert exported['human_acceptance'] == 'pending'
    assert exported['semantic_support'] == 'not_assessed'
    assert w.db_path.read_bytes() == before
    (w.root / 'source.txt').write_text('Changed synthetic evidence', encoding='utf-8')
    code, stale = cli('native-summary-export', *source_args, '--json')
    assert code == 1 and stale['status'] == 'stale' and stale['markdown'] is None
    assert w.db_path.read_bytes() == before
    (w.root / 'source.txt').write_text(original_text, encoding='utf-8')
    code, restored = cli('native-summary-export', *source_args, '--json')
    assert code == 0 and restored['markdown'] == exported['markdown']
    assert w.db_path.read_bytes() == before
