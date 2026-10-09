from collections import Counter
from types import SimpleNamespace
import unittest

from research_hub.source_fetch_pdf_sidebars import separate_marginal_pdf_text


def _page():
    words = []
    for i in range(40):
        top = 100 + 11 * i
        label = "Funding:" if i == 0 else "Citation:" if i == 1 else "Marginal"
        for j, text in enumerate((label, "note", "content")):
            words.append(
                dict(
                    text=text,
                    x0=30 + 35 * j,
                    x1=60 + 35 * j,
                    top=top,
                    bottom=top + 8,
                    upright=True,
                )
            )
        top = 100 + 15 * i
        for j, text in enumerate(("The", "wide", "body", "has", "continuous", "prose")):
            words.append(
                dict(
                    text=text,
                    x0=180 + 60 * j,
                    x1=215 + 60 * j,
                    top=top,
                    bottom=top + 10,
                    upright=True,
                )
            )
    original = " ".join(w["text"] for w in words)
    page = SimpleNamespace(
        width=612, height=1000, edges=[], images=[], extract_words=lambda: words
    )
    return page, original, words


class SidebarTests(unittest.TestCase):
    def test_narrow_margin_does_not_interrupt_body(self):
        page, old, _ = _page()
        new, diagnostic = separate_marginal_pdf_text(page, old)
        self.assertIsNotNone(diagnostic)
        self.assertEqual(diagnostic["fidelity_status"], "pending")
        self.assertTrue(new.startswith("The wide body has continuous prose"))
        self.assertEqual(Counter("".join(old.split())), Counter("".join(new.split())))

    def test_numeric_table_is_unchanged(self):
        page, _, words = _page()
        for w in words:
            if w["x0"] < 180:
                w["text"] = "123"
        old = " ".join(w["text"] for w in words)
        self.assertEqual(separate_marginal_pdf_text(page, old), (old, None))

    def test_crossing_text_and_rule_are_unchanged(self):
        for feature in ("text", "rule", "image"):
            page, old, words = _page()
            if feature == "text":
                words.append(
                    dict(
                        text="spanning",
                        x0=20,
                        x1=550,
                        top=200,
                        bottom=210,
                        upright=True,
                    )
                )
                old += " spanning"
            elif feature == "rule":
                page.edges = [dict(orientation="h", x0=20, x1=550, top=200)]
            else:
                page.images = [dict(x0=20, x1=550, top=200)]
            with self.subTest(feature=feature):
                self.assertEqual(separate_marginal_pdf_text(page, old), (old, None))

    def test_character_loss_and_normal_size_margin_are_unchanged(self):
        page, old, _ = _page()
        self.assertEqual(separate_marginal_pdf_text(page, old + "!"), (old + "!", None))
        page, old, words = _page()
        for w in words:
            w["bottom"] = w["top"] + 10
        self.assertEqual(separate_marginal_pdf_text(page, old), (old, None))

    def test_rotated_and_nonfinite_words_are_unchanged(self):
        for value in ("rotated", "nonfinite"):
            page, old, words = _page()
            if value == "rotated":
                words[0]["upright"] = False
            else:
                words[0]["top"] = float("nan")
            with self.subTest(value=value):
                self.assertEqual(separate_marginal_pdf_text(page, old), (old, None))

    def test_borderless_categorical_table_keeps_row_associations(self):
        page, _, words = _page()
        for index, word in enumerate(words):
            row = index // 9
            word["top"] = 100 + 15 * row
            word["bottom"] = word["top"] + (8 if word["x0"] < 180 else 10)
            if word["text"].endswith(":"):
                word["text"] = "Category"
        old = " ".join(w["text"] for w in words)
        self.assertEqual(separate_marginal_pdf_text(page, old), (old, None))

    def test_repeated_metadata_field_is_not_independent_evidence(self):
        page, _, words = _page()
        for word in words:
            if word["text"] in ("Funding:", "Citation:"):
                word["text"] = "Funding:" if word["text"] == "Funding:" else "FUNDING:"
        old = " ".join(word["text"] for word in words)
        self.assertEqual(separate_marginal_pdf_text(page, old), (old, None))

    def test_metadata_alias_is_not_an_independent_field(self):
        page, _, words = _page()
        for word in words:
            if word["text"] == "Funding:":
                word["text"] = "Data availability:"
            elif word["text"] == "Citation:":
                word["text"] = "Data availability statement:"
        old = " ".join(word["text"] for word in words)
        self.assertEqual(separate_marginal_pdf_text(page, old), (old, None))


if __name__ == "__main__":
    unittest.main()
