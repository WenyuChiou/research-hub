from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from research_hub.source_fetch_extraction import _extract_html, _extract_pdf


def _synthetic_pdf(pages: list[tuple[bool, str]]) -> bytes:
    """Build a small PDF without relying on private or generated fixtures."""
    font_id = 3 + len(pages) * 2
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            f"<< /Type /Pages /Count {len(pages)} /Kids ["
            + " ".join(f"{3 + index * 2} 0 R" for index in range(len(pages)))
            + "] >>"
        ).encode(),
    ]
    for index, (has_media_box, text) in enumerate(pages):
        page_id = 3 + index * 2
        content_id = page_id + 1
        media_box = " /MediaBox [0 0 612 792]" if has_media_box else ""
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R{media_box} "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode()
        )
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode() if text else b""
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(result)


def test_missing_media_box_recovers_with_explicit_geometry_and_blank_inventory():
    extracted = _extract_pdf(
        _synthetic_pdf([(False, "Recovered first page"), (True, "")])
    )

    assert extracted.text == "Recovered first page"
    assert extracted.diagnostics == {
        "pages_total": 2,
        "readable_pages": [1],
        "blank_pages": [2],
        "omitted_pages": [],
        "geometry_default_pages": [1],
        "geometry_default_media_box": [0.0, 0.0, 612.0, 792.0],
        "extraction_fidelity": (
            "Page structure and readable-page coverage were preserved; "
            "reading-order and complete readable-content fidelity remain pending."
        ),
    }
    assert extracted.locators[-1]["type"] == "pdf-geometry-recovery"
    assert extracted.locators[-1]["geometry_default_media_box"] == [
        0.0,
        0.0,
        612.0,
        792.0,
    ]


def test_normal_pdf_keeps_page_text_and_locator_shape():
    extracted = _extract_pdf(_synthetic_pdf([(True, "Normal page")]))

    assert extracted.text == "Normal page"
    assert extracted.locators == [
        {"type": "pdf-page", "value": 1, "start": 0, "end": 11}
    ]
    assert "geometry_default_pages" not in extracted.diagnostics


@pytest.mark.parametrize(
    "identifier", ["https://example.org/article", "urn:isbn:123", "repository-123"]
)
def test_html_page_identifiers_are_not_dois(identifier):
    html = f'<title>Neutral study</title><meta name="dc.identifier" content="{identifier}"><meta name="citation_abstract" content="Readable abstract remains available.">'
    extracted = _extract_html(html.encode(), "https://example.org/article")
    assert extracted.observed_doi == ""
    assert extracted.evidence_level == "abstract"
    assert extracted.text == "Readable abstract remains available."


@pytest.mark.parametrize(
    "identifier",
    ["10.1234/Example", "doi:10.1234/Example", "https://doi.org/10.1234/Example"],
)
def test_html_valid_metadata_doi_is_normalized(identifier):
    html = f'<title>Neutral study</title><meta name="dc.identifier" content="{identifier}">'
    extracted = _extract_html(html.encode(), "https://example.org/article")
    assert extracted.observed_doi == "10.1234/example"
    assert extracted.evidence_level == "metadata"


def test_html_invalid_citation_doi_does_not_mask_valid_dc_doi():
    html = '<title>Neutral study</title><meta name="citation_doi" content="https://example.org/article"><meta name="dc.identifier" content="10.1234/valid">'
    assert (
        _extract_html(html.encode(), "https://example.org/article").observed_doi
        == "10.1234/valid"
    )


@pytest.mark.parametrize(
    "metadata",
    [
        '<meta name="citation_doi" content="10.1234/one"><meta name="dc.identifier" content="10.1234/two">',
        '<meta name="citation_doi" content="10.1234/one"><meta name="citation_doi" content="10.1234/two">',
    ],
)
def test_html_conflicting_metadata_dois_are_omitted(metadata):
    extracted = _extract_html(
        ("<title>Neutral study</title>" + metadata).encode(),
        "https://example.org/article",
    )
    assert extracted.observed_doi == ""


def test_html_duplicate_prefixed_metadata_doi_is_one_identifier():
    html = '<title>Neutral study</title><meta name="citation_doi" content="doi:10.1234/Same"><meta name="dc.identifier" content="https://doi.org/10.1234/Same">'
    extracted = _extract_html(html.encode(), "https://example.org/article")
    assert extracted.observed_doi == "10.1234/same"


