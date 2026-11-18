"""Offline draft composition; not scientific support or destination acceptance."""
import copy
import hashlib
import json

import pytest

from research_hub.workspace.core import WorkspaceError, encoded
from research_hub.workspace.native_summary import FIELDS, MARKERS, MAX_ENVELOPE, NativeSummary, SECTIONS
from research_hub.workspace.native_summary_handoff import compose
from tests.test_workspace_native_summary import setup, POSIX


def snapshot(text='前🙂 unique quote. 後', start=10):
    sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
    context = {'schema': 'native-source-summary-v1', 'project_id': 'p',
               'source_record_id': 'source', 'source': {'title': 'Paper', 'locator': 'https://example.invalid'},
               'source_revision': 'a'*64, 'expected_revision': 'b'*64,
               'reading_scope': 'Selected synthetic paragraph only',
               'selections': [{'artifact_id': 'a', 'sha256': 'c'*64, 'text_sha256': sha,
                               'start': start, 'end': start+len(text)}],
               'selected_text': {'a': text}, 'coordinate_frame': 'file/python-unicode-codepoints', **MARKERS}
    sections = {section: [{'text': 'An authored claim', 'status': 'supported', 'reason': 'Caller assessment only',
                          'evidence': [{'artifact_id': 'a', 'quote': 'unique quote.'}]}] for section in SECTIONS}
    sections['methods'][0].update(status='analyst_inference', evidence=[])
    sections['limitations'][0].update(status='unknown', evidence=[])
    return context, sections


def test_composer_preserves_binding_labels_and_arguments_without_write():
    c, s = snapshot(); before = copy.deepcopy((c, s))
    result = compose(c, s)
    assert set(result) == FIELDS
    assert result['expected_revision'] == c['expected_revision']
    assert result['source_revision'] == c['source_revision']
    assert result['selections'] == c['selections']
    assert result['reading_scope'] == c['reading_scope']
    assert result['sections']['methods'][0]['status'] == 'analyst_inference'
    assert result['sections']['limitations'][0]['status'] == 'unknown'
    e = result['sections']['why'][0]['evidence'][0]
    assert e == {'artifact_id': 'a', 'quote': 'unique quote.', 'start': 13, 'end': 26}
    assert (c, s) == before
    result['source']['title'] = 'Output mutation'
    result['sections']['why'][0]['text'] = 'Output mutation'
    assert (c, s) == before


def test_explicit_range_disambiguates_repeated_quote_without_repair():
    c, s = snapshot('unique quote. / unique quote.', start=7)
    with pytest.raises(WorkspaceError, match='ambiguous'):
        compose(c, s)
    for items in s.values():
        for item in items:
            for e in item['evidence']:
                e.update(start=23, end=36)
    result = compose(c, s)
    assert result['sections']['why'][0]['evidence'][0]['start'] == 23
    s['why'][0]['evidence'][0]['start'] = 24
    with pytest.raises(WorkspaceError, match='does not match'):
        compose(c, s)


def test_overlapping_matches_are_ambiguous():
    c,s=snapshot('aaaa')
    for items in s.values():
        for i in items:
            for e in i['evidence']: e['quote']='aaa'
    with pytest.raises(WorkspaceError, match='ambiguous'): compose(c,s)


@pytest.mark.parametrize('mutation', [
    lambda c,s: c.update(human_acceptance='accepted'),
    lambda c,s: c.update(semantic_support='verified'),
    lambda c,s: c.update(coordinate_frame='utf-8-bytes'),
    lambda c,s: c.update(saved_at='pretend'),
    lambda c,s: c['selected_text'].update(unselected='extra'),
    lambda c,s: c['selected_text'].update(a='wrong text'),
    lambda c,s: c['selections'][0].update(start=True),
    lambda c,s: c['selections'][0].update(end=999),
    lambda c,s: c['selections'][0].update(text_sha256='f'*64),
    lambda c,s: c['selections'].append(copy.deepcopy(c['selections'][0])),
    lambda c,s: c.update(selections=[]),
    lambda c,s: c.update(source_revision='invalid'),
    lambda c,s: s['why'][0].update(status='verified'),
    lambda c,s: s['why'][0].update(evidence=[]),
    lambda c,s: s['why'][0].pop('reason'),
    lambda c,s: s['why'][0].update(extra='ignored?'),
    lambda c,s: s.pop('findings'),
    lambda c,s: s.update(additional=[]),
    lambda c,s: s['why'][0]['evidence'][0].update(artifact_id='other'),
    lambda c,s: s['why'][0]['evidence'][0].update(quote='absent'),
    lambda c,s: s['why'][0]['evidence'][0].update(quote=' '),
    lambda c,s: s['why'][0]['evidence'][0].update(start=13),
    lambda c,s: s['why'][0]['evidence'][0].update(start=13,end=True),
    lambda c,s: s['why'][0]['evidence'][0].update(path='/outside'),
    lambda c,s: s['why'][0].update(text='nul\x00'),
    lambda c,s: s['why'][0].update(text='\ud800'),
    lambda c,s: s['why'][0].update(text=float('nan')),
])
def test_invalid_context_or_authored_content_fails_closed_without_mutation(mutation):
    c,s=snapshot();mutation(c,s);before=copy.deepcopy((c,s))
    with pytest.raises(WorkspaceError): compose(c,s)
    # Compare serialization for the NaN case (NaN != itself).
    assert json.dumps((c,s),sort_keys=True)==json.dumps(before,sort_keys=True)


