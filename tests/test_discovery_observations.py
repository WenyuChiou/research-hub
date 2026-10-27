"""Synthetic native handoff; no live tool execution or semantic acceptance."""
import hashlib
import json
from copy import deepcopy

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError
from research_hub.workspace.text_intake import publication_supported
from research_hub.workspace.discovery import check_profile, save_profile, replay_profile


def profile(project='p'):
    return {'format':'research-discovery-observations/1.0','run_id':'synthetic-run',
      'project_id':project,'brief':'Synthetic scoped literature question',
      'capabilities':[{'name':'host search','kind':'search','availability':'available','observation':'visible host tool'}],
      'needs':[{'id':'n1','text':'Find closest work','families':['closest','contrary'],'status':'unresolved'}],
      'attempts':[{'id':'a1','need_ids':['n1'],'kind':'search','tool':'host search',
         'input':'synthetic query','status':'declared','outcome':'unknown','result_count':None,
         'receipt':None}],
      'sources':[{'id':'s1','work_id':'synthetic:1','title':'Synthetic closest work',
         'locator':'https://example.org/synthetic','access':'restricted','need_ids':['n1'],
         'relevance':'Potential closest method; abstract only, increment unresolved','version':None,'reading_level':'abstract',
         'reading_ref':'native-visible:read1','material':None,'attempt_ids':[]}],
      'completion':{'status':'partial','reason':'Closest work not established','residual_need_ids':['n1']}}


@pytest.fixture
def setup(tmp_path):
    if not publication_supported():
        pytest.skip('New optional discovery file route requires pinned directory primitives')
    w=Workspace(tmp_path);w.create_project(id='p',title='Synthetic')
    path=tmp_path/'native.json';path.write_text(json.dumps(profile()),encoding='utf-8')
    return w,path


def test_native_unknown_and_independent_read_are_valid_not_execution_proof(setup):
    w,path=setup;r=check_profile(w,'p',path.name)
    assert r['structure']=='valid' and r['binding']=='current'
    assert r['execution_verified'] is False and r['semantic_assessment']=='not-performed'
    assert r['declared_attempts']==1 and r['caller_observed_attempts']==0
    assert r['unknown_source_versions']==['s1']
    assert r['unbound_source_material']==['s1']


def test_save_restart_replay_idempotence_and_changed_profile(setup):
    w,path=setup;a=save_profile(w,'p',path.name);b=save_profile(Workspace(w.root),'p',path.name)
    assert a['artifact']['id']==b['artifact']['id']
    assert replay_profile(Workspace(w.root),'p',a['artifact']['id'])['report']['execution_verified'] is False
    p=profile();p['brief']='New scoped observation';path.write_text(json.dumps(p),encoding='utf-8')
    c=save_profile(w,'p',path.name)
    assert c['artifact']['id']!=a['artifact']['id']
    assert len(w.artifacts('p',history=True))==2
    assert not w.records('p')
    with w.db() as db:
        assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM decisions').fetchone()[0]==0


@pytest.mark.parametrize('change',[
 lambda p:p.update(format='research-discovery-observations/99'),
 lambda p:p['attempts'][0].update(need_ids=['missing']),
 lambda p:p['sources'][0].update(attempt_ids=['missing']),
 lambda p:p['needs'].append(deepcopy(p['needs'][0])),
 lambda p:p['completion'].update(status='bounded-complete'),
 lambda p:p['attempts'][0].update(status='planned',outcome='success',result_count=1),
 lambda p:p['attempts'][0].update(status='observed',outcome='empty',result_count=None),
 lambda p:p['attempts'][0].update(status='observed',outcome='timeout',result_count=0),
])
def test_invalid_or_falsely_complete_profile_does_not_write(setup,change):
    w,path=setup;p=profile();change(p);path.write_text(json.dumps(p),encoding='utf-8')
    with pytest.raises(WorkspaceError):save_profile(w,'p',path.name)
    assert w.artifacts('p')==[] and not (w.root/'hub-discovery').exists()


