"""Synthetic scoring-input provenance; no model quality acceptance."""
import copy
import pytest
from research_hub.fit_check import emit_prompt
from research_hub.discover import _merge_search_dict_candidates

@pytest.mark.parametrize("source,provenance", [
    ("web", ""), ("websearch", None), ("crossref", "web-search-snippet"),
    (" web ", " "), ("", "web-search-snippet"),
])
def test_web_excerpt_is_not_labeled_abstract(source, provenance):
    paper = {"title":"Example", "abstract":"Synthetic snippet.", "source":source,
             "abstract_source":provenance, "url":"https://example.invalid/paper"}
    before = copy.deepcopy(paper)
    prompt = emit_prompt("example", [paper])
    assert "**Abstract:**" not in prompt
    assert "**Web-search excerpt (not a paper abstract):**" in prompt
    assert "Synthetic snippet." in prompt
    assert "web-search-snippet" in prompt
    assert "https://example.invalid/paper" in prompt
    assert "insufficient evidence" in prompt
    assert paper == before

@pytest.mark.parametrize("source,provenance", [
    ("crossref", "crossref"), ("websearch", "crossref"), ("web", "unknown"),
    ("", ""), ("semantic-scholar", "semantic-scholar"),
])
def test_nonexcerpt_retains_abstract_and_discloses_provenance(source, provenance):
    prompt = emit_prompt("example", [{"title":"Example", "abstract":"Academic text.",
                         "source":source, "abstract_source":provenance}])
    assert "**Abstract:**" in prompt
    assert "**Web-search excerpt" not in prompt
    assert f"**Text provenance:** {provenance or 'unknown'};" in prompt
    assert "Academic text." in prompt

def test_discovery_merge_to_scoring_retains_recovered_academic_text():
    candidates = _merge_search_dict_candidates([
        {"title":"Example", "doi":"10.1/demo", "abstract":"Snippet", "source":"websearch"},
        {"title":"Example", "doi":"10.1/demo", "abstract":"Paper abstract", "source":"crossref",
         "abstract_source":"crossref"},
    ])
    prompt = emit_prompt("example", candidates)
    assert "**Abstract:**" in prompt and "Paper abstract" in prompt
    assert "Snippet" not in prompt
    assert "**Text provenance:** crossref;" in prompt

def test_discovery_merge_to_scoring_keeps_excerpt_warning():
    candidates = _merge_search_dict_candidates([
        {"title":"Example", "abstract":"Snippet", "source":"websearch",
         "url":"https://example.invalid/paper"}])
    prompt = emit_prompt("example", candidates)
    assert "**Abstract:**" not in prompt
    assert "Snippet" in prompt and "web-search-snippet" in prompt