def test_html_bibliography_doi_is_not_the_work_identifier():
    html = '<title>Neutral study</title><meta name="dc.identifier" content="https://example.org/article"><p>References: DOI:10.9999/another-work</p>'
    assert (
        _extract_html(html.encode(), "https://example.org/article").observed_doi == ""
    )


def test_corrupt_and_encrypted_pdf_remain_errors():
    with pytest.raises(ValueError, match="PDF parse failed"):
        _extract_pdf(b"%PDF-broken")

    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    encrypted = BytesIO()
    writer.write(encrypted)
    with pytest.raises(ValueError, match="PDF parse failed"):
        _extract_pdf(encrypted.getvalue())


def _work_table(*, doi: str = "10.1234/example", duplicate_title: bool = False) -> str:
    duplicate = (
        "<tr><th>Article Title</th><td>Duplicate</td></tr>" if duplicate_title else ""
    )
    return f"""<table><tr><th>Title (Primary)</th><td>Étude <em>nested</em></td></tr>
    {duplicate}<tr><th>DOI</th><td><a>{doi}</a></td></tr>
    <tr><th>Authors</th><td>Zoë Example; 李 明</td></tr>
    <tr><th>Year</th><td>2024</td></tr>
    <tr><th>Abstract</th><td>Résumé with <strong>nested evidence</strong> and enough text for abstract extraction.</td></tr></table>"""


def test_labeled_table_extracts_abstract_and_binds_utf8_source_fields():
    data = ("<html><title>Generic portal</title>" + _work_table() + "</html>").encode()
    extracted = _extract_html(data, "https://example.org/record")

    assert extracted.evidence_level == "abstract"
    assert extracted.text.startswith("Résumé with nested evidence")
    assert extracted.observed_title == "Étude nested"
    assert extracted.observed_doi == "10.1234/example"
    assert extracted.bibliographic_metadata["authors"] == "Zoë Example; 李 明"
    locator = extracted.locators[0]
    assert locator["source_sha256"] == sha256(data).hexdigest()
    for field in locator["fields"]:
        char_start, char_end = field["raw_characters"]
        byte_start, byte_end = field["raw_utf8_bytes"]
        raw = data[byte_start:byte_end]
        assert field["raw_element_sha256"] == sha256(raw).hexdigest()
        assert byte_end - byte_start >= char_end - char_start


@pytest.mark.parametrize(
    "html",
    [
        lambda: (
            "<title>Portal</title>" + _work_table() + _work_table(doi="10.1234/two")
        ),
        lambda: (
            '<meta name="citation_doi" content="10.9999/conflict"><title>Portal</title>'
            + _work_table()
        ),
        lambda: "<title>Portal</title>" + _work_table(duplicate_title=True),
    ],
)
def test_ambiguous_duplicate_or_conflicting_tables_are_rejected(html):
    extracted = _extract_html(html().encode(), "https://example.org/record")

    assert extracted.evidence_level == "metadata"
    assert extracted.text == "Portal"
    assert extracted.bibliographic_metadata == {}


def test_valid_full_text_is_not_downgraded_by_publication_table():
    article = (
        "<article><h2>Introduction</h2><p>"
        + "Substantive introduction evidence. " * 15
        + "</p><h2>Methods</h2><p>"
        + "Detailed reproducible methods and measurements. " * 15
        + "</p></article>"
    )
    extracted = _extract_html(
        ("<title>Portal</title>" + article + _work_table()).encode(),
        "https://example.org/record",
    )

    assert extracted.evidence_level == "full-text"
    assert "Substantive introduction evidence" in extracted.text
    assert extracted.observed_title == "Étude nested"


def test_publication_table_ignores_suppressed_cell_content():
    table = _work_table().replace(
        "Résumé with <strong>nested evidence</strong>",
        "Résumé <script>poison</script><style>hidden</style> with "
        "<strong>nested evidence</strong>",
    )
    extracted = _extract_html(
        ("<title>Portal</title>" + table).encode(),
        "https://example.org/record",
    )

    assert extracted.evidence_level == "abstract"
    assert "poison" not in extracted.text
    assert "hidden" not in extracted.text


