"""Offline storage-contract audit; only synthetic bytes and fake model/remote seams."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import errno
import json
import os
import re
import stat
import threading
import pytest
from research_hub import paper_summarize, summarize
from research_hub.pipeline import _render_obsidian_note, _folder_for_paper, _compose_hub_tags
from research_hub.paper import _parse_frontmatter
from research_hub.zotero.fetch import make_raw_md

EVIDENCE = Path(os.environ['HUB_AUDIT_EVIDENCE']) if os.environ.get('HUB_AUDIT_EVIDENCE') else None
ABSTRACT = ('A synthetic observational survey of 120 households found an association between '
            'trust and adaptation intention. The abstract does not establish causality, '
            'effect magnitude, statistical significance, or generalizability outside this sample.')
ENTRY = {'paper_slug': 'paper', 'summary': 'Trust and adaptation intention were associated.',
         'key_findings': ['Trust and adaptation intention were associated in 120 households.'],
         'methodology': 'An observational household survey.',
         'relevance': 'Evidence about adaptation intentions; no causal claim.'}
RESPONSE = ('SUMMARY: Trust and adaptation intention were associated.\n'
            'KEY_FINDINGS:\n- Trust and adaptation intention were associated in 120 households.\n'
            'METHODOLOGY: An observational household survey.\n'
            'RELEVANCE: Evidence about adaptation intentions; no causal claim.\n')

class Zotero:
    def __init__(self, fail=False):
        self.html = None
        self.fail = fail
    def children(self, key):
        assert key == 'AUDIT001'
        return []
    def everything(self, children):
        return children
    def item_template(self, kind):
        return {'itemType': kind}
    def create_items(self, items):
        if self.fail:
            raise RuntimeError('synthetic remote failure')
        self.html = items[0]['note']
        return {'successful': {'0': {'key': 'NOTE0001'}}}


def note(tmp_path, *, pipeline=True, abstract=ABSTRACT, key='AUDIT001'):
    cfg = SimpleNamespace(raw=tmp_path / 'raw', research_hub_dir=tmp_path / '.research_hub')
    p = cfg.raw / 'flood-adaptation' / 'paper.md'
    p.parent.mkdir(parents=True)
    if pipeline:
        pp = dict(title='Synthetic study', year=2026, journal='Synthetic Journal', doi='10.1000/audit',
                  abstract=abstract, zotero_key=key, summary='[TODO] Synthetic study',
                  key_findings=['[review and extract from Abstract section above]'],
                  methodology='[review abstract; refine after reading PDF]',
                  relevance='[TODO: fill relevance to cluster]', tags=['flood-risk'])
        text = _render_obsidian_note(pp, 'Audit collection', 'flood-adaptation', 'flood trust',
                                     cluster_moc_links=['Water-Resources-MOC'])
    else:
        text = make_raw_md(dict(title='Synthetic study', authors=[], tags=[], year=2026, journal='', doi='',
                                abstract=abstract, key=key), ['Audit collection'], [],
                           topic_cluster='flood-adaptation', moc_links=['Water-Resources-MOC'])
    text += '\n## Personal research notes\n\nKeep my exact 中文 note and $x=1$ unchanged.\n'
    p.write_text(text, encoding='utf-8')
    return cfg, p


def snapshot(name, before, after, details=None):
    if EVIDENCE is None:
        return
    d=EVIDENCE/name
    d.mkdir(exist_ok=True)
    (d/'before.md').write_bytes(before)
    (d/'after.md').write_bytes(after)
    if details is not None:
        (d/'details.json').write_text(json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8")


def test_01_canonical_pending_note_dual_apply_fills_all_sections(tmp_path):
    cfg,p=note(tmp_path)
    before=p.read_bytes()
    zot=Zotero()
    result=summarize.apply_summaries(cfg, 'flood-adaptation', [ENTRY], zot=zot)
    after=p.read_bytes()
    snapshot('canonical-pending',before,after,dict(result=result.to_dict(), zotero_html=zot.html))
    assert result.applied == ['paper']
    assert ENTRY['key_findings'][0] in paper_summarize.extract_markdown_section(after.decode(), 'Key Findings'), 'reported applied but canonical Key Findings pending block was not changed'
    assert 'Summary pending' not in after.decode()


@pytest.mark.parametrize('route', ['cluster', 'pending'])
@pytest.mark.parametrize('formula', [
    r'The fitted coefficient is $\beta = 0.2$; this is not a causal effect.',
    r'Keep $\alpha$, $\theta$, and literal \g<1> unchanged.',
])
def test_02_mathematical_backslashes_survive_actual_note_write(tmp_path, monkeypatch, route, formula):
    cfg,p=note(tmp_path)
    # Ensure old route has matching callouts, independent of the pending-block defect.
    if route=='cluster':
        text=p.read_text(encoding="utf-8").replace('> [!warning] Summary pending\n> Run `research-hub paper summarize --pending` to fill this\n> section from the abstract via paper-summarize.', '> [!success]\n> placeholder', 1)
        p.write_text(text, encoding="utf-8")
    before=p.read_bytes()
    if route=='cluster':
        payload={**ENTRY, 'summary': formula}
        summarize.apply_summaries(cfg, 'flood-adaptation', [payload], write_zotero=False)
    else:
        monkeypatch.setattr(paper_summarize, '_invoke_backend', lambda *a: RESPONSE.replace(ENTRY['summary'], formula))
        paper_summarize.summarize_pending(cfg, backend='codex')
    after=p.read_bytes()
    snapshot('formula-'+route+('-beta' if 'coefficient' in formula else '-alpha'),before,after,{'expected_literal':formula})
    assert formula in after.decode(), 'regex replacement interpreted mathematical backslash as an escape'
    assert b'\x08' not in after


@pytest.mark.parametrize('route', ['cluster', 'pending'])
def test_03_interrupted_summary_write_preserves_original(tmp_path, monkeypatch, route):
    cfg,p=note(tmp_path)
    before=p.read_bytes()
    monkeypatch.setattr(paper_summarize, '_invoke_backend', lambda *a: RESPONSE)
    original_open=Path.open
    original_fdopen=os.fdopen
    class PartialWrite:
        def __init__(self, h): self.h=h
        def __enter__(self): return self
        def __getattr__(self, name): return getattr(self.h, name)
        def __exit__(self,*args): self.h.close()
        def write(self,text):
            self.h.write(text[:47]); self.h.flush()
            raise OSError(errno.ENOSPC, 'synthetic disk-full after actual partial write')
    def faulty_open(path, mode='r', *args, **kwargs):
        handle=original_open(path,mode,*args,**kwargs)
        target = Path(path)
        is_note_write = target == p or (target.parent == p.parent and target.name.startswith(p.name + '.tmp.'))
        return PartialWrite(handle) if is_note_write and mode=='w' else handle
    def faulty_fdopen(fd, *args, **kwargs):
        return PartialWrite(original_fdopen(fd, *args, **kwargs))
    with patch.object(Path, 'open', faulty_open), patch.object(os, 'fdopen', faulty_fdopen):
        try:
            if route == 'pending':
                result = paper_summarize.summarize_pending(cfg, backend='codex')
                assert result[0].action == 'error' and 'synthetic disk-full' in result[0].error
            else:
                result = summarize.apply_summaries(cfg, 'flood-adaptation', [ENTRY], write_zotero=False)
                assert result.applied == [] and 'synthetic disk-full' in result.errors[0]
        except OSError as exc:
            # The unchanged baseline raises; still compare the actual bytes
            # below, so its primary failure is lost data rather than reporting.
            assert 'synthetic disk-full' in str(exc)
    after=p.read_bytes()
    snapshot('interrupted-write-'+route,before,after,{'injected':'ENOSPC after 47 characters flushed', 'before_bytes':len(before),'after_bytes':len(after)})
    assert after==before, 'direct truncating writer destroyed original note on partial write failure'
    assert not list(p.parent.glob(p.name + '.tmp.*'))
    assert not list(p.parent.glob('.' + p.name + '.*.tmp')), 'failed atomic write must clean temporary files'


def test_missing_abstract_never_calls_backend_and_retains_unknowns(tmp_path, monkeypatch):
    cfg,p=note(tmp_path,pipeline=False,abstract='',key='')
    before=p.read_bytes()
    def forbidden(*args): raise AssertionError('real or fake model should not be called for missing abstract')
    monkeypatch.setattr(paper_summarize,'_invoke_backend',forbidden)
    result=paper_summarize.summarize_pending(cfg, backend='codex')
    after=p.read_bytes()
    snapshot('missing-metadata',before,after,{'actions':[r.action for r in result]})
    assert result[0].action=='failed_no_abstract'
    meta=_parse_frontmatter(after.decode())
    assert not meta['doi'] and not meta['zotero-key']
    assert 'Personal research notes' in after.decode()


def test_source_prompt_boundaries_and_success_idempotency(tmp_path, monkeypatch):
    cfg,p=note(tmp_path,pipeline=False)
    before=p.read_bytes()
    prompts=[]
    def fake_backend(backend,prompt):
        prompts.append(prompt); return RESPONSE
    monkeypatch.setattr(paper_summarize,'_invoke_backend',fake_backend)
    first=paper_summarize.summarize_pending(cfg, backend='codex')
    after=p.read_bytes()
    second=paper_summarize.summarize_pending(cfg, backend='codex')
    snapshot('pending-success',before,after,{'actions':[r.action for r in first], 'rerun_count':len(second), 'prompt':prompts[0]})
    assert first[0].action=='done' and second==[] and p.read_bytes()==after
    assert ABSTRACT in prompts[0] and 'ONLY the abstract' in prompts[0]
    assert 'Keep my exact 中文 note and $x=1$ unchanged.' in after.decode()
    meta=_parse_frontmatter(after.decode())
    assert meta['zotero-key']=='AUDIT001' and meta['summarize_source']=='codex'
    assert '[[flood-adaptation/00_overview|flood-adaptation]]' in after.decode()
    assert '[[Water-Resources-MOC]]' in after.decode()


def test_missing_key_and_remote_error_roll_back(tmp_path):
    cfg,p=note(tmp_path,key='')
    before=p.read_bytes()
    r=summarize.apply_summaries(cfg,'flood-adaptation',[ENTRY],zot=Zotero())
    assert r.applied==[] and 'no zotero-key' in r.errors[0] and p.read_bytes()==before
    p.write_text(p.read_text(encoding="utf-8").replace('zotero-key: \n','zotero-key: AUDIT001\n'), encoding="utf-8")
    before=p.read_bytes()
    r=summarize.apply_summaries(cfg,'flood-adaptation',[ENTRY],zot=Zotero(fail=True))
    snapshot('remote-failure-rollback',before,p.read_bytes(),r.to_dict())
    assert r.applied==[] and 'zotero write outcome unknown' in r.errors[0] and p.read_bytes()==before


def test_classification_routes_are_explicit_not_scientific_inference(tmp_path):
    cfg=SimpleNamespace(raw=tmp_path/'raw')
    p={'sub_category':'methods-review','tags':['manual-tag'],'doc_type':'report'}
    assert _folder_for_paper(cfg,p,'flood-adaptation')==cfg.raw/'flood-adaptation'
    assert _folder_for_paper(cfg,p,None)==cfg.raw/'methods-review'
    assert _compose_hub_tags(p,'flood-adaptation')==['manual-tag','research-hub','cluster/flood-adaptation','type/report']


def test_full_ingest_routes_to_selected_cluster_and_repeat_preserves_manual_body(tmp_path,monkeypatch):
    from tests.test_pipeline import _configure, _paper
    from research_hub import pipeline
    from research_hub.clusters import ClusterRegistry
    cfg=_configure(monkeypatch,tmp_path,default_collection='ABCD1234')
    monkeypatch.delenv('RESEARCH_HUB_NO_ZOTERO',raising=False)
    ClusterRegistry(cfg.clusters_file).create(query='flood trust',name='Flood adaptation',
        slug='flood-adaptation',zotero_collection_key='ABCD1234')
    pp=_paper('Synthetic study','paper','10.1000/audit')
    pp['abstract']=ABSTRACT
    pp['sub_category']='different-source-category'
    created=[]
    class FakeClient:
        def item_template(self,kind): return {'itemType':kind}
        def create_items(self,items):
            created.extend(items)
            return {'successful':{str(i):{'key':'AUDIT001'} for i in range(len(items))}}
    monkeypatch.setattr(pipeline,'get_client',lambda:FakeClient())
    monkeypatch.setattr(pipeline,'check_duplicate',lambda *a,**kw:False)
    monkeypatch.setattr(pipeline,'add_note',lambda *a,**kw:True)
    monkeypatch.setattr(pipeline.time,'sleep',lambda _:None)
    input_path=cfg.root/'papers_input.json'
    input_path.write_text(json.dumps([pp]), encoding="utf-8")
    assert pipeline.run_pipeline(cluster_slug='flood-adaptation',query='flood trust')==0
    p=cfg.raw/'flood-adaptation'/'paper.md'
    assert p.is_file() and not (cfg.raw/'different-source-category'/'paper.md').exists()
    text=p.read_text(encoding="utf-8")+'\n## Manual annotation\n\nNever remove this 中文 interpretation.\n'
    p.write_text(text, encoding="utf-8")
    before=p.read_bytes()
    assert pipeline.run_pipeline(cluster_slug='flood-adaptation',query='new evidence query')==0
    after=p.read_bytes()
    snapshot('actual-repeat-ingest',before,after,{'zotero_created_count':len(created),'zotero_items':created})
    assert len(created)==1
    assert re.split(br'\r?\n---\r?\n',before,maxsplit=1)[1]==re.split(br'\r?\n---\r?\n',after,maxsplit=1)[1]
    meta=_parse_frontmatter(after.decode())
    assert meta['zotero-key']=='AUDIT001'
    assert meta['topic_cluster']=='flood-adaptation'
    assert meta['cluster_queries']==['flood trust','new evidence query']
    assert 'topic:flood-adaptation' in meta['tags']
    assert 'cluster/flood-adaptation' in [tag['tag'] for tag in created[0]['tags']]


def test_cluster_apply_preserves_personal_prose_after_managed_callout(tmp_path):
    cfg,p=note(tmp_path)
    text=p.read_text(encoding="utf-8").replace('^findings\n', '^findings\n\nPersonal caveat: missing causal identification; keep 中文.\n')
    text=text.replace('## Personal research notes', '## Summary of other work\n\nDo not overwrite this unrelated section.\n\n## Personal research notes')
    p.write_text(text, encoding="utf-8")
    before=p.read_bytes()
    result=summarize.apply_summaries(cfg,'flood-adaptation',[ENTRY],write_zotero=False)
    after=p.read_bytes()
    snapshot('managed-callout-boundary',before,after,result.to_dict())
    assert result.applied==['paper']
    assert 'Personal caveat: missing causal identification; keep 中文.' in after.decode()
    assert '## Summary of other work\n\nDo not overwrite this unrelated section.' in p.read_text(encoding="utf-8")
    assert after.split(b'## Summary of other work')[1]==before.split(b'## Summary of other work')[1]
    assert after.decode().count('^findings')==1


@pytest.mark.skipif(os.name == 'nt', reason='POSIX permission bits are not a Windows ACL assertion')
@pytest.mark.parametrize('route', ['cluster', 'pending'])
def test_atomic_summary_write_preserves_private_file_mode(tmp_path, monkeypatch, route):
    cfg,p=note(tmp_path)
    p.chmod(0o600)
    monkeypatch.setattr(paper_summarize,'_invoke_backend',lambda *a:RESPONSE)
    if route=='cluster':
        summarize.apply_summaries(cfg,'flood-adaptation',[ENTRY],write_zotero=False)
    else:
        paper_summarize.summarize_pending(cfg,backend='codex')
    assert stat.S_IMODE(p.stat().st_mode)==0o600


def test_duplicate_entries_have_exclusive_atomic_temporary_paths(tmp_path, monkeypatch):
    """No temp collisions or lost outcomes; Windows may reject a concurrent replace."""
    cfg,p=note(tmp_path)
    barrier=threading.Barrier(2)
    original_replace=os.replace
    expected=summarize._replace_obsidian_block(p.read_bytes().decode("utf-8"), summarize.PaperSummary(**ENTRY)).encode("utf-8")
    temporary_paths=[]
    replacement_errors=[]
    def synchronized_replace(src,dst):
        temporary_paths.append(str(src))
        barrier.wait(timeout=5)
        try:
            return original_replace(src,dst)
        except PermissionError as exc:
            replacement_errors.append(exc)
            raise
    monkeypatch.setattr(os,'replace',synchronized_replace)
    result=summarize.apply_summaries(cfg,'flood-adaptation',[ENTRY,ENTRY],write_zotero=False)
    # Windows can deny one simultaneous replace; this contract requires honest
    # per-entry outcomes and intact complete bytes, not dual concurrent success.
    assert result.applied and set(result.applied)=={'paper'}
    assert len(result.applied)+len(result.errors)==2
    assert len(result.errors)==len(replacement_errors)
    for exc in replacement_errors:
        assert os.name=='nt' and exc.winerror in {5,32}
        assert any('obsidian write failed: '+str(exc) in error for error in result.errors)
    assert len(set(temporary_paths))==2
    assert p.read_bytes()==expected
    assert not list(p.parent.glob('.' + p.name + '.*.tmp'))


@pytest.mark.parametrize('route', ['cluster', 'pending'])
def test_replace_permission_failure_preserves_original_and_reports_error(tmp_path, monkeypatch, route):
    cfg,p=note(tmp_path)
    before=p.read_bytes()
    monkeypatch.setattr(paper_summarize,'_invoke_backend',lambda *a:RESPONSE)
    def deny_replace(src,dst):
        assert Path(src).is_file() and Path(dst)==p
        raise PermissionError(errno.EACCES,'synthetic replacement denied')
    monkeypatch.setattr(os,'replace',deny_replace)
    if route=='cluster':
        result=summarize.apply_summaries(cfg,'flood-adaptation',[ENTRY],write_zotero=False)
        assert result.applied==[] and result.obsidian_writes==0
        assert len(result.errors)==1 and 'synthetic replacement denied' in result.errors[0]
    else:
        result=paper_summarize.summarize_pending(cfg,backend='codex')
        assert result[0].action=='error' and 'synthetic replacement denied' in result[0].error
    assert p.read_bytes()==before
    assert not list(p.parent.glob('.' + p.name + '.*.tmp'))


@pytest.mark.parametrize('route', ['cluster', 'pending'])
def test_manual_prose_and_extra_blank_lines_survive_both_summary_routes(tmp_path, monkeypatch, route):
    cfg,p=note(tmp_path)
    original=p.read_text(encoding="utf-8").replace('## Key Findings\n\n','## Key Findings\n\n\n')
    original=original.replace('^findings\n','^findings\n\nPersonal finding caveat: keep exactly 中文.\n')
    original=original.replace('^relevance\n','^relevance\n\n---\nSource-footer manual note stays.\n')
    p.write_text(original, encoding="utf-8")
    monkeypatch.setattr(paper_summarize,'_invoke_backend',lambda *a:RESPONSE)
    if route=='cluster':
        result=summarize.apply_summaries(cfg,'flood-adaptation',[ENTRY],write_zotero=False)
        assert result.applied==['paper']
    else:
        result=paper_summarize.summarize_pending(cfg,backend='codex')
        assert result[0].action=='done'
    after=p.read_text(encoding="utf-8")
    assert 'Summary pending' not in after
    assert 'Personal finding caveat: keep exactly 中文.' in after
    assert '\n---\nSource-footer manual note stays.\n' in after


@pytest.mark.parametrize('route', ['cluster', 'pending'])
def test_unrecognized_manual_section_fails_closed_without_success_or_writes(tmp_path, monkeypatch, route):
    cfg,p=note(tmp_path)
    original=p.read_text(encoding="utf-8")
    start=original.index('## Key Findings')
    end=original.index('## Methodology')
    original=original[:start]+'## Key Findings\n\nMy unmarked handwritten findings must stay.\n\n'+original[end:]
    p.write_text(original, encoding="utf-8")
    before=p.read_bytes()
    monkeypatch.setattr(paper_summarize,'_invoke_backend',lambda *a:RESPONSE)
    if route=='cluster':
        zot=Zotero()
        result=summarize.apply_summaries(cfg,'flood-adaptation',[ENTRY],zot=zot)
        assert result.applied==[] and 'managed callout' in result.errors[0]
        assert zot.html is None
    else:
        result=paper_summarize.summarize_pending(cfg,backend='codex')
        assert result[0].action=='error' and 'managed callout' in result[0].error
    assert p.read_bytes()==before


@pytest.mark.parametrize('route', ['cluster', 'pending'])
def test_crlf_manual_bytes_remain_unchanged(tmp_path, monkeypatch, route):
    cfg,p=note(tmp_path)
    p.write_bytes(p.read_text(encoding="utf-8").replace('\n','\r\n').encode("utf-8"))
    before=p.read_bytes()
    monkeypatch.setattr(paper_summarize,'_invoke_backend',lambda *a:RESPONSE)
    if route=='cluster':
        result=summarize.apply_summaries(cfg,'flood-adaptation',[ENTRY],write_zotero=False)
        assert result.applied==['paper']
    else:
        result=paper_summarize.summarize_pending(cfg,backend='codex')
        assert result[0].action=='done'
    after=p.read_bytes()
    assert after.split(b'## Personal research notes')[1]==before.split(b'## Personal research notes')[1]
    assert b'\n' not in after.replace(b'\r\n',b'')


def test_cluster_report_does_not_claim_success_after_local_write_error(tmp_path, monkeypatch):
    cfg,p=note(tmp_path)
    before=p.read_bytes()
    monkeypatch.setattr('research_hub.llm_cli.invoke_llm_cli',lambda *a:json.dumps({'summaries':[ENTRY]}))
    def fail_write(*args):
        raise OSError(errno.ENOSPC,'synthetic disk full')
    monkeypatch.setattr(summarize,'_write_note_text',fail_write)
    report=summarize.summarize_cluster(cfg,'flood-adaptation',llm_cli='codex',apply=True,write_zotero=False)
    assert report.ok is False and '0 applied' in report.error
    assert report.to_dict()['ok'] is False
    assert report.apply_result.applied==[] and 'synthetic disk full' in report.apply_result.errors[0]
    assert p.read_bytes()==before


def test_cluster_report_preserves_partial_success_without_hiding_failed_entry(tmp_path, monkeypatch):
    cfg,p=note(tmp_path)
    other=p.with_name('second.md')
    other.write_bytes(p.read_bytes())
    original=p.read_text(encoding="utf-8")
    start=original.index('## Key Findings')
    end=original.index('## Methodology')
    p.write_text(original[:start]+'## Key Findings\n\nKeep handwritten finding.\n\n'+original[end:], encoding="utf-8")
    before=p.read_bytes()
    payload={'summaries':[ENTRY,{**ENTRY,'paper_slug':'second'}]}
    monkeypatch.setattr('research_hub.llm_cli.invoke_llm_cli',lambda *a:json.dumps(payload))
    report=summarize.summarize_cluster(cfg,'flood-adaptation',llm_cli='codex',apply=True,write_zotero=False)
    assert report.ok is False
    assert '1 applied' in report.error
    assert report.apply_result.applied==['second']
    assert len(report.apply_result.errors)==1 and 'managed callout' in report.apply_result.errors[0]
    assert p.read_bytes()==before
    assert 'Summary pending' not in other.read_text(encoding="utf-8")
