"""Synthetic PDF coverage for geometry-derived character direction correction."""

from collections import Counter
from copy import deepcopy
import io
from types import SimpleNamespace
import unittest

from research_hub.source_fetch_pdf_orientation import extract_oriented_pdf_text

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def _pdf(*commands: str) -> bytes:
    """Build a real one-page PDF without optional fixture-generation packages."""
    content = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(data)


def _text(text: str, matrix: str = "1 0 0 1 40 740") -> str:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /F1 12 Tf {matrix} Tm ({escaped}) Tj ET"


def _characters(text: str) -> Counter:
    return Counter(char for char in text if not char.isspace())


@unittest.skipIf(pdfplumber is None, "PDF extraction requires pdfplumber")
class TestPdfOrientation(unittest.TestCase):
    def test_actual_pdf_rotated_character_direction(self):
        for matrix, rotation, expected_directions in [
            ("0 1 -1 0 400 100", 90, ("ltr", "btt")),
            ("0 -1 1 0 200 650", -90, ("rtl", "ttb")),
        ]:
            with (
                self.subTest(rotation=rotation),
                pdfplumber.open(
                    io.BytesIO(_pdf(_text("Header"), _text("Direction 35", matrix)))
                ) as pdf,
            ):
                source = pdf.pages[0]
                original = (source.extract_text() or "").strip()
                calls = []

                def extract_text(**kwargs):
                    calls.append(kwargs)
                    return source.extract_text(**kwargs)

                page = SimpleNamespace(chars=source.chars, extract_text=extract_text)
                corrected, diagnostic = extract_oriented_pdf_text(page, original)
                self.assertIn("Direction", corrected)
                self.assertIn("35", corrected)
                self.assertIn("Header", corrected)
                self.assertEqual(_characters(corrected), _characters(original))
                self.assertEqual(
                    calls,
                    [
                        {
                            "line_dir_rotated": expected_directions[0],
                            "char_dir_rotated": expected_directions[1],
                        }
                    ],
                )
                if diagnostic is not None:
                    self.assertEqual(diagnostic["rotation_degrees"], rotation)
                    self.assertEqual(diagnostic["reading_order"], "pending")
                    self.assertEqual(diagnostic["content_fidelity"], "pending")
                else:
                    # The default already uses downward direction for -90°.
                    self.assertEqual(rotation, -90)
                    self.assertEqual(corrected, original)

    def test_actual_pdf_horizontal_unchanged(self):
        with pdfplumber.open(io.BytesIO(_pdf(_text("Plain 123 text")))) as pdf:
            page = pdf.pages[0]
            original = (page.extract_text() or "").strip()
            self.assertEqual(
                extract_oriented_pdf_text(page, original), (original, None)
            )

    def test_actual_pdf_ambiguous_geometry_unchanged(self):
        for commands in [
            (_text("Left", "0 1 -1 0 400 100"), _text("Right", "0 -1 1 0 200 650")),
            (_text("Rotated", "0 1 -1 0 400 100"), _text("Skewed", "1 .2 0 1 40 740")),
            (
                _text("Rotated", "0 1 -1 0 400 100"),
                _text("Reflected", "-1 0 0 1 200 740"),
            ),
        ]:
            with (
                self.subTest(commands=commands),
                pdfplumber.open(io.BytesIO(_pdf(*commands))) as pdf,
            ):
                page = pdf.pages[0]
                original = (page.extract_text() or "").strip()
                self.assertEqual(
                    extract_oriented_pdf_text(page, original), (original, None)
                )

    def test_incomplete_geometry_unchanged(self):
        for invalid in [
            "missing-matrix",
            "nonfinite-matrix",
            "missing-box",
            "nonfinite-box",
            "upright-mismatch",
        ]:
            with (
                self.subTest(invalid=invalid),
                pdfplumber.open(
                    io.BytesIO(_pdf(_text("Direction 35", "0 1 -1 0 400 100")))
                ) as pdf,
            ):
                source = pdf.pages[0]
                original = (source.extract_text() or "").strip()
                chars = deepcopy(source.chars)
                if invalid == "missing-matrix":
                    del chars[0]["matrix"]
                elif invalid == "nonfinite-matrix":
                    chars[0]["matrix"] = (0, 1, -1, 0, float("nan"), 0)
                elif invalid == "missing-box":
                    del chars[0]["x0"]
                elif invalid == "nonfinite-box":
                    chars[0]["top"] = float("inf")
                else:
                    chars[0]["upright"] = True

                def unexpected_extraction(**kwargs):
                    self.fail("ambiguous geometry must not be re-extracted")

                page = SimpleNamespace(chars=chars, extract_text=unexpected_extraction)
                self.assertEqual(
                    extract_oriented_pdf_text(page, original), (original, None)
                )

    def test_candidate_character_loss_or_addition_unchanged(self):
        for candidate in ["Direction 3", "Direction 355", None]:
            with (
                self.subTest(candidate=candidate),
                pdfplumber.open(
                    io.BytesIO(_pdf(_text("Direction 35", "0 1 -1 0 400 100")))
                ) as pdf,
            ):
                source = pdf.pages[0]
                original = (source.extract_text() or "").strip()
                page = SimpleNamespace(
                    chars=source.chars, extract_text=lambda **kwargs: candidate
                )
                self.assertEqual(
                    extract_oriented_pdf_text(page, original), (original, None)
                )

    def test_accepted_diagnostic_is_scoped_and_hashed(self):
        with pdfplumber.open(
            io.BytesIO(_pdf(_text("Direction 35", "0 1 -1 0 400 100")))
        ) as pdf:
            page = pdf.pages[0]
            original = (page.extract_text() or "").strip()
            corrected, diagnostic = extract_oriented_pdf_text(page, original)
            self.assertNotEqual(corrected, original)
            self.assertEqual(diagnostic["scope"], "rotated-character-direction")
            self.assertEqual(
                diagnostic["nonwhitespace_character_preservation"], "verified"
            )
            self.assertNotEqual(
                diagnostic["source_text_sha256"], diagnostic["output_text_sha256"]
            )
            self.assertEqual(diagnostic["horizontal_chars"], 0)
            self.assertEqual(diagnostic["rotated_chars"], len(page.chars))
