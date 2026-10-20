from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import research_hub.describe as describe_module
from research_hub import __version__
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

    # v0.89.2 fix (post-release audit G2): pin to package version, not a
    # hardcoded string. Pre-fix the test silently broke on every minor bump
    # because describe.py special-cases only one version (0.88.15 → MANIFEST_VERSION).
    assert payload["version"] == __version__
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


def test_filtered_env_vars_skips_unrequested_manifest_sections(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("an unrequested manifest section was built")

    monkeypatch.setattr(describe_module, "_iter_subcommands", unexpected)
    monkeypatch.setattr(describe_module, "_mcp_tool_list", unexpected)
    monkeypatch.setattr(describe_module, "_bundled_skills", unexpected)

    payload = json.loads(describe_manifest(filter="env_vars"))
    repeated_single_filter = json.loads(describe_manifest(filter=["env_vars"]))

    assert payload == describe_module.ENV_VARS
    assert repeated_single_filter == payload


def test_filtered_subcommands_skips_mcp_tools_and_other_sections(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("an unrequested manifest section was built")

    monkeypatch.setattr(describe_module, "_mcp_tool_list", unexpected)
    monkeypatch.setattr(describe_module, "_bundled_skills", unexpected)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("filtered-smoke", help="Filtered smoke command")
    payload = json.loads(describe_manifest(filter="subcommands", parser=parser))

    assert [item["name"] for item in payload] == ["filtered-smoke"]


def test_filtered_mcp_tools_skips_unrelated_manifest_sections(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("an unrequested manifest section was built")

    monkeypatch.setattr(
        describe_module,
        "_mcp_tool_list",
        lambda: [{"name": "offline-tool", "summary": "Test tool"}],
    )
    monkeypatch.setattr(describe_module, "_iter_subcommands", unexpected)
    monkeypatch.setattr(describe_module, "_bundled_skills", unexpected)

    payload = json.loads(
        describe_manifest(filter="mcp_tools", parser=argparse.ArgumentParser())
    )

    assert payload == [{"name": "offline-tool", "summary": "Test tool"}]


def test_multiple_filters_include_only_requested_sections(monkeypatch):
    calls = []

    def subcommands(parser):
        calls.append("subcommands")
        return [{"name": "filtered-smoke"}]

    def mcp_tools():
        calls.append("mcp_tools")
        return [{"name": "offline-tool", "summary": "Test tool"}]

    def unexpected(*args, **kwargs):
        pytest.fail("an unrequested manifest section was built")

    monkeypatch.setattr(describe_module, "_iter_subcommands", subcommands)
    monkeypatch.setattr(describe_module, "_mcp_tool_list", mcp_tools)
    monkeypatch.setattr(describe_module, "_bundled_skills", unexpected)

    parser = argparse.ArgumentParser()
    payload = json.loads(
        describe_manifest(filter=["subcommands", "mcp_tools"], parser=parser)
    )

    assert list(payload) == ["subcommands", "mcp_tools"]
    assert payload["subcommands"] == [{"name": "filtered-smoke"}]
    assert payload["mcp_tools"] == [
        {"name": "offline-tool", "summary": "Test tool"}
    ]
    assert calls == ["subcommands", "mcp_tools"]


def test_multiple_filters_validate_before_building_sections(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("manifest sections should not be built for an invalid filter")

    monkeypatch.setattr(describe_module, "_iter_subcommands", unexpected)
    monkeypatch.setattr(describe_module, "_mcp_tool_list", unexpected)

    with pytest.raises(ValueError, match="Unknown manifest filter: unknown"):
        describe_manifest(filter=["subcommands", "unknown"])


def test_duplicate_filters_are_deduplicated(monkeypatch):
    calls = []

    def mcp_tools():
        calls.append("mcp_tools")
        return [{"name": "offline-tool", "summary": "Test tool"}]

    monkeypatch.setattr(describe_module, "_mcp_tool_list", mcp_tools)

    payload = json.loads(
        describe_manifest(filter=["mcp_tools", "mcp_tools"])
    )

    assert payload == [{"name": "offline-tool", "summary": "Test tool"}]
    assert calls == ["mcp_tools"]


def test_empty_filter_sequence_is_rejected_before_building_sections(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("manifest sections should not be built for an empty filter")

    monkeypatch.setattr(describe_module, "_mcp_tool_list", unexpected)

    with pytest.raises(ValueError, match="At least one manifest filter is required"):
        describe_manifest(filter=[])


def test_describe_cli_accepts_repeated_filters():
    args = build_parser().parse_args(
        ["describe", "--filter", "personae", "--filter", "env_vars"]
    )

    assert args.filter == ["personae", "env_vars"]


def test_unfiltered_manifest_still_builds_all_sections(monkeypatch):
    monkeypatch.setattr(
        describe_module,
        "_mcp_tool_list",
        lambda: [{"name": "offline-tool", "summary": "Test tool"}],
    )
    monkeypatch.setattr(
        describe_module,
        "_bundled_skills",
        lambda: [
            {
                "name": "offline-skill",
                "path": "skills_data/offline/SKILL.md",
                "trigger": "test",
            }
        ],
    )

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("manifest-smoke", help="Manifest smoke command")
    payload = json.loads(describe_manifest(parser=parser))

    assert set(payload) == {
        "version",
        "subcommands",
        "mcp_tools",
        "env_vars",
        "skills",
        "personae",
    }
    assert payload["mcp_tools"] == [{"name": "offline-tool", "summary": "Test tool"}]
    assert payload["skills"][0]["name"] == "offline-skill"
    assert [item["name"] for item in payload["subcommands"]] == ["manifest-smoke"]


def test_unknown_filter_is_rejected_before_building_sections(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("manifest sections should not be built for an invalid filter")

    monkeypatch.setattr(describe_module, "_mcp_tool_list", unexpected)

    with pytest.raises(ValueError, match="Unknown manifest filter: unknown"):
        describe_manifest(filter="unknown")


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


def test_python_module_describe_accepts_json_compat_flag():
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_path) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    proc = subprocess.run(
        [sys.executable, "-m", "research_hub", "describe", "--json"],
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
