"""Working prose is a local edit, never semantic/scientific acceptance."""
import hashlib
import json

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError, encoded
from research_hub.workspace.service import WorkspaceService


@pytest.fixture
def selected(tmp_path):
    w = Workspace(tmp_path)
    w.create_project(id='study', title='Synthetic', archetype='review', goal='Local test')
    raw = ('# Generated summary observation: local-one\n\n'
           'Evidence level: generated-summary. This is report-derived prose, NOT an original abstract or publisher capture.\n\n'
           '## Supplied generated summary\nDraft wording.\n\nRole candidate (not human acceptance): Test role\n').encode()
    checksum = hashlib.sha256(raw).hexdigest()
    (tmp_path / 'draft.md').write_bytes(raw)
    source = w.add_record('study', kind='source', data={
        'id': 'local-one', 'title': 'Synthetic paper', 'locator': 'https://example.invalid/paper',
        'summary': 'Original saved prose.', 'abstract': 'Publisher abstract.',
        'reading_level': 'abstract-snippet', 'reading_scope': 'abstract-snippet',
        'human_acceptance': 'pending', 'provenance': {'producer': 'synthetic'},
        'source_records': [{'observation_id': 'obs-one', 'source_id': 'local-one', 'work_id': 'work-one',
                            'evidence_level': 'generated-summary', 'status': 'available',
                            'text_path': 'draft.md', 'text_sha256': checksum, 'version_id': None}],
    })
    artifact = w.register_artifact('study', path='draft.md', role='evidence', source_record_id=source['id'])
    return WorkspaceService(tmp_path), source, artifact, raw


def context(service, source, artifact):
    return service.dispatch('project', 'working-summary-context', {
        'project_id': 'study', 'source_record_id': source['id'], 'artifact_id': artifact['id'],
    })['context']


def request(service, source, artifact):
    c = context(service, source, artifact)
    return {'project_id': 'study', 'source_record_id': source['id'], 'artifact_id': artifact['id'],
            'artifact_sha256': artifact['sha256'], 'expected_revision': c['revision'], 'text': 'Edited working prose.'}


def test_context_is_readonly_and_cancel_needs_no_write(selected):
    service, source, artifact, _ = selected
    before = service.workspace.db_path.read_bytes()
    c = context(service, source, artifact)
    assert c['draft_text'] == 'Draft wording.'
    assert c['working_summary'] is None
    assert c['artifact_sha256'] == artifact['sha256']
    assert service.workspace.db_path.read_bytes() == before
    assert service.workspace.records('study') == [source]


def test_save_repeat_and_fresh_service_preserve_originals(selected):
    service, source, artifact, raw = selected
    args = request(service, source, artifact)
    first = service.dispatch('project', 'working-summary-save', args)
    saved = first['record']
    assert first['reused'] is False
    assert saved['id'] == source['id']
    original = {k: v for k, v in saved['data'].items() if k != 'working_summary'}
    assert original == source['data']
    assert saved['data']['working_summary']['text'] == args['text']
    assert saved['data']['working_summary']['artifact_id'] == artifact['id']
    assert saved['data']['working_summary']['artifact_sha256'] == artifact['sha256']
    db_after = service.workspace.db_path.read_bytes()
    repeated = service.dispatch('project', 'working-summary-save', args)
    assert repeated['reused'] is True and repeated['record'] == saved
    assert service.workspace.db_path.read_bytes() == db_after
    fresh = WorkspaceService(service.workspace.root)
    assert fresh.workspace.snapshot('study')['records'] == [saved]
    assert context(fresh, saved, artifact)['working_summary']['text'] == args['text']
    assert (service.workspace.root / 'draft.md').read_bytes() == raw
    assert len(fresh.workspace.artifacts('study')) == 1


def test_stale_source_refuses_without_overwrite(selected):
    service, source, artifact, _ = selected
    args = request(service, source, artifact)
    changed = {**source['data'], 'relevance': 'Concurrent edit'}
    with service.workspace.db(write=True) as db:
        db.execute('UPDATE records SET body=? WHERE id=?', (encoded(changed), source['id']))
    before = service.workspace.db_path.read_bytes()
    with pytest.raises(WorkspaceError, match='changed') as err:
        service.dispatch('project', 'working-summary-save', args)
    assert err.value.code == 'stale_input'
    assert service.workspace.db_path.read_bytes() == before
    assert service.workspace.records('study')[0]['data'] == changed


def test_stale_editor_and_repeat_after_other_edit_are_rejected(selected):
    service, source, artifact, _ = selected
    old = request(service, source, artifact)
    service.dispatch('project', 'working-summary-save', old)
    with pytest.raises(WorkspaceError) as err:
        service.dispatch('project', 'working-summary-save', {**old, 'text': 'Another stale edit'})
    assert err.value.code == 'stale_input'
    current = request(service, source, artifact)
    service.dispatch('project', 'working-summary-save', {**current, 'text': 'New revision'})
    with pytest.raises(WorkspaceError):
        service.dispatch('project', 'working-summary-save', old)
    data = service.workspace.records('study')[0]['data']
    assert data['working_summary']['text'] == 'New revision'
    assert data['working_summary_history'][0]['text'] == 'Edited working prose.'
    assert data['human_acceptance'] == 'pending' and data['identity_status'] == 'unverified'


