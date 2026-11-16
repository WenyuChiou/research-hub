"""Installed entry routing preserves the existing offline audit boundary."""
import builtins
import csv
import io
import json

import pytest

from research_hub import cli_entry
from research_hub.workspace import batch_audit
from tests.test_workspace_batch_audit import manifest, snapshot
from tests.test_workspace_task_summary import candidate


def test_fast_entry_excludes_provider_cli(monkeypatch, tmp_path, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name != 'research_hub.cli', 'Offline audit imported provider CLI'
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    monkeypatch.setattr('research_hub.workspace.service.WorkspaceService.__init__',
                        lambda *a, **k: pytest.fail('Service initialization'))
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps({'version': 1, 'entries': [
        {'article_id': 'unavailable', 'declared_status': 'unknown',
         'reason_codes': ['source_unavailable']}]}))
    assert cli_entry.main(['task', 'audit-batch', str(path)]) == 1
    assert json.loads(capsys.readouterr().out)['counts']['unprepared'] == 1


@pytest.mark.parametrize('argv,code', [(['--help'], 0), ([], 2),
    (['manifest.json', '--format', 'xml'], 2), (['manifest.json', '--root', 'x'], 2),
    (['manifest.json', '--audit-output', 'x'], 2)])
def test_fast_parser_without_provider_cli(monkeypatch, capsys, argv, code):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name != 'research_hub.cli'
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    with pytest.raises(SystemExit) as error:
        cli_entry.main(['task', 'audit-batch', *argv])
    assert error.value.code == code
    if code == 0:
        assert '--format {json,csv}' in capsys.readouterr().out


@pytest.mark.parametrize('format', ['json', 'csv'])
@pytest.mark.parametrize('incomplete', [False, True])
def test_all_entrypoints_identical_and_readonly(candidate, tmp_path, capsys, monkeypatch, format, incomplete):
    from research_hub import cli
    root = candidate[0].workspace.root
    value = manifest(candidate)
    if incomplete:
        value['entries'].append({'article_id': 'unavailable', 'declared_status': 'unknown',
                                 'reason_codes': ['source_unavailable']})
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(value))
    before = snapshot(root)
    monkeypatch.setattr(cli, 'require_config', lambda: pytest.fail('Config initialization'))
    monkeypatch.setattr('research_hub.workspace.service.WorkspaceService.__init__',
                        lambda *a, **k: pytest.fail('Service initialization'))
    outputs = []
    for entry, prefix in [(batch_audit.main, []), (cli.main, ['task', 'audit-batch']),
                          (cli_entry.main, ['task', 'audit-batch'])]:
        assert entry([*prefix, str(path), '--format', format]) == int(incomplete)
        outputs.append(capsys.readouterr().out)
    assert outputs[0] == outputs[1] == outputs[2]
    assert snapshot(root) == before
    row = (json.loads(outputs[0])['entries'][0] if format == 'json'
           else next(csv.DictReader(io.StringIO(outputs[0]))))
    assert row['status'] == 'binding_pass'
    assert row['human_review'] == 'candidate_pending'
    assert row['scientific_acceptance'] == 'not_assessed'


@pytest.mark.parametrize('failure', ['malformed', 'existing', 'inside', 'missing_parent'])
def test_errors_preserve_code_and_files(candidate, tmp_path, capsys, failure):
    from research_hub import cli
    root = candidate[0].workspace.root
    path = tmp_path / 'manifest.json'
    path.write_text('private malformed data' if failure == 'malformed' else json.dumps(manifest(candidate)))
    output = {'existing': path, 'inside': root / 'report.json',
              'missing_parent': tmp_path / 'absent' / 'report.json'}.get(failure)
    before = snapshot(tmp_path)
    for entry, prefix in [(batch_audit.main, []), (cli.main, ['task', 'audit-batch']),
                          (cli_entry.main, ['task', 'audit-batch'])]:
        argv = [*prefix, str(path)] + (['--output', str(output)] if output else [])
        assert entry(argv) == 2
        captured = capsys.readouterr()
        assert captured.out == ''
        assert captured.err == 'Batch audit failed: invalid manifest or report destination; no workspace changes made.\n'
    assert snapshot(tmp_path) == before


def test_task_help_discovers_command(capsys):
    from research_hub import cli
    with pytest.raises(SystemExit) as error:
        cli.main(['task', '--help'])
    assert error.value.code == 0
    assert 'audit-batch' in capsys.readouterr().out


@pytest.mark.parametrize('format', ['json', 'csv'])
def test_new_output_file_matches_module(candidate, tmp_path, capsys, format):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest(candidate)))
    before = snapshot(candidate[0].workspace.root)
    assert batch_audit.main([str(path), '--format', format]) == 0
    expected = capsys.readouterr().out
    output = tmp_path.parent / (tmp_path.name + '-report.' + format)
    assert cli_entry.main(['task', 'audit-batch', str(path), '--format', format,
                           '--output', str(output)]) == 0
    assert capsys.readouterr().out == ''
    # CSV stdout capture retains CRLF; read without universal newline conversion.
    with output.open(newline='', encoding='utf-8') as stream:
        assert stream.read() == expected
    assert snapshot(candidate[0].workspace.root) == before


def test_implicit_argv_fast_entry(monkeypatch, tmp_path, capsys):
    import sys
    path = tmp_path / 'bad.json'
    path.write_text('{}')
    monkeypatch.setattr(sys, 'argv', ['research-hub', 'task', 'audit-batch', str(path)])
    assert cli_entry.main() == 2
    assert 'Batch audit failed:' in capsys.readouterr().err


def test_fresh_process_has_no_provider_config_or_service_startup(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps({'version': 1, 'entries': [
        {'article_id': 'unavailable', 'declared_status': 'unknown',
         'reason_codes': ['source_unavailable']}]}))
    script = '''
import builtins
import socket
import sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    assert name not in {'research_hub.cli', 'research_hub.config'}, name
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
socket.socket = lambda *a, **k: (_ for _ in ()).throw(AssertionError('Network'))
from research_hub.workspace.service import WorkspaceService
WorkspaceService.__init__ = lambda *a, **k: (_ for _ in ()).throw(AssertionError('Service'))
from research_hub.cli_entry import main
raise SystemExit(main(sys.argv[1:]))
'''
    env = dict(os.environ, HOME=str(tmp_path), RESEARCH_HUB_CONFIG=str(tmp_path / 'no-config.json'),
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', script, 'task', 'audit-batch', str(path)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1, result.stderr
    assert result.stderr == ''
    assert json.loads(result.stdout)['counts']['unprepared'] == 1
