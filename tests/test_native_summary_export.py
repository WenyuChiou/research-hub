"""Synthetic selected-source transfer; no real Obsidian/Roam acceptance."""
import json
import subprocess
import sys
import pytest
from research_hub.workspace.native_summary import NativeSummary
from research_hub.workspace.service import WorkspaceService
from tests.test_workspace_native_summary import setup, envelope, POSIX




@pytest.mark.skipif(not POSIX, reason="Pinned POSIX source-file reads")
def test_export_preserves_labels_and_binding_without_write(setup):
    w,r,a,text=setup
    n,value=envelope(setup)
    value['sections']['methods'][0].update(status='analyst_inference',reason='Inference only',evidence=[])
    value['sections']['limitations'][0].update(status='unknown',reason='Not established',evidence=[])
    n.import_summary('p',envelope=json.dumps(value))
    before=w.db_path.read_bytes()
    result=WorkspaceService(w.root).dispatch('project','native-summary-export',{'project_id':'p','source_record_id':r['id']})
    assert result['ok'] and result['human_acceptance']=='pending'
    md=result['markdown']
    for expected in ('## Why','## Objective','## Methods','## Findings','## Conclusions','## Key Points','## Limitations','[supported]','[analyst_inference]','[unknown]',value['source_revision'],value['selections'][0]['sha256']):
        assert expected in md
    assert '0:16' in md and '🙂' in md
    assert [line for line in md.splitlines() if line.startswith('## ')][1:] == [
        '## Why', '## Objective', '## Methods', '## Findings', '## Conclusions', '## Key Points', '## Limitations']
    assert w.db_path.read_bytes()==before


@pytest.mark.skipif(not POSIX, reason="Pinned POSIX source-file reads")
def test_export_missing_stale_unavailable_never_leaks(setup):
    w,r,a,text=setup
    n,value=envelope(setup)
    assert not n.export_markdown('p',source_record_id=r['id'])['ok']
    n.import_summary('p',envelope=json.dumps(value))
    original=w.root/'source.txt'; moved=w.root/'moved.txt'; original.rename(moved)
    result=n.export_markdown('p',source_record_id=r['id']); assert result['status']=='unavailable' and result['markdown'] is None
    moved.rename(original);original.write_text('changed')
    result=n.export_markdown('p',source_record_id=r['id']);assert result['status']=='stale' and result['markdown'] is None


@pytest.mark.skipif(not POSIX, reason="Pinned POSIX source-file reads")
def test_export_escapes_source_markup(setup):
    w,r,a,text=setup;n,value=envelope(setup)
    payload='<script>alert(1)</script> ![embed](file:///private) [[Other note]]\n# Heading'
    value['sections']['why'][0]['text']=payload
    n.import_summary('p',envelope=json.dumps(value))
    md=n.export_markdown('p',source_record_id=r['id'])['markdown']
    assert '<script>' not in md and '![embed]' not in md and '[[Other note]]' not in md
    assert '&lt;script&gt;' in md and '\\[\\[Other note\\]\\]' in md


@pytest.mark.skipif(not POSIX, reason="Pinned POSIX source-file reads")
def test_cli_plain_markdown_json_and_stale_failure(setup):
    w,r,a,text=setup;n,value=envelope(setup);n.import_summary('p',envelope=json.dumps(value))
    args=[sys.executable,'-m','research_hub','project','native-summary-export','--root',str(w.root),'--project','p','--source-record-id',r['id']]
    p=subprocess.run(args,text=True,capture_output=True);assert p.returncode==0 and p.stdout.startswith('# Test\n')
    q=subprocess.run(args+['--json'],text=True,capture_output=True);assert q.returncode==0 and json.loads(q.stdout)['markdown']==p.stdout
    (w.root/'source.txt').write_text('changed')
    q=subprocess.run(args,text=True,capture_output=True);assert q.returncode==1 and json.loads(q.stdout)['markdown'] is None


def test_portable_renderer_retains_untrusted_text_and_markers():
    from research_hub.workspace.native_summary_markdown import render
    from research_hub.workspace.native_summary import SECTIONS
    value = {'source': {'title': '<img> [[title]]', 'locator': 'https://example.invalid/a'},
             'reading_scope': 'Synthetic only', 'project_id': 'p', 'source_record_id': 'r',
             'source_revision': 'a' * 64, 'selections': [],
             'sections': {key: [{'text': '![[embed]]', 'status': 'unknown',
                                'reason': 'No evidence', 'evidence': []}] for key in SECTIONS}}
    md = render(value)
    assert '<img>' not in md and '[[embed]]' not in md
    assert md.count('[unknown]') == 7
    assert 'Human acceptance: pending' in md and 'Semantic support: not_assessed' in md


@pytest.mark.parametrize('status', ['missing', 'stale', 'unavailable'])
def test_export_portable_noncurrent_never_returns_prose(monkeypatch, status):
    n = NativeSummary(None)
    monkeypatch.setattr(n, 'read', lambda *a, **k: {'status': status, 'native_summary': {'private': 'must not render'}})
    result = n.export_markdown('p', source_record_id='r')
    assert result['ok'] is False and result['markdown'] is None
    assert 'private' not in json.dumps(result)
