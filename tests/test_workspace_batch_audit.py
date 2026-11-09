"""Synthetic offline auditing; candidate fixture is not live scientific evidence."""
import json
from pathlib import Path
import sqlite3

import pytest

from research_hub.workspace.batch_audit import audit, main, _ReadOnlyWorkspace
from research_hub.workspace.core import encoded, digest, WorkspaceError
from tests.test_workspace_task_summary import candidate, replace_task, reseal


def manifest(candidate):
    service, source, artifact, task = candidate
    return {"version": 1, "entries": [{
        "article_id": "B2-07", "workspace_root": str(service.workspace.root),
        "project_id": "study", "source_record_id": source["id"], "task_id": task["id"],
        "expected_source_sha256": artifact["sha256"],
        "expected_selected_sha256": task["request"]["research_draft"]["source_pack"]["text_sha256"],
    }]}


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def result(candidate):
    return audit(manifest(candidate))["entries"][0]


def test_pending_pass_readonly_repeatable(candidate):
    root = candidate[0].workspace.root
    before = snapshot(root)
    first = result(candidate)
    assert first == result(candidate)
    assert first['status'] == 'binding_pass'
    assert first['source_bound_statements'] == 1
    assert first['candidate_files_checked'] == 5
    assert first['selected_codepoints'] == len((root / 'source.txt').read_text())
    assert first['recorded_execution_mode'] == 'handoff'
    assert first['human_review'] == 'candidate_pending'
    assert first['scientific_acceptance'] == 'not_assessed'
    assert snapshot(root) == before
    assert str(root) not in json.dumps(first)
    assert 'blue water' not in json.dumps(first)


@pytest.mark.parametrize('change', ['source', 'candidate', 'offset', 'hash', 'cross_project',
                                    'cross_source', 'malformed', 'accepted', 'path_escape', 'source_escape', 'symlink'])
def test_fail_closed(candidate, change, tmp_path):
    service, source, _, task = candidate
    value = manifest(candidate)
    entry = value['entries'][0]
    root = service.workspace.root
    if change == 'source':
        (root / 'source.txt').write_text('changed private source')
    elif change == 'candidate':
        (root / task['result']['artifacts'][0]['path']).write_text('changed candidate')
    elif change == 'hash':
        entry['expected_selected_sha256'] = '0' * 64
    elif change == 'cross_project':
        entry['project_id'] = 'other'
    elif change == 'cross_source':
        entry['source_record_id'] = 'other'
    elif change == 'malformed':
        with service.workspace.db(write=True) as db:
            db.execute('UPDATE tasks SET body=? WHERE id=?', ('[]', task['id']))
    elif change == 'accepted':
        task['status'] = 'completed'
        task['result']['semantic_acceptance'] = 'accept'
        reseal(task)
        replace_task(candidate, task)
    elif change == 'offset':
        task['request']['research_draft']['source_selection']['start'] = 1
        reseal(task)
        replace_task(candidate, task)
    elif change == 'path_escape':
        task['result']['artifacts'][0]['path'] = '../private.txt'
        reseal(task)
        replace_task(candidate, task)
    elif change == 'source_escape':
        artifact = candidate[2]
        artifact['path'] = '../private.txt'
        with service.workspace.db(write=True) as db:
            db.execute('UPDATE artifacts SET body=? WHERE id=?', (encoded(artifact), artifact['id']))
    elif change == 'symlink':
        path = root / task['result']['artifacts'][0]['path']
        path.unlink()
        path.symlink_to(root / 'source.txt')
    before = snapshot(root)
    row = audit(value)['entries'][0]
    assert row['status'] in {'blocked', 'missing'}
    assert row['human_review'] == 'unknown'
    assert row['scientific_acceptance'] == 'not_assessed'
    assert snapshot(root) == before
    assert str(root) not in json.dumps(row)
    assert 'private' not in json.dumps(row)


