"""Actual apply consumer + durable journal with synthetic provider seams only."""
import tempfile,unittest,sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from research_hub import summarize
from research_hub.summary_journal import SummaryJournal
ENTRY={'paper_slug':'paper','key_findings':['Synthetic finding'],'methodology':'Synthetic method','relevance':'Synthetic relevance'}
class FakeZotero:
 library_id='123';library_type='user'
 def __init__(self,mode='ok',edit=None):self.mode=mode;self.writes=0;self.reads=0;self.edit=edit
 def children(self,key):self.reads+=1;return []
 def everything(self,children):return children
 def item_template(self,kind):return {'itemType':kind}
 def create_items(self,items):
  self.writes+=1
  if self.edit:self.edit()
  if self.mode=='lost':raise TimeoutError('synthetic lost acknowledgement')
  return {'successful':{'0':{'key':'SYNTHNOTE'}}}
class ApplyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.cfg=SimpleNamespace(root=self.root,raw=self.root/'raw',research_hub_dir=self.root/'.research_hub',zotero_library_id='123',zotero_library_type='user')
  self.note=self.cfg.raw/'cluster/paper.md';self.note.parent.mkdir(parents=True);self.original='---\ntitle: Synthetic\nzotero-key: PARENT01\n---\n\n## Abstract\n\nSelected synthetic abstract.\n\n## Key Findings\n\n> [!success]\n> [TODO]\n^findings\n\n## Personal notes\n\nKeep exact 中文.\n';self.note.write_text(self.original,encoding='utf-8')
 def apply(self,z=None,**kwargs):return summarize.apply_summaries(self.cfg,'cluster',[ENTRY],zot=z or FakeZotero(),**kwargs)
 def test_unknown_restart_blocks_replay_before_provider_or_local_write(self):
  z=FakeZotero('lost');first=self.apply(z);self.assertTrue(first.errors);self.assertEqual(z.writes,1)
  second=FakeZotero();result=self.apply(second);self.assertEqual(second.writes,0);self.assertEqual(second.reads,0);self.assertTrue(result.errors)
  self.assertEqual(self.note.read_text(encoding='utf-8'),self.original);rows=SummaryJournal(self.root).list();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['sinks']['zotero']['state'],'unknown')
 def test_predispatch_durability_failure_prevents_destination_io(self):
  z=FakeZotero()
  with patch.object(SummaryJournal,'_commit',side_effect=sqlite3.OperationalError('synthetic disk failure')):result=self.apply(z)
  self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertEqual(self.note.read_text(encoding='utf-8'),self.original)
 def test_confirmed_receipt_replay_is_read_only(self):
  z=FakeZotero();first=self.apply(z);self.assertEqual(first.applied,['paper']);self.assertTrue(first.to_dict().get('receipts'))
  second=FakeZotero();again=self.apply(second);self.assertEqual(second.writes,0);self.assertEqual(second.reads,0);self.assertTrue(again.to_dict().get('receipts'))
 def test_newer_personal_edit_is_distinct_from_remote_unknown(self):
  z=FakeZotero('lost',lambda:self.note.write_text(self.note.read_text(encoding='utf-8')+'\nHuman newer text\n',encoding='utf-8'))
  result=self.apply(z);self.assertTrue(result.errors);self.assertIn('Human newer text',self.note.read_text(encoding='utf-8'))
  receipt=result.to_dict()['receipts'][0];self.assertEqual(receipt['sinks']['zotero']['state'],'unknown');self.assertIn('preserved_newer',[o['status'] for o in receipt['observations']])
 def test_account_free_local_only_has_no_remote_call(self):
  z=FakeZotero();result=self.apply(z,write_zotero=False);self.assertEqual(result.applied,['paper'],result.to_dict());self.assertEqual(z.writes,0);self.assertEqual(z.reads,0);self.assertEqual(set(result.to_dict()['receipts'][0]['sinks']),{'local'})
 def test_both_disabled_does_not_initialize_journal(self):
  self.apply(write_zotero=False,write_obsidian=False);self.assertFalse(SummaryJournal(self.root).path.exists());self.assertEqual(self.note.read_text(encoding='utf-8'),self.original)
 def test_changed_candidate_cannot_bypass_unknown_target(self):
  self.apply(FakeZotero('lost'));z=FakeZotero();result=summarize.apply_summaries(self.cfg,'cluster',[{**ENTRY,'methodology':'different'}],zot=z);self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertEqual(z.reads,0)
 def test_missing_remote_identity_fails_before_local_write(self):
  z=FakeZotero();z.library_id=None;self.cfg.zotero_library_id=None
  result=self.apply(z);self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertEqual(self.note.read_text(encoding='utf-8'),self.original)
 def test_changed_configured_destination_fails_closed(self):
  z=FakeZotero();z.library_id='other';result=self.apply(z);self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertEqual(self.note.read_text(encoding='utf-8'),self.original)
 def test_oversized_candidate_rejects_without_claim(self):
  z=FakeZotero();result=summarize.apply_summaries(self.cfg,'cluster',[{**ENTRY,'methodology':'x'*100001}],zot=z)
  self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertFalse(SummaryJournal(self.root).path.exists());self.assertEqual(self.note.read_text(encoding='utf-8'),self.original)
 def test_positive_ack_persistence_failure_is_not_write_failure(self):
  real=SummaryJournal.acknowledge
  def fail(j,op,sink,token,outcome):
   if sink=='zotero':raise sqlite3.OperationalError('synthetic receipt lost')
   return real(j,op,sink,token,outcome)
  z=FakeZotero()
  with patch.object(SummaryJournal,'acknowledge',fail):result=self.apply(z)
  self.assertEqual(z.writes,1);self.assertTrue(result.errors);self.assertIn('reconciliation',result.errors[0]);self.assertNotEqual(self.note.read_text(encoding='utf-8'),self.original)
  again=FakeZotero();self.apply(again);self.assertEqual(again.writes,0)
 def test_compensation_failure_preserves_distinct_observation(self):
  real=summarize._write_note_text;calls=[]
  def write(path,text):
   calls.append(text)
   if len(calls)>1:raise OSError('synthetic compensation failure')
   return real(path,text)
  with patch.object(summarize,'_write_note_text',write):result=self.apply(FakeZotero('lost'))
  self.assertTrue(result.errors);receipt=result.to_dict()['receipts'][0];self.assertIn('compensation_unknown',[o['status'] for o in receipt['observations']]);self.assertEqual(receipt['sinks']['zotero']['state'],'unknown')
 def test_remote_claim_commit_failure_prevents_remote_write(self):
  real=SummaryJournal.dispatch
  def dispatch(j,op,sink):
   if sink=='zotero':raise sqlite3.OperationalError('synthetic predispatch persistence failure')
   return real(j,op,sink)
  z=FakeZotero()
  with patch.object(SummaryJournal,'dispatch',dispatch):result=self.apply(z)
  self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertEqual(self.note.read_text(encoding='utf-8'),self.original)
 def test_actual_cli_consumer_retains_cli_scope_and_receipt(self):
  import contextlib,io,json
  from research_hub import cli,llm_cli
  from research_hub.zotero import client
  z=FakeZotero('lost');out=io.StringIO();err=io.StringIO()
  with patch.object(cli,'get_config',return_value=self.cfg),patch.object(llm_cli,'invoke_llm_cli',return_value=json.dumps({'summaries':[ENTRY]})) as model,patch.object(client,'get_client',return_value=z):
   with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):rc=cli.main(['summarize','--cluster','cluster','--llm-cli','synthetic','--apply'])
  self.assertEqual(rc,1);self.assertEqual(model.call_count,1);self.assertIn('receipt ',out.getvalue(),{'stdout':out.getvalue(),'stderr':err.getvalue()});self.assertEqual(SummaryJournal(self.root).list()[0]['authorization']['kind'],'legacy_cli_explicit_apply')
 def test_actual_mcp_callable_consumer_retains_scope_no_human_promotion(self):
  from research_hub import config,mcp_server
  from research_hub.zotero import client
  z=FakeZotero('lost')
  with patch.object(config,'get_config',return_value=self.cfg),patch.object(client,'get_client',return_value=z):result=mcp_server.apply_cluster_summaries('cluster',{'summaries':[ENTRY]})
  self.assertTrue(result['errors']);self.assertIn('receipts',result,{'errors':result.get('errors')});self.assertEqual(result['receipts'][0]['authorization']['kind'],'legacy_mcp_apply_invocation');self.assertEqual(z.writes,1)
 def test_cross_transport_replay_retains_original_authorization(self):
  self.apply(provenance='legacy_cli_explicit_apply');z=FakeZotero();result=self.apply(z,provenance='legacy_mcp_apply_invocation')
  self.assertFalse(result.errors);self.assertEqual(z.writes,0);self.assertEqual(result.receipts[0]['authorization']['kind'],'legacy_cli_explicit_apply')
 def test_reserved_but_unstaged_local_intent_can_resume_without_new_identity(self):
  z=FakeZotero()
  with patch.object(SummaryJournal,'stage',side_effect=sqlite3.OperationalError('synthetic stage failure')):first=self.apply(z)
  self.assertTrue(first.errors);self.assertEqual(z.writes,0);old=SummaryJournal(self.root).list()[0]['id']
  result=self.apply(z);self.assertEqual(result.applied,['paper'],result.to_dict());self.assertEqual(z.writes,1);self.assertEqual(SummaryJournal(self.root).list()[0]['id'],old)
 def test_late_remote_ack_does_not_mark_compensated_local_sink_satisfied(self):
  self.apply(FakeZotero('lost'));journal=SummaryJournal(self.root);body=journal.list()[0]
  journal.acknowledge(body['id'],'zotero',body['sinks']['zotero']['dispatch_token'],'confirmed')
  z=FakeZotero();result=self.apply(z);self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertEqual(self.note.read_text(encoding='utf-8'),self.original)
  self.assertEqual(result.receipts[0]['sinks']['local']['state'],'compensated')
 def test_real_pyzotero_identity_with_fake_public_write_method(self):
  # Constructor/identity compatibility, NOT HTTP transport acceptance. Avoid
  # private httpx/httpx2 module imports that differ across supported SDKs.
  from pyzotero.zotero import Zotero
  import os,socket
  # Constructor-only offline fixture: no proxy use or socket connection is
  # permitted; public write method below is mocked before any apply call.
  proxy_names={'http_proxy','https_proxy','all_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'}
  environment={k:v for k,v in os.environ.items() if k not in proxy_names}
  with patch.dict(os.environ,environment,clear=True),patch.object(socket.socket,'connect',side_effect=AssertionError('No SDK network in identity test')):
   z=Zotero('123','user','synthetic-not-a-real-key')
  self.addCleanup(z.client.close)
  self.assertEqual(str(z.library_id),'123')
  self.assertIn(z.library_type,{'user','users'})
  with patch.object(z,'children',return_value=[]),patch.object(z,'everything',side_effect=lambda v:v),patch.object(z,'item_template',return_value={'itemType':'note'}),patch.object(z,'create_items',return_value={'successful':{'0':{'key':'SYNTHNOTE'}}}) as create:
   result=self.apply(z)
  self.assertEqual(result.applied,['paper'],result.to_dict())
  create.assert_called_once()
  payload=create.call_args.args[0]
  self.assertEqual(payload[0]['parentItem'],'PARENT01')
  self.assertEqual(payload[0]['tags'],[{'tag':'research-hub:summary:v1'}])
  self.assertEqual(result.receipts[0]['sinks']['zotero']['state'],'confirmed')
 def test_exact_lf_crlf_snapshots_and_account_free_apply(self):
  for newline in ('\n','\r\n'):
   with self.subTest(newline=repr(newline)),tempfile.TemporaryDirectory() as td:
    root=Path(td);cfg=SimpleNamespace(root=root,raw=root/'raw',research_hub_dir=root/'.research_hub')
    path=cfg.raw/'cluster/paper.md';path.parent.mkdir(parents=True)
    raw=self.original.replace('\n',newline).encode('utf-8');path.write_bytes(raw)
    result=summarize.apply_summaries(cfg,'cluster',[ENTRY],write_zotero=False)
    self.assertEqual(result.applied,['paper'],result.to_dict())
    journal=SummaryJournal(root);body=journal.list()[0]
    self.assertEqual(journal.material(body['id'],'before'),raw)
    self.assertEqual(journal.material(body['id'],'after'),path.read_bytes())
    self.assertIn(('Keep exact 中文.'+newline).encode('utf-8'),path.read_bytes())
    self.assertNotIn(b'\r\r\n',path.read_bytes())
 def test_old_private_schema_is_rejected_without_migration(self):
  self.apply(FakeZotero('lost'));j=SummaryJournal(self.root)
  with sqlite3.connect(j.path) as db:db.execute("UPDATE metadata SET value='1' WHERE name='schema_version'")
  before=j.path.read_bytes();z=FakeZotero();result=self.apply(z);self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertEqual(j.path.read_bytes(),before)
 def test_original_write_ack_cannot_clear_newer_compensation_uncertainty(self):
  real=summarize._write_note_text;writes=[]
  def write(path,text):
   writes.append(text);real(path,text)
   if len(writes)==2:raise OSError('synthetic compensation committed with lost reply')
  with patch.object(summarize,'_write_note_text',write):self.apply(FakeZotero('lost'))
  self.assertEqual(self.note.read_text(encoding='utf-8'),self.original);j=SummaryJournal(self.root);body=j.list()[0]
  j.acknowledge(body['id'],'local',body['sinks']['local']['dispatch_token'],'confirmed')
  self.assertEqual(j.get(body['id'])['sinks']['local']['state'],'unknown')
  j.acknowledge(body['id'],'zotero',body['sinks']['zotero']['dispatch_token'],'confirmed')
  result=self.apply(FakeZotero());self.assertTrue(result.errors);self.assertEqual(j.get(body['id'])['sinks']['local']['state'],'unknown')
 def test_conflict_receipt_read_failure_preserves_original_operation_identity(self):
  from research_hub import summary_apply_journal
  from research_hub.summary_journal import JournalError
  first=self.apply(FakeZotero('lost'));original_id=first.receipts[0]['operation_id'];z=FakeZotero()
  with patch.object(summary_apply_journal,'_receipt',side_effect=JournalError('synthetic receipt read failure','storage_unavailable')):
   result=summarize.apply_summaries(self.cfg,'cluster',[{**ENTRY,'methodology':'different candidate'}],zot=z)
  self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertEqual(z.reads,0)
  self.assertEqual(result.receipts[0]['operation_id'],original_id)
  self.assertTrue(result.receipts[0]['dispatch_may_have_started'])
 def test_unreadable_same_identity_never_claims_prior_dispatch_was_unsent(self):
  from research_hub.summary_journal import JournalError
  first=self.apply(FakeZotero('lost'));old=first.receipts[0]['operation_id'];z=FakeZotero()
  with patch.object(SummaryJournal,'lookup_for_apply',side_effect=JournalError('synthetic read failure','storage_unavailable')),patch.object(SummaryJournal,'recover',side_effect=JournalError('synthetic read failure','storage_unavailable')):
   result=self.apply(z)
  self.assertTrue(result.errors);self.assertEqual(z.writes,0);self.assertEqual(z.reads,0)
  self.assertEqual(result.receipts[0]['operation_id'],old)
  self.assertTrue(result.receipts[0]['dispatch_may_have_started'])
  self.assertFalse(result.receipts[0]['current_attempt_dispatched'])
  self.assertIn('requires reconciliation',result.errors[0])
if __name__=='__main__':unittest.main()
