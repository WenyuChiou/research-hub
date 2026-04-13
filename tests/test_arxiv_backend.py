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
