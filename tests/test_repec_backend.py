from __future__ import annotations

from unittest.mock import Mock, patch

from research_hub.search.repec import RepecBackend


def _response(*, text="", status_code=200):
    response = Mock()
    response.status_code = status_code
    response.text = text
    return response


_HTML = """
<html>
  <body>
    <a href="/p/abc/handle1.html">one</a>
    <a href="/p/def/handle2.html">two</a>
    <a href="/p/ghi/handle3.html">three</a>
  </body>
</html>
"""

_XML = """
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <GetRecord>
    <record>
      <metadata>
        <oai_dc:dc>
          <dc:title>Economic Growth</dc:title>
          <dc:creator>Jane Doe</dc:creator>
          <dc:creator>John Roe</dc:creator>
          <dc:date>2024-01-01</dc:date>
          <dc:identifier>https://doi.org/10.1000/repec</dc:identifier>
          <dc:identifier>https://ideas.repec.org/p/abc/handle1.html</dc:identifier>
          <dc:source>Journal of Economics</dc:source>
          <dc:type>Working Paper</dc:type>
        </oai_dc:dc>
      </metadata>
    </record>
  </GetRecord>
</OAI-PMH>
"""


@patch("research_hub.search.repec.requests.get")
def test_repec_search_extracts_handles_from_html(mock_get):
    mock_get.return_value = _response(text=_HTML)

    handles = RepecBackend(delay_seconds=0)._search_handles("growth", limit=3)

    assert handles == ["RePEc:abc:handle1", "RePEc:def:handle2", "RePEc:ghi:handle3"]


@patch("research_hub.search.repec.requests.get")
def test_repec_fetch_oai_record_parses_dc_xml(mock_get):
    mock_get.return_value = _response(text=_XML)

    result = RepecBackend(delay_seconds=0)._fetch_oai_record("RePEc:abc:handle1")

    assert result is not None
    assert result.title == "Economic Growth"
    assert result.authors == ["Jane Doe", "John Roe"]
    assert result.year == 2024


@patch("research_hub.search.repec.requests.get")
def test_repec_extracts_doi_from_dc_identifier_when_present(mock_get):
    mock_get.return_value = _response(text=_XML)

    result = RepecBackend(delay_seconds=0)._fetch_oai_record("RePEc:abc:handle1")

    assert result is not None
    assert result.doi == "10.1000/repec"


@patch("research_hub.search.repec.requests.get")
def test_repec_handles_missing_doi_in_identifier(mock_get):
    xml = _XML.replace("<dc:identifier>https://doi.org/10.1000/repec</dc:identifier>\n", "")
    mock_get.return_value = _response(text=xml)

    result = RepecBackend(delay_seconds=0)._fetch_oai_record("RePEc:abc:handle1")

    assert result is not None
    assert result.doi == ""


@patch("research_hub.search.repec.requests.get")
def test_repec_year_filter_applied_after_oai_fetch(mock_get):
    mock_get.side_effect = [_response(text=_HTML), _response(text=_XML.replace("2024-01-01", "2020-01-01"))]

    results = RepecBackend(delay_seconds=0).search("growth", limit=1, year_from=2024)

    assert results == []


@patch("research_hub.search.repec.requests.get")
def test_repec_doc_type_normalized_from_dc_type(mock_get):
    mock_get.return_value = _response(text=_XML)

    result = RepecBackend(delay_seconds=0)._fetch_oai_record("RePEc:abc:handle1")

    assert result is not None
    assert result.doc_type == "working-paper"


@patch("research_hub.search.repec.requests.get")
def test_repec_search_returns_empty_on_html_404(mock_get):
    mock_get.return_value = _response(status_code=404)

    assert RepecBackend(delay_seconds=0).search("growth") == []


@patch("research_hub.search.repec.requests.get")
def test_repec_oai_returns_none_on_xml_parse_error(mock_get):
    mock_get.return_value = _response(text="<broken")

    assert RepecBackend(delay_seconds=0)._fetch_oai_record("RePEc:abc:handle1") is None
