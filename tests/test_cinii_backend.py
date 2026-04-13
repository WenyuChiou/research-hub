from __future__ import annotations

from unittest.mock import patch

from research_hub.search import SearchResult
from research_hub.search.cinii import CiniiBackend


class _Response:
    def __init__(self, text: str = "", status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


def _atom_entry(
    *,
    title: str = "Japanese Flood Study",
    author_names: tuple[str, ...] = ("Yuki Tanaka", "Aiko Sato"),
    publication_date: str = "2024-05-01",
    dc_date: str | None = None,
    doi_identifier: str | None = "https://doi.org/10.1234/JP-001",
    prism_doi: str | None = None,
    publisher: str = "Journal of Rivers",
    publication_name: str | None = None,
    summary: str = "Flood adaptation in Japan.",
    dc_type: str = "journal article",
    link: str = "https://cir.nii.ac.jp/crid/123",
) -> str:
    authors_xml = "".join(f"<author><name>{author}</name></author>" for author in author_names)
    identifiers = ""
    if doi_identifier is not None:
        identifiers += f"<dc:identifier>{doi_identifier}</dc:identifier>"
    prism_doi_xml = f"<prism:doi>{prism_doi}</prism:doi>" if prism_doi is not None else ""
    dc_date_xml = f"<dc:date>{dc_date}</dc:date>" if dc_date is not None else ""
    publication_name_xml = (
        f"<prism:publicationName>{publication_name}</prism:publicationName>"
        if publication_name is not None
        else ""
    )
    return f"""
    <entry>
      <title>{title}</title>
      {authors_xml}
      <id>{link}</id>
      <link rel="alternate" href="{link}" />
      <summary>{summary}</summary>
      <prism:publicationDate>{publication_date}</prism:publicationDate>
      {dc_date_xml}
      {publication_name_xml}
      <dc:publisher>{publisher}</dc:publisher>
      {identifiers}
      {prism_doi_xml}
      <dc:type>{dc_type}</dc:type>
    </entry>
    """


def _atom_feed(*entries: str) -> str:
    joined = "\n".join(entries)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:dcterms="http://purl.org/dc/terms/"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:prism="http://prismstandard.org/namespaces/basic/2.0/"
      xmlns:cinii="https://cir.nii.ac.jp/schema/1.0/">
  {joined}
</feed>"""


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_search_parses_atom_entries(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_atom_feed(_atom_entry(), _atom_entry(title="Paper Two")))

    results = CiniiBackend().search("flood")

    assert len(results) == 2


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_search_extracts_title_authors_year_doi(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_atom_feed(_atom_entry()))

    result = CiniiBackend().search("flood")[0]

    assert result.title == "Japanese Flood Study"
    assert result.authors == ["Yuki Tanaka", "Aiko Sato"]
    assert result.year == 2024
    assert result.doi == "10.1234/jp-001"


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_search_year_filter_uses_from_until_params(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_atom_feed())

    CiniiBackend().search("flood", year_from=2020, year_to=2024)

    assert mock_get.call_args.kwargs["params"]["from"] == "2020-01-01"
    assert mock_get.call_args.kwargs["params"]["until"] == "2024-12-31"


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_extracts_doi_from_dc_identifier_https_doi_org_prefix(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_atom_feed(_atom_entry(doi_identifier="https://doi.org/10.7777/ABC")))

    result = CiniiBackend().search("flood")[0]

    assert result.doi == "10.7777/abc"


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_extracts_doi_from_info_doi_prefix(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_atom_feed(_atom_entry(doi_identifier="info:doi/10.8888/XYZ")))

    result = CiniiBackend().search("flood")[0]

    assert result.doi == "10.8888/xyz"


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_extracts_doi_from_prism_doi_element(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_atom_feed(_atom_entry(doi_identifier=None, prism_doi="10.9999/DEF")))

    result = CiniiBackend().search("flood")[0]

    assert result.doi == "10.9999/def"


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_handles_japanese_title_text(mock_get, _mock_sleep):
    japanese_title = "\u6d2a\u6c34\u9069\u5fdc\u306b\u95a2\u3059\u308b\u7814\u7a76"
    mock_get.return_value = _Response(_atom_feed(_atom_entry(title=japanese_title)))

    result = CiniiBackend().search("\u6d2a\u6c34")[0]

    assert result.title == japanese_title


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_year_extracted_from_prism_publicationdate(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_atom_feed(_atom_entry(publication_date="2023-12-31", dc_date="2022-01-01")))

    result = CiniiBackend().search("flood")[0]

    assert result.year == 2023


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_doc_type_thesis_when_dc_type_says_thesis(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_atom_feed(_atom_entry(dc_type="doctoral thesis")))

    result = CiniiBackend().search("flood")[0]

    assert result.doc_type == "thesis"


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_returns_empty_on_404(mock_get, _mock_sleep):
    mock_get.return_value = _Response(status_code=404)

    assert CiniiBackend().search("flood") == []


@patch("research_hub.search.cinii.time.sleep")
@patch("research_hub.search.cinii.requests.get")
def test_cinii_handles_xml_parse_error_gracefully(mock_get, _mock_sleep):
    mock_get.return_value = _Response("<feed><broken>")

    assert CiniiBackend().search("flood") == []


@patch("research_hub.search.cinii.CiniiBackend.search")
def test_cinii_get_paper_by_doi_returns_first_match(mock_search):
    expected = SearchResult(title="Paper", doi="10.1/a", source="cinii")
    mock_search.return_value = [expected]

    result = CiniiBackend().get_paper("10.1/a")

    assert result is expected
