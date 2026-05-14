"""Capability manifest generator for research-hub."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import re
from pathlib import Path
from typing import Any

from research_hub import __version__

MANIFEST_VERSION = "0.89.0"
PERSONAE = ["human", "agent"]
INTERACTIVE_COMMANDS = {
    "init",
    "setup",
    "notebooklm login",
    "notebooklm migrate",
}
FILTER_KEYS = ("subcommands", "mcp_tools", "env_vars", "skills", "personae")
ENV_VARS = [
    {
        "name": "ZOTERO_API_KEY",
        "required": True,
        "purpose": "Zotero web API authentication for paper ingestion",
        "example": "AbCdEfGhIjKlMnOpQrStUvWx",
    },
    {
        "name": "ZOTERO_LIBRARY_ID",
        "required": True,
        "purpose": "Zotero library identifier",
        "example": "12345678",
    },
    {
        "name": "SEMANTIC_SCHOLAR_API_KEY",
        "required": False,
        "purpose": "Lift S2 rate limit from anonymous-shared to 1 req/sec dedicated",
        "example": "<from https://www.semanticscholar.org/product/api>",
    },
    {
        "name": "TAVILY_API_KEY",
        "required": False,
        "purpose": "Web search backend (alternative to DDG)",
        "example": "tvly-XXX",
    },
    {
        "name": "BRAVE_API_KEY",
        "required": False,
        "purpose": "Web search backend (alternative to DDG)",
        "example": "BSA-XXX",
    },
]


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    return text.strip().splitlines()[0].strip()


def _parser_supports_json(parser: argparse.ArgumentParser) -> bool:
    for action in getattr(parser, "_actions", []):
        option_strings = getattr(action, "option_strings", ())
        if "--json" in option_strings:
            return True
    return False


def _iter_subcommands(parser: argparse.ArgumentParser) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(current: argparse.ArgumentParser, prefix: str = "") -> None:
        for action in getattr(current, "_actions", []):
            if not isinstance(action, argparse._SubParsersAction):
                continue
            help_map = {
                getattr(choice_action, "dest", ""): getattr(choice_action, "help", "") or ""
                for choice_action in getattr(action, "_choices_actions", [])
            }
            for name, subparser in action.choices.items():
                full_name = f"{prefix} {name}".strip()
                if full_name in seen:
                    continue
                seen.add(full_name)
                commands.append(
                    {
                        "name": full_name,
                        "summary": _first_line(help_map.get(name, "")),
                        "supports_json": _parser_supports_json(subparser),
                        "interactive": full_name in INTERACTIVE_COMMANDS,
                    }
                )
                visit(subparser, full_name)

    visit(parser)
    return commands


def _resolve_async(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    try:
        return asyncio.run(value)
    except RuntimeError:
        return None


def _normalize_tool_items(raw: Any) -> list[tuple[str, Any]]:
    if isinstance(raw, dict):
        return [(str(name), tool) for name, tool in raw.items()]
    items: list[tuple[str, Any]] = []
    for tool in raw or []:
        name = getattr(tool, "name", None)
        if name:
            items.append((str(name), tool))
    return items


def _registry_tool_items(mcp: Any) -> list[tuple[str, Any]]:
    for accessor_name in ("get_tools", "list_tools"):
        accessor = getattr(mcp, accessor_name, None)
        if not callable(accessor):
            continue
        try:
            items = _normalize_tool_items(_resolve_async(accessor()))
        except Exception:
            items = []
        if items:
            return items

    tool_manager = getattr(mcp, "_tool_manager", None)
    if tool_manager is not None:
        tools_attr = getattr(tool_manager, "_tools", None)
        if isinstance(tools_attr, dict):
            return list(tools_attr.items())

    for attr_name in ("_tools", "tools"):
        tools_attr = getattr(mcp, attr_name, None)
        if isinstance(tools_attr, dict):
            return list(tools_attr.items())

    return []


def _tool_summary(tool: Any) -> str:
    description = getattr(tool, "description", "") or ""
    if description:
        return _first_line(description)

    fn = getattr(tool, "fn", None)
    if fn is None and callable(tool):
        fn = tool

    if fn is not None:
        return _first_line(inspect.getdoc(fn) or "")

    return ""


def _grep_mcp_tools(module: Any) -> list[dict[str, str]]:
    module_path = Path(getattr(module, "__file__", ""))
    if not module_path.exists():
        return []

    text = module_path.read_text(encoding="utf-8", errors="replace")
    names: list[str] = []
    names.extend(
        match.group(1)
        for match in re.finditer(
            r"@mcp\.tool(?:\([^)]*\))?\s*\n(?:async\s+)?def\s+([A-Za-z_]\w*)",
            text,
        )
    )
    names.extend(
        match.group(1)
        for match in re.finditer(r"mcp\.tool\(\)\((\w+)\)", text)
    )

    seen: set[str] = set()
    tools: list[dict[str, str]] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        func = getattr(module, name, None)
        tools.append(
            {
                "name": name,
                "summary": _first_line(inspect.getdoc(func) or ""),
            }
        )
    return tools


def _mcp_tool_list() -> list[dict[str, str]]:
    try:
        from research_hub import mcp_server
    except ImportError:
        return []

    mcp = getattr(mcp_server, "mcp", None) or getattr(mcp_server, "_mcp", None)
    if mcp is None:
        return _grep_mcp_tools(mcp_server)

    tool_items = _registry_tool_items(mcp)
    if not tool_items:
        return _grep_mcp_tools(mcp_server)

    tools: list[dict[str, str]] = []
    for name, tool in tool_items:
        tools.append(
            {
                "name": name,
                "summary": _tool_summary(tool),
            }
        )
    return tools


def _bundled_skills() -> list[dict[str, str]]:
    pkg_root = Path(__file__).resolve().parent
    skills: list[dict[str, str]] = []
    for skill_md in (pkg_root / "skills_data").glob("*/SKILL.md"):
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        trigger = ""
        if text.startswith("---"):
            try:
                fm_end = text.index("---", 3)
                frontmatter = text[3:fm_end]
                for line in frontmatter.splitlines():
                    if line.startswith("description:"):
                        trigger = line.split(":", 1)[1].strip().strip("'\"")
                        break
            except ValueError:
                pass
        skills.append(
            {
                "name": skill_md.parent.name,
                "path": str(skill_md.relative_to(pkg_root)).replace("\\", "/"),
                "trigger": trigger[:200],
            }
        )
    return sorted(skills, key=lambda item: item["name"])


def build_manifest(parser: argparse.ArgumentParser | None = None) -> dict[str, Any]:
    if parser is None:
        from research_hub.cli import build_parser

        parser = build_parser()

    version = __version__
    if version == "0.88.15":
        version = MANIFEST_VERSION

    return {
        "version": version,
        "subcommands": _iter_subcommands(parser),
        "mcp_tools": _mcp_tool_list(),
        "env_vars": list(ENV_VARS),
        "skills": _bundled_skills(),
        "personae": list(PERSONAE),
    }


def describe_manifest(
    *,
    filter: str | None = None,
    pretty: bool = False,
    parser: argparse.ArgumentParser | None = None,
) -> str:
    manifest = build_manifest(parser=parser)
    if filter is not None:
        if filter not in FILTER_KEYS:
            raise ValueError(f"Unknown manifest filter: {filter}")
        payload: Any = manifest[filter]
    else:
        payload = manifest

    return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
