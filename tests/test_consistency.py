"""Verify every MCP tool has a corresponding concept in the CLI.

This test catches drift when one surface adds a feature without the other.
"""

from __future__ import annotations

import argparse

from research_hub.cli import build_parser
from research_hub.mcp_server import mcp

from tests._mcp_helpers import _list_mcp_tool_names


EXPECTED_MAPPINGS = {
    "search_papers": "search",
    "web_search": "websearch",
    "enrich_candidates": "enrich",
    "verify_paper": "verify",
    "suggest_integration": "suggest",
    "list_clusters": "clusters list",
    "show_cluster": "clusters show",
    "propose_cluster_rebind": "clusters rebind --emit",
    "apply_cluster_rebind": "clusters rebind --apply",
    "list_orphan_papers": "mcp-only",
    "summarize_rebind_status": "mcp-only",
    "cluster_rebind": "clusters rebind",
    "export_citation": "cite",
    "build_citation": "cite --inline/--markdown",
    "run_doctor": "doctor",
    "get_config_info": "doctor",
    "remove_paper": "remove",
    "mark_paper": "mark",
    "move_paper": "move",
    "search_vault": "find",
    "merge_clusters": "clusters merge",
    "split_cluster": "clusters split",
    "get_references": "references",
    "get_citations": "cited-by",
    "propose_research_setup": "mcp-only",
    "add_paper": "add",
    "generate_dashboard": "dashboard",
    "download_artifacts": "notebooklm download",
    "read_briefing": "notebooklm read-briefing",
    "list_quotes": "quote list",
    "capture_quote": "quote",
    "compose_draft": "compose-draft",
    "get_topic_digest": "topic digest",
    "write_topic_overview": "mcp-only",
    "read_topic_overview": "topic show",
    "propose_subtopics": "topic propose",
    "emit_assignment_prompt": "topic assign emit",
    "apply_subtopic_assignments": "topic assign apply",
    "build_topic_notes": "topic build",
    "list_topic_notes": "topic list",
    "fit_check_prompt": "fit-check emit",
    "fit_check_apply": "fit-check apply",
    "fit_check_audit": "fit-check audit",
    "fit_check_drift": "fit-check drift",
    "autofill_emit": "autofill emit",
    "autofill_apply": "autofill apply",
    "list_crystals": "crystal list",
    "read_crystal": "crystal read",
    "emit_crystal_prompt": "crystal emit",
    "apply_crystals": "crystal apply",
    "check_crystal_staleness": "crystal check",
    "list_entities": "memory list --kind entities",
    "list_claims": "memory list --kind claims",
    "list_methods": "memory list --kind methods",
    "read_cluster_memory": "memory read",
    "cluster_prisma": "clusters prisma",
    "label_paper": "label",
    "list_papers_by_label": "find --label",
    "prune_cluster": "paper prune",
    "apply_fit_check_to_labels": "fit-check apply-labels",
    "discover_new": "discover new",
    "discover_variants": "discover variants",
    "discover_continue": "discover continue",
    "discover_status": "discover status",
    "discover_clean": "discover clean",
    "examples_list": "examples list",
    "examples_show": "examples show",
    "examples_copy": "examples copy",
    "suggest_cluster_split": "clusters analyze --split-suggestion",
    "import_folder_tool": "import-folder",
    "notebooklm_bundle": "notebooklm bundle",
    "notebooklm_upload": "notebooklm upload",
    "notebooklm_generate": "notebooklm generate",
    "notebooklm_download": "notebooklm download",
    "ask_cluster_notebooklm": "notebooklm ask",
    "ask_cluster": "ask",
    "brief_cluster": "mcp-only",
    "sync_cluster": "mcp-only",
    "compose_brief_draft": "mcp-only",
    "emit_cluster_base": "bases emit",
    "auto_research_topic": "auto",
    "cleanup_garbage": "cleanup",
    "tidy_vault": "tidy",
    "plan_research_workflow": "plan",
    "workflow_initialize": "workflow init",
    "workflow_status": "workflow status",
    "workflow_validate": "workflow validate",
    "workflow_decide": "workflow decide",
    "workflow_resume": "workflow resume",
    "workflow_migrate": "workflow migrate",
    "collect_to_cluster": "mcp-only",
    "summarize_cluster": "summarize",
    "apply_cluster_summaries": "mcp-only",
    "list_quarantine": "quarantine list",
    "show_quarantine": "quarantine show",
    "restore_quarantine": "quarantine restore",
}


