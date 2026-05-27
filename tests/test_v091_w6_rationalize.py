from __future__ import annotations

from pathlib import Path
import warnings

import pytest

from tests._mcp_helpers import _get_mcp_tool, _list_mcp_tool_names


CLI_DEPRECATED_ALIASES = [
    ["ask", "--help"],
    ["summarize", "--help"],
    ["cleanup", "--help"],
    ["label-bulk", "--help"],
]


def _assert_deprecated(call):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        result = call()
    assert any(
        warning.category is DeprecationWarning and "deprecated" in str(warning.message)
        for warning in caught
    )
    assert any("v2.0.0" in str(warning.message) for warning in caught)
    return result


def _call_tool(mcp_server, name: str, *args, **kwargs):
    # Pass ``module=mcp_server`` so deprecated MCP aliases hidden behind
    # ``RESEARCH_HUB_MCP_INCLUDE_DEPRECATED`` env gate still resolve via
    # the module attribute fallback (the function definition is intact,
    # only the @mcp.tool registration is conditional).
    tool = _get_mcp_tool(mcp_server.mcp, name, module=mcp_server)
    assert tool is not None, f"MCP tool not registered or unknown: {name}"
    fn = getattr(tool, "fn", tool)
    return fn(*args, **kwargs)


@pytest.mark.parametrize("argv", CLI_DEPRECATED_ALIASES)
def test_cli_deprecated_alias_help_exits_zero_and_warns(argv):
    from research_hub.cli import main

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        with pytest.raises(SystemExit) as excinfo:
            main(argv)

    assert excinfo.value.code == 0
    assert any(
        warning.category is DeprecationWarning and "deprecated" in str(warning.message)
        for warning in caught
    )
    assert any("v2.0.0" in str(warning.message) for warning in caught)


def test_mcp_consolidated_tools_registered_and_deprecated_aliases_hidden():
    """The canonical consolidated tools (cluster_rebind, ask_cluster,
    read_cluster_memory) MUST be registered as MCP tools. The 10
    deprecated aliases that those tools replaced MUST be hidden from
    the default MCP surface (gated by RESEARCH_HUB_MCP_INCLUDE_DEPRECATED).

    The deprecated aliases are still importable as Python functions —
    only their FastMCP registration is gated — so legacy in-process
    callers keep working. The renamed test (was
    ``_and_deprecated_aliases_registered``) reflects the inverted
    contract."""
    from research_hub import mcp_server

    surface = _list_mcp_tool_names(mcp_server.mcp)

    canonical = {"ask_cluster", "cluster_rebind", "read_cluster_memory"}
    assert canonical <= surface, (
        f"Consolidated tools missing from MCP surface: {canonical - surface}"
    )

    deprecated = {
        "ask_cluster_notebooklm",
        "read_briefing",
        "brief_cluster",
        "propose_cluster_rebind",
        "apply_cluster_rebind",
        "list_orphan_papers",
        "summarize_rebind_status",
        "list_entities",
        "list_claims",
        "list_methods",
    }
    leaking = deprecated & surface
    assert not leaking, (
        f"Deprecated aliases should be hidden by default but still in MCP "
        f"surface: {sorted(leaking)}. Check _deprecated_mcp_tool gating."
    )
    # The Python functions MUST still exist so legacy in-process callers
    # (and the env-var-on path) keep working.
    for alias in deprecated:
        assert callable(getattr(mcp_server, alias, None)), (
            f"Deprecated alias function {alias!r} should still be importable "
            "from research_hub.mcp_server (only the @mcp.tool registration "
            "is gated, not the function itself)."
        )


