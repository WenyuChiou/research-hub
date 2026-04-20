"""Generate docs/images/lazy-mode-demo.gif — a 3-scene user journey.

v2 (v0.52.1): larger canvas (1280x760), bigger font (17pt), 3 scenes:
  1. Chat: user asks "Claude, research harness engineering"
  2. Terminal: auto pipeline runs, 9 stages scroll
  3. Dashboard screenshot splice-in (real PNG scaled down)
  4. Terminal: cached `ask` returns answer in <1s

Pure Python + Pillow. No ffmpeg, no asciinema.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ---------- Canvas + palette ----------

W, H = 1280, 760
PAD = 24

# VS Code-ish dark terminal palette
BG_TERM = (26, 28, 34)
BG_CHAT = (36, 40, 50)
BG_CHROME = (48, 52, 62)
FG = (230, 230, 235)
FG_DIM = (150, 155, 165)
FG_MUTED = (100, 105, 115)
CYAN = (130, 200, 255)
GREEN = (130, 230, 150)
YELLOW = (240, 220, 130)
RED = (240, 130, 130)
ORANGE = (255, 175, 100)
PURPLE = (200, 160, 240)
USER_BUBBLE = (70, 130, 180)
AI_BUBBLE = (60, 70, 85)


# ---------- Fonts ----------

def _try(p: str, size: int):
    if os.path.exists(p):
        return ImageFont.truetype(p, size)
    return None


def load_fonts():
    mono_paths = [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\cour.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    ui_paths = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\seguisb.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    mono = next((f for f in (_try(p, 17) for p in mono_paths) if f), ImageFont.load_default())
    mono_big = next((f for f in (_try(p, 22) for p in mono_paths) if f), mono)
    ui = next((f for f in (_try(p, 19) for p in ui_paths) if f), mono)
    ui_big = next((f for f in (_try(p, 28) for p in ui_paths) if f), ui)
    return mono, mono_big, ui, ui_big


MONO, MONO_BIG, UI, UI_BIG = load_fonts()
CHAR_W, CHAR_H = 10, 22  # monospace cell size


# ---------- Chrome (shared) ----------

def draw_window_chrome(img: Image.Image, title: str):
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (W, 36)], fill=BG_CHROME)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 22 + i * 22
        d.ellipse([(cx - 7, 11), (cx + 7, 25)], fill=c)
    d.text((W // 2 - 180, 6), title, fill=FG_DIM, font=UI)


# ---------- Scene 1: chat ----------

def render_chat(messages: list[tuple[str, str, int]]) -> Image.Image:
    """messages: list of (role, text, y_bottom)."""
    img = Image.new("RGB", (W, H), BG_CHAT)
    draw_window_chrome(img, "Claude Desktop  —  research-hub MCP connected")
    d = ImageDraw.Draw(img)
    y = 70
    for role, text, reveal in messages:
        bubble_color = USER_BUBBLE if role == "user" else AI_BUBBLE
        align_right = role == "user"
        shown = text[:reveal]
        # Compute bubble size
        lines = wrap_text(shown, max_chars=70)
        bubble_h = len(lines) * 30 + 20
        bubble_w = min(max((len(l) for l in lines), default=0), 70) * 11 + 30
        x0 = W - PAD - bubble_w if align_right else PAD + 60
        x1 = x0 + bubble_w
        d.rounded_rectangle([(x0, y), (x1, y + bubble_h)], radius=14, fill=bubble_color)
        # Avatar
        if role == "user":
            d.ellipse([(x1 + 10, y + 4), (x1 + 44, y + 38)], fill=(100, 180, 220))
            d.text((x1 + 19, y + 7), "You", fill=(255, 255, 255), font=ImageFont.load_default())
        else:
            d.ellipse([(PAD + 14, y + 4), (PAD + 48, y + 38)], fill=(220, 140, 80))
            d.text((PAD + 19, y + 7), "AI", fill=(255, 255, 255), font=ImageFont.load_default())
        ty = y + 10
        for line in lines:
            d.text((x0 + 16, ty), line, fill=FG, font=UI)
            ty += 30
        y += bubble_h + 20
    return img


def wrap_text(text: str, max_chars: int = 70) -> list[str]:
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]


# ---------- Scene 2 + 4: terminal ----------

def render_terminal(lines: list[str], typed_partial: str | None = None,
                    title: str = "research-hub  —  lazy mode") -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TERM)
    draw_window_chrome(img, title)
    d = ImageDraw.Draw(img)
    y = 50 + PAD
    visible = lines[-30:]
    for line in visible:
        color = line_color(line)
        d.text((PAD, y), line, fill=color, font=MONO)
        y += CHAR_H
    if typed_partial is not None:
        d.text((PAD, y), typed_partial, fill=CYAN, font=MONO)
        cx = PAD + len(typed_partial) * CHAR_W
        d.rectangle([(cx, y + 3), (cx + CHAR_W - 2, y + CHAR_H - 2)], fill=FG)
    return img


def line_color(line: str) -> tuple[int, int, int]:
    if line.startswith("$ "):
        return CYAN
    if line.startswith("[OK]"):
        return GREEN
    if line.startswith("[FAIL]"):
        return RED
    if line.startswith("["):
        return YELLOW
    if line.startswith("  Done") or line.startswith("=====") or line.startswith("  NotebookLM") or line.startswith("  Brief"):
        return ORANGE
    if line.startswith("  #") or line.startswith("#"):
        return FG_MUTED
    if line.startswith("> "):
        return PURPLE
    return FG


# ---------- Scene 3: dashboard screenshot ----------

def render_dashboard_scene(overlay_text: str | None = None) -> Image.Image:
    """Splice in the real dashboard-overview PNG, scaled + with title bar."""
    img = Image.new("RGB", (W, H), (240, 240, 245))
    draw_window_chrome(img, "Browser  —  http://127.0.0.1:8765  (research-hub dashboard)")
    png_path = Path(__file__).parent.parent / "images" / "dashboard-overview.png"
    if png_path.exists():
        dash = Image.open(png_path).convert("RGB")
        # Scale down to fit below the chrome bar, preserving aspect ratio
        target_w = W
        target_h = H - 36
        orig_w, orig_h = dash.size
        ratio = min(target_w / orig_w, target_h / orig_h)
        new_size = (int(orig_w * ratio), int(orig_h * ratio))
        dash = dash.resize(new_size, Image.Resampling.LANCZOS)
        # Center
        offset_x = (W - new_size[0]) // 2
        offset_y = 36 + (target_h - new_size[1]) // 2
        img.paste(dash, (offset_x, offset_y))
    if overlay_text:
        d = ImageDraw.Draw(img)
        # Darken bottom strip for legibility
        d.rectangle([(0, H - 80), (W, H)], fill=(0, 0, 0))
        d.text((PAD, H - 55), overlay_text, fill=(255, 255, 255), font=UI_BIG)
    return img


# ---------- Build frames ----------

def build_frames():
    frames = []

    # --- Scene 1: Title card + chat ---
    title = Image.new("RGB", (W, H), (18, 20, 26))
    draw_window_chrome(title, "research-hub  —  30-second demo")
    d = ImageDraw.Draw(title)
    d.text((PAD, 120), "One sentence in.", fill=CYAN, font=UI_BIG)
    d.text((PAD, 165), "Papers + AI brief + cached answers out.", fill=FG, font=UI_BIG)
    d.text((PAD, 215), "~50 seconds. Zero API keys.", fill=GREEN, font=UI_BIG)
    d.text((PAD, 290), "Any AI with MCP, CLI, REST, or Python import can drive it.", fill=FG_DIM, font=UI)
    d.text((PAD, 320), "Below: Claude Desktop conversation -> auto pipeline -> live dashboard -> cached query.", fill=FG_MUTED, font=UI)
    for _ in range(40):
        frames.append(title)

    # Chat scene — user types, AI responds
    user_msg = "Claude, research harness engineering for me"
    ai_msg_1 = "I'll plan first. Suggested: cluster=harness-engineering, max_papers=8, with crystals via your claude CLI. ~196s total. Proceed?"
    ai_msg_2 = "Running auto_research_topic() via research-hub MCP..."
    # Type user message
    for i in range(1, len(user_msg) + 1, 2):
        frames.append(render_chat([("user", user_msg, i)]))
    for _ in range(8):
        frames.append(render_chat([("user", user_msg, len(user_msg))]))
    # AI first response reveal
    for i in range(1, len(ai_msg_1) + 1, 3):
        frames.append(render_chat([("user", user_msg, len(user_msg)), ("ai", ai_msg_1, i)]))
    for _ in range(20):
        frames.append(render_chat([("user", user_msg, len(user_msg)), ("ai", ai_msg_1, len(ai_msg_1))]))
    # AI transitions to "running"
    for i in range(1, len(ai_msg_2) + 1, 3):
        frames.append(render_chat([("user", user_msg, len(user_msg)),
                                   ("ai", ai_msg_1, len(ai_msg_1)),
                                   ("ai", ai_msg_2, i)]))
    for _ in range(6):
        frames.append(render_chat([("user", user_msg, len(user_msg)),
                                   ("ai", ai_msg_1, len(ai_msg_1)),
                                   ("ai", ai_msg_2, len(ai_msg_2))]))

    # --- Scene 2: Terminal showing auto pipeline ---
    term_lines: list[str] = []
    auto_events = [
        ("$ research-hub auto \"harness engineering\" --with-crystals", None),
        ("", 2),
        ("[OK] cluster        created: harness-engineering", 3),
        ("[OK] zotero.bind    created collection 9FHZCK4N", 4),
        ("[OK] search         8 results (arxiv, semantic-scholar)", 5),
        ("[OK] ingest         8 papers in raw/harness-engineering/", 6),
        ("[OK] nlm.bundle     7 PDFs (24 MB)", 5),
        ("[OK] nlm.upload     8 succeeded", 5),
        ("[OK] nlm.generate   brief generation triggered", 5),
        ("[OK] nlm.download   1893 chars saved", 5),
        ("[OK] crystals       10 crystals via claude", 7),
        ("", 2),
        ("============================================================", 2),
        ("  Done in 187s. Cluster: harness-engineering", 3),
        ("============================================================", 2),
        ("  NotebookLM: https://notebooklm.google.com/notebook/99866...", 3),
        ("  Brief:      .research_hub/artifacts/.../brief-*.txt", 3),
        ("", 2),
        ("  # Now open the live dashboard:", 3),
    ]
    for text, hold in auto_events:
        term_lines.append(text)
        frames.append(render_terminal(term_lines))
        if hold:
            for _ in range(hold):
                frames.append(render_terminal(term_lines))

    # v2 (v0.53): dropped the embedded dashboard screenshot scene -- the
    # dashboard PNG is 2880x10810, which shrinks to illegible text at
    # 1280x724. Per-user feedback, the dashboard is better shown as a
    # separate static 6-tab grid in README (below the GIF) than crammed
    # into a single GIF frame. The GIF now ends with a pointer to it.
    term_lines.append("")
    term_lines.append("  # Live dashboard (screenshot grid below in the README):")
    term_lines.append("$ research-hub serve --dashboard    # -> http://127.0.0.1:8765")
    term_lines.append("")
    for _ in range(14):
        frames.append(render_terminal(term_lines))

    # --- Scene 3: cached ask returns instantly ---
    term_lines_q: list[str] = [
        "",
        "  # Any subsequent question reads a cached crystal in <1s:",
        "",
    ]
    ask_cmd = "$ research-hub ask harness-engineering \"what's the SOTA?\""
    for i in range(1, len(ask_cmd) + 1, 2):
        frames.append(render_terminal(term_lines_q, typed_partial=ask_cmd[:i],
                                       title="research-hub  —  cached query"))
    term_lines_q.append(ask_cmd)
    frames.append(render_terminal(term_lines_q, title="research-hub  —  cached query"))
    answer_lines = [
        "",
        "  SOTA per thread: evaluation (vla-eval, 47x throughput),",
        "  memory (M*, task-optimized beats fixed),",
        "  security (SafeHarness, 38%/42% reduction),",
        "  domain (llvm-autofix +22%, DebugHarness ~90% patch rate).",
        "",
        "  # returned in 0.3 seconds  ·  ~1 KB read  ·  0 tokens spent",
    ]
    for line in answer_lines:
        term_lines_q.append(line)
        frames.append(render_terminal(term_lines_q, title="research-hub  —  cached query"))
    for _ in range(40):
        frames.append(render_terminal(term_lines_q, title="research-hub  —  cached query"))

    # --- End card ---
    end = Image.new("RGB", (W, H), (18, 20, 26))
    draw_window_chrome(end, "research-hub")
    d = ImageDraw.Draw(end)
    d.text((PAD, 150), "That's it.", fill=CYAN, font=UI_BIG)
    d.text((PAD, 205), "~3 minutes to ingest.", fill=FG, font=UI_BIG)
    d.text((PAD, 245), "~$0 if you use a subscription CLI (claude / codex / gemini).", fill=FG, font=UI_BIG)
    d.text((PAD, 285), "Subsequent queries: zero tokens forever.", fill=GREEN, font=UI_BIG)
    d.text((PAD, 380), "pip install research-hub-pipeline[playwright,secrets]", fill=ORANGE, font=MONO_BIG)
    d.text((PAD, 425), "research-hub init  &&  research-hub auto \"your topic\"", fill=ORANGE, font=MONO_BIG)
    d.text((PAD, 500), "github.com/WenyuChiou/research-hub", fill=FG_DIM, font=UI)
    for _ in range(45):
        frames.append(end)

    return frames


def save_gif(frames, out_path: Path):
    durations = [80] * len(frames)
    durations[0] = 500
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)


if __name__ == "__main__":
    out = Path(__file__).parent.parent / "images" / "lazy-mode-demo.gif"
    print("Building frames...")
    frames = build_frames()
    print(f"  {len(frames)} frames ({W}x{H})")
    print(f"Saving -> {out}")
    save_gif(frames, out)
    mb = out.stat().st_size / (1024 * 1024)
    print(f"  {mb:.2f} MB")
