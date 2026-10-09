"""Conservative separation of an asymmetric marginal text flow."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import math
import re
from typing import Any


def separate_marginal_pdf_text(
    page: Any, original: str
) -> tuple[str, dict[str, Any] | None]:
    """Keep a clearly narrower margin from interrupting the wide prose column.

    Only a single sustained outer gutter with small margin type is eligible.
    Tables, crossing interior text/rules, rotations and ambiguous gutters keep
    the original. This does not establish document-level reading order.
    """
    try:
        width, height = float(page.width), float(page.height)
        words = page.extract_words()
        for word in words:
            values = [float(word[k]) for k in ("x0", "x1", "top", "bottom")]
            if not all(math.isfinite(v) for v in values):
                return original, None
            if not word.get("upright", True) or "(cid:" in word["text"]:
                return original, None
        if (
            not math.isfinite(width)
            or not math.isfinite(height)
            or min(width, height) <= 0
        ):
            return original, None
    except (AttributeError, KeyError, TypeError, ValueError):
        return original, None
    if len(words) < 40:
        return original, None
    rows: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not rows or abs(word["top"] - rows[-1][0]["top"]) > 3:
            rows.append([])
        rows[-1].append(word)
    for row in rows:
        row.sort(key=lambda w: w["x0"])
    candidates = {
        (left["x1"] + right["x0"]) / 2
        for row in rows
        for left, right in zip(row, row[1:])
        if right["x0"] - left["x1"] >= 12
        and (
            0.1 < (left["x1"] + right["x0"]) / (2 * width) < 0.35
            or 0.65 < (left["x1"] + right["x0"]) / (2 * width) < 0.9
        )
    }
    accepted = []
    for point in candidates:
        leading, trailing, left_rows, right_rows = [], [], [], []
        valid = True
        for row in rows:
            if any(w["x0"] < point < w["x1"] for w in row):
                if max(w["bottom"] for w in row) <= height * 0.15:
                    leading.append(row)
                elif min(w["top"] for w in row) >= height * 0.9:
                    trailing.append(row)
                else:
                    valid = False
                    break
            else:
                left_rows.append([w for w in row if w["x1"] <= point])
                right_rows.append([w for w in row if w["x0"] >= point])
        if not valid:
            continue
        support = sum(bool(a and b) for a, b in zip(left_rows, right_rows))
        columns = [
            [w for row in group for w in row] for group in (left_rows, right_rows)
        ]
        if support < 6 or any(len(col) < 20 for col in columns):
            continue
        nonempty_rows = [
            sum(bool(row) for row in group) for group in (left_rows, right_rows)
        ]
        if support >= min(nonempty_rows) * 0.8:
            continue
        extents = [
            max(w["x1"] for w in col) - min(w["x0"] for w in col) for col in columns
        ]
        narrow = 0 if extents[0] < extents[1] else 1
        wide = 1 - narrow
        marginal_text = "\n".join(
            " ".join(w["text"] for w in row)
            for row in (left_rows, right_rows)[narrow]
            if row
        )
        metadata_fields = {
            re.sub(r" statement$", "", field.casefold())
            for field in re.findall(
                r"(?im)^(Citation|Editor|Received|Accepted|Published|Copyright|Funding|Competing interests|Data availability(?: statement)?|Peer Review History)\s*:",
                marginal_text,
            )
        }
        if len(metadata_fields) < 2:
            continue
        if extents[narrow] > extents[wide] * 0.5:
            continue
        sizes = [sorted(w["bottom"] - w["top"] for w in col) for col in columns]
        medians = [group[len(group) // 2] for group in sizes]
        if min(medians) <= 0 or medians[narrow] >= medians[wide] * 0.9:
            continue
        for col in columns:
            numeric = sum(bool(re.fullmatch(r"[\d.,%+−-]+", w["text"])) for w in col)
            if numeric >= len(col) * 0.2:
                valid = False
        if not valid:
            continue
        try:
            if any(
                e.get("orientation") == "h"
                and e["x0"] < point < e["x1"]
                and height * 0.15 < e["top"] < height * 0.9
                for e in page.edges
            ):
                continue
            if any(
                im["x0"] < point < im["x1"] and height * 0.15 < im["top"] < height * 0.9
                for im in page.images
            ):
                continue
        except (AttributeError, KeyError, TypeError):
            return original, None
        accepted.append(
            (support, point, wide, leading, trailing, left_rows, right_rows)
        )
    if not accepted:
        return original, None
    accepted.sort(key=lambda item: (-item[0], item[1]))
    support, point, wide, leading, trailing, left_rows, right_rows = accepted[0]
    if any(
        abs(other[1] - point) > 12 and other[0] >= support * 0.85
        for other in accepted[1:]
    ):
        return original, None
    columns = (left_rows, right_rows)
    ordered_rows = leading + columns[wide] + columns[1 - wide] + trailing
    corrected = "\n".join(
        " ".join(w["text"] for w in row) for row in ordered_rows if row
    ).strip()
    if sum(len(row) for row in ordered_rows) != len(words):
        return original, None
    if Counter(c for c in original if not c.isspace()) != Counter(
        c for c in corrected if not c.isspace()
    ):
        return original, None
    if corrected == original:
        return original, None
    return corrected, {
        "status": "reordered",
        "reason": "asymmetric-small-type-marginal-flow",
        "gutter_x": round(point, 3),
        "wide_column": "left" if wide == 0 else "right",
        "word_preservation": "verified",
        "fidelity_status": "pending",
        "source_text_sha256": sha256(original.encode()).hexdigest(),
        "output_text_sha256": sha256(corrected.encode()).hexdigest(),
    }