def test_missing_database_not_initialized(candidate, tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    value = manifest(candidate)
    value['entries'][0]['workspace_root'] = str(empty)
    assert audit(value)['entries'][0]['status'] == 'missing'
    assert list(empty.iterdir()) == []


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_database_sidecars_refused(candidate, suffix):
    db = candidate[0].workspace.db_path
    Path(str(db) + suffix).write_bytes(b'')
    before = snapshot(candidate[0].workspace.root)
    assert result(candidate)['diagnostic'] == 'active_database'
    assert snapshot(candidate[0].workspace.root) == before


def test_duplicate_entries_fail_before_read(candidate, monkeypatch):
    value = manifest(candidate)
    value['entries'] *= 2
    monkeypatch.setattr(_ReadOnlyWorkspace, '__init__', lambda *a: pytest.fail('Unexpected read'))
    with pytest.raises(ValueError):
        audit(value)


def test_placeholders_preserve_denominator(candidate):
    value = manifest(candidate)
    value['entries'] += [{'article_id': f'B2-{i:02}', 'declared_status': 'unknown',
                          'reason_codes': ['source_unavailable']} for i in range(20, 39)]
    report = audit(value)
    assert len(report['entries']) == 20
    assert report['counts']['binding_pass'] == 1
    assert report['counts']['unprepared'] == 19
    assert report['verified_totals']['source_bound_statements'] == 1
    assert report['verified_totals']['candidate_files_checked'] == 5
    assert report['entries'][1]['source_bound_statements'] is None
    assert report['entries'][1]['declared_source_status'] == 'unknown'
    assert report['entries'][1]['diagnostic'] == 'not_audited'


def test_cli_csv_and_output_boundary(candidate, tmp_path, capsys):
    # Manifest and report sit outside the selected nested workspace root.
    value = manifest(candidate)
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(value))
    assert main([str(path), '--format', 'csv']) == 0
    assert 'binding_pass' in capsys.readouterr().out
    output = tmp_path / 'report.json'
    assert main([str(path), '--output', str(output)]) == 2
    assert not output.exists()
    assert str(tmp_path) not in capsys.readouterr().err


def test_cli_invalid_json_redacted(tmp_path, capsys):
    path = tmp_path / 'private-manifest.json'
    path.write_text('{"version":1,"version":1,"entries":[]}')
    assert main([str(path)]) == 2
    assert str(tmp_path) not in capsys.readouterr().err


def test_readonly_guard(candidate):
    workspace = _ReadOnlyWorkspace(candidate[0].workspace.root)
    with pytest.raises(WorkspaceError):
        with workspace.db(write=True):
            pass
    with workspace.db() as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute('CREATE TABLE forbidden (id TEXT)')


def test_symlink_root_rejected(candidate, tmp_path):
    link = tmp_path / 'linked-root'
    link.symlink_to(candidate[0].workspace.root, target_is_directory=True)
    value = manifest(candidate)
    value['entries'][0]['workspace_root'] = str(link)
    assert audit(value)['entries'][0]['diagnostic'] == 'unsafe_path'


def test_tampered_quote_offsets_rejected_even_if_rehashed(candidate):
    import hashlib
    service, _, _, task = candidate
    item = next(i for i in task['result']['artifacts'] if i['path'].endswith('/draft-response.json'))
    path = service.workspace.root / item['path']
    response = json.loads(path.read_text())
    response['summary'][0]['start'] += 1
    raw = encoded(response).encode()
    path.write_bytes(raw)
    item['sha256'] = hashlib.sha256(raw).hexdigest()
    reseal(task)
    replace_task(candidate, task)
    assert result(candidate)['status'] == 'blocked'


def test_database_changes_detected(candidate, monkeypatch):
    import research_hub.workspace.batch_audit as module
    original = module.selection
    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        task = candidate[3]
        task['extra'] = 'changed'
        replace_task(candidate, task)
        return value
    monkeypatch.setattr(module, 'selection', changed)
    assert result(candidate)['diagnostic'] == 'changed_database'


def test_cli_new_external_report_and_no_overwrite(candidate, tmp_path, capsys):
    # The pytest temp root is isolated; create a sibling report outside the
    # selected workspace instead of requiring writes inside that workspace.
    output = tmp_path.parent / (tmp_path.name + '-audit.json')
    path = tmp_path / 'input.json'
    path.write_text(json.dumps(manifest(candidate)))
    assert main([str(path), '--output', str(output)]) == 0
    raw = output.read_bytes()
    assert json.loads(raw)['counts']['binding_pass'] == 1
    assert main([str(path), '--output', str(output)]) == 2
    assert output.read_bytes() == raw
    assert str(tmp_path) not in capsys.readouterr().err


def test_cli_placeholder_exit_one(tmp_path, capsys):
    path = tmp_path / 'input.json'
    path.write_text(json.dumps({'version': 1, 'entries': [{'article_id': 'B2-01',
                          'declared_status': 'blocked', 'reason_codes': ['source_unavailable']}]}))
    assert main([str(path)]) == 1
    assert json.loads(capsys.readouterr().out)['counts']['unprepared'] == 1
