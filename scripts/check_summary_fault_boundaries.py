"""Synthetic direct fault probes. No external adapter, model, vault or subprocess."""
import json,socket,subprocess,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

def forbidden(*a,**k): raise AssertionError('No network or subprocess allowed')
class NoSocket(socket.socket):
 def __init__(self,*a,**k): forbidden()
socket.socket=NoSocket;socket.create_connection=forbidden;subprocess.Popen=forbidden
# Parent-authorized import-only stub: these patterns are unused in apply_summaries.
# Avoid importing search adapters and unavailable requests; exercised writer stays real.
import sys, types
stub=types.ModuleType('research_hub.search.abstract_recovery');stub._PLACEHOLDER_PATTERNS=[]
sys.modules['research_hub.search.abstract_recovery']=stub
from research_hub import summarize as s
ENTRY=dict(paper_slug='paper',key_findings=['synthetic finding'],methodology='synthetic method',relevance='synthetic relevance')
results=[]
class Remote:
 def __init__(self,kind,path):self.kind=kind;self.path=path;self.calls=0;self.remote_text='old'
 def children(self,key):return [{'data':dict(key='NOTE0001',version=1,parentItem=key,itemType='note',note='old',tags=[{'tag':'research-hub:summary:v1'}])}]
 def everything(self,x):return x
 def update_item(self,data):
  self.calls+=1;self.remote_text=data['note']
  if self.kind=='human':self.path.write_text('NEW HUMAN ANNOTATION 中文\n',encoding='utf8')
  if self.kind=='false':return False
  if self.kind in ('timeout','human','rollback'):raise TimeoutError('synthetic acknowledgement lost after commit')
  return True

def case(kind):
 with tempfile.TemporaryDirectory(prefix='hub-summary-fault-') as td:
  p=Path(td)/'paper.md';original='## Personal note\n\nOriginal 中文\n';p.write_text(original,encoding='utf8')
  papers=[dict(slug='paper',path=p,zotero_key='PARENT01',title='Synthetic')]
  remote=Remote(kind,p);write=s._write_note_text
  def fail_rollback(path,text):
   if text==original:raise OSError('synthetic rollback ENOSPC')
   return write(path,text)
  with patch.object(s,'_read_cluster_papers_with_abstracts',return_value=papers),patch.object(s,'_write_note_text',fail_rollback if kind=='rollback' else write):
   try:
    result=s.apply_summaries(SimpleNamespace(),'synthetic',[ENTRY],zot=remote)
    data=dict(result=result.to_dict(),raised=None)
   except Exception as e:data=dict(result=None,raised=repr(e))
  data.update(case=kind,calls=remote.calls,remote_committed=remote.remote_text!='old',local_restored=p.read_text()==original,local_text=p.read_text())
  expected=(data['result'] is not None and 'outcome unknown' in ' '.join(data['result']['errors'])) if kind in ('timeout','false') else (data['result'] is not None and any('rollback' in e.lower() for e in data['result']['errors'])) if kind=='rollback' else p.read_text()=='NEW HUMAN ANNOTATION 中文\n'
  data['desired_contract_pass']=expected;results.append(data)
for kind in ['timeout','false','rollback','human']:case(kind)
# Countercase: explicit remote rejection before commit still permits successful local rollback.
with tempfile.TemporaryDirectory(prefix='hub-summary-counter-') as td:
 p=Path(td)/'paper.md';p.write_text('Original note\n');before=p.read_bytes()
 with patch.object(s,'_write_zotero_child_note',side_effect=RuntimeError('synthetic known rejection')):
  outcome=s._apply_one_entry(ENTRY,{'paper':dict(path=p,zotero_key='PARENT01')},{'paper'},object(),True,True)
 assert not outcome.applied and p.read_bytes()==before
 results.append(dict(case='known-rejection-countercase',desired_contract_pass=True))
print(json.dumps(results,ensure_ascii=False,indent=2))
assert all(x['desired_contract_pass'] for x in results),'Synthetic red: requested failure/recovery guarantees not met'
# A rollback error must not hide an independently successful peer's receipt.
with tempfile.TemporaryDirectory(prefix='hub-summary-peers-') as td:
 paths={slug:Path(td)/(slug+'.md') for slug in ('paper','peer')}
 originals={slug:f'Original {slug}\n' for slug in paths}
 for slug,path in paths.items():path.write_text(originals[slug])
 papers=[dict(slug=slug,path=path,zotero_key='PARENT01' if slug=='paper' else 'PARENT02',title=slug) for slug,path in paths.items()]
 class Peers(Remote):
  def update_item(self,data):
   self.calls+=1
   if data['parentItem']=='PARENT01':raise TimeoutError('Synthetic uncertain update')
   return True
 remote=Peers('peer',paths['paper']);write=s._write_note_text
 def failed_compensation(path,text):
  if path==paths['paper'] and text==originals['paper']:raise OSError('Synthetic rollback full disk')
  return write(path,text)
 with patch.object(s,'_read_cluster_papers_with_abstracts',return_value=papers),patch.object(s,'_write_note_text',failed_compensation):
  result=s.apply_summaries(SimpleNamespace(),'synthetic',[ENTRY,{**ENTRY,'paper_slug':'peer'}],zot=remote)
 assert result.applied==['peer'] and len(result.errors)==1
 assert 'outcome unknown' in result.errors[0] and 'rollback unavailable' in result.errors[0]
 assert result.obsidian_writes==result.zotero_writes==1 and remote.calls==2
 assert result.to_dict()['errors']==result.errors
 print(json.dumps({'case':'successful-peer-retained-after-compensation-failure','status':'PASS','result':result.to_dict()}))
# Missing parent never calls remote; even failed local compensation is structured.
with tempfile.TemporaryDirectory(prefix='hub-summary-missing-parent-') as td:
 p=Path(td)/'paper.md';original='Original\n';p.write_text(original);write=s._write_note_text
 def fail_restore(path,text):
  if text==original:raise OSError('Synthetic rollback unavailable')
  return write(path,text)
 with patch.object(s,'_write_note_text',fail_restore):
  outcome=s._apply_one_entry(ENTRY,{'paper':dict(path=p,zotero_key='')},{'paper'},object(),True,True)
 assert not outcome.applied and 'no zotero-key' in outcome.error and 'rollback unavailable' in outcome.error
 print(json.dumps({'case':'missing-parent-compensation-failure','status':'PASS'}))
# Unknown classification must not erase actionable adapter conflict diagnostics.
class Conflict(Remote):
 def update_item(self,data):
  self.calls+=1
  raise RuntimeError('synthetic version conflict')
remote=Conflict('conflict',None)
try:s._write_zotero_child_note(remote,'PARENT01','new')
except RuntimeError as error:
 assert 'version conflict' in str(error) and 'no automatic retry' in str(error)
 assert isinstance(error,s._ZoteroWriteUncertain)
else:raise AssertionError('Unconfirmed conflict accepted')
assert remote.calls==1
print(json.dumps({'case':'conflict-diagnostic-retained-no-retry','status':'PASS'}))
