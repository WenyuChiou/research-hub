"""Generic web search backend with provider auto-detection.

Providers are selected from environment variables or an explicit provider name:
- Tavily: set ``TAVILY_API_KEY``. Recommended for AI-agent workflows.
- Brave: set ``BRAVE_SEARCH_API_KEY``. Best general free-tier option.
- Google CSE: set ``GOOGLE_CSE_API_KEY`` and ``GOOGLE_CSE_CX``.
- DuckDuckGo HTML: no key required, but parsing is fragile and best-effort only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import logging
import os
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

from research_hub.search.base import SearchResult


logger = logging.getLogger(__name__)

_TIMEOUT = 20
_USER_AGENT = "research-hub/0.51"
_NEWS_DOMAINS = {
    "nytimes.com", "wsj.com", "ft.com", "bbc.com", "cnn.com", "reuters.com",
    "apnews.com", "theguardian.com", "washingtonpost.com", "bloomberg.com",
}
_BLOG_DOMAINS = {"medium.com", "substack.com", "dev.to", "hashnode.dev"}
_DOCS_HINTS = ("docs.", "readthedocs.io", "github.com", "developer.", "developers.")
_YEAR_RE = re.compile(r"(19|20)\d{2}")


@dataclass
class _ProviderConfig:
    name: str
    api_key: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current_link: dict[str, str] | None = None
        self._current_snippet_index: int | None = None
        self._capture_title = False
        self._capture_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        classes = attr_map.get("class", "") or ""
        if tag == "a" and "result__a" in classes:
            self._current_link = {"title": "", "url": attr_map.get("href", "") or "", "content": ""}
            self.results.append(self._current_link)
            self._capture_title = True
            return
        if self.results and "result__snippet" in classes:
            self._current_snippet_index = len(self.results) - 1
            self._capture_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._capture_title = False
            self._current_link = None
        if self._capture_snippet and tag in {"a", "div", "span"}:
            self._capture_snippet = False
            self._current_snippet_index = None

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._capture_title and self._current_link is not None:
            self._current_link["title"] = f'{self._current_link["title"]} {text}'.strip()
        elif self._capture_snippet and self._current_snippet_index is not None:
            current = self.results[self._current_snippet_index]
            current["content"] = f'{current["content"]} {text}'.strip()


class WebSearchBackend:
    name = "websearch"

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider

    def search(self, query: str, *, limit: int = 10, **_: object) -> list[SearchResult]:
        if not query.strip():
            return []
        cfg = _select_provider(self.provider)
        try:
            return _fetch(cfg, query, limit)
        except Exception as exc:
            logger.warning("websearch (%s) failed: %s", cfg.name, exc)
            return []

    def get_paper(self, identifier: str) -> SearchResult | None:
        del identifier
        return None


def _select_provider(provider: str | None) -> _ProviderConfig:
    if provider and provider != "auto":
        return _provider_config(provider)
    for candidate in ("tavily", "brave", "google_cse"):
        cfg = _provider_config(candidate)
        if cfg.api_key:
            return cfg
    return _provider_config("ddg")


def _provider_config(name: str) -> _ProviderConfig:
    if name == "tavily":
        return _ProviderConfig(name="tavily", api_key=os.environ.get("TAVILY_API_KEY"))
    if name == "brave":
        return _ProviderConfig(name="brave", api_key=os.environ.get("BRAVE_SEARCH_API_KEY"))
    if name == "google_cse":
        return _ProviderConfig(
            name="google_cse",
            api_key=os.environ.get("GOOGLE_CSE_API_KEY"),
            extra={"cx": os.environ.get("GOOGLE_CSE_CX", "")},
        )
    if name == "ddg":
        return _ProviderConfig(name="ddg")
    raise ValueError(f"unknown websearch provider: {name}")


def _fetch(cfg: _ProviderConfig, query: str, limit: int) -> list[SearchResult]:
    if cfg.name == "tavily":
        return _fetch_tavily(cfg, query, limit)
    if cfg.name == "brave":
        return _fetch_brave(cfg, query, limit)
    if cfg.name == "google_cse":
        return _fetch_google_cse(cfg, query, limit)
    return _fetch_ddg(cfg, query, limit)


def _fetch_tavily(cfg: _ProviderConfig, query: str, limit: int) -> list[SearchResult]:
    response = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": cfg.api_key, "query": query, "max_results": limit},
        timeout=_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    return [_result_from_item(item, snippet_key="content", score_key="score") for item in payload.get("results", [])[:limit]]


def _fetch_brave(cfg: _ProviderConfig, query: str, limit: int) -> list[SearchResult]:
    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": limit},
        timeout=_TIMEOUT,
        headers={"User-Agent": _USER_AGENT, "X-Subscription-Token": cfg.api_key or ""},
    )
    response.raise_for_status()
    payload = response.json()
    return [_result_from_item(item, snippet_key="description") for item in payload.get("web", {}).get("results", [])[:limit]]


def _fetch_google_cse(cfg: _ProviderConfig, query: str, limit: int) -> list[SearchResult]:
    response = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": cfg.api_key, "cx": cfg.extra.get("cx", ""), "q": query, "num": limit},
        timeout=_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    return [_result_from_item(item, url_key="link", snippet_key="snippet") for item in payload.get("items", [])[:limit]]


def _fetch_ddg(cfg: _ProviderConfig, query: str, limit: int) -> list[SearchResult]:
    del cfg
    response = requests.get(
        f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
        timeout=_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()
    parser = _DuckDuckGoHTMLParser()
    parser.feed(response.text)
    return [_result_from_item(item, snippet_key="content") for item in parser.results[:limit]]


def _result_from_item(
    item: dict[str, object],
    *,
    url_key: str = "url",
    snippet_key: str = "content",
    score_key: str | None = None,
) -> SearchResult:
    url = _clean_ddg_url(str(item.get(url_key, "") or ""))
    domain = _registered_domain(url)
    confidence = float(item.get(score_key, 0.6) or 0.6) if score_key else 0.6
    return SearchResult(
        title=str(item.get("title", "") or ""),
        abstract=str(item.get(snippet_key, "") or ""),
        year=_extract_year(url, item),
        authors=[],
        venue=domain,
        url=url,
        source="web",
        confidence=confidence,
        found_in=["websearch"],
        doc_type=_guess_doc_type(domain, url),
    )


def _clean_ddg_url(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" in (parsed.netloc or ""):
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            return unquote(uddg[0])
    return url


def _registered_domain(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _extract_year(url: str, item: dict[str, object]) -> int | None:
    for key in ("published_date", "publishedDate", "date"):
        value = str(item.get(key, "") or "")
        if len(value) >= 4 and value[:4].isdigit():
            return int(value[:4])
    for match in _YEAR_RE.finditer(url):
        year = int(match.group(0))
        if 1900 <= year <= 2099:
            return year
    return None


def _guess_doc_type(domain: str, url: str) -> str:
    if domain in _NEWS_DOMAINS:
        return "news"
    if domain in _BLOG_DOMAINS:
        return "blog"
    if any(hint in domain for hint in _DOCS_HINTS) or any(hint in url for hint in ("/docs/", "/readme", "/wiki/")):
        return "docs"
    return "article"
