"""Task-derived working prose never mutates source evidence or human decisions."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import uuid

import pytest

from research_hub.workspace.core import WorkspaceError, digest, encoded
from research_hub.workspace.service import WorkspaceService
from research_hub.workspace.working_summary import WorkingSummary


@pytest.fixture
def candidate(tmp_path):
    service = WorkspaceService(tmp_path)
    w = service.workspace
    w.create_project(id='study', title='Synthetic study', archetype='review', goal='Local test')
    text = 'Synthetic observations show blue water. Evidence is limited.'
    (tmp_path / 'source.txt').write_text(text)
    source = w.add_record('study', kind='source', data={'title': 'Synthetic paper', 'locator': 'https://example.invalid/test',
                         'abstract': text, 'summary': 'Original prose', 'human_acceptance': 'pending'})
    assert 'id' not in source['data'] and 'source_records' not in source['data']
    artifact = w.register_artifact('study', path='source.txt', role='evidence', source_record_id=source['id'])
    task = service.tasks.create('study', operation='paper-abstract-draft', mode='handoff', source_selection={
        'source_record_id': source['id'], 'artifact_id': artifact['id'], 'start': 0, 'end': len(text)})
    response = {'summary': [{'text': 'The synthetic observation is blue water.', 'quote': 'blue water'}],
                'findings': [], 'methodology': [], 'limitations': []}
    task = service.tasks.import_result(task['id'], draft_response=response, input_hash=digest(task['request']))
    return service, source, artifact, task


def context(c):
    service, source, _, task = c
    return WorkingSummary(service.workspace).context('study', source_record_id=source['id'], task_id=task['id'])['context']


def request(c):
    item = context(c)
    return {'source_record_id': c[1]['id'], 'task_id': c[3]['id'], 'provenance': item['provenance'],
            'expected_revision': item['revision'], 'text': 'My explicitly saved working prose.'}


def save(c, args):
    return WorkingSummary(c[0].workspace).save('study', **args)


def replace_task(c, task):
    with c[0].workspace.db(write=True) as db:
        db.execute('UPDATE tasks SET body=? WHERE id=?', (encoded(task), task['id']))


def reseal(task):
    task['result']['input_hash'] = digest(task['request'])
    task['action_hash'] = digest({'request': task['request'], 'result': task['result']})


def test_read_save_retry_restart_and_history_preserve_all_authority(candidate):
    service, source, artifact, task = candidate
    w = service.workspace
    before = w.db_path.read_bytes()
    files = {p['path']: (w.root / p['path']).read_bytes() for p in task['result']['artifacts']}
    args = request(candidate)
    assert w.db_path.read_bytes() == before
    item = context(candidate)
    assert item['draft_text'] == task['result']['prose']
    assert item['working_summary'] is None and 'artifact_id' not in item
    result = save(candidate, args)
    saved = result['record']['data']['working_summary']
    assert set(saved) == {'text', 'provenance', 'source_revision', 'previous_revision', 'saved_at'}
    assert saved['provenance'] == args['provenance'] and saved['text'] == args['text']
    assert {k: v for k,v in result['record']['data'].items() if k != 'working_summary'} == source['data']
    after = w.db_path.read_bytes()
    assert save(candidate, args)['reused'] is True
    assert after == w.db_path.read_bytes()
    fresh = WorkspaceService(w.root)
    assert fresh.tasks.get(task['id']) == service.tasks.get(task['id'])
    assert context((fresh, source, artifact, task))['working_summary'] == saved
    second = request(candidate)
    second['text'] = 'A second explicit edit.'
    assert save(candidate, second)['record']['data']['working_summary_history'] == [saved]
    with pytest.raises(WorkspaceError, match='changed'):
        save(candidate, args)
    assert w.artifacts('study')[0]['sha256'] == artifact['sha256']
    assert all((w.root / p).read_bytes() == raw for p,raw in files.items())
    with w.db() as db:
        assert json.loads(db.execute('SELECT body FROM tasks WHERE id=?', (task['id'],)).fetchone()[0]) == task
        assert db.execute('SELECT COUNT(*) FROM decisions').fetchone()[0] == 0


@pytest.mark.parametrize('change', ['project','source','task','request-project','request-task','request-operation','source-pack','source-selection','status','accepted','input-hash','action-hash'])
def test_identity_and_pending_state_fail_closed(candidate, change, monkeypatch):
    task = deepcopy(candidate[3]); source = candidate[1]
    if change == 'project': task['project_id'] = 'other'
    elif change == 'source': source = {**source, 'id': 'other'}
    elif change == 'task': task['id'] = uuid.uuid4().hex
    elif change.startswith('request-'):
        field = change.removeprefix('request-')
        task['request'][{'project':'project','task':'task_id','operation':'operation'}[field]] = {'id':'other'} if field == 'project' else 'other'
    elif change == 'source-pack': task['request']['research_draft']['source_pack']['source_record_id'] = 'other'
    elif change == 'source-selection': task['request']['research_draft']['source_selection']['source_record_id'] = 'other'
    elif change == 'status': task['status'] = 'completed'
    elif change == 'accepted': task['result']['semantic_acceptance'] = 'accept'
    elif change == 'input-hash': task['result']['input_hash'] = '0'*64
    elif change == 'action-hash': task['action_hash'] = '0'*64
    with candidate[0].workspace.db(write=True) as db:
        db.execute('UPDATE tasks SET body=? WHERE id=?',(encoded(task),candidate[3]['id']))
    # Scope/hash rejection must occur before freshness can read any files.
    monkeypatch.setattr(candidate[0].tasks.__class__, 'check_inputs', lambda *a: pytest.fail('unscoped file read'))
    with pytest.raises(WorkspaceError): context((candidate[0],source,candidate[2],candidate[3]))


@pytest.mark.parametrize('change', ['duplicate','foreign-path','absolute','traversal','missing','mixed-parent','malformed-sha','extra-field'])
def test_candidate_scope_rejected_before_file_reads(candidate, change, monkeypatch):
    task = deepcopy(candidate[3]); files = task['result']['artifacts']
    if change == 'duplicate': files[-1] = files[0]
    elif change == 'foreign-path': files[0]['path'] = 'proposals/'+'a'*32+'-'+'b'*32+'/draft.md'
    elif change == 'absolute': files[0]['path'] = '/tmp/draft.md'
    elif change == 'traversal': files[0]['path'] = 'proposals/../draft.md'
    elif change == 'missing': files.pop()
    elif change == 'mixed-parent': files[0]['path'] = 'proposals/'+task['id']+'-'+'b'*32+'/draft.md'
    elif change == 'malformed-sha': files[0]['sha256'] = 'no'
    elif change == 'extra-field': files[0]['other'] = 'unused'
    reseal(task); replace_task(candidate,task)
    monkeypatch.setattr(candidate[0].tasks.__class__, 'check_inputs', lambda *a: pytest.fail('unscoped file read'))
    with pytest.raises(WorkspaceError): context(candidate)


@pytest.mark.parametrize('name', ['draft.md','draft-response.json','raw-draft-response.json','selected-source.txt','binding-check.json'])
@pytest.mark.parametrize('resealed', [False, True])
def test_tampered_files_fail_even_with_updated_registry_hash(candidate, name, resealed):
    task = deepcopy(candidate[3]); item = next(a for a in task['result']['artifacts'] if a['path'].endswith('/'+name))
    path = candidate[0].workspace.root / item['path']
    path.write_text('tampered')
    if resealed:
        item['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        reseal(task); replace_task(candidate,task)
    before = candidate[0].workspace.db_path.read_bytes()
    with pytest.raises(WorkspaceError): context(candidate)
    assert candidate[0].workspace.db_path.read_bytes() == before


@pytest.mark.parametrize('change', ['source-bytes','source-metadata','source-owner','prose','binding','profile','instructions','request-revision'])
def test_current_source_request_and_result_required(candidate, change):
    args = request(candidate)
    service, source, artifact, original = candidate
    task = deepcopy(original)
    if change == 'source-bytes': (service.workspace.root / 'source.txt').write_text('changed')
    elif change == 'source-metadata':
        with service.workspace.db(write=True) as db:
            db.execute('UPDATE records SET body=? WHERE id=?',(encoded({**source['data'],'title':'Changed'}),source['id']))
    elif change == 'source-owner':
        with service.workspace.db(write=True) as db:
            db.execute('UPDATE artifacts SET body=? WHERE id=?',(encoded({**artifact,'source_record_id':'other'}),artifact['id']))
    else:
        if change == 'prose': task['result']['prose'] = 'unbound replacement'
        elif change == 'binding': task['result']['source_binding']['statements'] = 9
        elif change == 'profile': task['request']['research_draft']['profile']['profile_version'] = 1
        elif change == 'instructions': task['request']['instructions'] = 'new task revision'
        elif change == 'request-revision': task['request']['revision'] = 8
        reseal(task); replace_task(candidate,task)
    before = service.workspace.db_path.read_bytes()
    with pytest.raises(WorkspaceError): save(candidate,args)
    assert service.workspace.db_path.read_bytes() == before


def test_two_concurrent_saves_do_not_overwrite(candidate):
    args = request(candidate)
    def attempt(text):
        try: return save(candidate,{**args,'text':text})
        except WorkspaceError as error: return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt,['first','second']))
    assert sum(isinstance(v,dict) for v in results) == 1
    assert 'stale_input' in results
    assert 'working_summary_history' not in candidate[0].workspace.records('study')[0]['data']


@pytest.mark.parametrize('text', ['', ' '*2, 'x'*40001, '\ud800'])
def test_invalid_text_never_saved(candidate,text):
    args=request(candidate)
    with pytest.raises(WorkspaceError): save(candidate,{**args,'text':text})
    assert 'working_summary' not in candidate[0].workspace.records('study')[0]['data']


def test_unrelated_metadata_change_conflicts_and_mixed_selector_rejected(candidate):
    args=request(candidate)
    service,source,artifact,_=candidate
    with service.workspace.db(write=True) as db:
        db.execute('UPDATE records SET body=? WHERE id=?',(encoded({**source['data'],'note':'concurrent human edit'}),source['id']))
    with pytest.raises(WorkspaceError): save(candidate,args)
    with pytest.raises(WorkspaceError): save(candidate,{**args,'artifact_id':artifact['id']})
    with pytest.raises(WorkspaceError): save(candidate,{**args,'artifact_sha256':artifact['sha256']})


@pytest.mark.parametrize('change', ['manuscript','extra-input','revision-path','foreign-input','adapter','records'])
def test_no_unscoped_freshness_reads(candidate, change, monkeypatch):
    task=deepcopy(candidate[3]); request=task['request']
    sentinel=candidate[0].workspace.root/'unrelated-private.txt';sentinel.write_text('synthetic sentinel')
    if change=='manuscript': request['manuscript_state_path']='unrelated-private.txt'
    elif change=='extra-input': request['artifacts'].append({**request['artifacts'][0],'path':'unrelated-private.txt'})
    elif change=='foreign-input': request['artifacts'][0]['path']='unrelated-private.txt'
    elif change=='revision-path':
        request['revision_context']={'prose':'prior','artifacts':[{'path':'unrelated-private.txt','sha256':'0'*64}],'reviewed_action_hash':'0'*64}
        task['attempts']=[{'result':{'prose':'prior','artifacts':request['revision_context']['artifacts']},'decision':{'decision':'revise','affected_action_hash':'0'*64}}]
    elif change=='adapter': request['adapter_sha256']='0'*64
    elif change=='records': request['records']=[{'id':'other'}]
    reseal(task);replace_task(candidate,task)
    monkeypatch.setattr(candidate[0].tasks.__class__, 'check_inputs', lambda *a: pytest.fail('unscoped freshness read'))
    with pytest.raises(WorkspaceError):context(candidate)


@pytest.mark.parametrize('table', ['records','artifacts','tasks'])
@pytest.mark.parametrize('body', ['[]','null','"text"','{}'])
def test_malformed_ledger_sanitized(candidate,table,body):
    index={'records':1,'artifacts':2,'tasks':3}[table]
    with candidate[0].workspace.db(write=True) as db:
        db.execute(f'UPDATE {table} SET body=? WHERE id=?',(body,candidate[index]['id']))
    with pytest.raises(WorkspaceError): context(candidate)


def test_symlink_and_oversized_candidate_rejected(candidate):
    path=candidate[0].workspace.root/candidate[3]['result']['artifacts'][0]['path']
    original=path.read_bytes();path.unlink();path.symlink_to(candidate[0].workspace.root/'source.txt')
    with pytest.raises(WorkspaceError):context(candidate)
    path.unlink();path.write_bytes(b'x'*200001)
    with pytest.raises(WorkspaceError,match='limit'):context(candidate)
    path.write_bytes(original)
    assert context(candidate)['draft_text']==candidate[3]['result']['prose']


def test_blob_profile_and_missing_data_id(tmp_path):
    import base64
    from research_hub.workspace._sqlite_text_intake import SQLiteTextIntake
    service=WorkspaceService(tmp_path);w=service.workspace
    w.create_project(id='study',title='Synthetic',archetype='review',goal='Test')
    w.initialize_preparations()
    text='One exact synthetic quote.'
    result=SQLiteTextIntake(w).save('study',intake_request={'version':1,'workspace_instance_id':w.preparation_namespace(),'key':str(uuid.uuid4())},title='Synthetic source',reading_scope='abstract',input_kind='paste',format='txt',content_base64=base64.b64encode(text.encode()).decode())
    source=result['record'];artifact=result['artifact']
    task=service.tasks.create('study',operation='paper-abstract-draft',source_selection={'source_record_id':source['id'],'artifact_id':artifact['id'],'start':0,'end':len(text)})
    assert task['request']['research_draft']['profile']['profile_version']==3
    task=service.tasks.import_result(task['id'],input_hash=digest(task['request']),draft_response={'summary':[{'text':'Synthetic working candidate.','quote':'exact synthetic quote'}],'findings':[],'methodology':[],'limitations':[]})
    fixture=(service,source,artifact,task)
    assert 'id' not in source['data']
    assert save(fixture,request(fixture))['record']['data']['working_summary']['provenance']['task_id']==task['id']


def test_frozen_v1_profile_supported(candidate):
    from research_hub.workspace.research_draft import prepare
    service,source,artifact,old=candidate
    task=service.tasks.create('study',operation='paper-abstract-draft',source_selection=old['request']['research_draft']['source_selection'])
    task['request']['research_draft']=prepare(service.workspace,'study',task['request']['research_draft']['source_selection'],profile_version=1)
    task['action_hash']=digest(task['request'])
    replace_task((service,source,artifact,task),task)
    text=task['request']['research_draft']['source_pack']['text'];quote='blue water';start=text.index(quote)
    task=service.tasks.import_result(task['id'],input_hash=digest(task['request']),draft_response={'summary':[{'text':'Blue water in synthetic example.','quote':quote,'start':start,'end':start+len(quote)}],'findings':[],'methodology':[],'limitations':[]})
    fixture=(service,source,artifact,task)
    assert save(fixture,request(fixture))['reused'] is False


def test_valid_revision_retains_previous_candidate_provenance(candidate):
    # Synthetic ledger fixture for an already revised task; no approval API is called.
    service,source,artifact,old=candidate
    task=deepcopy(old)
    task['attempts']=[{'result':deepcopy(old['result']),'decision':{'decision':'revise','affected_action_hash':old['action_hash']}}]
    task['request']['revision_context']={'prose':old['result']['prose'],'artifacts':old['result']['artifacts'],'reviewed_action_hash':old['action_hash']}
    task['request']['revision_instruction']='Revise synthetic wording.'
    task['request']['revision']=1
    task['result']=None;task['status']='awaiting_agent';task['action_hash']=digest(task['request'])
    replace_task(candidate,task)
    task=service.tasks.import_result(task['id'],input_hash=digest(task['request']),draft_response={'summary':[{'text':'Revised synthetic wording.','quote':'blue water'}],'findings':[],'methodology':[],'limitations':[]})
    fixture=(service,source,artifact,task)
    assert save(fixture,request(fixture))['record']['data']['working_summary']['provenance']['action_hash']==task['action_hash']
    previous=service.workspace.root/old['result']['artifacts'][0]['path'];previous.write_text('changed earlier candidate')
    with pytest.raises(WorkspaceError):context(fixture)


def test_http_task_context_save_and_guards(candidate):
    import threading
    from urllib.request import Request,urlopen
    from urllib.error import HTTPError
    from urllib.parse import urlencode
    from research_hub.workspace.server import WorkspaceServer
    service,source,artifact,task=candidate
    server=WorkspaceServer(service.workspace.root,port=0)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    base=f'http://127.0.0.1:{server.server_port}/api/v1/projects/study/working-summary'
    def http(url,data=None,headers=None):
        try: response=urlopen(Request(url,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**(headers or {})}),timeout=4)
        except HTTPError as error: response=error
        with response:return response.status,json.loads(response.read())
    try:
        query=urlencode({'source_record_id':source['id'],'task_id':task['id']});url=base+'?'+query
        before=service.workspace.db_path.read_bytes()
        assert http(url)[0]==200 and service.workspace.db_path.read_bytes()==before
        assert http(url+'&artifact_id='+artifact['id'])[0]==400
        assert http(url+'&task_id='+task['id'])[0]==400
        assert http(url,headers={'Origin':'https://example.invalid'})[0]==403
        assert http(url,headers={'Sec-Fetch-Site':'cross-site'})[0]==403
        args=request(candidate)
        assert http(base,args)[0]==403
        assert service.workspace.db_path.read_bytes()==before
        status,result=http(base,args,{'X-CSRF-Token':server.csrf})
        assert status==200 and result['record']['data']['working_summary']['provenance']==args['provenance']
        assert http(url)[1]['context']['working_summary']['text']==args['text']
        assert http(base,{**args,'human_acceptance':'accepted'},{'X-CSRF-Token':server.csrf})[0]==400
        assert service.tasks.get(task['id'])['status']=='awaiting_human'
    finally:
        server.shutdown();server.server_close();worker.join(timeout=3)
    assert not worker.is_alive()


@pytest.mark.parametrize(('raw', 'expected'), [
    ('\ufeff', '\ufeff'),
    ('\ufeffWorking prose\ufeff', '\ufeffWorking prose\ufeff'),
    ('\u0085Working prose\u0085', 'Working prose'),
    ('\u001cWorking prose\u001c', 'Working prose'),
    ('\u001dWorking prose\u001d', 'Working prose'),
    ('\u001eWorking prose\u001e', 'Working prose'),
    ('\u001fWorking prose\u001f', 'Working prose'),
    ('\u0085摘要\r\n🌿\r下一行\u0085', '摘要\n🌿\r下一行'),
])
def test_task_summary_unicode_normalization_receipt_and_retry(candidate, raw, expected):
    args = {**request(candidate), 'text': raw}
    original_task = deepcopy(candidate[3])
    result = save(candidate, args)
    saved = result['record']['data']['working_summary']
    assert saved['text'] == expected
    assert saved['provenance'] == args['provenance']
    assert saved['previous_revision'] == args['expected_revision']
    assert save(candidate, args)['reused'] is True
    assert context(candidate)['working_summary'] == saved
    with candidate[0].workspace.db() as db:
        assert json.loads(db.execute('SELECT body FROM tasks WHERE id=?', (original_task['id'],)).fetchone()[0]) == original_task
    assert {k: v for k, v in result['record']['data'].items() if k != 'working_summary'} == candidate[1]['data']


def test_task_summary_python_whitespace_only_rejected(candidate):
    args = {**request(candidate), 'text': '\u0085\u001c\u001d\u001e\u001f'}
    before = candidate[0].workspace.db_path.read_bytes()
    with pytest.raises(WorkspaceError, match='nonempty'):
        save(candidate, args)
    assert candidate[0].workspace.db_path.read_bytes() == before
