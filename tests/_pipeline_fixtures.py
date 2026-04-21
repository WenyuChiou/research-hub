from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_hub.notebooklm.client import BriefingArtifact, NotebookHandle, UploadResult


PDF_BLOB = b"%PDF\n"
BRIEF_TEXT = "Pipeline synthesis brief text."


@dataclass
class FakeResponse:
    payload: Any = None
    text: str = ""
    status_code: int = 200
    content: bytes = b""

    def json(self) -> Any:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>https://arxiv.org/abs/2604.08224v1</id>
    <title>Arxiv Pipeline Agents</title>
    <summary>Arxiv abstract about pipeline agents.</summary>
    <published>2026-04-01T00:00:00Z</published>
    <author><name>Jane Doe</name></author>
  </entry>
</feed>
"""

S2_JSON = {
    "data": [
        {
            "title": "Semantic Pipeline Agents",
            "abstract": "Semantic Scholar abstract.",
            "year": 2025,
            "authors": [{"name": "Alex Roe"}],
            "externalIds": {"DOI": "10.1000/s2", "ArXiv": "2604.08225"},
            "venue": "S2 Venue",
            "citationCount": 7,
            "url": "https://semanticscholar.org/paper/x",
            "openAccessPdf": {"url": "https://example.test/s2.pdf"},
            "publicationTypes": ["JournalArticle"],
        }
    ]
}

OPENALEX_JSON = {
    "results": [
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1000/openalex",
            "title": "OpenAlex Pipeline Agents",
            "publication_year": 2024,
            "authorships": [{"author": {"display_name": "Open Author"}}],
            "primary_location": {"source": {"display_name": "Open Venue"}},
            "locations": [{"source": {"display_name": "arXiv"}, "landing_page_url": "https://arxiv.org/abs/2604.08226"}],
            "cited_by_count": 11,
            "abstract_inverted_index": {"OpenAlex": [0], "abstract": [1]},
            "open_access": {"is_oa": True, "oa_url": "https://example.test/openalex.pdf"},
            "type": "article",
        }
    ]
}

CROSSREF_JSON = {
    "message": {
        "items": [
            {
                "DOI": "10.1000/crossref",
                "title": ["Crossref Pipeline Agents"],
                "author": [{"given": "Cross", "family": "Author"}],
                "issued": {"date-parts": [[2023, 1, 1]]},
                "container-title": ["Crossref Venue"],
                "is-referenced-by-count": 3,
                "type": "journal-article",
            }
        ]
    }
}

PUBMED_SEARCH_JSON = {"esearchresult": {"idlist": ["12345"]}}
PUBMED_SUMMARY_JSON = {
    "result": {
        "12345": {
            "title": "PubMed Pipeline Agents",
            "authors": [{"name": "Pub Author"}],
            "pubdate": "2022 Jan",
            "articleids": [{"idtype": "doi", "value": "10.1000/pubmed"}],
            "source": "PubMed Venue",
        }
    }
}

BIORXIV_JSON = {
    "collection": [
        {
            "title": "BioRxiv Pipeline Agents",
            "authors": "Bio Author",
            "date": "2021-01-01",
            "doi": "10.1101/2021.01.01.1",
            "abstract": "pipeline agents biology",
        }
    ]
}

DBLP_JSON = {
    "result": {
        "hits": {
            "hit": [
                {
                    "info": {
                        "title": "DBLP Pipeline Agents.",
                        "authors": {"author": [{"text": "DBLP Author"}]},
                        "year": "2020",
                        "venue": "DBLP Venue",
                        "doi": "10.1000/dblp",
                        "ee": "https://doi.org/10.1000/dblp",
                        "type": "Journal Articles",
                    }
                }
            ]
        }
    }
}

TAVILY_JSON = {
    "results": [
        {
            "title": "Web Pipeline Agents",
            "url": "https://example.test/pipeline-agents-2026",
            "content": "Web result about pipeline agents.",
            "score": 0.8,
        }
    ]
}


def backend_response(name: str, url: str = "") -> FakeResponse:
    if name == "arxiv":
        return FakeResponse(text=ARXIV_XML)
    if name == "semantic-scholar":
        return FakeResponse(payload=S2_JSON)
    if name == "openalex":
        return FakeResponse(payload=OPENALEX_JSON)
    if name == "crossref":
        return FakeResponse(payload=CROSSREF_JSON)
    if name == "pubmed":
        if "esummary" in url:
            return FakeResponse(payload=PUBMED_SUMMARY_JSON)
        return FakeResponse(payload=PUBMED_SEARCH_JSON)
    if name == "biorxiv":
        return FakeResponse(payload=BIORXIV_JSON)
    if name == "dblp":
        return FakeResponse(payload=DBLP_JSON)
    if name == "websearch":
        return FakeResponse(payload=TAVILY_JSON)
    raise AssertionError(name)


def paper_input(title: str, slug: str, doi: str, *, arxiv_id: str = "") -> dict[str, Any]:
    entry = {
        "title": title,
        "doi": doi,
        "authors": [{"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}],
        "authors_str": "Doe, Jane",
        "year": 2026,
        "abstract": f"{title} abstract",
        "journal": "Fixture Journal",
        "summary": f"{title} summary",
        "key_findings": ["fixture finding"],
        "methodology": "fixture method",
        "relevance": "fixture relevance",
        "slug": slug,
        "sub_category": "llm-agents-for-abm",
        "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
    }
    if arxiv_id:
        entry["arxiv_id"] = arxiv_id
    return entry


def write_note(path: Path, *, title: str, doi: str, year: int = 2026, arxiv_id: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    url_line = f'url: "https://arxiv.org/abs/{arxiv_id}"\n' if arxiv_id else ""
    path.write_text(
        (
            "---\n"
            f'title: "{title}"\n'
            'authors: "Doe, Jane"\n'
            f'year: "{year}"\n'
            f'doi: "{doi}"\n'
            f"{url_line}"
            "topic_cluster: llm-agents-for-abm\n"
            "---\n\n"
            "## Summary\nFixture note.\n"
        ),
        encoding="utf-8",
    )


class FakeNotebookLMClient:
    uploaded: list[str] = []
    trigger_returns_none = False

    def __init__(self, page) -> None:
        self.page = page

    def open_or_create_notebook(self, name: str) -> NotebookHandle:
        self.page.calls.append(("open_or_create", name))
        return NotebookHandle(name=name, url="https://notebooklm.google.com/notebook/fixture", notebook_id="fixture")

    def open_notebook_by_name(self, name: str) -> NotebookHandle:
        self.page.calls.append(("open", name))
        return NotebookHandle(name=name, url="https://notebooklm.google.com/notebook/fixture", notebook_id="fixture")

    def upload_pdf(self, pdf_path: Path) -> UploadResult:
        self.uploaded.append(str(pdf_path))
        self.page.calls.append(("upload_pdf", str(pdf_path)))
        return UploadResult(source_kind="pdf", path_or_url=str(pdf_path), success=True)

    def upload_url(self, url: str) -> UploadResult:
        self.uploaded.append(url)
        self.page.calls.append(("upload_url", url))
        return UploadResult(source_kind="url", path_or_url=url, success=True)

    def trigger_briefing(self) -> str:
        self.page.calls.append(("trigger", "brief"))
        if self.trigger_returns_none:
            from research_hub.notebooklm.client import NotebookLMError

            raise NotebookLMError("Generation button not found", selector="fixture")
        return self.page.url

    def download_briefing(self, handle: NotebookHandle) -> BriefingArtifact:
        self.page.calls.append(("download", handle.name))
        return BriefingArtifact(
            notebook_name=handle.name,
            notebook_url=handle.url,
            notebook_id=handle.notebook_id,
            text=BRIEF_TEXT,
            titles=["Briefing"],
            source_count=3,
        )


class FakePage:
    def __init__(self) -> None:
        self.url = "https://notebooklm.google.com/notebook/fixture"
        self.calls: list[tuple[str, str]] = []

    def goto(self, url: str) -> None:
        self.url = url
        self.calls.append(("goto", url))

    def wait_for_load_state(self, state: str) -> None:
        self.calls.append(("load_state", state))


@contextmanager
def fake_cdp_session(*args, **kwargs):
    del args, kwargs
    yield object(), FakePage()

