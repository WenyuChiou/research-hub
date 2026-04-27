"""v0.68.5 — bibliographic locator fields (volume, issue, pages) must
flow end-to-end from search backend → SearchResult → papers_input dict.

Real incident: 8 ingested flood-relocation papers all had empty
volume/issue/pages in Zotero + Obsidian, even though OpenAlex and
Crossref returned the data. Root cause: SearchResult dataclass had no
fields for them, so backends couldn't populate even if they wanted to.

Tests target each integration point:
  1. SearchResult dataclass exposes the three fields
  2. Each of the 4 backends extracts them when present in API response
  3. _to_papers_input propagates them into the ingest dict
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from research_hub.discover import _to_papers_input
from research_hub.search.base import SearchResult
from research_hub.search.crossref import CrossrefBackend
from research_hub.search.openalex import OpenAlexBackend
from research_hub.search.arxiv_backend import ArxivBackend


def test_searchresult_dataclass_has_volume_issue_pages_fields():
    """v0.68.5: dataclass must expose the 3 new bibliographic fields with
    str defaults (not None — downstream writers expect strings)."""
    r = SearchResult(title="x")
    assert r.volume == ""
    assert r.issue == ""
    assert r.pages == ""

    r2 = SearchResult(title="x", volume="45", issue="3", pages="123-145")
    assert r2.volume == "45"
    assert r2.issue == "3"
    assert r2.pages == "123-145"


def test_openalex_extracts_volume_issue_pages_from_biblio():
    """OpenAlex returns biblio.{volume,issue,first_page,last_page};
    parser must combine first_page + last_page into 'first-last' form."""
    client = OpenAlexBackend()
    work = {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1/test",
        "title": "Sample paper",
        "publication_year": 2024,
        "authorships": [],
        "primary_location": {"source": {"display_name": "Journal X"}},
        "locations": [],
        "open_access": {"is_oa": False},
        "type": "article",
        "biblio": {
            "volume": "45",
            "issue": "3",
            "first_page": "123",
            "last_page": "145",
        },
    }
    result = client._parse_work(work)
    assert result.volume == "45"
    assert result.issue == "3"
    assert result.pages == "123-145"


def test_openalex_handles_single_page_biblio():
    """When first_page == last_page or last_page is missing, emit just
    the first_page (no spurious 'X-X' or 'X-' form)."""
    client = OpenAlexBackend()
    work_single = {
        "title": "x", "biblio": {"first_page": "42", "last_page": ""},
        "open_access": {}, "primary_location": {},
    }
    assert client._parse_work(work_single).pages == "42"

    work_same = {
        "title": "x", "biblio": {"first_page": "42", "last_page": "42"},
        "open_access": {}, "primary_location": {},
    }
    assert client._parse_work(work_same).pages == "42"


def test_openalex_select_param_includes_biblio():
    """The biblio block must be in the API request `select`, otherwise
    OpenAlex won't return it and the parser sees nothing."""
    import inspect
    src = inspect.getsource(OpenAlexBackend.search)
    assert "biblio" in src, "OpenAlex search() must request 'biblio' in select"


def test_crossref_extracts_volume_issue_pages_from_response():
    """Crossref returns volume/issue as strings + page in canonical
    'first-last' form (already collapsed)."""
    client = CrossrefBackend()
    work = {
        "DOI": "10.1/test",
        "title": ["A paper"],
        "author": [{"family": "Doe", "given": "Jane"}],
        "issued": {"date-parts": [[2024]]},
        "container-title": ["Journal Y"],
        "type": "journal-article",
        "is-referenced-by-count": 5,
        "volume": "12",
        "issue": "4",
        "page": "200-215",
    }
    result = client._parse_work(work)
    assert result.volume == "12"
    assert result.issue == "4"
    assert result.pages == "200-215"


def test_crossref_select_param_includes_volume_issue_page():
    import inspect
    src = inspect.getsource(CrossrefBackend.search)
    for token in ("volume", "issue", "page"):
        assert token in src, f"Crossref search() must request {token!r} in select"