def test_mcp_ask_cluster_dispatch_and_aliases_warn(monkeypatch):
    from research_hub import mcp_server

    monkeypatch.setattr(
        mcp_server,
        "_ask_cluster_local_impl",
        lambda cluster_slug, question=None, detail="gist": {
            "cluster": cluster_slug,
            "source": "local",
            "question": question,
            "detail": detail,
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "_ask_cluster_notebooklm_impl",
        lambda cluster, question, headless=True, timeout_sec=120: {
            "cluster": cluster,
            "source": "notebooklm",
            "question": question,
            "headless": headless,
            "timeout_sec": timeout_sec,
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "_read_briefing_impl",
        lambda cluster_slug, max_chars=mcp_server._BRIEFING_MAX_CHARS: {
            "cluster": cluster_slug,
            "source": "briefing",
            "max_chars": max_chars,
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "_brief_cluster_impl",
        lambda cluster_slug, force_regenerate=False: {
            "cluster": cluster_slug,
            "source": "brief",
            "force_regenerate": force_regenerate,
        },
    )

    assert _call_tool(
        mcp_server,
        "ask_cluster",
        cluster="alpha",
        question="What changed?",
        source="local",
    ) == {
        "cluster": "alpha",
        "source": "local",
        "question": "What changed?",
        "detail": "gist",
    }

    expected_nlm = _call_tool(
        mcp_server,
        "ask_cluster",
        cluster="alpha",
        question="Why?",
        source="notebooklm",
        headless=False,
        timeout_sec=5,
    )
    actual_nlm = _assert_deprecated(
        lambda: _call_tool(
            mcp_server,
            "ask_cluster_notebooklm",
            cluster="alpha",
            question="Why?",
            headless=False,
            timeout_sec=5,
        )
    )
    assert actual_nlm == expected_nlm

    expected_briefing = _call_tool(
        mcp_server,
        "ask_cluster",
        cluster="alpha",
        source="notebooklm",
        mode="briefing",
        max_chars=25,
    )
    actual_briefing = _assert_deprecated(
        lambda: _call_tool(mcp_server, "read_briefing", cluster_slug="alpha", max_chars=25)
    )
    assert actual_briefing == expected_briefing

    expected_brief = _call_tool(
        mcp_server,
        "ask_cluster",
        cluster="alpha",
        source="notebooklm",
        mode="brief",
        force_regenerate=True,
    )
    actual_brief = _assert_deprecated(
        lambda: _call_tool(mcp_server, "brief_cluster", cluster_slug="alpha", force_regenerate=True)
    )
    assert actual_brief == expected_brief


def test_mcp_cluster_rebind_dispatch_and_aliases_warn(monkeypatch):
    from research_hub import mcp_server

    monkeypatch.setattr(
        mcp_server,
        "_cluster_rebind_propose_impl",
        lambda cluster_slug="": {"action": "propose", "cluster_slug": cluster_slug},
    )
    monkeypatch.setattr(
        mcp_server,
        "_cluster_rebind_apply_impl",
        lambda report_path, dry_run=True, auto_create_new=False: {
            "action": "apply",
            "report_path": report_path,
            "dry_run": dry_run,
            "auto_create_new": auto_create_new,
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "_cluster_rebind_list_orphans_impl",
        lambda folder="": {"action": "list_orphans", "folder": folder},
    )
    monkeypatch.setattr(
        mcp_server,
        "_cluster_rebind_status_impl",
        lambda: {"action": "status"},
    )

    cases = [
        (
            "propose_cluster_rebind",
            {"cluster_slug": "alpha"},
            {"action": "propose", "cluster_slug": "alpha"},
        ),
        (
            "apply_cluster_rebind",
            {"report_path": "report.md", "dry_run": False, "auto_create_new": True},
            {
                "action": "apply",
                "report_path": "report.md",
                "dry_run": False,
                "auto_create_new": True,
            },
        ),
        (
            "list_orphan_papers",
            {"folder": "orphan-folder"},
            {"action": "list_orphans", "folder": "orphan-folder"},
        ),
        ("summarize_rebind_status", {}, {"action": "status"}),
    ]

    for old_name, kwargs, expected in cases:
        canonical_kwargs = {"action": expected["action"], **kwargs}
        if expected["action"] == "list_orphans":
            canonical_kwargs["action"] = "list_orphans"
        if expected["action"] == "status":
            canonical_kwargs = {"action": "status"}
        canonical = _call_tool(mcp_server, "cluster_rebind", **canonical_kwargs)
        actual = _assert_deprecated(lambda n=old_name, kw=kwargs: _call_tool(mcp_server, n, **kw))
        assert canonical == expected
        assert actual == canonical


def test_mcp_read_cluster_memory_dispatch_and_aliases_warn(monkeypatch):
    from research_hub import mcp_server

    monkeypatch.setattr(
        mcp_server,
        "_memory_entities_impl",
        lambda cluster: {"cluster": cluster, "kind": "entities"},
    )
    monkeypatch.setattr(
        mcp_server,
        "_memory_claims_impl",
        lambda cluster, min_confidence="low": {
            "cluster": cluster,
            "kind": "claims",
            "min_confidence": min_confidence,
        },
    )
    monkeypatch.setattr(
        mcp_server,
        "_memory_methods_impl",
        lambda cluster: {"cluster": cluster, "kind": "methods"},
    )
    monkeypatch.setattr(
        mcp_server,
        "_memory_all_impl",
        lambda cluster: {"cluster": cluster, "kind": "all"},
    )

    assert _call_tool(mcp_server, "read_cluster_memory", cluster="alpha") == {
        "cluster": "alpha",
        "kind": "all",
    }

    expected_entities = _call_tool(
        mcp_server,
        "read_cluster_memory",
        cluster="alpha",
        kind="entities",
    )
    assert _assert_deprecated(
        lambda: _call_tool(mcp_server, "list_entities", cluster="alpha")
    ) == expected_entities

    expected_claims = _call_tool(
        mcp_server,
        "read_cluster_memory",
        cluster="alpha",
        kind="claims",
        min_confidence="medium",
    )
    assert _assert_deprecated(
        lambda: _call_tool(mcp_server, "list_claims", cluster="alpha", min_confidence="medium")
    ) == expected_claims

    expected_methods = _call_tool(
        mcp_server,
        "read_cluster_memory",
        cluster="alpha",
        kind="methods",
    )
    assert _assert_deprecated(
        lambda: _call_tool(mcp_server, "list_methods", cluster="alpha")
    ) == expected_methods


def test_stable_api_deprecated_section_lists_aliases():
    text = Path("docs/stable-api.md").read_text(encoding="utf-8")
    aliases = [
        "research-hub ask",
        "research-hub summarize",
        "research-hub cleanup",
        "research-hub label-bulk",
        "ask_cluster_notebooklm",
        "read_briefing",
        "brief_cluster",
        "propose_cluster_rebind",
        "apply_cluster_rebind",
        "list_orphan_papers",
        "summarize_rebind_status",
        "list_entities",
        "list_claims",
        "list_methods",
    ]

    assert "### Deprecated" in text
    for alias in aliases:
        assert alias in text
    assert "v2.0.0" in text