@pytest.mark.parametrize('change', ['wrong-source', 'wrong-hash', 'file-changed', 'ambiguous-observation'])
def test_changed_or_unbound_artifact_cannot_save(selected, change):
    service, source, artifact, _ = selected
    args = request(service, source, artifact)
    if change == 'wrong-source':
        args['source_record_id'] = 'other'
    elif change == 'wrong-hash':
        args['artifact_sha256'] = '0' * 64
    elif change == 'file-changed':
        (service.workspace.root / 'draft.md').write_text('Changed bytes', encoding='utf-8')
    else:
        data = json.loads(json.dumps(source['data']))
        data['source_records'].append(dict(data['source_records'][0]))
        with service.workspace.db(write=True) as db:
            db.execute('UPDATE records SET body=? WHERE id=?', (encoded(data), source['id']))
    before = service.workspace.db_path.read_bytes()
    with pytest.raises(WorkspaceError):
        service.dispatch('project', 'working-summary-save', args)
    assert service.workspace.db_path.read_bytes() == before
    assert 'working_summary' not in service.workspace.records('study')[0]['data']


@pytest.mark.parametrize('text', ['', '   ', 'x' * 40001, None], ids=['empty', 'whitespace', 'oversized', 'null'])
def test_invalid_text_is_not_saved(selected, text):
    service, source, artifact, _ = selected
    args = request(service, source, artifact)
    before = service.workspace.db_path.read_bytes()
    with pytest.raises(WorkspaceError):
        service.dispatch('project', 'working-summary-save', {**args, 'text': text})
    assert service.workspace.db_path.read_bytes() == before


def test_foreign_registration_identity_rejected_before_file_read(selected, monkeypatch):
    import research_hub.workspace.working_summary as summaries
    service, source, artifact, _ = selected
    altered = {**artifact, 'project_id': 'elsewhere'}
    with service.workspace.db(write=True) as db:
        db.execute('UPDATE artifacts SET body=? WHERE id=?', (encoded(altered), artifact['id']))
    def forbidden(*args, **kwargs):
        pytest.fail('Foreign registration must be rejected before reading any file')
    monkeypatch.setattr(summaries, 'read_selected_text', forbidden)
    with pytest.raises(WorkspaceError) as err:
        context(service, source, artifact)
    assert err.value.code == 'invalid_source'


def test_human_acceptance_gate_is_not_a_working_summary_operation(selected):
    from research_hub.workspace.tasks import TaskService
    service, source, artifact, _ = selected
    service.dispatch('project', 'working-summary-save', request(service, source, artifact))
    with pytest.raises(WorkspaceError) as err:
        TaskService(service.workspace).decide('not-an-approval', outcome='accept', actor='agent',
            rationale='Not human approval', action_hash='0' * 64)
    assert err.value.code == 'human_required'
    assert service.workspace.records('study')[0]['data']['human_acceptance'] == 'pending'


def test_actual_http_context_save_and_csrf_guard(selected):
    import threading
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    from urllib.parse import urlencode
    from research_hub.workspace.server import WorkspaceServer
    service, source, artifact, _ = selected
    server = WorkspaceServer(service.workspace.root, port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}/api/v1/projects/study/working-summary'
    def http(url, data=None, headers=None):
        try:
            response = urlopen(Request(url, data=json.dumps(data).encode() if data is not None else None,
                headers={'Content-Type': 'application/json', **(headers or {})}), timeout=4)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())
    try:
        url = base + '?' + urlencode({'source_record_id': source['id'], 'artifact_id': artifact['id']})
        status, result = http(url)
        assert status == 200 and result['context']['draft_text'] == 'Draft wording.'
        args = {k: v for k, v in request(service, source, artifact).items() if k != 'project_id'}
        before = service.workspace.db_path.read_bytes()
        assert http(base, args)[0] == 403
        assert http(url, headers={'Origin': 'https://example.invalid'})[0] == 403
        assert service.workspace.db_path.read_bytes() == before
        status, saved = http(base, args, {'X-CSRF-Token': server.csrf})
        assert status == 200 and saved['record']['id'] == source['id']
        assert http(url)[1]['context']['working_summary']['text'] == args['text']
        status, body = http(base, {**args, 'human_acceptance': 'accepted'}, {'X-CSRF-Token': server.csrf})
        assert status == 400 and body['code'] == 'invalid_request'
        assert service.workspace.records('study')[0]['data']['human_acceptance'] == 'pending'
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
    assert not worker.is_alive()