def test_crossref_handles_missing_locator_fields():
    """Some Crossref entries have no volume/issue/page — must default to ''."""
    client = CrossrefBackend()
    work = {
        "DOI": "10.1/x", "title": ["x"], "author": [],
        "issued": {"date-parts": [[2024]]}, "container-title": [],
        "type": "journal-article",
    }
    result = client._parse_work(work)
    assert result.volume == ""
    assert result.issue == ""
    assert result.pages == ""


def test_semantic_scholar_extracts_volume_pages_from_journal_block():
    """S2 returns journal.{volume,pages} when available. issue is not
    exposed by S2's schema; leave it ''."""
    item = {
        "title": "Some paper",
        "abstract": "Abstract",
        "year": 2024,
        "authors": [{"name": "Jane Doe"}],
        "externalIds": {"DOI": "10.1/test"},
        "venue": "J",
        "journal": {"volume": "10", "pages": "1-20", "name": "J"},
    }
    result = SearchResult.from_s2_json(item)
    assert result.volume == "10"
    assert result.pages == "1-20"
    assert result.issue == ""  # S2 doesn't expose issue


def test_semantic_scholar_handles_missing_journal_block():
    """When S2 omits journal entirely, all 3 fields default to ''."""
    item = {"title": "x", "externalIds": {}}
    result = SearchResult.from_s2_json(item)
    assert result.volume == ""
    assert result.issue == ""
    assert result.pages == ""


def test_arxiv_extracts_pages_from_comment_when_matches_pattern():
    """arXiv has no journal volume/issue. The arxiv:comment field
    sometimes carries '<n> pages' which is the closest analog."""
    xml = """<entry xmlns="http://www.w3.org/2005/Atom"
                   xmlns:arxiv="http://arxiv.org/schemas/atom">
      <id>http://arxiv.org/abs/2401.12345v1</id>
      <title>Sample preprint</title>
      <summary>An abstract.</summary>
      <published>2024-01-15T00:00:00Z</published>
      <arxiv:comment>12 pages, 5 figures, NeurIPS 2024 submission</arxiv:comment>
    </entry>"""
    entry = ET.fromstring(xml)
    client = ArxivBackend()
    result = client._parse_entry(entry)
    assert result is not None
    assert result.pages == "12"
    # arXiv preprints have no journal volume/issue
    assert result.volume == ""
    assert result.issue == ""


def test_arxiv_pages_empty_when_comment_has_no_page_count():
    xml = """<entry xmlns="http://www.w3.org/2005/Atom"
                   xmlns:arxiv="http://arxiv.org/schemas/atom">
      <id>http://arxiv.org/abs/2401.99999v1</id>
      <title>x</title>
      <summary>x</summary>
      <published>2024-01-01T00:00:00Z</published>
      <arxiv:comment>preliminary draft, comments welcome</arxiv:comment>
    </entry>"""
    entry = ET.fromstring(xml)
    client = ArxivBackend()
    result = client._parse_entry(entry)
    assert result.pages == ""


def test_to_papers_input_propagates_volume_issue_pages():
    """End-to-end: a candidate with all 3 locator fields must surface
    them in the ingest dict that pipeline.run_pipeline reads."""
    candidate = {
        "title": "Paper",
        "doi": "10.1/x",
        "authors": ["Jane Doe"],
        "year": 2024,
        "abstract": "abstract",
        "venue": "Journal Z",
        "source": "openalex",
        "volume": "45",
        "issue": "3",
        "pages": "123-145",
    }
    [entry] = _to_papers_input([candidate], cluster_slug="c")
    assert entry["volume"] == "45"
    assert entry["issue"] == "3"
    assert entry["pages"] == "123-145"


def test_to_papers_input_defaults_locators_to_empty_string_when_absent():
    """Backward-compat: candidates from older code paths that don't include
    these keys must still produce well-formed entries (empty strings, not
    KeyError)."""
    candidate = {
        "title": "Old-style", "doi": "10.1/y", "authors": [], "year": 2024,
        "abstract": "", "venue": "", "source": "arxiv",
    }
    [entry] = _to_papers_input([candidate], cluster_slug="c")
    assert entry["volume"] == ""
    assert entry["issue"] == ""
    assert entry["pages"] == ""
