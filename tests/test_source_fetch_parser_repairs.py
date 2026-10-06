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
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"\nendstream"
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
    assert extracted.locators[-1]["geometry_default_media_box"] == [0.0, 0.0, 612.0, 792.0]


def test_normal_pdf_keeps_page_text_and_locator_shape():
    extracted = _extract_pdf(_synthetic_pdf([(True, "Normal page")]))

    assert extracted.text == "Normal page"
    assert extracted.locators == [
        {"type": "pdf-page", "value": 1, "start": 0, "end": 11}
    ]
    assert "geometry_default_pages" not in extracted.diagnostics


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
    duplicate = "<tr><th>Article Title</th><td>Duplicate</td></tr>" if duplicate_title else ""
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
        lambda: "<title>Portal</title>" + _work_table() + _work_table(doi="10.1234/two"),
        lambda: '<meta name="citation_doi" content="10.9999/conflict"><title>Portal</title>' + _work_table(),
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
        f"<title>Portal</title><template><{void_tag}/>"
        + _work_table()
        + "</template>"
    )
    extracted = _extract_html(html.encode(), "https://example.org/record")

    assert extracted.evidence_level == "metadata"
    assert extracted.text == "Portal"
    assert extracted.observed_doi == ""
    assert extracted.bibliographic_metadata == {}