def test_saved_receipt_is_byte_binding_not_authenticity_and_tamper_blocks_save(setup):
    w,path=setup;capture=w.root/'capture.txt';capture.write_bytes(b'synthetic tool observation')
    p=profile();p['attempts'][0].update(status='observed',outcome='partial',receipt={
      'reference':'native-call:1','material':{'path':'capture.txt','sha256':hashlib.sha256(capture.read_bytes()).hexdigest()}})
    path.write_text(json.dumps(p),encoding='utf-8');a=save_profile(w,'p',path.name)
    assert a['report']['caller_observed_attempts']==1 and not a['report']['execution_verified']
    capture.write_bytes(b'changed')
    assert replay_profile(w,'p',a['artifact']['id'])['report']['binding']=='not-current'
    with pytest.raises(WorkspaceError):save_profile(w,'p',path.name)


def test_expected_snapshot_hash_blocks_validate_register_swap(setup,monkeypatch):
    w,path=setup;original=w.register_artifact
    def swapped(project_id,**values):
        (w.root/values['path']).write_text('{}',encoding='utf-8')
        return original(project_id,**values)
    monkeypatch.setattr(w,'register_artifact',swapped)
    with pytest.raises(WorkspaceError):save_profile(w,'p',path.name)
    assert w.artifacts('p')==[]


def test_database_failure_keeps_identified_snapshot_for_explicit_replay(setup,monkeypatch):
    w,path=setup
    with monkeypatch.context() as m:
        m.setattr(w,'register_artifact',lambda *a,**kw: (_ for _ in ()).throw(OSError('synthetic DB failure')))
        r=save_profile(w,'p',path.name)
    assert r['ok'] is False and r['code']=='registration_incomplete'
    assert (w.root/r['snapshot_path']).is_file() and w.artifacts('p')==[]
    assert save_profile(w,'p',path.name)['ok'] is True


def test_scope_and_unknown_artifact_replay_rejected(setup):
    w,path=setup;w.create_project(id='other',title='Other')
    a=save_profile(w,'p',path.name)
    with pytest.raises(WorkspaceError):save_profile(w,'other',path.name)
    with pytest.raises(WorkspaceError):replay_profile(w,'other',a['artifact']['id'])


@pytest.mark.skipif(not publication_supported(), reason='Pinned directory primitives unavailable')
def test_actual_cli_routes_use_no_account_config_and_replay(tmp_path,monkeypatch,capsys):
    from research_hub import cli, config
    def forbidden(*args,**kwargs):raise AssertionError('No account configuration')
    monkeypatch.setattr(cli,'get_config',forbidden);monkeypatch.setattr(config,'get_config',forbidden)
    root=tmp_path/'work';root.mkdir();(root/'native.json').write_text(json.dumps(profile()),encoding='utf-8')
    base=['--root',str(root),'--project','p','--json']
    assert cli.main(['project','discovery-check',*base,'--path','native.json'])==0
    assert json.loads(capsys.readouterr().out)['report']['execution_verified'] is False
    assert not (root/'.research').exists() # optional check needs no initialized Hub workspace
    assert cli.main(['project','create','p','--root',str(root),'--title','Synthetic','--json'])==0
    capsys.readouterr()
    assert cli.main(['project','discovery-save',*base,'--path','native.json'])==0
    artifact=json.loads(capsys.readouterr().out)['artifact']['id']
    assert cli.main(['project','discovery-replay',*base,'--artifact-id',artifact])==0
    assert json.loads(capsys.readouterr().out)['report']['semantic_assessment']=='not-performed'


@pytest.mark.parametrize('host,available', [('Codex',True),('Claude Code',True),('another host',False)])
def test_host_brand_does_not_imply_deep_research_or_search_execution(setup,host,available):
    w,path=setup;p=profile();p['capabilities']=[{'name':host,'kind':'deep-research',
        'availability':'available' if available else 'unavailable','observation':'synthetic inventory only'}]
    path.write_text(json.dumps(p),encoding='utf-8')
    r=check_profile(w,'p',path.name)
    assert r['caller_observed_attempts']==0 and not r['execution_verified']


