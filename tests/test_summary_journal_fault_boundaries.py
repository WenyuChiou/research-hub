"""Actual apply with synthetic sinks; no provider/model/transport acceptance.
Retained independent failure-boundary controls, CI-collected.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3,tempfile
import pytest
from research_hub import summarize
from research_hub.summary_journal import SummaryJournal,JournalError
ENTRY={'paper_slug':'paper','key_findings':['Synthetic finding'],'methodology':'Synthetic method','relevance':'Synthetic scope'}
class Remote:
 library_id='123';library_type='users'
 def __init__(self,lost=False):self.calls=0;self.reads=0;self.lost=lost
 def children(self,key):self.reads+=1;return []
 def everything(self,x):return x
 def item_template(self,kind):return {'itemType':kind}
 def create_items(self,items):
  self.calls+=1
  if self.lost:raise TimeoutError('Synthetic lost acknowledgement')
  return {'successful':{'0':{'key':'SYNTHETIC'}}}
@pytest.fixture
def setup():
 temp=tempfile.TemporaryDirectory(prefix="hub-wiring-independent-");tmp_path=Path(temp.name)
 cfg=SimpleNamespace(root=tmp_path,raw=tmp_path/'raw',research_hub_dir=tmp_path/'.research_hub',zotero_library_id='000123',zotero_library_type='user')
 note=cfg.raw/'cluster/paper.md';note.parent.mkdir(parents=True)
 raw='---\ntitle: Synthetic\nzotero-key: PARENT01\n---\n\n## Abstract\n\nSynthetic selected abstract.\n\n## Personal notes\n\nOriginal 中文\n';note.write_text(raw,encoding='utf-8')
 yield cfg,note,raw
 temp.cleanup()

def apply(cfg,z):return summarize.apply_summaries(cfg,'cluster',[ENTRY],zot=z)

def test_reserve_stage_failure_keeps_identity_and_resume(setup):
 cfg,note,raw=setup;z=Remote()
 with patch.object(SummaryJournal,'stage',side_effect=sqlite3.OperationalError('Synthetic stage commit failure')):first=apply(cfg,z)
 assert first.errors and z.calls==z.reads==0 and note.read_text(encoding='utf-8')==raw
 j=SummaryJournal(cfg.root);op=j.list()[0]['id'];assert j.get(op)['candidate_sha256'] is None
 second=apply(cfg,z);assert second.applied==['paper'] and z.calls==1 and len(j.list())==1 and j.get(op)['id']==op
 assert second.receipts[0]['authorization']==first.receipts[0]['authorization']

def test_numeric_plural_aliases_do_not_bypass_unknown(setup):
 cfg,note,raw=setup;old=Remote(True);first=apply(cfg,old);assert first.errors and old.calls==1
 z=Remote();z.library_type='user';z.library_id='000123';cfg.zotero_library_type='users';cfg.zotero_library_id=123
 again=apply(cfg,z);assert again.errors and z.calls==z.reads==0 and again.receipts[0]['operation_id']==first.receipts[0]['operation_id']

def test_committed_dispatch_reply_lost_never_invokes_sink_or_replays(setup):
 cfg,note,raw=setup;real=SummaryJournal._commit;fired=False
 def commit(j,db):
  nonlocal fired
  row=db.execute("SELECT body FROM operations LIMIT 1").fetchone();body=__import__('json').loads(row[0]) if row else None
  real(j,db)
  if not fired and body and body['sinks']['local']['state']=='dispatching':
   fired=True;raise sqlite3.OperationalError('Synthetic commit succeeded but acknowledgement lost')
 z=Remote()
 with patch.object(SummaryJournal,'_commit',commit):first=apply(cfg,z)
 assert fired and first.errors and z.calls==0 and note.read_text(encoding='utf-8')==raw
 fresh=Remote();second=apply(cfg,fresh);assert second.errors and fresh.calls==fresh.reads==0
 assert SummaryJournal(cfg.root).list()[0]['sinks']['local']['state']=='unknown'



def test_corrupt_staged_material_blocks_actual_apply_without_destination_io(setup):
 cfg,note,raw=setup;z=Remote()
 with patch.object(SummaryJournal,'dispatch',side_effect=JournalError('Synthetic predispatch stop','storage_unavailable')):
  first=apply(cfg,z)
 assert first.errors and z.calls==z.reads==0 and note.read_text(encoding='utf-8')==raw
 j=SummaryJournal(cfg.root);body=j.list()[0]
 with sqlite3.connect(j.path) as db:
  db.execute("UPDATE materials SET content=? WHERE kind='candidate'",(b'corrupt synthetic material',))
 before=j.path.read_bytes();fresh=Remote();again=apply(cfg,fresh)
 assert again.errors and fresh.calls==fresh.reads==0 and note.read_text(encoding='utf-8')==raw
 assert j.path.read_bytes()==before
 assert again.receipts[0]['operation_id']==body['id']
