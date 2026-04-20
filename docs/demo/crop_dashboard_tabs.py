"""Crop the dashboard tab PNGs to just the visible-above-fold hero content.

Full-page renders are 2880×5000-10810 which is way more than a reader
needs to see at a glance. This crops each pick to the top N pixels
(the part visible without scrolling) and scales to ~1400px wide so
README thumbnails stay readable.

Pure Pillow, no external deps.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image


HERE = Path(__file__).parent
IMG_DIR = HERE.parent / "images"

# (source_name, crop_top_px_from_original, caption)
# crop_top_px is measured on the ORIGINAL 2880-wide full-page render.
TABS = [
    ("dashboard-overview.png",          3500, "Overview — treemap + storage map + recent feed"),
    ("dashboard-library-subtopic.png",  3200, "Library — per-cluster drill-down"),
    ("dashboard-diagnostics.png",       3500, "Diagnostics — health badges + grouped drift alerts"),
    ("dashboard-manage-live.png",       3200, "Manage — every CLI action as a button"),
]

TARGET_W = 1400


def crop_to_hero(src: Path, dst: Path, crop_top_px: int) -> None:
    img = Image.open(src).convert("RGB")
    w, h = img.size
    top_slice = img.crop((0, 0, w, min(crop_top_px, h)))
    # Downscale preserving aspect
    ratio = TARGET_W / w
    new_size = (TARGET_W, int(top_slice.height * ratio))
    resized = top_slice.resize(new_size, Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    resized.save(dst, optimize=True)
    kb = dst.stat().st_size / 1024
    print(f"  {dst.name:45} {new_size[0]:>5}x{new_size[1]:<5}  {kb:>6.1f} KB")


def main() -> None:
    out_dir = IMG_DIR / "hero"
    print(f"Cropping + downsizing -> {out_dir}")
    for src_name, crop_px, _caption in TABS:
        src = IMG_DIR / src_name
        if not src.exists():
            print(f"  SKIP (missing): {src_name}")
            continue
        dst = out_dir / src_name  # same filename, different dir
        crop_to_hero(src, dst, crop_px)


if __name__ == "__main__":
    main()
