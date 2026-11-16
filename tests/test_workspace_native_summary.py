"""Synthetic authored summaries: binding checks do not prove entailment."""
import copy
import json
import os

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError, encoded
from research_hub.workspace.native_summary import NativeSummary, SECTIONS, FIELDS, parse, project_records, contains_native, validate
from research_hub.workspace.tasks import TaskService

POSIX = os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and os.open in os.supports_dir_fd


@pytest.fixture
def setup(tmp_path):
    w = Workspace(tmp_path)
    w.create_project(id='p', title='Synthetic', archetype='review', goal='Test')
    record = w.add_record('p', kind='source', data={'id': 'paper', 'title': 'Test', 'locator': 'https://example.invalid', 'reading_scope': 'Selected synthetic text'})
    text = '🙂 Evidence here. ' + 'x' * 47000
    (tmp_path / 'source.txt').write_text(text, encoding='utf-8')
    a = w.register_artifact('p', path='source.txt', role='evidence', source_record_id=record['id'])
    return w, record, a, text


def envelope(setup):
    w, r, a, text = setup
    n = NativeSummary(w)
    c = n.context('p', source_record_id=r['id'], selections=[{'artifact_id': a['id'], 'start': 0, 'end': len(text)}])['context']
    value = {k: c[k] for k in FIELDS if k != 'sections'}
    value['sections'] = {s: [{'text': 'A claim', 'status': 'supported', 'reason': 'Caller assessment only',
                             'evidence': [{'artifact_id': a['id'], 'quote': text[:16], 'start': 0, 'end': 16}]}] for s in SECTIONS}
    return n, value


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
def test_import_replay_read_and_stale(setup):
    w, r, a, text = setup
    n, value = envelope(setup)
    assert n.read('p', source_record_id=r['id'])['status'] == 'missing'
    result = n.import_summary('p', envelope=json.dumps(value))
    assert result['native_summary']['human_acceptance'] == 'pending'
    assert result['native_summary']['semantic_support'] == 'not_assessed'
    assert n.import_summary('p', envelope=json.dumps(value))['reused']
    assert n.read('p', source_record_id=r['id'])['status'] == 'current'
    (w.root / 'source.txt').write_text('changed')
    assert n.read('p', source_record_id=r['id'])['native_summary'] is None
    with pytest.raises(WorkspaceError):
        n.import_summary('p', envelope=json.dumps(value))


@pytest.mark.parametrize('raw', ['{"x":1,"x":2}', '{"x":"\\ud800"}', '{"x":"\\u0000"}', '{"x":NaN}', 'x' * 262145])
def test_strict_json_portable(raw):
    with pytest.raises(WorkspaceError):
        parse(raw)


@pytest.mark.parametrize('code, expected', [
    ('unsupported_capability', 'unavailable'),
    ('source_unavailable', 'unavailable'),
    ('stale_input', 'stale'),
    ('invalid_source', 'stale'),
    ('unsafe_path', 'stale'),
    ('unsupported_storage', 'stale'),
])
def test_read_distinguishes_unavailable_access_from_invalid_binding(setup, monkeypatch, code, expected):
    w, r, _, text = setup
    # Portable binding fixture; this does not claim native platform file access.
    monkeypatch.setattr('research_hub.workspace.native_summary.read_path', lambda *_: text.encode('utf-8'))
    n, value = envelope(setup)
    saved = n.import_summary('p', envelope=json.dumps(value))['native_summary']
    before = w.db_path.read_bytes()

    def unavailable(*_):
        raise WorkspaceError('Private path and source content must not leak', code)

    monkeypatch.setattr('research_hub.workspace.native_summary.read_path', unavailable)
    result = n.read('p', source_record_id=r['id'])
    assert result == {'ok': True, 'status': expected, 'native_summary': None,
                      'human_acceptance': 'pending', 'semantic_support': 'not_assessed'}
    assert w.db_path.read_bytes() == before
    # Changing the read status must not soften context/import failure gates.
    with pytest.raises(WorkspaceError) as error:
        n.import_summary('p', envelope=json.dumps(value))
    assert error.value.code == code
    assert w.db_path.read_bytes() == before
    monkeypatch.setattr('research_hub.workspace.native_summary.read_path', lambda *_: text.encode('utf-8'))
    restored = n.read('p', source_record_id=r['id'])
    assert restored['status'] == 'current' and restored['native_summary'] == saved
    assert w.db_path.read_bytes() == before


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
def test_missing_file_is_unavailable_but_changed_bytes_are_stale(setup):
    w, r, _, _ = setup
    n, value = envelope(setup)
    n.import_summary('p', envelope=json.dumps(value))
    before = w.db_path.read_bytes()
    original, moved = w.root / 'source.txt', w.root / 'temporarily-moved.txt'
    original.rename(moved)
    unavailable = n.read('p', source_record_id=r['id'])
    assert unavailable['status'] == 'unavailable' and unavailable['native_summary'] is None
    assert w.db_path.read_bytes() == before
    moved.rename(original)
    assert n.read('p', source_record_id=r['id'])['status'] == 'current'
    original.write_text('Changed evidence', encoding='utf-8')
    stale = n.read('p', source_record_id=r['id'])
    assert stale['status'] == 'stale' and stale['native_summary'] is None
    assert w.db_path.read_bytes() == before


