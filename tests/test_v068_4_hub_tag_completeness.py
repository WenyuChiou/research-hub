"""v0.68.4 — auto pipeline previously emitted only 2/4 hub tag namespaces
(`research-hub` + `cluster/<slug>`) on ingested papers, leaving downstream
queries that filter by `type/` or `src/` blind.

Real incident: a real ingest of "post-flood household relocation" produced
8 papers in Zotero collection C7S7A9KA — every paper missing both
`type/journalArticle` and `src/<backend>` tags. Backfill required a manual
script. These tests prevent the regression.

Also covers Bug C: when the search backend returned a real abstract,
notes were still TODO skeletons. Now the abstract seeds the summary.
"""

from __future__ import annotations

from research_hub.pipeline import _compose_hub_tags
from research_hub.discover import _to_papers_input


def test_compose_hub_tags_defaults_type_to_journal_article():
    """The pipeline always creates journalArticle Zotero items, so when
    the search backend didn't supply a doc_type we should still emit
    `type/journalArticle` rather than dropping the namespace."""
    pp = {"title": "Some paper"}  # no doc_type, no publication_type
    tags = _compose_hub_tags(pp, cluster_slug="my-cluster")
    assert "type/journalArticle" in tags


def test_compose_hub_tags_includes_src_when_backend_present():
    pp = {"title": "Some paper", "source": "openalex"}
    tags = _compose_hub_tags(pp, cluster_slug="my-cluster")
    assert "src/openalex" in tags


def test_compose_hub_tags_full_namespace_for_typical_ingest():
    """End-to-end shape check: a paper coming from openalex into a
    cluster should land all 4 hub tag namespaces."""
    pp = {"title": "X", "source": "openalex"}
    tags = _compose_hub_tags(pp, cluster_slug="post-flood-household-relocation")
    assert set(tags) >= {
        "research-hub",
        "cluster/post-flood-household-relocation",
        "type/journalArticle",
        "src/openalex",
    }


def test_to_papers_input_propagates_source_field():
    """Bug A regression: _to_papers_input dropped the `source` field
    so _compose_hub_tags couldn't emit src/<backend>."""
    candidate = {
        "title": "Paper A",
        "doi": "10.1/x",
        "authors": ["Alice Smith"],
        "year": 2025,
        "abstract": "Some abstract.",
        "source": "openalex",
    }
    [entry] = _to_papers_input([candidate], cluster_slug="my-cluster")
    assert entry.get("source") == "openalex"


def test_to_papers_input_propagates_found_in_when_source_absent():
    candidate = {
        "title": "Paper B",
        "doi": "10.1/y",
        "authors": ["Bob Jones"],
        "year": 2025,
        "abstract": "Abstract",
        "found_in": "crossref",  # alternate field name some backends use
    }
    [entry] = _to_papers_input([candidate], cluster_slug="c")
    assert entry.get("source") == "crossref"


def test_to_papers_input_seeds_summary_with_real_abstract():
    """Bug C regression: when the backend returned a real abstract,
    summary was still '[TODO] <title>' instead of the abstract content."""
    abstract = "We study how households relocate after major floods using survey data from 1200 respondents."
    candidate = {
        "title": "Household relocation post-flood",
        "doi": "10.1/z",
        "authors": ["Chen Li"],
        "year": 2025,
        "abstract": abstract,
        "source": "openalex",
    }
    [entry] = _to_papers_input([candidate], cluster_slug="c")
    assert "TODO" not in entry["summary"]
    assert entry["summary"].startswith("We study how households relocate")


def test_to_papers_input_keeps_todo_when_no_abstract():
    """When backend genuinely has no abstract, fall back to TODO marker
    so the user sees an explicit prompt to fill it in."""
    candidate = {
        "title": "No-abstract paper",
        "doi": "10.1/w",
        "authors": ["Ed Long"],
        "year": 2025,
        "abstract": "",
        "source": "semantic-scholar",
    }
    [entry] = _to_papers_input([candidate], cluster_slug="c")
    assert "TODO" in entry["summary"]
    assert entry["abstract"] == "(no abstract)"


def test_to_papers_input_treats_no_abstract_string_as_missing():
    """Some backends literally return the string '(no abstract)' rather
    than empty — treat that as missing too."""
    candidate = {
        "title": "Sentinel-string paper",
        "doi": "10.1/v",
        "authors": ["Faye Zhao"],
        "year": 2025,
        "abstract": "(no abstract)",
        "source": "arxiv",
    }
    [entry] = _to_papers_input([candidate], cluster_slug="c")
    assert "TODO" in entry["summary"]