@pytest.mark.parametrize('badpath',['../outside.txt','/absolute.txt','C:/secret','a\\b','.research/workspace.sqlite3','.git/config','.GiT/config','.RESEARCH/workspace.sqlite3'])
def test_material_paths_do_not_escape_or_read_internal_state(setup,badpath):
    w,path=setup;p=profile();p['sources'][0]['material']={'path':badpath,'sha256':'0'*64}
    path.write_text(json.dumps(p),encoding='utf-8')
    with pytest.raises(WorkspaceError):check_profile(w,'p',path.name)


def test_linked_material_rejected(setup,tmp_path):
    w,path=setup;(tmp_path/'real.txt').write_text('synthetic');(tmp_path/'link.txt').symlink_to(tmp_path/'real.txt')
    p=profile();p['sources'][0]['material']={'path':'link.txt','sha256':'0'*64};path.write_text(json.dumps(p))
    with pytest.raises(WorkspaceError):check_profile(w,'p',path.name)


@pytest.mark.parametrize('raw',[b'{"format":1,"format":2}', b'{"value":NaN}', b'\xff'])
def test_ambiguous_json_rejected_without_echoing_input(setup,raw):
    w,path=setup;path.write_bytes(raw)
    with pytest.raises(WorkspaceError):check_profile(w,'p',path.name)


def test_oversize_and_missing_material_are_not_empty_search(setup,monkeypatch):
    from research_hub.workspace import discovery
    w,path=setup
    with monkeypatch.context() as m:
        m.setattr(discovery,'MAX_PROFILE_BYTES',2)
        with pytest.raises(WorkspaceError):check_profile(w,'p',path.name)
    p=profile();p['sources'][0]['material']={'path':'missing.txt','sha256':'0'*64};path.write_text(json.dumps(p))
    r=check_profile(w,'p',path.name)
    assert r['binding']=='not-current' and r['material_bindings'][0]['status']=='unknown'


def test_original_profile_swap_after_capture_cannot_change_saved_snapshot(setup,monkeypatch):
    from research_hub.workspace import discovery
    w,path=setup;original=discovery._assess
    def swap(*args):
        result=original(*args);path.write_text('{}',encoding='utf-8');return result
    monkeypatch.setattr(discovery,'_assess',swap)
    saved=save_profile(w,'p',path.name)
    persisted=json.loads((w.root/saved['artifact']['path']).read_text(encoding='utf-8'))
    assert persisted==profile()


def test_generic_registration_remains_generic_but_expected_hash_blocks_wrong_bytes(setup):
    w,path=setup
    with pytest.raises(WorkspaceError):
        w.register_artifact('p',path=path.name,role='evidence',expected_sha256='0'*64)
    assert w.artifacts('p')==[]
    path.write_text('{}',encoding='utf-8')
    assert w.register_artifact('p',path=path.name,role='evidence')['current']


def test_no_receipt_does_not_become_observed_or_empty_and_no_bound_material_is_explicit(setup):
    w,path=setup;p=profile();p['attempts'][0].update(status='observed',outcome='success')
    path.write_text(json.dumps(p),encoding='utf-8')
    with pytest.raises(WorkspaceError):check_profile(w,'p',path.name)
    path.write_text(json.dumps(profile()),encoding='utf-8')
    assert check_profile(w,'p',path.name)['material_reference_count']==0


def test_covered_need_cannot_be_declared_without_observed_result(setup):
    w,path=setup;p=profile();p['needs'][0]['status']='covered';p['completion'].update(status='bounded-complete',residual_need_ids=[])
    path.write_text(json.dumps(p),encoding='utf-8')
    with pytest.raises(WorkspaceError):check_profile(w,'p',path.name)


def test_snapshot_write_failure_has_no_registration(setup,monkeypatch):
    from research_hub.workspace import discovery
    w,path=setup
    monkeypatch.setattr(discovery.local_files,'_publish_copy',lambda *a,**kw: (_ for _ in ()).throw(OSError('synthetic write failure')))
    with pytest.raises(OSError):save_profile(w,'p',path.name)
    assert w.artifacts('p')==[]