def test_task_projection_and_legacy_gate_portable(tmp_path):
    rows = [{'id': 'r', 'kind': 'source', 'data': {'native_summary': {'secret': 1}, 'native_summary_history': [], 'working_summary': 'keep', 'title': 'keep'}}]
    assert contains_native(rows)
    projected = project_records(rows)
    assert projected[0]['data'] == {'working_summary': 'keep', 'title': 'keep'}
    assert rows[0]['data']['native_summary'] == {'secret': 1}
    t = TaskService(Workspace(tmp_path))
    refs, reasons = t._input_assessment({'project_id': 'p', 'request': {'records': rows}})
    assert refs == [] and reasons[0]['code'] == 'native-summary-outside-task-scope'
    with pytest.raises(WorkspaceError):
        t._check_inputs({'request': {'records': rows}})


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
@pytest.mark.parametrize('change', ['quote', 'offset', 'owner', 'revision', 'scope', 'field', 'status', 'project'])
def test_import_rejects_without_write(setup, change):
    w, r, a, text = setup
    n, value = envelope(setup)
    item = value['sections']['why'][0]
    if change == 'quote': item['evidence'][0]['quote'] = 'wrong'
    if change == 'offset': item['evidence'][0]['end'] += 1
    if change == 'owner': value['source_record_id'] = 'wrong'
    if change == 'revision': value['expected_revision'] = '0' * 64
    if change == 'scope': value['reading_scope'] = 'Full paper'
    if change == 'field': value['accepted'] = True
    if change == 'status': item['status'] = 'verified'
    if change == 'project': value['project_id'] = 'wrong'
    before = w.records('p')
    with pytest.raises(WorkspaceError): n.import_summary('p', envelope=json.dumps(value))
    assert w.records('p') == before


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
def test_history_cas_limit_and_rollback(setup):
    w, r, a, text = setup
    n, original = envelope(setup)
    n.import_summary('p', envelope=json.dumps(original))
    for i in range(20):
        n, value = envelope(setup)
        value['sections']['why'][0]['text'] = str(i)
        n.import_summary('p', envelope=json.dumps(value))
    assert len(w.records('p')[0]['data']['native_summary_history']) == 20
    n, value = envelope(setup)
    value['sections']['why'][0]['text'] = 'overflow'
    before = w.records('p')
    with pytest.raises(WorkspaceError, match='history is full'):
        n.import_summary('p', envelope=json.dumps(value))
    assert w.records('p') == before
    with pytest.raises(WorkspaceError): n.import_summary('p', envelope=json.dumps(original))


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
def test_safe_paths_and_symlinks(setup, tmp_path):
    from research_hub.workspace.native_summary import read_path
    w, *_ = setup
    (tmp_path / 'link.txt').symlink_to(tmp_path / 'source.txt')
    for path in ('../source.txt', '/etc/passwd', 'link.txt', './source.txt', 'a\\b', 'a//b'):
        with pytest.raises(WorkspaceError): read_path(w, path, 50000)


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
def test_fresh_context_required_and_no_unrelated_scan(setup, monkeypatch):
    w, r, a, text = setup
    monkeypatch.setattr(w, 'artifacts', lambda *_: pytest.fail('broad artifact scan'))
    monkeypatch.setattr(w, 'records', lambda *_: pytest.fail('broad source scan'))
    n, value = envelope(setup)
    n.import_summary('p', envelope=json.dumps(value))
    n, newer = envelope(setup)
    assert newer['expected_revision'] != value['expected_revision']
    assert newer['source_revision'] == value['source_revision']
    newer['sections']['why'][0]['text'] = 'Updated'
    n.import_summary('p', envelope=json.dumps(newer))
    assert n.read('p', source_record_id=r['id'])['status'] == 'current'


