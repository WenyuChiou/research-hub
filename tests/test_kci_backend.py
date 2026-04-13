from __future__ import annotations

from unittest.mock import patch

from research_hub.search import SearchResult
from research_hub.search.kci import KciBackend


class _Response:
    def __init__(self, payload: dict | None = None, status_code: int = 200, json_error: Exception | None = None) -> None:
        self._payload = payload or {}
        self.status_code = status_code
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def _article(**overrides):
    article = {
        "titleEng": "Flood Adaptation in Korea",
        "title": "\ud55c\uad6d \ud64d\uc218 \uc801\uc751",
        "authors": [{"nameEng": "Min Kim"}],
        "publishedYear": "2024",
        "journalNameEng": "Korean Climate Journal",
        "doi": "10.1234/KR-001",
        "linkUrl": "https://www.kci.go.kr/article/1",
        "abstractEng": "Climate adaptation study.",
        "citedCount": 7,
    }
    article.update(overrides)
    return article


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_search_extracts_title_authors_year_doi(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"articles": [_article()]})

    result = KciBackend().search("flood")[0]

    assert result.title == "Flood Adaptation in Korea"
    assert result.authors == ["Min Kim"]
    assert result.year == 2024
    assert result.doi == "10.1234/kr-001"


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_search_handles_titleeng_field_first(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"articles": [_article(titleEng="English Title", title="Korean Title")]})

    result = KciBackend().search("flood")[0]

    assert result.title == "English Title"


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_search_falls_back_to_title_when_titleeng_missing(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"articles": [_article(titleEng="", title="Korean Title")]})

    result = KciBackend().search("flood")[0]

    assert result.title == "Korean Title"


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_handles_authors_as_list_of_dicts(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"articles": [_article(authors=[{"nameEng": "Min Kim"}, {"name": "Lee"}])]})

    result = KciBackend().search("flood")[0]

    assert result.authors == ["Min Kim", "Lee"]


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_handles_authors_as_list_of_strings(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"articles": [_article(authors=["Min Kim", "Su Park"])]})

    result = KciBackend().search("flood")[0]

    assert result.authors == ["Min Kim", "Su Park"]


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_handles_authors_as_comma_separated_string(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"articles": [_article(authors="Min Kim, Su Park")]})

    result = KciBackend().search("flood")[0]

    assert result.authors == ["Min Kim", "Su Park"]


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_year_filter_uses_startyear_endyear_params(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"articles": []})

    KciBackend().search("flood", year_from=2020, year_to=2024)

    assert mock_get.call_args.kwargs["params"]["startYear"] == 2020
    assert mock_get.call_args.kwargs["params"]["endYear"] == 2024


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_extracts_journal_name_eng(mock_get, _mock_sleep):
    mock_get.return_value = _Response(
        {"articles": [_article(journalNameEng="KCI Journal", journalName="\ub85c\uceec\uc800\ub110")]}
    )

    result = KciBackend().search("flood")[0]

    assert result.venue == "KCI Journal"


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_builds_url_from_articleid_when_linkurl_missing(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"articles": [_article(linkUrl="", articleId="ARTI123")]})

    result = KciBackend().search("flood")[0]

    assert result.url.endswith("sereArticleSearchBean.artiId=ARTI123")


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_returns_empty_on_404(mock_get, _mock_sleep):
    mock_get.return_value = _Response(status_code=404)

    assert KciBackend().search("flood") == []


@patch("research_hub.search.kci.time.sleep")
@patch("research_hub.search.kci.requests.get")
def test_kci_returns_empty_on_invalid_json(mock_get, _mock_sleep):
    mock_get.return_value = _Response(json_error=ValueError("bad json"))

    assert KciBackend().search("flood") == []


@patch("research_hub.search.kci.KciBackend.search")
def test_kci_get_paper_by_doi_returns_first_match(mock_search):
    expected = SearchResult(title="Paper", doi="10.1/a", source="kci")
    mock_search.return_value = [expected]

    result = KciBackend().get_paper("10.1/a")

    assert result is expected