def test_existing_corrupt_snapshot_is_never_overwritten(setup):
    w,path=setup;a=save_profile(w,'p',path.name);target=w.root/a['artifact']['path'];target.write_bytes(b'corrupt')
    with pytest.raises(WorkspaceError):save_profile(w,'p',path.name)
    assert target.read_bytes()==b'corrupt'
    with pytest.raises(WorkspaceError):replay_profile(w,'p',a['artifact']['id'])


def test_profile_messages_do_not_echo_private_value(setup):
    w,path=setup;p=profile();p['format']='PRIVATE-SENTINEL';path.write_text(json.dumps(p))
    with pytest.raises(WorkspaceError) as failure:check_profile(w,'p',path.name)
    assert 'PRIVATE-SENTINEL' not in str(failure.value)


def test_portable_profile_schema_and_skill_are_packaged_and_native_first():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    for rel in ['research-hub/SKILL.md','research-hub/references/native-discovery-export.md']:
        assert (root/'skills'/rel).read_bytes()==(root/'src/research_hub/skills_data'/rel).read_bytes()
    schema=json.loads((root/'src/research_hub/schemas/research-discovery-observations-1.0.json').read_text(encoding='utf-8'))
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(profile()))


def test_lost_database_ack_reconciles_same_registered_artifact(setup,monkeypatch):
    w,path=setup;original=w.register_artifact
    def lost_ack(*args,**kwargs):
        original(*args,**kwargs)
        raise OSError('synthetic acknowledgment lost')
    with monkeypatch.context() as m:
        m.setattr(w,'register_artifact',lost_ack)
        first=save_profile(w,'p',path.name)
    assert first['code']=='registration_incomplete'
    saved_id=w.artifacts('p')[0]['id']
    assert save_profile(Workspace(w.root),'p',path.name)['artifact']['id']==saved_id
    assert len(w.artifacts('p',history=True))==1


def test_need_and_capability_inventory_cannot_be_empty_completion(setup):
    w,path=setup;p=profile();p.update(capabilities=[],needs=[],attempts=[],sources=[])
    p['completion'].update(status='bounded-complete',residual_need_ids=[])
    path.write_text(json.dumps(p))
    with pytest.raises(WorkspaceError):check_profile(w,'p',path.name)


def test_nonregular_profile_cannot_block_reader(setup):
    import os
    if not hasattr(os,'mkfifo'):
        pytest.skip('FIFO special-file control is POSIX-only')
    w,path=setup;path.unlink();os.mkfifo(path)
    with pytest.raises(WorkspaceError):check_profile(w,'p',path.name)


def test_existing_mcp_callable_uses_same_optional_check_not_execution(setup):
    from research_hub.mcp_server import workspace_project
    w,path=setup
    result=workspace_project(str(w.root),'discovery-check',{'project_id':'p','path':path.name})
    assert result['ok'] and result['report']['execution_verified'] is False


def test_replay_does_not_enumerate_or_hash_unrelated_project_files(setup,monkeypatch):
    w,path=setup;a=save_profile(w,'p',path.name)
    def forbidden(*args,**kwargs):raise AssertionError('Unrelated artifacts must not be scanned')
    monkeypatch.setattr(w,'artifacts',forbidden)
    assert replay_profile(w,'p',a['artifact']['id'])['ok']


def test_unsupported_platform_fails_closed_without_changing_native_export(tmp_path,monkeypatch):
    from research_hub.workspace import discovery
    w=Workspace(tmp_path);p=tmp_path/'native.json';raw=json.dumps(profile()).encode();p.write_bytes(raw)
    monkeypatch.setattr(discovery.local_files,'publication_supported',lambda:False)
    with pytest.raises(WorkspaceError) as failure:check_profile(w,'p',p.name)
    assert failure.value.code=='unsupported_capability'
    assert p.read_bytes()==raw and not (tmp_path/'.research').exists()