def test_owned_selection_rejected_before_file_access_portable(setup, monkeypatch):
    from research_hub.workspace.native_summary import _selection
    w, r, a, _ = setup
    monkeypatch.setattr('research_hub.workspace.native_summary.read_path', lambda *_: pytest.fail('must not read'))
    with w.db() as db, pytest.raises(WorkspaceError, match='owned'):
        _selection(w, db, 'p', 'another-source', [{'artifact_id': a['id'], 'start': 0, 'end': 1}])


def test_schema_and_quote_validation_portable(setup, monkeypatch):
    from research_hub.workspace.native_summary import _base, _bound
    w, r, a, text = setup
    selection = {'artifact_id': a['id'], 'start': 0, 'end': len(text), 'sha256': a['sha256'], 'text_sha256': a['sha256']}
    value = {'schema': 'native-source-summary-v1', 'project_id': 'p', 'source_record_id': r['id'],
             'source': {'title': 'Test', 'locator': 'https://example.invalid'},
             'reading_scope': r['data']['reading_scope'], 'source_revision': _base(r), 'expected_revision': _base(r),
             'selections': [selection], 'sections': {s: [{'text': 'Unknown', 'status': 'unknown', 'reason': 'Not assessed', 'evidence': []}] for s in SECTIONS}}
    validate(value)
    monkeypatch.setattr('research_hub.workspace.native_summary._selection', lambda *args: ([selection], {a['id']: text}))
    item = value['sections']['why'][0]
    item['evidence'] = [{'artifact_id': a['id'], 'quote': text[:1], 'start': 0, 'end': 1}]
    _bound(w, None, r, value)
    item['evidence'][0]['end'] = 2
    with pytest.raises(WorkspaceError, match='Unicode'):
        _bound(w, None, r, value)
    item['evidence'] = []
    item['status'] = 'supported'
    with pytest.raises(WorkspaceError): validate(value)


def test_native_changes_do_not_change_generic_task_freshness(setup):
    w, r, a, _ = setup
    service = TaskService(w)
    task = service.create('p', operation='review')
    data = copy.deepcopy(r['data'])
    data.update(native_summary={'private': 'not an input'}, native_summary_history=[{'private': 'old'}])
    with w.db(write=True) as db:
        db.execute('UPDATE records SET body=? WHERE id=?', (encoded(data), r['id']))
    assert service.get(task['id'])['freshness']['status'] == 'current'
    newer = service.create('p', operation='review')
    assert not contains_native(newer['request']['records'])
    assert not contains_native(service.handoff(newer['id'])['packet']['records'])
    data['title'] = 'Changed scientific identity'
    with w.db(write=True) as db:
        db.execute('UPDATE records SET body=? WHERE id=?', (encoded(data), r['id']))
    assert service.get(task['id'])['freshness']['status'] == 'stale'


@pytest.mark.parametrize('operation', ['handoff', 'claim', 'import'])
def test_serialized_native_task_blocks_execution_without_rewrite(setup, operation):
    from research_hub.workspace.core import digest
    w, r, a, _ = setup
    service = TaskService(w)
    task = service.create('p', operation='review', mode='connected' if operation == 'claim' else 'handoff')
    task['request']['records'][0]['data']['native_summary_history'] = [{'text': 'private'}]
    with w.db(write=True) as db:
        db.execute('UPDATE tasks SET body=? WHERE id=?', (encoded(task), task['id']))
    request_before = copy.deepcopy(task['request'])
    with pytest.raises(WorkspaceError, match='native summary'):
        if operation == 'import':
            service.import_result(task['id'], prose='No leakage', status='completed', input_hash=digest(task['request']))
        else:
            getattr(service, operation)(task['id'])
    assert service.get(task['id'])['request'] == request_before


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
def test_guarded_http_reader_has_no_import_route(setup):
    import threading
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    from research_hub.workspace.server import WorkspaceServer
    w, r, *_ = setup
    n, value = envelope(setup)
    n.import_summary('p', envelope=json.dumps(value))
    server = WorkspaceServer(w.root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/api/v1/projects/p/native-summary'
    try:
        with urlopen(base + '?source_record_id=' + r['id']) as response:
            body = json.load(response)
        assert body['status'] == 'current'
        assert 'selected_text' not in body['native_summary']
        for query in ('', '?source_record_id=x&source_record_id=y', '?source_record_id=x&path=source.txt'):
            with pytest.raises(HTTPError) as error:
                urlopen(base + query)
            assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '?source_record_id=' + r['id'], headers={'Origin': 'https://example.invalid'}))
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base, data=b'{}', headers={'X-CSRF-Token': server.csrf, 'Content-Type': 'application/json'}))
        assert error.value.code in (400, 404)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
