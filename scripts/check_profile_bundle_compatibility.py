"""Offline real adapter/Prepare checks; historical bytes are not live write guidance."""
import base64,hashlib,json,socket,subprocess,tempfile,uuid
from pathlib import Path
class NoSocket(socket.socket):
 def __init__(self,*a,**k):raise AssertionError('No network')
socket.socket=NoSocket
subprocess.Popen=lambda *a,**k:(_ for _ in ()).throw(AssertionError('No subprocess'))
from research_hub.workspace.research_draft import AbstractDraftAdapter,FILES
from research_hub.workspace.core import Workspace,WorkspaceError
from research_hub.workspace._sqlite_text_intake import SQLiteTextIntake
from research_hub.workspace.tasks import TaskService
root=Path(__file__).resolve().parents[1]
fixture=json.loads((root/'web/src/test-fixtures/sqlite-service.json').read_text())
checks=[]
for v in (1,2,3):
 adapter=AbstractDraftAdapter(v)
 assert all(hashlib.sha256(text.encode()).hexdigest()==FILES[name] for name,text in adapter.material.items())
 checks.append({'version':v,'manifest':adapter.manifest,'sha256':adapter.sha256})
assert checks[2]['manifest']==fixture['prepared']['task']['request']['research_draft']['profile']
with tempfile.TemporaryDirectory(prefix='hub-profile-compat-') as td:
 ws=Workspace(Path(td));ws.create_project(id='synthetic',title='Synthetic')
 raw=b'Synthetic selected abstract.';payload=dict(intake_request=dict(version=1,workspace_instance_id=ws.preparation_namespace(),key=str(uuid.uuid4())),title='Synthetic',reading_scope='abstract',input_kind='paste',format='txt',content_base64=base64.b64encode(raw).decode())
 saved=SQLiteTextIntake(ws).save('synthetic',**payload);tasks=TaskService(ws)
 selection=dict(artifact_id=saved['artifact']['id'],source_record_id=saved['record']['id'],start=0,end=len(raw))
 task=tasks.create('synthetic',operation='paper-abstract-draft',source_selection=selection)
 assert task['request']['research_draft']['profile']==checks[2]['manifest']
 assert task['request']['research_draft']['source_pack']['text']==raw.decode()
 (ws.root/'legacy.txt').write_bytes(raw);artifact=ws.register_artifact('synthetic',path='legacy.txt',role='evidence');record=ws.add_record('synthetic',kind='source',data={'title':'Legacy','locator':'fixture:legacy'})
 old=tasks.create('synthetic',operation='paper-abstract-draft',source_selection=dict(artifact_id=artifact['id'],source_record_id=record['id'],start=0,end=len(raw)))
 assert old['request']['research_draft']['profile']==checks[1]['manifest']
 assert tasks.get(task['id'])['freshness']['status']=='current'
print(json.dumps({'status':'PASS','profiles':checks,'prepare':['legacy-profile2','blob-profile3'],'scope':'Actual local adapters/tasks, no provider/HTTP/browser'},indent=2))
# Mutate only a disposable copy of package assets; real loader must fail closed.
import shutil
from unittest.mock import patch
from research_hub.workspace import research_draft
with tempfile.TemporaryDirectory(prefix='hub-profile-tamper-') as td:
 tmp=Path(td);source=root/'src/research_hub/skills_data/_profiles'
 shutil.copytree(source,tmp/'skills_data/_profiles')
 target=tmp/'skills_data/_profiles/abstract-draft-instructions-v1/paper-summarize/SKILL.md'
 target.write_bytes(target.read_bytes()+b'\nSynthetic mutation')
 with patch.object(research_draft,'__file__',str(tmp/'workspace/research_draft.py')):
  for v in (1,2,3):
   try:AbstractDraftAdapter(v)
   except WorkspaceError as e:assert e.code=='adapter_changed'
   else:raise AssertionError('Mutated bundle accepted')
print(json.dumps({'status':'PASS','mutation_guards':[1,2,3]}))
