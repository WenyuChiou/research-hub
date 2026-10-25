"""Synthetic journal foundation only; no provider adapter, model or transport."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from research_hub.summary_journal import SummaryJournal, JournalError, MAX_CANDIDATE_BYTES, MAX_SNAPSHOT_BYTES, MAX_METADATA_BYTES, scope_digest

class JournalTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.j=SummaryJournal(self.root)
  self.source={'reference':'synthetic:abstract','sha256':'a'*64,'coverage':'abstract'}
  self.targets={'local':'raw/cluster/paper.md','zotero':'users:1:parent:PARENT01:summary:v1'}
  self.auth={'kind':'legacy_cli_explicit_apply','reference':'synthetic-invocation','scope_sha256':scope_digest(self.source,self.targets)}
 def reserve(self,op='op-one',j=None,**kw):return (j or self.j).reserve(op,self.source,kw.get('targets',self.targets),kw.get('authorization',self.auth))
 def stage(self,op='op-one',j=None):return (j or self.j).stage(op,b'{"summary":"synthetic"}',before=b'personal\r\nold',after=b'personal\r\nnew')
 def error(self,code,fn):
  with self.assertRaises(JournalError) as c:fn()
  self.assertEqual(c.exception.code,code)
 def test_read_does_not_initialize(self):
  self.assertEqual(self.j.list(),[]);self.assertFalse((self.root/'.research_hub').exists())
 def test_claim_before_generation_and_changed_payload_cannot_bypass(self):
  original=self.reserve();self.error('target_unresolved',lambda:self.reserve('new-op'))
  self.stage();self.error('intent_conflict',lambda:self.j.stage('op-one',b'changed',before=b'x',after=b'y'))
  self.assertEqual(self.j.get('op-one')['authorization'],original['authorization'])
 def test_restart_unknown_no_resend_and_late_ack_bound(self):
  self.reserve();self.stage();d=self.j.dispatch('op-one','zotero');token=d['sinks']['zotero']['dispatch_token']
  reopened=SummaryJournal(self.root);reopened.recover('op-one');self.assertEqual(reopened.get('op-one')['sinks']['zotero']['state'],'unknown')
  self.error('invalid_transition',lambda:reopened.dispatch('op-one','zotero'))
  reopened.observe('op-one','zotero','not_observed');self.assertEqual(reopened.get('op-one')['sinks']['zotero']['state'],'unknown')
  self.error('stale_dispatch',lambda:reopened.acknowledge('op-one','zotero','wrong','confirmed'))
  reopened.acknowledge('op-one','zotero',token,'confirmed');self.assertEqual(reopened.get('op-one')['sinks']['local']['state'],'prepared_unsent')
 def test_completed_lookup_never_replays_and_claims_release_only_all_sinks(self):
  self.reserve();self.stage()
  for sink in self.targets:
   d=self.j.dispatch('op-one',sink);self.j.acknowledge('op-one',sink,d['sinks'][sink]['dispatch_token'],'confirmed')
  self.assertEqual(self.reserve()['id'],'op-one');self.error('invalid_transition',lambda:self.j.dispatch('op-one','local'))
  self.reserve('explicit-new');self.assertEqual(self.j.get('op-one')['sinks']['local']['state'],'confirmed')
 def test_scope_change_rejected_not_human_approval(self):
  self.reserve();self.error('intent_conflict',lambda:self.reserve(targets={'local':'other'},authorization={**self.auth,'scope_sha256':scope_digest(self.source,{'local':'other'})}))
  self.error('invalid_authorization',lambda:self.reserve('fake',authorization={**self.auth,'kind':'workspace_human_approved'}))
 def test_unrelated_personal_edit_does_not_change_authorization(self):
  self.reserve();self.stage();auth=self.j.get('op-one')['authorization'];self.j.observe('op-one','local','preserved_newer');self.assertEqual(self.j.get('op-one')['authorization'],auth)
 def test_size_limits_reject_before_db_write(self):
  self.error('too_large',lambda:self.reserve('large',authorization={**self.auth,'reference':'x'*MAX_METADATA_BYTES}));self.assertFalse(self.j.path.exists())
  self.reserve();before=self.j.get('op-one');self.error('too_large',lambda:self.j.stage('op-one',b'x'*(MAX_CANDIDATE_BYTES+1),before=b'a',after=b'b'));self.assertEqual(before,self.j.get('op-one'))
  self.error('too_large',lambda:self.j.stage('op-one',b'x',before=b'a'*(MAX_SNAPSHOT_BYTES+1),after=b'b'))
 def test_exact_byte_limits_and_unicode(self):
  self.reserve();raw=('😀'*(MAX_CANDIDATE_BYTES//4)).encode();self.j.stage('op-one',raw,before=b'a'*MAX_SNAPSHOT_BYTES,after=b'b');self.assertEqual(self.j.material('op-one','candidate'),raw)
 def test_corrupt_unknown_schema_no_reset(self):
  self.reserve();db=sqlite3.connect(self.j.path);db.execute("UPDATE metadata SET value='99' WHERE name='schema_version'");db.commit();db.close();before=self.j.path.read_bytes();self.error('unsupported_schema',lambda:self.j.get('op-one'));self.assertEqual(before,self.j.path.read_bytes())
 def test_corrupt_material_blocks_dispatch(self):
  self.reserve();self.stage();db=sqlite3.connect(self.j.path);db.execute("UPDATE materials SET content=? WHERE kind='candidate'",(b'changed',));db.commit();db.close();self.error('corrupt_material',lambda:self.j.dispatch('op-one','local'))
 def test_commit_failure_rolls_back_claim_and_no_dispatch(self):
  class Failing(SummaryJournal):
   def _commit(self,db):raise sqlite3.OperationalError('synthetic disk failure')
  self.reserve();self.stage();j=Failing(self.root);self.error('storage_unavailable',lambda:j.dispatch('op-one','local'));self.assertEqual(self.j.get('op-one')['sinks']['local']['state'],'prepared_unsent')
 def test_two_connections_share_target_claim(self):
  self.reserve();other=SummaryJournal(self.root);self.error('target_unresolved',lambda:self.reserve('op-two',j=other));self.assertEqual(len(other.list()),1)
 def test_late_old_observation_cannot_overwrite_new_operation(self):
  self.reserve();self.stage()
  for sink in self.targets:
   d=self.j.dispatch('op-one',sink);self.j.acknowledge('op-one',sink,d['sinks'][sink]['dispatch_token'],'confirmed')
  new=self.reserve('explicit-new');self.j.observe('op-one','zotero','matching_content');self.assertEqual(self.j.get('explicit-new'),new)
 def test_linked_database_rejected(self):
  other=self.root/'other';other.write_bytes(b'untouched');self.j.path.parent.mkdir();self.j.path.symlink_to(other);self.error('unsafe_path',lambda:self.j.list());self.assertEqual(other.read_bytes(),b'untouched')
 def test_concurrent_claim_only_one_winner(self):
  from concurrent.futures import ThreadPoolExecutor
  from threading import Barrier
  barrier=Barrier(2)
  def claim(op):
   barrier.wait(timeout=3)
   try:self.reserve(op,j=SummaryJournal(self.root));return 'reserved'
   except JournalError as e:return e.code
  with ThreadPoolExecutor(max_workers=2) as pool:
   results=list(pool.map(claim,['a','b']))
  self.assertEqual(sorted(results),['reserved','target_unresolved'])
 def test_observations_are_bounded_idempotent_and_do_not_release(self):
  self.reserve();self.j.observe('op-one','zotero','matching_content');self.j.observe('op-one','zotero','matching_content')
  self.assertEqual(len(self.j.observations('op-one')),1)
  self.error('target_unresolved',lambda:self.reserve('still-blocked'))
  self.assertEqual(self.j.get('op-one')['sinks']['zotero']['state'],'prepared_unsent')
 def test_corrupt_boolean_version_rejected(self):
  import json
  self.reserve();body=self.j.get('op-one');body['schema_version']=True
  db=sqlite3.connect(self.j.path);db.execute('UPDATE operations SET body=?',(json.dumps(body),));db.commit();db.close()
  self.error('corrupt_operation',lambda:self.j.get('op-one'))
 def test_changed_note_id_cannot_release_logical_parent(self):
  self.reserve();self.stage();d=self.j.dispatch('op-one','zotero');self.j.recover('op-one');self.j.observe('op-one','zotero','changed')
  changed_source={**self.source,'sha256':'b'*64};auth={**self.auth,'scope_sha256':scope_digest(changed_source,self.targets)}
  self.error('target_unresolved',lambda:self.j.reserve('new-payload',changed_source,self.targets,auth))
 def test_unknown_cannot_be_acknowledged_as_rejection_by_observation(self):
  self.reserve();self.stage();d=self.j.dispatch('op-one','zotero');self.j.recover('op-one')
  self.error('invalid_input',lambda:self.j.acknowledge('op-one','zotero',d['sinks']['zotero']['dispatch_token'],'not_observed'))
  self.assertEqual(self.j.get('op-one')['sinks']['zotero']['state'],'unknown')
 def test_recovery_store_contains_exact_bom_crlf_nonbmp_bytes(self):
  self.reserve();raw='\ufeff😀\r\n'.encode();self.j.stage('op-one',raw,before=raw,after=raw)
  self.assertEqual(self.j.material('op-one','before'),raw)
 def test_persisted_authorization_is_revalidated_before_dispatch(self):
  import json
  mutations=[lambda a:a.update(kind='workspace_human_approved'),lambda a:a.pop('reference'),lambda a:a.update(reference=''),lambda a:a.update(human_approved=True)]
  for index,mutation in enumerate(mutations):
   with self.subTest(index=index),tempfile.TemporaryDirectory() as td:
    j=SummaryJournal(td);self.reserve(j=j);self.stage(j=j);body=j.get('op-one');mutation(body['authorization'])
    with sqlite3.connect(j.path) as db:db.execute('UPDATE operations SET body=?',(json.dumps(body),))
    self.error('corrupt_operation',lambda:j.dispatch('op-one','zotero'))
 def test_persisted_source_and_targets_are_revalidated(self):
  import json
  self.reserve();self.stage();body=self.j.get('op-one');body['source']['coverage']='invented-full-review';body['authorization']['scope_sha256']=scope_digest(body['source'],body['targets'])
  with sqlite3.connect(self.j.path) as db:db.execute('UPDATE operations SET body=?',(json.dumps(body),))
  self.error('corrupt_operation',lambda:self.j.dispatch('op-one','local'))
if __name__=='__main__':unittest.main()
