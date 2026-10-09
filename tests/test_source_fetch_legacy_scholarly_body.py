import pytest

from research_hub.source_fetch_extraction import _extract_html


def legacy(*, article_type="Text.Article", close=True, conclusions=True, refs=True):
    head = (
        '<meta name="DC.Title" content="A validation study">'
        '<meta name="DC.Creator" content="Researcher">'
        '<meta name="DC.Date" content="2007-03-31">'
        f'<meta name="DC.Type" content="{article_type}">'
        '<meta name="DC.Description" content="An abstract summary.">'
    )
    body = '<h3>Introduction</h3><p>' + "Relevant observed methods. " * 8 + '</p>'
    if conclusions:
        body += '<h3>Conclusions</h3><p>' + "Findings and their limitations. " * 8 + '</p>'
    if refs:
        body += '<h3>References</h3><p>' + "Author and source bibliographic record. " * 8 + '</p>'
    return ('<html><head>' + head + '</head><body>' + body + ('</body></html>' if close else '')).encode()


def test_complete_typed_legacy_article_preserves_body():
    result = _extract_html(legacy(), "https://example.org/paper")
    assert result.evidence_level == "full-text"
    assert "Relevant observed methods" in result.text
    assert "Findings and their limitations" in result.text
    assert result.diagnostics["legacy_scholarly_body"]["closed_body"] is True


@pytest.mark.parametrize("settings", [
    {"article_type": "Blog"}, {"close": False},
    {"conclusions": False}, {"refs": False},
])
def test_missing_legacy_proof_remains_abstract(settings):
    result = _extract_html(legacy(**settings), "https://example.org/paper")
    assert result.evidence_level == "abstract"
    assert result.text == "An abstract summary."


def test_legacy_keywords_in_abstract_are_insufficient():
    data = legacy().replace(b'<body>', b'<body><script>Introduction Conclusions References</script>')
    data = data.replace(b'<h3>', b'<p>').replace(b'</h3>', b'</p>')
    assert _extract_html(data, "https://example.org/paper").evidence_level == "abstract"


def test_standard_article_path_is_unchanged():
    data = b'<html><article><h2>Introduction</h2>' + b'methods ' * 60
    data += b'<h2>Results</h2>' + b'findings ' * 60 + b'</article></html>'
    result = _extract_html(data, "https://example.org/paper")
    assert result.evidence_level == "full-text"
    assert "legacy_scholarly_body" not in result.diagnostics


@pytest.mark.parametrize("container", ['div id="abstract"', 'section class="abstract"', 'nav'])
def test_structured_abstract_or_navigation_cannot_be_full_body(container):
    opening = ('<' + container + '>').encode()
    closing = ('</' + container.split()[0] + '>').encode()
    data = legacy().replace(b'<body>', b'<body>' + opening)
    data = data.replace(b'</body>', closing + b'</body>')
    assert _extract_html(data, "https://example.org/paper").evidence_level == "abstract"


def test_nested_body_does_not_assert_document_closure():
    data = legacy().replace(b'<body>', b'<body><body>')
    assert _extract_html(data, "https://example.org/paper").evidence_level == "abstract"


@pytest.mark.parametrize("marker", [
    'id="article-abstract"', 'class="abstract-content"', 'itemprop="abstract"',
])
def test_compound_abstract_markers_cannot_satisfy_body_sections(marker):
    data = legacy().replace(b'<body>', ('<body><div ' + marker + '>').encode())
    data = data.replace(b'</body>', b'</div></body>')
    assert _extract_html(data, "https://example.org/paper").evidence_level == "abstract"


def test_void_abstract_metadata_does_not_swallow_legacy_article():
    data = legacy().replace(b'</head>', b'<meta itemprop="abstract" content="Summary."></head>')
    result = _extract_html(data, "https://example.org/paper")
    assert result.evidence_level == "full-text"
    assert "Findings and their limitations" in result.text
