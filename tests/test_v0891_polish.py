"""v0.89.1 polish — 3 fixes from the v0.89.0 code-review skill audit.

1. `_emit_cli_json` adds `default=str` so unknown types (datetime,
   bytes, Exception, custom objects) serialize via str() instead of
   crashing json.dumps.
2. `describe.py` argparse private-API access now has a defensive
   block-comment flagging Python 3.10–3.14 contract.
3. `_HOME.md` Dashboard link uses `http://127.0.0.1:8765/` instead
   of `file:///C:/...` (which broke on iOS).
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Fix 1 — _emit_cli_json default=str
# ---------------------------------------------------------------------------


def test_v0891_emit_cli_json_handles_datetime() -> None:
    """v0.89.0 _json_safe returned datetime objects verbatim → json.dumps
    crashed. v0.89.1: default=str catches the leak."""
    from research_hub.cli import _emit_cli_json

    report = {
        "started_at": datetime(2026, 5, 14, 12, 34, 56, tzinfo=timezone.utc),
        "count": 5,
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        _emit_cli_json("test", 0, report)

    out = buf.getvalue()
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["command"] == "test"
    assert "2026-05-14" in payload["report"]["started_at"]


def test_v0891_emit_cli_json_handles_bytes() -> None:
    from research_hub.cli import _emit_cli_json

    report = {"raw_pdf_header": b"%PDF-1.4\n%fake"}
    buf = io.StringIO()
    with redirect_stdout(buf):
        _emit_cli_json("test", 0, report)

    payload = json.loads(buf.getvalue())
    assert "PDF" in payload["report"]["raw_pdf_header"]


def test_v0891_emit_cli_json_handles_exception_in_report() -> None:
    """An Exception instance accidentally sneaking into a Report
    payload won't crash the CLI — it serializes as its str()."""
    from research_hub.cli import _emit_cli_json

    report = {"upstream_error": ValueError("rate limit hit")}
    buf = io.StringIO()
    with redirect_stdout(buf):
        _emit_cli_json("test", 1, report)

    payload = json.loads(buf.getvalue())
    assert payload["ok"] is False
    assert "rate limit" in payload["report"]["upstream_error"]


# ---------------------------------------------------------------------------
# Fix 2 — describe.py defensive comment present
# ---------------------------------------------------------------------------


def test_v0891_describe_argparse_private_api_comment_present() -> None:
    """Structural lock-in: the comment must explain the private-API
    dependency, name the supported Python range, and reference where
    to look if it breaks. Codifies the v0.89.0 code-review P2 finding."""
    from research_hub import describe

    src = Path(describe.__file__).read_text(encoding="utf-8")
    # Look for the key signal phrases — robust to small wording changes
    assert "argparse private-API" in src or "private-API" in src
    assert "_actions" in src
    assert "_choices_actions" in src or "_SubParsersAction" in src
    # Should reference the supported Python range for context
    assert "3.10" in src or "3.14" in src


# ---------------------------------------------------------------------------
# Fix 3 — _HOME.md Dashboard link uses http:// not file://
# ---------------------------------------------------------------------------


def test_v0891_home_dashboard_link_uses_http_not_file_uri(tmp_path: Path) -> None:
    """W3 audit (v0.88.9) finding: file:///C:/... breaks on iOS Obsidian.
    v0.89.1: write http://127.0.0.1:8765/ + markdown-summary fallback."""
    from research_hub.vault.hub_overview import populate_home

    # Minimal cfg shim — just needs root + clusters_file + research_hub_dir
    vault = tmp_path / "vault"
    rh_dir = vault / ".research_hub"
    rh_dir.mkdir(parents=True)
    (rh_dir / "clusters.yaml").write_text("clusters: {}\n", encoding="utf-8")
    (vault / "raw").mkdir()
    (vault / "hub").mkdir()

    cfg = SimpleNamespace(
        root=vault,
        raw=vault / "raw",
        hub=vault / "hub",
        research_hub_dir=rh_dir,
        clusters_file=rh_dir / "clusters.yaml",
    )

    home_path = populate_home(cfg)
    text = home_path.read_text(encoding="utf-8")

    # Critical assertions — what changed in v0.89.1
    assert "http://127.0.0.1:8765" in text, (
        "Dashboard link must use HTTP for iOS compatibility"
    )
    # The old file:// URI must be gone (would still work on desktop
    # but breaks mobile, the W3 finding's whole point)
    assert "file://" not in text, (
        "file:// URIs in _HOME.md break iOS Obsidian (W3 finding)"
    )
    # Markdown summary fallback still present
    assert ".research_hub/dashboard-summary.md" in text
    # Hint about how to start the live dashboard
    assert "research-hub serve --dashboard" in text
