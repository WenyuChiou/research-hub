"""Verify every MCP tool has a corresponding concept in the CLI.

This test catches drift when one surface adds a feature without the other.
"""

from __future__ import annotations

from research_hub.mcp_server import mcp


EXPECTED_MAPPINGS = {
    "search_papers": "search",
    "verify_paper": "verify",
    "suggest_integration": "suggest",
    "list_clusters": "clusters list",
    "show_cluster": "clusters show",
    "export_citation": "cite",
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
}


def test_every_mcp_tool_is_documented_in_expected_mappings():
    tool_names = set(mcp._tool_manager._tools.keys())
    for name in tool_names:
        assert name in EXPECTED_MAPPINGS, (
            f"MCP tool {name!r} has no documented CLI mapping. "
            f"Add it to EXPECTED_MAPPINGS or document it as 'mcp-only'."
        )


def test_no_orphaned_mappings():
    tool_names = set(mcp._tool_manager._tools.keys())
    for name in EXPECTED_MAPPINGS:
        assert name in tool_names, (
            f"EXPECTED_MAPPINGS has {name!r} but no such MCP tool exists. "
            f"Remove it from EXPECTED_MAPPINGS."
        )


def test_mcp_tool_count_at_least_18():
    assert len(mcp._tool_manager._tools) >= 18