def test_every_mcp_tool_is_documented_in_expected_mappings():
    tool_names = _list_mcp_tool_names(mcp)
    for name in tool_names:
        assert name in EXPECTED_MAPPINGS, (
            f"MCP tool {name!r} has no documented CLI mapping. "
            f"Add it to EXPECTED_MAPPINGS or document it as 'mcp-only'."
        )


# Deprecated MCP aliases whose @mcp.tool registration is gated by the
# RESEARCH_HUB_MCP_INCLUDE_DEPRECATED env var (see
# `mcp_server._deprecated_mcp_tool`). They stay in EXPECTED_MAPPINGS as
# documentation (CLI users still see them and need to know the
# replacement), but the orphan check below MUST skip them since the
# default test environment doesn't register them on the MCP instance.
_DEPRECATED_ENV_GATED = frozenset({
    "propose_cluster_rebind",
    "apply_cluster_rebind",
    "list_orphan_papers",
    "summarize_rebind_status",
    "list_entities",
    "list_claims",
    "list_methods",
    "read_briefing",
    "ask_cluster_notebooklm",
    "brief_cluster",
})


def test_no_orphaned_mappings():
    tool_names = _list_mcp_tool_names(mcp)
    for name in EXPECTED_MAPPINGS:
        if name in _DEPRECATED_ENV_GATED:
            # Hidden by default — registration gated by
            # RESEARCH_HUB_MCP_INCLUDE_DEPRECATED. Doc stays in mapping.
            continue
        assert name in tool_names, (
            f"EXPECTED_MAPPINGS has {name!r} but no such MCP tool exists. "
            f"Remove it from EXPECTED_MAPPINGS."
        )


def test_mcp_tool_count_at_least_18():
    assert len(_list_mcp_tool_names(mcp)) >= 60


# --- CLI -> MCP parity gate (reverse direction; FUNC-1 prevention) -----------
# Top-level CLI commands intentionally local/setup-only and NOT exposed as MCP
# tools (an autonomous agent doesn't drive these remotely). Adding a NEW CLI
# command forces a decision: give it an MCP tool (-> it appears in
# EXPECTED_MAPPINGS via its CLI command) OR list it here. A new agent-facing
# command shipped CLI-only (the FUNC-1 quarantine bug) lands in NEITHER set and
# fails test_every_agent_facing_cli_command_has_mcp_coverage below.
CLI_ONLY_EXEMPT = frozenset({
    "init", "setup", "config", "ezproxy", "install", "where", "package-dxt",
    "describe", "serve", "run", "ingest", "index", "dedup", "context",
    "label-bulk", "status", "vault", "migrate-yaml", "synthesize", "sync",
    "pipeline", "zotero",
})


def _cli_top_level_commands() -> set[str]:
    parser = build_parser()
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    assert subs, "build_parser() exposes no subparsers"
    return set(subs[0].choices.keys())


def _mcp_backed_cli_commands() -> set[str]:
    # the top-level CLI command each MCP tool maps to (first token of the value)
    return {
        value.split()[0]
        for value in EXPECTED_MAPPINGS.values()
        if value and value != "mcp-only"
    }


def test_every_agent_facing_cli_command_has_mcp_coverage():
    """Reverse of test_every_mcp_tool_is_documented_in_expected_mappings: catch a
    CLI command that SHOULD be MCP-reachable but isn't. The fit-check quarantine
    feature (FUNC-1) shipped CLI-only and left MCP agents a dead-end hint; this
    gate forces every new top-level command to be classified MCP-backed or
    explicitly CLI-only."""
    cli_top = _cli_top_level_commands()
    mcp_backed = _mcp_backed_cli_commands()

    unclassified = cli_top - mcp_backed - CLI_ONLY_EXEMPT
    assert not unclassified, (
        f"Top-level CLI command(s) {sorted(unclassified)} are neither MCP-backed "
        "nor CLI_ONLY_EXEMPT. If agent-facing: add an MCP tool + an "
        "EXPECTED_MAPPINGS entry (the FUNC-1 quarantine lesson). If intentionally "
        "local/setup-only: add to CLI_ONLY_EXEMPT in tests/test_consistency.py."
    )


def test_cli_only_exempt_has_no_stale_entries():
    """Renaming/removing a command must drop it from CLI_ONLY_EXEMPT too."""
    stale = CLI_ONLY_EXEMPT - _cli_top_level_commands()
    assert not stale, (
        f"CLI_ONLY_EXEMPT lists command(s) that no longer exist: {sorted(stale)}"
    )
