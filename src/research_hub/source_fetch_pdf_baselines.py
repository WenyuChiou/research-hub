"""Align matching glyph baselines without merging distinct script positions."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import math
from typing import Any


class _BaselinePage:
    def __init__(self, page: Any, chars: list[dict[str, Any]]):
        self._page, self.chars = page, chars

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def extract_text(self, **kwargs: Any) -> str:
        from pdfplumber.utils import extract_text

        return extract_text(self.chars, **kwargs)

    def extract_words(self, **kwargs: Any) -> list[dict[str, Any]]:
        from pdfplumber.utils import extract_words

        return extract_words(self.chars, **kwargs)


def align_pdf_baselines(
    page: Any, original: str
) -> tuple[Any, str, dict[str, Any] | None]:
    """Use matrix baselines only for equal-size horizontal glyphs on one line.

    True raised/lowered baselines and different-size superscripts stay separate.
    A changed character inventory discards the entire candidate.
    """
    try:
        chars = [dict(char) for char in page.chars]
        font_descents: dict[str, set[float]] = {}
        for font in page.pdf.rsrcmgr._cached_fonts.values():
            font_descents.setdefault(str(font.fontname), set()).add(
                float(font.get_descent())
            )
        for char in chars:
            matrix = tuple(float(v) for v in char["matrix"])
            if len(matrix) != 6 or not all(math.isfinite(v) for v in matrix):
                return page, original, None
            a, b, c, d, _, _ = matrix
            if (
                a <= 0
                or d <= 0
                or abs(b) > 1e-6
                or abs(c) > 1e-6
                or not char["upright"]
            ):
                return page, original, None
            char["_baseline"] = matrix[5]
            char["_scale"] = float(char["size"])
            if not math.isfinite(char["_scale"]) or char["_scale"] <= 0:
                return page, original, None
            if not all(
                math.isfinite(float(char[k])) for k in ("top", "bottom", "doctop")
            ):
                return page, original, None
            descents = font_descents.get(char["fontname"], set())
            if len(descents) != 1:
                char["_eligible"] = False
            else:
                descent = next(iter(descents))
                expected_bottom = (
                    float(page.height) - matrix[5] - char["_scale"] * descent
                )
                char["_eligible"] = (
                    math.isfinite(descent)
                    and abs(char["bottom"] - expected_bottom) <= 0.2
                )
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return page, original, None
    groups: list[list[dict[str, Any]]] = []
    for char in sorted(chars, key=lambda ch: (-ch["_baseline"], ch["_scale"])):
        if not char["_eligible"]:
            continue
        group = next(
            (
                g
                for g in reversed(groups)
                if abs(g[0]["_baseline"] - char["_baseline"]) <= 0.15
                and abs(g[0]["_scale"] - char["_scale"]) <= 0.02 * char["_scale"]
            ),
            None,
        )
        if group is None:
            groups.append([char])
        else:
            group.append(char)
    changed = 0
    for group in groups:
        if len(group) < 8:
            continue
        tops = Counter(round(float(ch["top"]), 2) for ch in group)
        target, count = tops.most_common(1)[0]
        if count < len(group) * 0.6:
            continue
        for char in group:
            delta = target - char["top"]
            if abs(delta) > 0.5:
                char["top"] += delta
                char["bottom"] += delta
                char["doctop"] += delta
                changed += 1
    if not changed:
        return page, original, None
    for char in chars:
        del char["_baseline"], char["_scale"], char["_eligible"]
    proxy = _BaselinePage(page, chars)
    try:
        corrected = proxy.extract_text().strip()
    except (TypeError, ValueError, KeyError):
        return page, original, None
    if Counter(c for c in original if not c.isspace()) != Counter(
        c for c in corrected if not c.isspace()
    ):
        return page, original, None
    if corrected == original:
        return page, original, None
    return (
        proxy,
        corrected,
        {
            "status": "reordered",
            "reason": "equal-scale-matrix-baseline-alignment",
            "adjusted_characters": changed,
            "fidelity_status": "pending",
            "source_text_sha256": sha256(original.encode()).hexdigest(),
            "output_text_sha256": sha256(corrected.encode()).hexdigest(),
        },
    )
