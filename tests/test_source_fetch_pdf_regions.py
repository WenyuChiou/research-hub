"""Extraction repairs preserve unresolved fidelity and every source character."""

from collections import Counter
from types import SimpleNamespace

from research_hub.source_fetch_extraction import _pdf_reading_order_text
from research_hub.source_fetch_pdf_regions import reorder_prose_regions


def word(text, x0, x1, top):
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": top + 10}


def prose_rows(top=20):
    return [
        [
            word(f"Leftflowcontainsacompleteproseargument{i}.", 40, 260, top + i * 16),
            word(
                f"Rightflowcontainsaseparateproseargument{i}.", 340, 560, top + i * 16
            ),
        ]
        for i in range(8)
    ]


def text_of(rows):
    return "\n".join(" ".join(w["text"] for w in row) for row in rows)


def page_of(rows, *, edges=(), images=()):
    return SimpleNamespace(
        width=600,
        edges=edges,
        images=images,
        extract_words=lambda: [w for row in rows for w in row],
    )


def test_spanning_front_matter_and_footer_keep_their_place():
    header = [word("Complete source title and author block", 80, 520, 0)]
    footer = [word("Journal publication and source page", 100, 500, 165)]
    rows = [header, *prose_rows(), footer]
    repaired, diagnostics = reorder_prose_regions(
        page_of(rows), rows, 300, text_of(rows)
    )
    assert repaired.splitlines() == [
        header[0]["text"],
        *[r[0]["text"] for r in rows[1:-1]],
        *[r[1]["text"] for r in rows[1:-1]],
        footer[0]["text"],
    ]
    assert diagnostics["fidelity_status"] == "pending"
    assert diagnostics["words"] == 18


def test_unpaired_column_heading_is_part_of_its_column():
    rows = [[word("Abstract", 40, 110, 4)], *prose_rows()]
    original = text_of(rows)
    repaired, diagnostics = reorder_prose_regions(page_of(rows), rows, 300, original)
    assert repaired.splitlines() == [
        "Abstract",
        *[r[0]["text"] for r in rows[1:]],
        *[r[1]["text"] for r in rows[1:]],
    ]
    assert diagnostics["reason"] == "sustained-two-column-prose-regions"
    assert diagnostics["fidelity_status"] == "pending"


def test_two_prose_bands_with_an_unresolved_spanning_block_are_preserved():
    caption = [
        word(
            "A full-width caption separates the two observed prose flows", 60, 540, 170
        )
    ]
    rows = [*prose_rows(), caption, *prose_rows(200)]
    assert reorder_prose_regions(page_of(rows), rows, 300, text_of(rows)) is None


def test_page_fallback_keeps_front_matter_and_full_width_title_out_of_prose():
    metadata = [
        [word("Title", 40, 120, 0), word("Journal", 360, 420, 0)],
        [word("Year", 40, 120, 16), word("Authors", 360, 420, 16)],
        [word("The source title spans the page", 60, 540, 32)],
        [word("Abstract", 40, 110, 48)],
    ]
    rows = [*metadata, *prose_rows(64)]
    repaired, diagnostics = _pdf_reading_order_text(page_of(rows), text_of(rows))
    assert repaired.splitlines() == [
        *text_of(metadata).splitlines(),
        *[row[0]["text"] for row in rows[4:]],
        *[row[1]["text"] for row in rows[4:]],
    ]
    assert diagnostics["reason"] == "sustained-two-column-prose-regions"
    assert diagnostics["fidelity_status"] == "pending"
    assert Counter(c for c in repaired if not c.isspace()) == Counter(
        c for c in text_of(rows) if not c.isspace()
    )


def test_spanning_graphic_prevents_reordering_the_band():
    rows = prose_rows()
    edge = {"orientation": "h", "x0": 20, "x1": 580, "top": 80}
    assert (
        reorder_prose_regions(page_of(rows, edges=[edge]), rows, 300, text_of(rows))
        is None
    )


def test_page_fallback_preserves_a_band_enclosed_by_outside_horizontal_rules():
    metadata = [
        [word("Title", 40, 120, 0), word("Journal", 360, 420, 0)],
        [word("Year", 40, 120, 16), word("Authors", 360, 420, 16)],
        [word("The source title spans the page", 60, 540, 32)],
        [word("Abstract", 40, 110, 48)],
    ]
    rows = [*metadata, *prose_rows(64)]
    edges = [
        {"orientation": "h", "x0": 20, "x1": 580, "top": 44},
        {"orientation": "h", "x0": 20, "x1": 580, "top": 192},
    ]
    original = text_of(rows)
    output, diagnostics = _pdf_reading_order_text(page_of(rows, edges=edges), original)
    assert output == original
    assert diagnostics["status"] == "pending"


def test_spanning_image_prevents_reordering_the_band():
    rows = prose_rows()
    image = {"x0": 20, "x1": 580, "top": 60, "bottom": 90}
    assert (
        reorder_prose_regions(page_of(rows, images=[image]), rows, 300, text_of(rows))
        is None
    )


def test_unresolved_glyph_prevents_reordering_the_band():
    rows = prose_rows()
    rows[2][0]["text"] += "(cid:17)"
    assert reorder_prose_regions(page_of(rows), rows, 300, text_of(rows)) is None


def test_numeric_layout_prevents_reordering_the_band():
    rows = prose_rows()
    for row in rows:
        row.extend(
            word(str(i), 270 + i * 3, 272 + i * 3, row[0]["top"]) for i in range(5)
        )
    assert reorder_prose_regions(page_of(rows), rows, 300, text_of(rows)) is None


def test_single_column_prose_stays_unchanged():
    rows = [[row[0]] for row in prose_rows()]
    assert reorder_prose_regions(page_of(rows), rows, 300, text_of(rows)) is None


def test_sparse_two_column_rows_do_not_establish_a_flow():
    rows = prose_rows()[:5]
    assert reorder_prose_regions(page_of(rows), rows, 300, text_of(rows)) is None


def test_character_disagreement_prevents_reordering():
    rows = prose_rows()
    assert (
        reorder_prose_regions(page_of(rows), rows, 300, text_of(rows) + "missing")
        is None
    )


def test_graphic_band_is_preserved_when_another_band_can_be_repaired():
    first = prose_rows()
    caption = [word("Full-width separator", 80, 520, 170)]
    second = prose_rows(200)
    rows = [*first, caption, *second]
    edge = {"orientation": "h", "x0": 20, "x1": 580, "top": 240}
    repaired, diagnostics = reorder_prose_regions(
        page_of(rows, edges=[edge]), rows, 300, text_of(rows)
    )
    assert repaired.splitlines()[17:] == text_of(second).splitlines()
    assert diagnostics["unreordered_regions"] == 1
    assert diagnostics["fidelity_status"] == "pending"
