from copy import deepcopy
import io
from types import SimpleNamespace
import unittest

import pdfplumber
from pdfplumber.utils import extract_text
from research_hub.source_fetch_pdf_baselines import align_pdf_baselines
from tests.test_source_fetch_pdf_orientation import _pdf


def _page():
    chars = []
    for i, ch in enumerate("The INLINE word continues."):
        top = 104.0 if 4 <= i < 10 else 100.0
        chars.append(
            dict(
                text=ch,
                x0=20 + 6 * i,
                x1=26 + 6 * i,
                top=top,
                bottom=top + 10,
                doctop=top,
                size=10,
                fontname="InlineFace" if 4 <= i < 10 else "NormalFace",
                upright=True,
                matrix=(1, 0, 0, 1, 20 + 6 * i, 500),
            )
        )
    fonts = {
        1: SimpleNamespace(fontname="NormalFace", get_descent=lambda: 0.0),
        2: SimpleNamespace(fontname="InlineFace", get_descent=lambda: -0.4),
    }
    return SimpleNamespace(
        chars=chars,
        height=610,
        pdf=SimpleNamespace(rsrcmgr=SimpleNamespace(_cached_fonts=fonts)),
    )


class BaselineTests(unittest.TestCase):
    def test_matching_matrix_baseline_restores_inline_text(self):
        page = _page()
        before = deepcopy(page.chars)
        old = extract_text(page.chars)
        proxy, new, diagnostic = align_pdf_baselines(page, old)
        self.assertEqual(new, "The INLINE word continues.")
        self.assertEqual(page.chars, before)
        self.assertEqual(diagnostic["fidelity_status"], "pending")
        self.assertNotEqual(proxy, page)

    def test_true_superscript_is_not_shifted(self):
        page = _page()
        for ch in page.chars[4:10]:
            ch.update(matrix=(1, 0, 0, 0.6, ch["x0"], 510), size=6)
        old = extract_text(page.chars)
        self.assertEqual(align_pdf_baselines(page, old), (page, old, None))

    def test_ambiguous_geometry_stays_unchanged(self):
        for variant in ("missing", "nonfinite", "rotation", "different-scale"):
            page = _page()
            old = extract_text(page.chars)
            if variant == "missing":
                del page.chars[0]["matrix"]
            elif variant == "nonfinite":
                page.chars[0]["matrix"] = (1, 0, 0, 1, 0, float("nan"))
            elif variant == "rotation":
                page.chars[0]["matrix"] = (0, 1, -1, 0, 0, 0)
            else:
                for ch in page.chars[4:10]:
                    ch["matrix"] = (1, 0, 0, 0.6, ch["x0"], 500)
                    ch["size"] = 6
            with self.subTest(variant=variant):
                self.assertEqual(align_pdf_baselines(page, old), (page, old, None))

    def test_character_loss_is_not_accepted(self):
        page = _page()
        old = extract_text(page.chars) + "!"
        self.assertEqual(align_pdf_baselines(page, old), (page, old, None))

    def test_real_pdf_font_size_difference_is_unchanged(self):
        data = _pdf(
            "BT /F1 24 Tf 1 0 0 1 30 650 Tm (Section) Tj ET",
            "BT /F1 10 Tf 1 0 0 1 230 650 Tm (A long body paragraph stays on its own line.) Tj ET",
        )
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page = pdf.pages[0]
            old = page.extract_text().strip()
            self.assertEqual(align_pdf_baselines(page, old), (page, old, None))

    def test_real_pdf_text_rise_is_not_normalized(self):
        for rise in (12, -12):
            data = _pdf(
                f"BT /F1 12 Tf 1 0 0 1 40 700 Tm (Measured concentration x) Tj {rise} Ts (2) Tj 0 Ts ( was reported.) Tj ET"
            )
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                page = pdf.pages[0]
                old = page.extract_text().strip()
                with self.subTest(rise=rise):
                    self.assertEqual(align_pdf_baselines(page, old), (page, old, None))


if __name__ == "__main__":
    unittest.main()
