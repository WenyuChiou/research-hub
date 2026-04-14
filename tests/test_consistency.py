"""Verify every MCP tool has a corresponding concept in the CLI.

This test catches drift when one surface adds a feature without the other.
"""

from __future__ import annotations

from research_hub.mcp_server import mcp

from tests._mcp_helpers import _list_mcp_tool_names


EXPECTED_MAPPINGS = {
    "search_papers": "search",
    "enrich_candidates": "enrich",
    "verify_paper": "verify",
    "suggest_integration": "suggest",
    "list_clusters": "clusters list",
    "show_cluster": "clusters show",
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
}


def test_every_mcp_tool_is_documented_in_expected_mappings():
    tool_names = _list_mcp_tool_names(mcp)
    for name in tool_names:
        assert name in EXPECTED_MAPPINGS, (
            f"MCP tool {name!r} has no documented CLI mapping. "
            f"Add it to EXPECTED_MAPPINGS or document it as 'mcp-only'."
        )


def test_no_orphaned_mappings():
    tool_names = _list_mcp_tool_names(mcp)
    for name in EXPECTED_MAPPINGS:
        assert name in tool_names, (
            f"EXPECTED_MAPPINGS has {name!r} but no such MCP tool exists. "
            f"Remove it from EXPECTED_MAPPINGS."
        )


def test_mcp_tool_count_at_least_18():
    assert len(_list_mcp_tool_names(mcp)) >= 52
