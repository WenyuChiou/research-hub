from __future__ import annotations

from unittest.mock import patch

from research_hub.search.arxiv_backend import ArxivBackend


class _Response:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from requests.exceptions import HTTPError

            raise HTTPError(f"{self.status_code}")


def _feed(entries: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'
        f"{entries}"
        "</feed>"
    )


def _entry(arxiv_id: str, year: int, doi: str | None = "10.1234/foo") -> str:
    doi_xml = f"<arxiv:doi>{doi}</arxiv:doi>" if doi is not None else ""
    return f"""
    <entry>
      <id>http://arxiv.org/abs/{arxiv_id}v2</id>
      <published>{year}-01-02T00:00:00Z</published>
      <title>
        LLM agent benchmark
      </title>
      <summary>
        Evaluation of agent systems
      </summary>
      <author><name>Jane Doe</name></author>
      <author><name>John Roe</name></author>
      {doi_xml}
    </entry>
    """


@patch("research_hub.search.arxiv_backend.time.sleep")
@patch("research_hub.search.arxiv_backend.requests.get")
def test_arxiv_search_parses_atom_feed(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_feed(_entry("2411.12345", 2024)))

    result = ArxivBackend().search("llm")

    assert len(result) == 1
    assert result[0].title == "LLM agent benchmark"
    assert result[0].abstract == "Evaluation of agent systems"
    assert result[0].arxiv_id == "2411.12345"
    assert result[0].year == 2024
    assert result[0].authors == ["Jane Doe", "John Roe"]


@patch("research_hub.search.arxiv_backend.time.sleep")
@patch("research_hub.search.arxiv_backend.requests.get")
def test_arxiv_extracts_arxiv_id_without_version(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_feed(_entry("2411.12345", 2024)))

    result = ArxivBackend().search("llm")

    assert result[0].arxiv_id == "2411.12345"


@patch("research_hub.search.arxiv_backend.time.sleep")
@patch("research_hub.search.arxiv_backend.requests.get")
def test_arxiv_uses_doi_when_present(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_feed(_entry("2411.12345", 2024, doi="10.1234/foo")))

    result = ArxivBackend().search("llm")

    assert result[0].doi == "10.1234/foo"


@patch("research_hub.search.arxiv_backend.time.sleep")
@patch("research_hub.search.arxiv_backend.requests.get")
def test_arxiv_missing_doi_leaves_empty(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_feed(_entry("2411.12345", 2024, doi=None)))

    result = ArxivBackend().search("llm")

    assert result[0].doi == ""


@patch("research_hub.search.arxiv_backend.time.sleep")
@patch("research_hub.search.arxiv_backend.requests.get")
def test_arxiv_year_filter_applied_client_side(mock_get, _mock_sleep):
    mock_get.return_value = _Response(
        _feed(
            _entry("2311.12345", 2023)
            + _entry("2411.12345", 2024)
            + _entry("2511.12345", 2025)
        )
    )

    result = ArxivBackend().search("llm", year_from=2024, year_to=2024)

    assert [item.year for item in result] == [2024]


@patch("research_hub.search.arxiv_backend.time.sleep")
@patch("research_hub.search.arxiv_backend.requests.get")
def test_arxiv_pdf_url_built_from_arxiv_id(mock_get, _mock_sleep):
    mock_get.return_value = _Response(_feed(_entry("2411.12345", 2024)))

    result = ArxivBackend().search("llm")

    assert result[0].pdf_url == "https://arxiv.org/pdf/2411.12345.pdf"


def test_build_arxiv_query_splits_into_and_terms():
    """Regression: quoted phrase matching missed real arxiv results because
    no paper contained the exact query string verbatim. Build an AND-joined
    term query instead."""
    from research_hub.search.arxiv_backend import _build_arxiv_query

    result = _build_arxiv_query("LLM agent software engineering")
    # Every term should be present as its own all: clause, AND-joined
    assert "all:LLM" in result
    assert "all:agent" in result
    assert "all:software" in result
    assert "all:engineering" in result
    assert " AND " in result
    # No phrase quoting
    assert '"LLM agent software engineering"' not in result


def test_build_arxiv_query_preserves_explicit_quoted_phrases():
    from research_hub.search.arxiv_backend import _build_arxiv_query

    result = _build_arxiv_query('"SWE-bench" agent')
    # Quoted phrase preserved, loose term AND-joined
    assert 'all:"SWE-bench"' in result
    assert "all:agent" in result


def test_build_arxiv_query_empty_falls_back_to_wildcard():
    from research_hub.search.arxiv_backend import _build_arxiv_query

    assert _build_arxiv_query("") == "all:*"


def test_build_arxiv_query_single_word():
    from research_hub.search.arxiv_backend import _build_arxiv_query

    result = _build_arxiv_query("transformer")
    assert result == "all:transformer"