def test_conflicting_title_doi_partial_table_rejects_mixed_work():
    partial = """<table>
    <tr><th>Title</th><td>A different work</td></tr>
    <tr><th>DOI</th><td>10.9999/different</td></tr>
    </table>"""
    extracted = _extract_html(
        ("<title>Portal</title>" + _work_table() + partial).encode(),
        "https://example.org/record",
    )

    assert extracted.evidence_level == "metadata"
    assert extracted.text == "Portal"
    assert extracted.bibliographic_metadata == {}


def test_invalid_utf8_disables_raw_byte_bound_table_provenance():
    data = b"<title>Portal</title>\xff" + _work_table().encode()
    extracted = _extract_html(data, "https://example.org/record")

    assert extracted.evidence_level == "metadata"
    assert extracted.text == "Portal"
    assert extracted.bibliographic_metadata == {}


@pytest.mark.parametrize("void_tag", ["br", "img", "input", "meta"])
def test_self_closing_void_tag_does_not_escape_suppressed_ancestry(void_tag):
    html = (
        f"<title>Portal</title><template><{void_tag}/>" + _work_table() + "</template>"
    )
    extracted = _extract_html(html.encode(), "https://example.org/record")

    assert extracted.evidence_level == "metadata"
    assert extracted.text == "Portal"
    assert extracted.observed_doi == ""
    assert extracted.bibliographic_metadata == {}


@pytest.mark.parametrize(
    "marker",
    ["abstractportal", "rendering_abstractportal", "rendering_output_abstractportal"],
)
def test_compound_abstract_container_exposes_body_without_full_text_upgrade(marker):
    body = (
        "The saved abstract describes a bounded method and its unresolved limitations."
    )
    html = f'<title>Neutral study</title><h2>Abstract</h2><div class="{marker}"><div><p>{body}</p></div></div>'
    extracted = _extract_html(html.encode(), "https://example.org/record")
    assert extracted.text == body
    assert extracted.evidence_level == "abstract"
    assert extracted.locators == [
        {"type": "html-section", "value": "Abstract", "start": 0, "end": len(body)}
    ]


@pytest.mark.parametrize(
    "tag", ["script", "style", "noscript", "template", "form", "nav"]
)
def test_compound_abstract_marker_inside_suppressed_container_is_not_evidence(tag):
    body = (
        "This apparent abstract occurs in a suppressed container and is not evidence."
    )
    html = f'<title>Neutral study</title><{tag}><div class="abstractportal"><p>{body}</p></div></{tag}>'
    extracted = _extract_html(html.encode(), "https://example.org/record")
    assert extracted.text == "Neutral study"
    assert extracted.evidence_level == "metadata"


@pytest.mark.parametrize("marker", ["notabstractportal", "abstractportalnavigation"])
def test_similar_compound_container_names_are_not_abstract_markers(marker):
    html = f'<title>Neutral study</title><div class="{marker}">An unrelated block contains enough text but is not an abstract.</div>'
    extracted = _extract_html(html.encode(), "https://example.org/record")
    assert extracted.text == "Neutral study"
    assert extracted.evidence_level == "metadata"


@pytest.mark.parametrize(
    "attribute",
    [
        "hidden",
        'aria-hidden="true"',
        'style="display: none"',
        'style="visibility: hidden!important"',
    ],
)
@pytest.mark.parametrize("location", ["container", "ancestor", "descendant"])
def test_hidden_abstract_body_is_not_evidence_and_does_not_hide_later_visible_body(
    attribute, location
):
    hidden_text = (
        "This hidden text is long enough to be mistaken for a research abstract."
    )
    marked = (
        f'<div class="abstractportal" {attribute if location == "container" else ""}>'
    )
    marked += (
        f"<p {attribute if location == 'descendant' else ''}>{hidden_text}</p></div>"
    )
    if location == "ancestor":
        marked = f"<section {attribute}>{marked}</section>"
    visible = "This later visible abstract has enough text to establish readable abstract evidence."
    rejected = _extract_html(
        ("<title>Neutral study</title>" + marked).encode(), "https://example.org/record"
    )
    assert rejected.text == "Neutral study"
    assert rejected.evidence_level == "metadata"
    accepted = _extract_html(
        (marked + f'<div class="abstractportal">{visible}</div>').encode(),
        "https://example.org/record",
    )
    assert accepted.text == visible
    assert accepted.evidence_level == "abstract"
