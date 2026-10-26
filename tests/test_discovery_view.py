"""Read-only Stage1 projection, synthetic bytes only; no native execution proof."""
import json

import pytest

from tests.test_discovery_observations import setup, profile
from research_hub.workspace.discovery import save_profile
from research_hub.workspace.service import WorkspaceService
from research_hub.workspace.core import WorkspaceError


def test_projection_exact_artifact_scope_and_no_raw_capture(setup):
    w, path = setup
    saved = save_profile(w, 'p', path.name)
    service = WorkspaceService(w.root)
    result = service.dispatch('project', 'discovery-view', {
        'project_id': 'p', 'artifact_id': saved['artifact']['id']})
    assert result['ok']
    assert result['discovery']['brief'] == profile()['brief']
    assert result['discovery']['sources'][0]['id'] == 's1'
    assert 'material' not in result['discovery']['sources'][0]
    assert result['report']['unbound_source_material'] == ['s1']
    assert result['report']['execution_verified'] is False
    assert result['report']['semantic_assessment'] == 'not-performed'
    assert saved['view_path'].startswith('/app/#literature?project=p&discovery=')
    w.create_project(id='other', title='Other')
    with pytest.raises(WorkspaceError):
        service.dispatch('project', 'discovery-view', {
            'project_id': 'other', 'artifact_id': saved['artifact']['id']})
    with w.db() as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 0


def test_projection_reads_unknown_reference_without_silent_success(setup):
    w, path = setup
    import hashlib
    capture = w.root / 'receipt.txt'
    capture.write_bytes(b'SYNTHETIC PRIVATE CAPTURE MUST NOT APPEAR')
    p = profile()
    p['attempts'][0].update(status='observed', outcome='partial', receipt={
        'reference': 'opaque-caller-ref',
        'material': {'path': capture.name, 'sha256': hashlib.sha256(capture.read_bytes()).hexdigest()}})
    path.write_text(json.dumps(p), encoding='utf-8')
    saved = save_profile(w, 'p', path.name)
    capture.unlink()
    result = WorkspaceService(w.root).dispatch('project', 'discovery-view', {
        'project_id': 'p', 'artifact_id': saved['artifact']['id']})
    assert result['ok'] is True  # readable projection, not research/binding success
    assert result['report']['binding'] == 'not-current'
    assert result['report']['material_bindings'][0]['status'] == 'unknown'
    assert 'receipt' not in result['discovery']['attempts'][0]
    assert 'receipt.txt' not in json.dumps(result)
    assert 'PRIVATE CAPTURE' not in json.dumps(result)
    assert result['discovery']['completion']['status'] == 'partial'


def test_changed_snapshot_cannot_be_presented_as_original(setup):
    w, path = setup
    saved = save_profile(w, 'p', path.name)
    target = w.root / saved['artifact']['path']
    changed = json.loads(target.read_text(encoding='utf-8'))
    changed['brief'] = 'Changed after save'
    target.write_text(json.dumps(changed), encoding='utf-8')
    with pytest.raises(WorkspaceError, match='snapshot changed'):
        WorkspaceService(w.root).dispatch('project', 'discovery-view', {
            'project_id': 'p', 'artifact_id': saved['artifact']['id']})


def test_get_route_is_read_only_and_still_rejects_untrusted_origin(setup):
    from types import SimpleNamespace
    from research_hub.workspace.server import WorkspaceHandler
    w, path = setup
    saved = save_profile(w, 'p', path.name)
    service = WorkspaceService(w.root)
    calls = []
    def call(resource, operation, data):
        calls.append((resource, operation, data))
        return service.dispatch(resource, operation, data)
    handler = WorkspaceHandler.__new__(WorkspaceHandler)
    handler.server = SimpleNamespace(_call=call)
    handler.path = '/api/v1/projects/p/artifacts/' + saved['artifact']['id'] + '/discovery'
    handler._trusted_origin = lambda: True
    results = []
    handler._result = results.append
    handler.do_GET()
    assert calls[0][1] == 'discovery-view' and results[0]['ok']
    assert len(calls) == 1
    handler._trusted_origin = lambda: False
    denied = []
    handler._reply = lambda status, data: denied.append((status, data))
    handler.do_GET()
    assert len(calls) == 1 and denied[0][0] == 403


def test_projection_does_not_fallback_when_platform_guard_unavailable(setup, monkeypatch):
    from research_hub.workspace import text_intake
    w, path = setup
    saved = save_profile(w, 'p', path.name)
    monkeypatch.setattr(text_intake, 'publication_supported', lambda: False)
    with pytest.raises(WorkspaceError) as error:
        WorkspaceService(w.root).dispatch('project', 'discovery-view', {
            'project_id': 'p', 'artifact_id': saved['artifact']['id']})
    assert error.value.code == 'unsupported_capability'


def test_hosted_browser_fixture_uses_actual_service_without_tasks_or_semantic_claim(setup):
    from scripts.workspace_browser_discovery import prepare_discovery_fixture
    w, _ = setup
    fixture = prepare_discovery_fixture(w)
    report = WorkspaceService(w.root).dispatch('project', 'discovery-view', {
        'project_id': fixture['project_id'], 'artifact_id': fixture['saved']['artifact']['id']})
    assert report['report']['material_reference_count'] == 1
    assert report['report']['unbound_source_material'] == ['s1', 's2']
    assert report['report']['execution_verified'] is False
    assert not w.records(fixture['project_id'])
    fixture['receipt'].unlink()
    report = WorkspaceService(w.root).dispatch('project', 'discovery-view', {
        'project_id': fixture['project_id'], 'artifact_id': fixture['saved']['artifact']['id']})
    assert report['report']['material_bindings'] == [{'kind':'attempt','id':'a1','status':'unknown'}]


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE'])
def test_browser_guard_blocks_mutations_before_dispatch(method):
    from types import SimpleNamespace
    from scripts.workspace_browser_discovery import guard_read_only
    calls = []
    route = SimpleNamespace(request=SimpleNamespace(method=method),
        fulfill=lambda **data: calls.append(data),
        continue_=lambda: pytest.fail('Mutation must not dispatch'))
    writes = []
    guard_read_only(route, writes)
    assert writes == [{'method': method}]
    assert calls[0]['status'] == 403


def test_browser_guard_preserves_real_read_dispatch():
    from types import SimpleNamespace
    from scripts.workspace_browser_discovery import guard_read_only
    calls = []
    route = SimpleNamespace(request=SimpleNamespace(method='GET'),
        fulfill=lambda **_: pytest.fail('Read must use actual service'),
        continue_=lambda: calls.append('read'))
    writes = []
    guard_read_only(route, writes)
    assert calls == ['read'] and not writes
