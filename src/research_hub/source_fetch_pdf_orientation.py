"""Conservative correction of PDF character direction from glyph geometry."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import math
from typing import Any


def _character_orientation(char: dict[str, Any]) -> int | None:
    """Accept only finite, non-reflected axis-aligned glyph transforms."""
    try:
        matrix = char["matrix"]
        if len(matrix) != 6 or not isinstance(char["text"], str):
            return None
        a, b, c, d, e, f = (float(value) for value in matrix)
        x0, x1, top, bottom = (
            float(char[key]) for key in ("x0", "x1", "top", "bottom")
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not all(
        math.isfinite(value) for value in (a, b, c, d, e, f, x0, x1, top, bottom)
    ):
        return None
    if x1 < x0 or bottom < top:
        return None
    scale = max(abs(a), abs(b), abs(c), abs(d))
    if scale == 0:
        return None
    epsilon = scale * 1e-6
    if abs(b) <= epsilon and abs(c) <= epsilon and a > epsilon and d > epsilon:
        orientation = 0
    elif abs(a) <= epsilon and abs(d) <= epsilon and b > epsilon and c < -epsilon:
        orientation = 90
    elif abs(a) <= epsilon and abs(d) <= epsilon and b < -epsilon and c > epsilon:
        orientation = -90
    else:
        return None
    # pdfplumber uses this flag to choose its rotated extraction settings.
    if char.get("upright") != (orientation == 0):
        return None
    return orientation


def extract_oriented_pdf_text(
    page: Any, original: str
) -> tuple[str, dict[str, Any] | None]:
    """Correct one unambiguous quarter-turn without asserting page reading order.

    Horizontal glyphs may coexist with one rotation sign. Missing/ambiguous
    geometry or any non-whitespace character change preserves ``original``.
    This changes character direction only; table order and complete source
    fidelity still need independent review.
    """
    try:
        chars = page.chars
        orientations = [_character_orientation(char) for char in chars]
    except (AttributeError, TypeError):
        return original, None
    if not orientations or None in orientations:
        return original, None
    rotations = set(orientations) - {0}
    if len(rotations) != 1:
        return original, None
    rotation = rotations.pop()
    line_dir, char_dir = ("ltr", "btt") if rotation == 90 else ("rtl", "ttb")
    try:
        corrected = page.extract_text(
            line_dir_rotated=line_dir, char_dir_rotated=char_dir
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return original, None
    if not isinstance(corrected, str):
        return original, None
    corrected = corrected.strip()
    before = Counter(char for char in original if not char.isspace())
    after = Counter(char for char in corrected if not char.isspace())
    if before != after or corrected == original:
        return original, None
    return corrected, {
        "status": "corrected",
        "reason": "matrix-derived-rotated-character-direction",
        "scope": "rotated-character-direction",
        "rotation_degrees": rotation,
        "rotated_chars": orientations.count(rotation),
        "horizontal_chars": orientations.count(0),
        "line_dir_rotated": line_dir,
        "char_dir_rotated": char_dir,
        "nonwhitespace_character_preservation": "verified",
        "reading_order": "pending",
        "content_fidelity": "pending",
        "source_text_sha256": sha256(original.encode()).hexdigest(),
        "output_text_sha256": sha256(corrected.encode()).hexdigest(),
    }


__all__ = ["extract_oriented_pdf_text"]
