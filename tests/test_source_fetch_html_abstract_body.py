"""HTML abstracts must not provide the body evidence for article/main."""

import pytest

from research_hub.source_fetch_extraction import _extract_html


_URL = "https://example.org/synthetic-paper"
_INTRO = "The study describes the collected samples and the bounded comparison. " * 4
_RESULTS = "The measured observations support the comparison within stated limits. " * 4
_ABSTRACT_INTRO = "ABSTRACT_ONLY overview of the proposed method and its scope. " * 7
_ABSTRACT_RESULTS = "ABSTRACT_ONLY overview of the reported comparison and its limits. " * 7


def _sections(introduction, results):
    return (
        f"<h3>Introduction</h3><p>{introduction}</p>"
        f"<h3>Results</h3><p>{results}</p>"
    )


def _abstract(container):
    tag = container.split()[0]
    # Nested matching tags exercise recovery of the following genuine body.
    return (
        f"<{container}><h2>Abstract</h2><{tag}>"
        + _sections(_ABSTRACT_INTRO, _ABSTRACT_RESULTS)
        + f"</{tag}></{tag}>"
    )


def _page(article_tag, content):
    return (
        '<html><head><meta name="citation_title" content="Synthetic boundary study">'
        '<meta name="citation_doi" content="10.5555/synthetic-boundary-study">'
        f"</head><body><{article_tag}>{content}</{article_tag}></body></html>"
    ).encode()


@pytest.mark.parametrize("article_tag", ["article", "main"])
@pytest.mark.parametrize("container", ['section id="abstract"', 'div class="article-abstract"'])
def test_marked_structured_abstract_does_not_establish_full_body(article_tag, container):
    result = _extract_html(_page(article_tag, _abstract(container)), _URL)

    assert result.evidence_level == "abstract"
    assert _ABSTRACT_INTRO.strip() in result.text
    assert _ABSTRACT_RESULTS.strip() in result.text
    assert [locator["value"] for locator in result.locators] == ["Abstract"]


@pytest.mark.parametrize("article_tag", ["article", "main"])
@pytest.mark.parametrize("container", ['section id="abstract"', 'div class="article-abstract"'])
def test_real_body_after_nested_abstract_remains_full_text(article_tag, container):
    content = _abstract(container) + _sections(_INTRO, _RESULTS)
    result = _extract_html(_page(article_tag, content), _URL)

    assert result.evidence_level == "full-text"
    assert _INTRO.strip() in result.text
    assert _RESULTS.strip() in result.text
    assert "ABSTRACT_ONLY" not in result.text
    assert [locator["value"] for locator in result.locators] == ["Introduction", "Results"]


@pytest.mark.parametrize("article_tag", ["article", "main"])
def test_abstract_cannot_pad_a_body_below_existing_length_threshold(article_tag):
    short_sections = _sections("Body method. " * 9, "Body finding. " * 9)
    content = _abstract('section id="abstract"') + short_sections
    result = _extract_html(_page(article_tag, content), _URL)

    assert result.evidence_level == "abstract"
    assert "ABSTRACT_ONLY" in result.text
    assert "Body method." not in result.text


@pytest.mark.parametrize("article_tag", ["article", "main"])
def test_short_genuine_body_allowed_by_existing_contract(article_tag):
    result = _extract_html(_page(article_tag, _sections(_INTRO, _RESULTS)), _URL)

    assert result.evidence_level == "full-text"
    assert 500 <= len(result.text) < 650
    assert _INTRO.strip() in result.text
    assert _RESULTS.strip() in result.text


@pytest.mark.parametrize("article_tag", ["article", "main"])
@pytest.mark.parametrize("explicit_end", [False, True])
@pytest.mark.parametrize("body_wrapper", [False, True])
def test_abstract_paragraph_closes_before_genuine_body(article_tag, explicit_end, body_wrapper):
    abstract = '<p class="abstract"><em>' + _ABSTRACT_INTRO + "</em>"
    abstract += "</p>" if explicit_end else ""
    body = _sections(_INTRO, _RESULTS).replace("h3>", "h2>")
    if body_wrapper:
        body = "<div>" + body + "</div>"
    result = _extract_html(_page(article_tag, abstract + body), _URL)

    assert result.evidence_level == "full-text"
    assert _INTRO.strip() in result.text
    assert _RESULTS.strip() in result.text
    assert "ABSTRACT_ONLY" not in result.text
    assert [locator["value"] for locator in result.locators] == ["Introduction", "Results"]
    for locator in result.locators:
        assert result.text[locator["start"] : locator["end"]].startswith(locator["value"])


@pytest.mark.parametrize("article_tag", ["article", "main"])
def test_implicit_abstract_paragraph_does_not_capture_short_body(article_tag):
    abstract = '<p class="abstract">' + _ABSTRACT_INTRO
    body = _sections("Body method. " * 9, "Body finding. " * 9)
    result = _extract_html(_page(article_tag, abstract + body), _URL)

    assert result.evidence_level == "abstract"
    assert result.text == _ABSTRACT_INTRO.strip()
    assert [locator["value"] for locator in result.locators] == ["Abstract"]


@pytest.mark.parametrize("article_tag", ["article", "main"])
def test_inline_markup_does_not_end_marked_abstract_paragraph(article_tag):
    abstract = '<p class="abstract"><span>' + _ABSTRACT_INTRO + "</span><em>Inline ending.</em></p>"
    result = _extract_html(_page(article_tag, abstract), _URL)

    assert result.evidence_level == "abstract"
    assert result.text == _ABSTRACT_INTRO.strip() + " Inline ending."


@pytest.mark.parametrize("article_tag", ["article", "main"])
def test_template_headings_do_not_end_marked_abstract_paragraph(article_tag):
    abstract = (
        '<p class="abstract">' + _ABSTRACT_INTRO
        + "<template>" + _sections(_INTRO, _RESULTS) + "</template>Visible ending.</p>"
    )
    result = _extract_html(_page(article_tag, abstract), _URL)

    assert result.evidence_level == "abstract"
    assert result.text == _ABSTRACT_INTRO.strip() + " Visible ending."


@pytest.mark.parametrize("article_tag", ["article", "main"])
def test_implicit_abstract_paragraph_ends_with_article_container(article_tag):
    data = _page(article_tag, '<p class="abstract">' + _ABSTRACT_INTRO)
    outside_body = _sections(_INTRO, _RESULTS).encode()
    data = data.replace(b"</body>", outside_body + b"</body>")
    result = _extract_html(data, _URL)

    assert result.evidence_level == "abstract"
    assert result.text == _ABSTRACT_INTRO.strip()
    assert [locator["value"] for locator in result.locators] == ["Abstract"]