def test_cli_native_operations(setup, capsys):
    import argparse
    from research_hub.workspace.cli import add_workspace_parsers, dispatch_workspace
    w, r, a, text = setup
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest='command'))
    common = ['--root', str(w.root), '--project', 'p', '--json']
    args = parser.parse_args(['project', 'native-summary-context', *common, '--source-record-id', r['id'], '--selections', json.dumps([{'artifact_id': a['id'], 'start': 0, 'end': len(text)}])])
    assert dispatch_workspace(args) == 0
    assert json.loads(capsys.readouterr().out)['context']['source_record_id'] == r['id']
    n, value = envelope(setup)
    (w.root / 'authored.json').write_text(json.dumps(value), encoding='utf-8')
    args = parser.parse_args(['project', 'native-summary-import', *common, '--path', 'authored.json'])
    assert dispatch_workspace(args) == 0
    assert json.loads(capsys.readouterr().out)['reused'] is False
    args = parser.parse_args(['project', 'native-summary-read', *common, '--source-record-id', r['id']])
    assert dispatch_workspace(args) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'current'


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
@pytest.mark.parametrize('missing', ['saved_at', 'human_acceptance', 'semantic_support', 'all'])
def test_persisted_unsaved_envelope_never_reads_current(setup, missing):
    w, r, *_ = setup
    n, value = envelope(setup)
    saved = n.import_summary('p', envelope=json.dumps(value))['native_summary']
    for key in (('saved_at', 'human_acceptance', 'semantic_support') if missing == 'all' else (missing,)):
        saved.pop(key)
    data = {**r['data'], 'native_summary': saved}
    with w.db(write=True) as db:
        db.execute('UPDATE records SET body=? WHERE id=?', (encoded(data), r['id']))
    result = n.read('p', source_record_id=r['id'])
    assert result['status'] == 'stale'
    assert result['native_summary'] is None


@pytest.mark.parametrize('stored', [None, {'private': 'invalid'}, 'malformed'])
def test_snapshot_only_presence_flag_no_unvalidated_prose(setup, stored):
    w, r, *_ = setup
    assert w.snapshot('p')['records'] == [r]
    data = {**r['data'], 'native_summary': stored, 'native_summary_history': [{'secret': 'old'}]}
    with w.db(write=True) as db:
        db.execute('UPDATE records SET body=? WHERE id=?', (encoded(data), r['id']))
    projected = w.snapshot('p')['records'][0]
    assert projected == {**r, 'native_summary_available': True}
    assert w.records('p')[0]['data'] == data
    assert 'native_summary_available' not in TaskService(w).create('p', operation='review')['request']['records'][0]


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX file reads')
@pytest.mark.parametrize('existing', [False, True])
def test_saved_metadata_limit_rejects_atomically_and_preserves_usability(setup, existing):
    from research_hub.workspace.native_summary import MAX_ENVELOPE
    w, r, *_ = setup
    n, first = envelope(setup)
    if existing:
        n.import_summary('p', envelope=encoded(first))
        n, second = envelope(setup)
        second['sections']['why'][0]['text'] = 'Second valid version'
        n.import_summary('p', envelope=encoded(second))
    n, oversized = envelope(setup)
    oversized['sections'] = {s: [{'text': 'x' * 9000, 'status': 'unknown',
                                  'reason': 'y' * 9000, 'evidence': []} for _ in range(2)]
                               for s in SECTIONS}
    remaining = MAX_ENVELOPE - 1 - len(encoded(oversized).encode('utf-8'))
    assert remaining > 0
    for items in oversized['sections'].values():
        for item in items:
            extra = min(remaining, 12000 - len(item['text']))
            item['text'] += 'z' * extra
            remaining -= extra
    assert remaining == 0
    raw = encoded(oversized)
    assert len(raw.encode('utf-8')) == MAX_ENVELOPE - 1
    validate(oversized)  # Authored input itself satisfies the complete schema.
    records_before, bytes_before = w.records('p'), w.db_path.read_bytes()
    with pytest.raises(WorkspaceError, match='envelope limit'):
        n.import_summary('p', envelope=raw)
    assert w.records('p') == records_before
    assert w.db_path.read_bytes() == bytes_before
    assert n.read('p', source_record_id=r['id'])['status'] == ('current' if existing else 'missing')
    if existing:
        assert n.import_summary('p', envelope=encoded(second))['reused']
    n, valid = envelope(setup)
    valid['sections']['why'][0]['text'] = 'Subsequent valid update'
    n.import_summary('p', envelope=encoded(valid))
    assert n.read('p', source_record_id=r['id'])['status'] == 'current'
