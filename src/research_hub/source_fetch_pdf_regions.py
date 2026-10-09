"""Conservative prose ordering between observed full-width PDF rows."""

from collections import Counter
from hashlib import sha256
import re
from typing import Any


def reorder_prose_regions(
    page: Any,
    rows: list[list[dict[str, Any]]],
    gutter: float,
    original: str,
) -> tuple[str, dict[str, Any]] | None:
    """Preserve spanning rows; reorder one independently sustained prose band.

    This is an extraction repair, never a content-fidelity confirmation. Regions
    with graphics, numeric layouts or unresolved glyphs retain their row order.
    """
    pieces: list[list[list[dict[str, Any]]]] = []
    band: list[list[dict[str, Any]]] = []
    repaired: list[dict[str, Any]] = []
    preserved_regions = 0

    def flush() -> None:
        nonlocal band, preserved_regions
        if not band:
            return
        first = min(w["top"] for row in band for w in row)
        last = max(w["bottom"] for row in band for w in row)
        columns = [
            [[w for w in row if w["x1"] <= gutter] for row in band],
            [[w for w in row if w["x0"] >= gutter] for row in band],
        ]
        supported = sum(
            bool(left and right)
            and min(w["x0"] for w in right) - max(w["x1"] for w in left) >= 18
            for left, right in zip(*columns)
        )
        horizontal = [
            edge
            for edge in page.edges
            if edge.get("orientation") == "h" and edge["x0"] < gutter < edge["x1"]
        ]
        graphic = (
            any(first <= edge["top"] <= last for edge in horizontal)
            or (
                len(horizontal) >= 2
                and min(edge["top"] for edge in horizontal) <= last
                and max(edge["top"] for edge in horizontal) >= first
            )
        ) or any(
            item["x0"] < gutter < item["x1"]
            and item["top"] < last
            and item["bottom"] > first
            for item in getattr(page, "images", ())
        )
        prose = []
        for column in columns:
            words = [w for row in column for w in row]
            count = 0
            for row in column:
                line = " ".join(w["text"] for w in row)
                letters = len(re.findall(r"[^\W\d_]", line))
                if (
                    "(cid:" not in line
                    and letters >= 20
                    and letters >= len("".join(line.split())) * 0.65
                ):
                    count += 1
            numeric = sum(bool(re.fullmatch(r"[\d.,%+−-]+", w["text"])) for w in words)
            prose.append(
                count >= 6
                and words
                and numeric < len(words) * 0.25
                and not any("(cid:" in w["text"] for w in words)
            )
        if supported >= 6 and all(prose) and not graphic:
            ordered = columns[0] + columns[1]
            pieces.append(ordered)
            repaired.append(
                {
                    "top": round(first, 3),
                    "bottom": round(last, 3),
                    "words": sum(map(len, band)),
                }
            )
        else:
            pieces.append(band)
            preserved_regions += 1
        band = []

    for row in rows:
        if any(w["x0"] < gutter < w["x1"] for w in row):
            flush()
            pieces.append([row])
        else:
            band.append(row)
    flush()
    if len(repaired) != 1:
        return None
    ordered_rows = [row for piece in pieces for row in piece if row]
    text = "\n".join(" ".join(w["text"] for w in row) for row in ordered_rows).strip()
    before = Counter(c for c in original if not c.isspace())
    after = Counter(c for c in text if not c.isspace())
    if before != after or sum(map(len, ordered_rows)) != sum(map(len, rows)):
        return None
    if "".join(original.split()) == "".join(text.split()):
        return None
    return text, {
        "status": "reordered",
        "reason": "sustained-two-column-prose-regions",
        "gutter_x": round(gutter, 3),
        "words": sum(map(len, rows)),
        "word_preservation": "verified",
        "fidelity_status": "pending",
        "reordered_regions": repaired,
        "unreordered_regions": preserved_regions,
        "source_text_sha256": sha256(original.encode()).hexdigest(),
        "output_text_sha256": sha256(text.encode()).hexdigest(),
    }
