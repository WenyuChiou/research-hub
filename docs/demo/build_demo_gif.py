"""Generate docs/images/lazy-mode-demo.gif from real captured terminal output.

Renders frames as PIL images with monospace font + ANSI-style coloring,
then saves an animated GIF. No ffmpeg, no external recorder needed.

Idea: 3 commands, each typed character-by-character (typing effect),
then output revealed line-by-line. End result fits in ~2-3 MB GIF
suitable for GitHub README.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# ---------- Terminal styling ----------

CHAR_W = 9          # monospace cell width in px
CHAR_H = 18         # monospace cell height in px
PADDING = 16        # window padding

COLS = 100
ROWS = 32

WIDTH = COLS * CHAR_W + 2 * PADDING
HEIGHT = ROWS * CHAR_H + 2 * PADDING + 28  # extra room for title bar

# A "macOS-y" terminal palette
BG = (30, 30, 38)
FG = (220, 220, 220)
PROMPT_FG = (130, 200, 255)   # cyan-ish
GREEN = (130, 230, 130)
YELLOW = (230, 220, 130)
DIM = (140, 140, 150)
RED = (240, 130, 130)
TITLE_BG = (50, 50, 60)


# ---------- Font ----------

def _load_font() -> ImageFont.FreeTypeFont:
    candidates = [
        # Windows
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\cour.ttf",
        # macOS
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, 14)
    return ImageFont.load_default()


FONT = _load_font()


# ---------- Coloring rules ----------
# Tag certain line patterns so the renderer can color them without
# requiring real ANSI parsing.

def _color_for_line(line: str) -> tuple[int, int, int]:
    if line.startswith("$ "):
        return PROMPT_FG
    if line.startswith("  intent:") or line.startswith("  When ready, run:"):
        return GREEN
    if line.startswith("  field:") or line.startswith("  suggested ") or line.startswith("  do_"):
        return YELLOW
    if line.startswith("# "):
        return GREEN
    if "Please confirm" in line:
        return YELLOW
    return FG


# ---------- Frame rendering ----------

def render_frame(lines: list[str], typed_partial: str | None = None) -> Image.Image:
    """Render the current screen state to a PIL image.

    `lines`: every line that has fully appeared so far (top of the window).
    `typed_partial`: an in-progress prompt line being typed (cursor blinks
    just after this).
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # Title bar (window chrome)
    draw.rectangle([(0, 0), (WIDTH, 28)], fill=TITLE_BG)
    # mac-style traffic-light dots
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 18 + i * 22
        draw.ellipse([(cx - 6, 8), (cx + 6, 20)], fill=c)
    draw.text((WIDTH // 2 - 90, 6), "research-hub  —  lazy mode demo",
              fill=DIM, font=FONT)

    # Body lines
    y = PADDING + 28
    visible = lines[-(ROWS - 1):] if len(lines) > ROWS - 1 else lines
    for line in visible:
        color = _color_for_line(line)
        draw.text((PADDING, y), line[:COLS], fill=color, font=FONT)
        y += CHAR_H

    # Cursor for in-progress typing
    if typed_partial is not None:
        cur_color = PROMPT_FG
        draw.text((PADDING, y), typed_partial[:COLS], fill=cur_color, font=FONT)
        cx = PADDING + len(typed_partial) * CHAR_W
        draw.rectangle([(cx, y + 2), (cx + CHAR_W - 2, y + CHAR_H - 2)],
                       fill=FG)

    return img


# ---------- Demo script ----------

DEMO = [
    # (kind, content, frame_count_hint)
    # kind: "type" = type a command (char-by-char), "out" = reveal output (line-by-line),
    #       "wait" = pause without changing state
    ("type", "$ research-hub plan \"I want to learn harness engineering\""),
    ("out", [
        "",
        "  intent: You want to research \"harness engineering\"",
        "          (parsed from: \"I want to learn harness engineering\")",
        "",
        "  suggested topic:    harness engineering",
        "  suggested cluster:  harness-engineering",
        "  max_papers:         8",
        "  do_nlm:             True",
        "  do_crystals:        True",
        "  field:              (auto)",
        "  est. duration:      ~196s",
        "",
        "  When ready, run:",
        "    research-hub auto \"harness engineering\" --with-crystals",
    ]),
    ("wait", 12),

    ("type", "$ research-hub ask llm-evaluation-harness \"what is the SOTA?\""),
    ("out", [
        "",
        "  SOTA per thread: evaluation (vla-eval, 47x throughput),",
        "  memory (M*, task-optimized beats fixed across 4 benchmarks),",
        "  security (SafeHarness, 38%/42% reduction vs unprotected),",
        "  domain (llvm-autofix-mini +22%, DebugHarness ~90% patch rate).",
        "  Unsolved: do harness design principles transfer across",
        "  domains, can evolving harnesses remain secure.",
        "",
        "  -- read in <1 second from cached crystal, 0 LLM calls --",
    ]),
    ("wait", 12),

    ("type", "$ research-hub websearch \"kepano obsidian bases\" --limit 3 --json"),
    ("out", [
        "",
        "  [github.com           ] kepano (Steph Ango) - GitHub",
        "  [mastodon.social      ] kepano: \"One of my favorite use cases...\"",
        "  [forum.obsidian.md    ] Bases Basic: Displaying Notes in the Same Folder",
        "",
        "  -- DDG fallback, no API key required --",
    ]),
    ("wait", 14),

    ("out", [
        "",
        "# 3 lazy-mode entry points. Zero API keys. ~3 minutes total.",
    ]),
    ("wait", 25),
]


def build_frames() -> list[Image.Image]:
    frames: list[Image.Image] = []
    static_lines: list[str] = []
    for kind, content, *rest in [(c[0], c[1]) + tuple(c[2:]) for c in DEMO]:
        if kind == "type":
            # Char-by-char typing
            for i in range(1, len(content) + 1):
                frames.append(render_frame(static_lines, typed_partial=content[:i]))
            # Pause briefly with full line shown + cursor
            for _ in range(2):
                frames.append(render_frame(static_lines, typed_partial=content))
            # Then commit it
            static_lines.append(content)
            frames.append(render_frame(static_lines))
        elif kind == "out":
            for line in content:
                static_lines.append(line)
                frames.append(render_frame(static_lines))
        elif kind == "wait":
            n = content if isinstance(content, int) else 10
            last = render_frame(static_lines)
            for _ in range(n):
                frames.append(last)
    return frames


def save_gif(frames: list[Image.Image], out_path: Path,
             frame_duration_ms: int = 50,
             pause_first_frame_ms: int = 600) -> None:
    """Write animated GIF. First frame held a bit longer so viewers see it."""
    durations = [pause_first_frame_ms] + [frame_duration_ms] * (len(frames) - 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    out = Path(__file__).parent.parent / "images" / "lazy-mode-demo.gif"
    print(f"Building frames...")
    frames = build_frames()
    print(f"  {len(frames)} frames")
    print(f"Saving GIF -> {out}")
    save_gif(frames, out)
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"  {size_mb:.2f} MB")
