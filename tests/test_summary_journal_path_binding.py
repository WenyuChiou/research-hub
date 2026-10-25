"""Synthetic ancestor alias model; not native Windows/macOS acceptance."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import pytest
from research_hub import summarize
from research_hub.summary_journal import SummaryJournal

ENTRY={'paper_slug':'paper','key_findings':['Synthetic finding'],'methodology':'Synthetic method','relevance':'Synthetic scope'}
RAW=b'---\ntitle: Synthetic\n---\n\n## Abstract\n\nSynthetic abstract.\n\n## Personal notes\n\nUntouched human text.\n'

def fixture(tmp_path):
    real=tmp_path/'real-parent';real.mkdir()
    alias=tmp_path/'alias-parent'
    try:alias.symlink_to(real,target_is_directory=True)
    except OSError as exc:
        if getattr(exc,'winerror',None)==1314:pytest.skip('Synthetic ancestor symlink unavailable without privilege')
        raise
    root=alias/'selected';raw=root/'raw';path=raw/'cluster/paper.md';path.parent.mkdir(parents=True);path.write_bytes(RAW)
    return SimpleNamespace(root=root,raw=raw,research_hub_dir=root/'.research_hub'),path

def test_approved_ancestor_alias_applies_with_canonical_identity_and_no_replay(tmp_path):
    cfg,path=fixture(tmp_path)
    result=summarize.apply_summaries(cfg,'cluster',[ENTRY],write_zotero=False)
    assert result.applied==['paper'],result.to_dict()
    journal=SummaryJournal(cfg.root);body=journal.list()[0]
    assert body['targets']['local']==str(path.resolve())
    assert journal.material(body['id'],'before')==RAW
    after=path.read_bytes();assert b'Untouched human text.' in after
    canonical=SimpleNamespace(root=cfg.root.resolve(),raw=cfg.raw.resolve(),research_hub_dir=cfg.research_hub_dir.resolve())
    replay=summarize.apply_summaries(canonical,'cluster',[ENTRY],write_zotero=False)
    assert replay.skipped and not replay.errors and path.read_bytes()==after
    assert replay.receipts[0]['operation_id']==body['id']

@pytest.mark.parametrize('kind',['outside','prefix-sibling','traversal','leaf-link','inside-link','directory-link','raw-link','raw-reparse'])
def test_alias_repair_never_admits_unselected_or_linked_source(tmp_path,monkeypatch,kind):
    from unittest.mock import Mock
    import stat
    cfg,path=fixture(tmp_path)
    outside=tmp_path/'outside.md';outside.write_bytes(RAW)
    chosen=path
    if kind=='outside':chosen=outside
    elif kind=='prefix-sibling':
        chosen=cfg.raw.with_name('raw-extra')/'paper.md';chosen.parent.mkdir();chosen.write_bytes(RAW)
    elif kind=='traversal':chosen=cfg.raw/'cluster'/'..'/'cluster'/'paper.md'
    elif kind in {'leaf-link','inside-link'}:
        chosen=path.with_name('linked.md');chosen.symlink_to(outside if kind=='leaf-link' else path)
    elif kind=='directory-link':
        linked=cfg.raw/'linked';linked.symlink_to(outside.parent,target_is_directory=True);chosen=linked/outside.name
    elif kind=='raw-link':
        linked=cfg.root/'raw-alias';linked.symlink_to(cfg.raw.resolve(),target_is_directory=True);cfg.raw=linked;chosen=linked/'cluster/paper.md'
    elif kind=='raw-reparse':
        original=Path.lstat
        def lstat(p,*args,**kwargs):
            if p==cfg.raw.absolute():return SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0x400)
            return original(p,*args,**kwargs)
        monkeypatch.setattr(Path,'lstat',lstat)
    # Bypass only inventory reads to deliver an adversarial synthetic path to
    # actual apply; production inventory's earlier reads are not covered here.
    monkeypatch.setattr(summarize,'_read_cluster_papers_with_abstracts',lambda *a,**k:[{'slug':'paper','path':chosen,'abstract':'Synthetic abstract.','title':'Synthetic'}])
    write=Mock(side_effect=AssertionError('Rejected path must not dispatch'))
    monkeypatch.setattr(summarize,'_write_note_text',write)
    result=summarize.apply_summaries(cfg,'cluster',[ENTRY],write_zotero=False)
    assert result.errors and not result.applied,result.to_dict()
    assert write.call_count==0 and outside.read_bytes()==RAW and path.read_bytes()==RAW
    assert not SummaryJournal(cfg.root).path.exists()

def test_canonical_inventory_path_under_approved_alias_is_same_target(tmp_path,monkeypatch):
    cfg,path=fixture(tmp_path)
    monkeypatch.setattr(summarize,'_read_cluster_papers_with_abstracts',lambda *a,**k:[{'slug':'paper','path':path.resolve(),'abstract':'Synthetic abstract.','title':'Synthetic'}])
    result=summarize.apply_summaries(cfg,'cluster',[ENTRY],write_zotero=False)
    assert result.applied==['paper'],result.to_dict()
    body=SummaryJournal(cfg.root).list()[0]
    assert body['targets']['local']==str(path.resolve())
    assert SummaryJournal(cfg.root).material(body['id'],'before')==RAW
