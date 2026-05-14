from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from research_hub.cli import build_parser
from research_hub.describe import describe_manifest


def _top_level_subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )


def test_describe_manifest_returns_valid_json_with_expected_keys():
    payload = json.loads(describe_manifest())

    assert payload["version"] == "0.89.0"
    assert set(payload) == {"version", "subcommands", "mcp_tools", "env_vars", "skills", "personae"}
    assert payload["personae"] == ["human", "agent"]


def test_describe_manifest_reports_expected_subcommands_and_json_support():
    payload = json.loads(describe_manifest())
    subcommands = payload["subcommands"]

    assert subcommands
    names = {item["name"] for item in subcommands}
    assert {"auto", "doctor", "dashboard"} <= names
    assert "notebooklm login" in names
    assert next(item for item in subcommands if item["name"] == "notebooklm login")["interactive"] is True
    assert sum(1 for item in subcommands if item["supports_json"]) >= 5


def test_describe_manifest_reports_mcp_tools_env_vars_and_skills():
    payload = json.loads(describe_manifest())

    mcp_names = {tool["name"] for tool in payload["mcp_tools"]}
    env_vars = {item["name"]: item for item in payload["env_vars"]}
    skills = {item["name"]: item for item in payload["skills"]}

    assert payload["mcp_tools"]
    assert "add_paper" in mcp_names
    assert env_vars["ZOTERO_API_KEY"]["required"] is True
    assert "research-hub" in skills
    assert skills["research-hub"]["path"] == "skills_data/research-hub/SKILL.md"


def test_describe_manifest_filter_returns_only_requested_subtree():
    payload = json.loads(describe_manifest(filter="subcommands"))

    assert isinstance(payload, list)
    assert payload
    assert all(set(item) == {"name", "summary", "supports_json", "interactive"} for item in payload)


def test_describe_manifest_reflects_parser_changes_without_code_updates():
    parser = build_parser()
    fake_parser = _top_level_subparsers(parser).add_parser(
        "manifest-smoke",
        help="Synthetic manifest smoke command",
    )
    fake_parser.add_argument("--json", action="store_true")

    payload = json.loads(describe_manifest(parser=parser))
    fake_entry = next(item for item in payload["subcommands"] if item["name"] == "manifest-smoke")

    assert fake_entry["summary"] == "Synthetic manifest smoke command"
    assert fake_entry["supports_json"] is True
    assert fake_entry["interactive"] is False


def test_python_module_describe_subprocess_emits_valid_json():
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_path) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    proc = subprocess.run(
        [sys.executable, "-m", "research_hub", "describe"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert set(payload) == {"version", "subcommands", "mcp_tools", "env_vars", "skills", "personae"}