def test_pinned_publication_parent_swap_does_not_write_redirected_directory(setup,monkeypatch,tmp_path):
    from contextlib import contextmanager
    from research_hub.workspace import discovery
    w,path=setup;outside=tmp_path/'redirect-target';outside.mkdir(mode=0o700)
    original=discovery.local_files._directory;swapped=False
    @contextmanager
    def swap(root,parts,**kwargs):
        nonlocal swapped
        with original(root,parts,**kwargs) as fd:
            if parts==('hub-discovery',) and kwargs.get('create') and not swapped:
                swapped=True
                (root/'hub-discovery').rename(root/'held-directory')
                (root/'hub-discovery').symlink_to(outside,target_is_directory=True)
            yield fd
    monkeypatch.setattr(discovery.local_files,'_directory',swap)
    with pytest.raises((WorkspaceError,OSError)):save_profile(w,'p',path.name)
    assert list(outside.iterdir())==[] and w.artifacts('p')==[]


def test_pinned_material_parent_swap_never_reads_redirected_bytes(setup,monkeypatch,tmp_path):
    from contextlib import contextmanager
    from research_hub.workspace import discovery
    w,path=setup;papers=tmp_path/'papers';papers.mkdir();(papers/'source.txt').write_bytes(b'synthetic original')
    outside=tmp_path/'redirect-target';outside.mkdir();(outside/'source.txt').write_bytes(b'synthetic replacement')
    p=profile();p['sources'][0]['material']={'path':'papers/source.txt','sha256':hashlib.sha256(b'synthetic original').hexdigest()}
    path.write_text(json.dumps(p));original=discovery.local_files._directory;swapped=False
    @contextmanager
    def swap(root,parts,**kwargs):
        nonlocal swapped
        with original(root,parts,**kwargs) as fd:
            if parts==('papers',) and not swapped:
                swapped=True;papers.rename(tmp_path/'held-papers');papers.symlink_to(outside,target_is_directory=True)
            yield fd
    monkeypatch.setattr(discovery.local_files,'_directory',swap)
    with pytest.raises((WorkspaceError,OSError)):check_profile(w,'p',path.name)


def test_expected_hash_registration_rejects_fifo_leaf_without_blocking(setup,monkeypatch):
    import os
    w,path=setup;original=w.register_artifact
    def swap(project_id,**values):
        target=w.root/values['path'];target.unlink();os.mkfifo(target)
        return original(project_id,**values)
    monkeypatch.setattr(w,'register_artifact',swap)
    with pytest.raises(WorkspaceError):save_profile(w,'p',path.name)
    with w.db() as db:assert db.execute('SELECT count(*) FROM artifacts').fetchone()[0]==0


@pytest.mark.skipif(not publication_supported(), reason='Pinned directory primitives unavailable')
def test_actual_module_entrypoint_checks_portable_profile_without_initialization(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    path=tmp_path/'native.json';path.write_text(json.dumps(profile()),encoding='utf-8')
    env=dict(os.environ);env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    result=subprocess.run([sys.executable,'-m','research_hub','project','discovery-check',
        '--root',str(tmp_path),'--project','p','--path',path.name,'--json'],
        env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)['report']
    assert report['declared_attempts']==1 and report['execution_verified'] is False
    assert not (tmp_path/'.research').exists()


def test_material_reference_count_does_not_count_unique_captures_or_verified_calls(setup):
    w, path = setup
    capture = w.root / 'shared-capture.txt'
    capture.write_bytes(b'synthetic shared tool return')
    p = profile()
    material = {'path': capture.name, 'sha256': hashlib.sha256(capture.read_bytes()).hexdigest()}
    p['attempts'][0].update(status='observed', outcome='partial', receipt={
        'reference': 'caller-capture:one', 'material': material})
    second = deepcopy(p['attempts'][0])
    second['id'] = 'a2'
    p['attempts'].append(second)
    path.write_text(json.dumps(p), encoding='utf-8')
    result = check_profile(w, 'p', path.name)
    assert result['material_reference_count'] == 2
    assert len(result['material_bindings']) == 2
    assert result['unbound_source_material'] == ['s1']
    assert result['execution_verified'] is False
    assert 'bound_material_count' not in result
    capture.write_bytes(b'changed')
    stale = check_profile(w, 'p', path.name)
    assert stale['material_reference_count'] == 2
    assert [b['status'] for b in stale['material_bindings']] == ['stale', 'stale']
