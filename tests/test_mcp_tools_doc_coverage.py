"""Drift gate: docs/mcp-tools.md must keep up with the live MCP tool surface.

The README points users at `research-hub describe --filter mcp_tools` for the
*live* count, but `docs/mcp-tools.md` is a hand-curated per-tool reference and
had silently drifted (56 documented vs 79 live at 2026-06-01). This gate makes
the drift visible + enforced: a NEW MCP tool must be documented in
mcp-tools.md, or consciously added to the (shrinking) known-gap allowlist.

Pattern mirrors `tests/test_consistency.py`'s CLI_ONLY_EXEMPT gate.
"""

from __future__ import annotations

from pathlib import Path

from research_hub.mcp_server import mcp

from tests._mcp_helpers import _list_mcp_tool_names

_DOC = Path(__file__).resolve().parent.parent / "docs" / "mcp-tools.md"

# MCP tools NOT yet documented in docs/mcp-tools.md (doc-debt as of 2026-06-01).
# This set must only SHRINK: document a tool -> remove it here. A newly-added
# MCP tool that is neither documented nor listed here fails the coverage test.
_DOC_GAP_ALLOWLIST = frozenset({
    "apply_cluster_summaries",
    "ask_cluster",
    "auto_research_topic",
    "cleanup_garbage",
    "cluster_rebind",
    "collect_to_cluster",
    "compose_brief_draft",
    "compose_draft",
    "download_artifacts",
    "emit_cluster_base",
    "import_folder_tool",
    "list_quarantine",
    "notebooklm_bundle",
    "notebooklm_download",
    "notebooklm_generate",
    "notebooklm_upload",
    "plan_research_workflow",
    "restore_quarantine",
    "show_quarantine",
    "summarize_cluster",
    "sync_cluster",
    "tidy_vault",
    "web_search",
})


def _is_documented(doc: str, name: str) -> bool:
    return f"`{name}(" in doc or f"### {name}" in doc or f"`{name}`" in doc


def test_mcp_tools_doc_covers_all_live_tools_except_known_gap():
    doc = _DOC.read_text(encoding="utf-8")
    live = set(_list_mcp_tool_names(mcp))
    undocumented = {t for t in live if not _is_documented(doc, t)}
    new_gaps = undocumented - _DOC_GAP_ALLOWLIST
    assert not new_gaps, (
        f"MCP tool(s) {sorted(new_gaps)} are live but undocumented in "
        "docs/mcp-tools.md. Add a `### `tool(...)`` entry there, or (only if "
        "deliberate) add the name to _DOC_GAP_ALLOWLIST in this test."
    )


def test_mcp_doc_gap_allowlist_has_no_stale_entries():
    """The gap must shrink: an allowlisted tool that is now documented (or no
    longer exists) must be removed from the allowlist."""
    doc = _DOC.read_text(encoding="utf-8")
    live = set(_list_mcp_tool_names(mcp))
    stale = {
        t for t in _DOC_GAP_ALLOWLIST if t not in live or _is_documented(doc, t)
    }
    assert not stale, (
        f"_DOC_GAP_ALLOWLIST has stale entries {sorted(stale)} (now documented "
        "or no longer a live MCP tool). Remove them — the gap only shrinks."
    )