def test_quote_does_not_normalize_case_spacing_or_unicode():
    c,s=snapshot('unique  quote. café')
    with pytest.raises(WorkspaceError, match='absent'): compose(c,s)
    s['why'][0]['evidence'][0]['quote']='cafe\u0301'
    with pytest.raises(WorkspaceError, match='absent'): compose(c,s)


def two_artifacts():
    c,s=snapshot('one unique quote.',start=7)
    text='🙂 second unique quote.'
    c['selected_text']['b']=text
    c['selections'].append({'artifact_id':'b','sha256':'d'*64,
                            'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                            'start':100,'end':100+len(text)})
    return c,s


def test_multiple_artifacts_keep_their_own_absolute_coordinate_origins():
    c,s=two_artifacts()
    s['objective'][0]['evidence'][0]['artifact_id']='b'
    value=compose(c,s)
    assert value['sections']['why'][0]['evidence'][0]['start']==11
    assert value['sections']['objective'][0]['evidence'][0]['start']==109


def test_composer_never_searches_a_different_selected_artifact():
    c,s=two_artifacts()
    s['why'][0]['evidence'][0]['quote']='second unique quote.'
    with pytest.raises(WorkspaceError,match='absent'): compose(c,s)


def test_crlf_quotes_are_preserved_not_normalized():
    c,s=snapshot('before\r\nunique quote.\r\nafter',start=2)
    for items in s.values():
        for item in items:
            for e in item['evidence']: e['quote']='\r\nunique quote.\r\n'
    value=compose(c,s)
    e=value['sections']['why'][0]['evidence'][0]
    assert e['quote']=='\r\nunique quote.\r\n' and e['start']==8 and e['end']==25
    s['why'][0]['evidence'][0]['quote']='\nunique quote.\n'
    with pytest.raises(WorkspaceError,match='absent'): compose(c,s)


def test_selected_text_total_limit_is_preserved():
    c,s=snapshot('unique quote.'+'x'*MAX_ENVELOPE)
    with pytest.raises(WorkspaceError) as error: compose(c,s)
    assert error.value.code=='context_limit'


@pytest.mark.parametrize('target',['context','sections'])
def test_initial_size_rejection_keeps_context_limit_code(target):
    c,s=snapshot()
    if target=='context':
        c['selected_text']['a']='x'*(2*MAX_ENVELOPE)
    else:
        s['why'][0]['text']='x'*MAX_ENVELOPE
    with pytest.raises(WorkspaceError) as error: compose(c,s)
    assert error.value.code=='context_limit'


def test_output_budget_includes_added_offsets_and_saved_metadata():
    c,s=snapshot()
    s={name:[{'text':'x','status':'unknown','reason':'Not checked','evidence':[]} for _ in range(12)] for name in SECTIONS}
    value={key:c[key] for key in FIELDS if key!='sections'}
    value['sections']=s
    remaining=MAX_ENVELOPE-2-len(encoded(value).encode('utf-8'))
    for items in s.values():
        for item in items:
            count=min(11999,remaining)
            item['text']+='x'*count
            remaining-=count
    assert remaining==0 and len(encoded(value).encode('utf-8'))==MAX_ENVELOPE-2
    with pytest.raises(WorkspaceError) as error: compose(c,s)
    assert error.value.code=='context_limit'
    s['why'][0]['text']=s['why'][0]['text'][:-200]
    assert compose(c,s)['sections']==s


@pytest.mark.skipif(not POSIX,reason='Existing pinned POSIX file-backed fixture')
def test_composed_envelope_imports_normally_and_live_gate_rejects_stale(setup):
    w,r,a,text=setup
    n=NativeSummary(w)
    c=n.context('p',source_record_id=r['id'],selections=[{'artifact_id':a['id'],'start':0,'end':len(text)}])['context']
    _,s=snapshot()
    for items in s.values():
        for i in items:
            for e in i['evidence']: e.update(artifact_id=a['id'],quote=text[:16])
    before=w.db_path.read_bytes()
    result=compose(c,s)
    assert w.db_path.read_bytes()==before
    saved=n.import_summary('p',envelope=json.dumps(result))['native_summary']
    assert saved['human_acceptance']=='pending' and saved['semantic_support']=='not_assessed'
    assert n.read('p',source_record_id=r['id'])['native_summary']==saved
    before=w.db_path.read_bytes()
    s['why'][0]['text']='A different authored claim'
    stale=compose(c,s)  # Offline composition cannot refresh compare-and-save.
    assert stale['expected_revision']==c['expected_revision']
    with pytest.raises(WorkspaceError) as error:
        n.import_summary('p',envelope=json.dumps(stale))
    assert error.value.code=='stale_input' and w.db_path.read_bytes()==before
    (w.root/'source.txt').write_text('Changed synthetic source',encoding='utf-8')
    with pytest.raises(WorkspaceError): n.import_summary('p',envelope=json.dumps(result))
    assert w.db_path.read_bytes()==before
