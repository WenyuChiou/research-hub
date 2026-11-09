"""Synthetic offline fixtures: attribution/plumbing, not publisher validation."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from research_hub.discover import _merge_search_dict_candidates, _search_result_to_candidate, _to_papers_input
from research_hub.search.abstract_recovery import RecoveredAbstract
from research_hub.search.websearch import _result_from_item


@pytest.mark.parametrize('key', ['content', 'description', 'snippet'])
def test_web_excerpt_explicitly_marked(key):
    result = _result_from_item({'title': 'Fixture', key: 'Search excerpt'}, snippet_key=key)
    assert result.abstract == 'Search excerpt'  # Search display remains compatible.
    assert result.abstract_source == 'web-search-snippet'


@pytest.mark.parametrize('incoming_source', ['openalex', 'web-search-snippet', ''])
def test_merge_copies_text_and_source_together(incoming_source):
    rows = [{'title': 'Fixture', 'abstract': '', 'abstract_source': 'stale'},
            {'title': 'Fixture', 'abstract': 'Incoming', 'abstract_source': incoming_source}]
    assert _merge_search_dict_candidates(rows)[0]['abstract_source'] == incoming_source


@pytest.mark.parametrize('source', ['web-search-snippet', ''])
@pytest.mark.parametrize('recovered', [True, False])
def test_web_excerpt_does_not_block_recovery_or_seed_abstract(monkeypatch, source, recovered):
    lookup = Mock(return_value=RecoveredAbstract('Recovered fixture' if recovered else '', 'crossref' if recovered else ''))
    monkeypatch.setattr('research_hub.search.abstract_recovery.recover_abstract', lookup)
    candidate = {'title': 'Fixture', 'doi': '10.1234/fixture', 'source': 'web',
                 'abstract': 'Search excerpt', 'abstract_source': source}
    before = deepcopy(candidate)
    paper = _to_papers_input([candidate], None)[0]
    lookup.assert_called_once_with('10.1234/fixture', timeout=10)
    assert paper['abstract'] == ('Recovered fixture' if recovered else '(no abstract)')
    assert paper['abstract_source'] == ('crossref' if recovered else '')
    assert 'Search excerpt' not in paper['summary']
    assert candidate == before


def test_web_excerpt_without_doi_is_not_abstract(monkeypatch):
    lookup = Mock(side_effect=AssertionError('Unexpected lookup'))
    monkeypatch.setattr('research_hub.search.abstract_recovery.recover_abstract', lookup)
    candidate = _search_result_to_candidate(_result_from_item({'title': 'Fixture', 'content': 'Search excerpt'}))
    paper = _to_papers_input([candidate], None)[0]
    assert paper['abstract'] == '(no abstract)'
    assert paper['abstract_source'] == ''
    lookup.assert_not_called()


@pytest.mark.parametrize('source', ['openalex', ''])
def test_compatible_academic_abstract_is_retained(monkeypatch, source):
    lookup = Mock(side_effect=AssertionError('Unexpected lookup'))
    monkeypatch.setattr('research_hub.search.abstract_recovery.recover_abstract', lookup)
    paper = _to_papers_input([{'title': 'Fixture', 'doi': '10.1234/fixture', 'source': 'openalex',
                             'abstract': 'Observed fixture', 'abstract_source': source}], None)[0]
    assert (paper['abstract'], paper['abstract_source']) == ('Observed fixture', source)
    lookup.assert_not_called()


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('snippet_source', ['web-search-snippet', '', ' '])
@pytest.mark.parametrize('academic_text', ['', 'Observed fixture'])
@pytest.mark.parametrize('merge_kind', ['dict', 'search'])
def test_mixed_merges_keep_abstract_and_origin(monkeypatch, reverse, snippet_source, academic_text, merge_kind):
    from research_hub.search.base import SearchResult
    from research_hub.search._rank import merge_results
    lookup = Mock(side_effect=AssertionError('No DOI, no lookup'))
    monkeypatch.setattr('research_hub.search.abstract_recovery.recover_abstract', lookup)
    rows = [{'title': 'Fixture', 'source': 'web', 'abstract': 'Search excerpt', 'abstract_source': snippet_source},
            {'title': 'Fixture', 'source': 'openalex', 'abstract': academic_text, 'abstract_source': 'openalex' if academic_text else ''}]
    if reverse:
        rows.reverse()
    before = deepcopy(rows)
    if merge_kind == 'dict':
        merged = _merge_search_dict_candidates(rows)[0]
    else:
        results = merge_results({str(i): [SearchResult(**row)] for i, row in enumerate(rows)})
        merged = _search_result_to_candidate(results[0])
    paper = _to_papers_input([merged], None)[0]
    assert paper['abstract'] == (academic_text or '(no abstract)')
    assert paper['abstract_source'] == ('openalex' if academic_text else '')
    assert merged['source'] == rows[0]['source']
    assert rows == before
    lookup.assert_not_called()


@pytest.mark.parametrize('merge_kind', ['dict', 'search'])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('unknown_source', ['', ' '])
def test_web_merge_preserves_unknown_academic_abstract(monkeypatch, merge_kind, reverse, unknown_source):
    from research_hub.search.base import SearchResult
    from research_hub.search._rank import merge_results
    lookup = Mock(side_effect=AssertionError('No lookup'))
    monkeypatch.setattr('research_hub.search.abstract_recovery.recover_abstract', lookup)
    rows = [{'title': 'Fixture', 'source': 'web', 'abstract': 'Search excerpt'},
            {'title': 'Fixture', 'source': 'openalex', 'abstract': 'Observed fixture', 'abstract_source': unknown_source}]
    if reverse:
        rows.reverse()
    if merge_kind == 'dict':
        merged = _merge_search_dict_candidates(rows)[0]
    else:
        merged = _search_result_to_candidate(merge_results({str(i): [SearchResult(**row)] for i, row in enumerate(rows)})[0])
    paper = _to_papers_input([merged], None)[0]
    assert paper['abstract'] == 'Observed fixture'
    assert paper['abstract_source'] == ('' if reverse else 'unknown')
    assert merged['source'] == rows[0]['source']
    lookup.assert_not_called()


@pytest.mark.parametrize('entrypoint', ['cli', 'mcp'])
def test_public_web_outputs_keep_excerpt_marker(monkeypatch, capsys, tmp_path, entrypoint):
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path))
    import json
    result = _result_from_item({'title': 'Fixture', 'content': 'Search excerpt'})
    monkeypatch.setattr('research_hub.search.websearch.WebSearchBackend.search', lambda *a, **kw: [result])
    if entrypoint == 'cli':
        from research_hub.cli import main
        assert main(['websearch', 'fixture', '--provider', 'ddg', '--json']) == 0
        payload = json.loads(capsys.readouterr().out)
    else:
        from research_hub import mcp_server
        from tests._mcp_helpers import _get_mcp_tool
        payload = _get_mcp_tool(mcp_server.mcp, 'web_search').fn(query='fixture', provider='ddg')
    assert payload['ok'] is True
    row = payload['results'][0]
    assert (row['abstract'], row['abstract_source']) == ('Search excerpt', 'web-search-snippet')
    assert _to_papers_input([row], None)[0]['abstract'] == '(no abstract)'
