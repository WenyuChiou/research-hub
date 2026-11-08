"""Guidance and offline CLI-preview contracts, not research or destination E2E."""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import re
import shlex
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills/research-hub"
MIRROR = ROOT / "src/research_hub/skills_data/research-hub"


def _normalized(text):
    return " ".join(text.split())


def _require(text, clauses):
    text = _normalized(text)
    for clause in clauses:
        assert clause in text, f"missing native handoff boundary: {clause}"


ENTRY_CLAUSES = (
    "Honor the user's explicitly requested output format over this default",
    "For native-only research, default to readable inline bibliographic records",
    "title, authors and year when known, source identity and locator, publication version or unknown, actual reading level and access limits",
    "distinguish assessed claims from leads and unverified claims",
    "Preserve the source and claim audit boundaries in `references/research-protocol.md` and `references/source-claim-audit.md`",
    "Prepare `papers` JSON only for a selected Hub ingest or an explicit request for that structured handoff",
    "The separate `research-discovery-observations/1.0` export remains optional",
    "Native-only research does not inherently require JSON or the Hub CLI",
)
PROTOCOL_CLAUSES = (
    "For a selected `papers` handoff, use the existing `source_records` list",
    "Native-only results can retain the same source, version, reading and claim boundaries in readable inline form",
)


def test_native_only_and_structured_handoff_boundaries_are_explicit():
    entry = (SOURCE / "SKILL.md").read_text(encoding="utf-8")
    native_step = entry.split("2. If the host has native research tools", 1)[1].split("3. Before any real ingest", 1)[0]
    protocol = (SOURCE / "references/research-protocol.md").read_text(encoding="utf-8")
    binding = protocol.split("## Bind findings and preserve versions", 1)[1].split("## Bound completion honestly", 1)[0]
    _require(native_step, ENTRY_CLAUSES)
    _require(binding, PROTOCOL_CLAUSES)
    assert "Prepare bibliographic records in the JSON `papers` shape" not in _normalized(native_step)
    assert "Do not pass a `ResearchEvidencePacket` directly as papers input" in _normalized(native_step)


def test_native_only_skips_hub_preflight_before_command_blocks():
    entry = (SOURCE / "SKILL.md").read_text(encoding="utf-8")
    runtime = entry.split("## Runtime contract", 1)[1].split("## Shared research contract", 1)[0]
    preflight = entry.split("## Agent preflight protocol", 1)[1].split("2. If the host has native research tools", 1)[0]
    runtime_before_commands = _normalized(runtime.split("```bash", 1)[0])
    preflight_before_commands = _normalized(preflight.split("```bash", 1)[0])
    assert "For native-only research, skip Hub-specific describe, doctor and setup checks" in runtime_before_commands
    assert "inventory host-native capabilities and follow the shared research contract" in runtime_before_commands
    assert "For native-only research, skip Hub-specific preflight and Hub-only steps 3–7 unless a Hub operation is selected" in preflight_before_commands
    assert "For a selected Hub operation, check the available installed interface separately" in preflight_before_commands
    assert "Inventory the actual host-native search" in preflight_before_commands


@pytest.mark.parametrize("missing", ENTRY_CLAUSES)
def test_contract_detects_lost_entry_boundary(missing):
    authored = "\n".join(ENTRY_CLAUSES)
    with pytest.raises(AssertionError, match="missing native handoff boundary"):
        _require(authored.replace(missing, ""), ENTRY_CLAUSES)


@pytest.mark.parametrize("missing", PROTOCOL_CLAUSES)
def test_contract_detects_lost_protocol_boundary(missing):
    authored = "\n".join(PROTOCOL_CLAUSES)
    with pytest.raises(AssertionError, match="missing native handoff boundary"):
        _require(authored.replace(missing, ""), PROTOCOL_CLAUSES)


@pytest.mark.parametrize("path", ["SKILL.md", "references/research-protocol.md"])
def test_source_and_packaged_guidance_match(path):
    assert (SOURCE / path).read_bytes() == (MIRROR / path).read_bytes()


ROUTES = (
    "**Native-only research**",
    "**Hub-only metadata save**",
    "**Optional external destinations**",
)
HUB_SAVE_CLAUSES = (
    "The agent prepares and safely quotes SOURCE_BATCH_JSON; never ask the researcher to handwrite JSON",
    "array of source data objects",
    "Only run --apply after the user has authorized this selected local metadata write",
    "Do not promote abstract-snippet to abstract or full text",
    "metadata save does not verify the paper, summary, source version or actual reading",
    "Zotero, Obsidian and NotebookLM remain `not-performed`",
)


def _route(entry, label):
    section = entry.split("3. Before any real ingest", 1)[1].split("4. Use CLI-managed", 1)[0]
    assert label in section, f"missing Stage1 destination route: {label}"
    route = section.split(label, 1)[1]
    for other in ROUTES:
        if other in route:
            route = route.split(other, 1)[0]
    return route


def _batch_examples(entry, payload):
    from research_hub.workspace.cli import add_workspace_parsers

    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    blocks = re.findall(r"```bash\s*(.*?)```", _route(entry, ROUTES[1]), re.S)
    commands = [shlex.split(line.strip()) for block in blocks for line in block.splitlines()
                if line.strip().startswith("research-hub ")]
    assert len(commands) == 2, "Hub metadata route needs explicit preview and apply examples"
    parsed = []
    for command in commands:
        assert command[:3] == ["research-hub", "project", "record"]
        assert command.count("SOURCE_BATCH_JSON") == 1
        args = parser.parse_args([json.dumps(payload) if value == "SOURCE_BATCH_JSON" else value
                                  for value in command[1:]])
        assert args.kind == "source" and args.batch, "Hub save must use the source batch contract"
        assert args.root == "SELECTED_ROOT" and args.project == "selected-project"
        assert args.dry_run != args.apply, "Hub batch mode must be explicit"
        assert args.existing_records is None
        assert json.loads(args.data) == payload
        parsed.append(args)
    assert [(args.dry_run, args.apply) for args in parsed] == [(True, False), (False, True)]
    return parsed


@pytest.mark.parametrize("tree", [SOURCE, MIRROR], ids=["source", "packaged"])
def test_three_stage1_destinations_have_separate_requirements(tree):
    entry = (tree / "SKILL.md").read_text(encoding="utf-8")
    native = _route(entry, ROUTES[0])
    hub = _route(entry, ROUTES[1])
    external = _route(entry, ROUTES[2])
    _require(native, ("no Hub installation, JSON, integration account or destination write",))
    _require(hub, HUB_SAVE_CLAUSES)
    _require(hub, (
        "Do not run doctor or setup for a Hub-only metadata save",
        "batch_id", "upstream id", "locator", "identity_status=unverified", "human_acceptance=pending",
        "A dry-run does not open the root or check live storage",
        "An exact replay can reuse existing Hub IDs; a conflict rolls the entire batch back",
    ))
    _require(external, ("separate authorization and receipts for each selected destination",))


@pytest.mark.parametrize("tree", [SOURCE, MIRROR], ids=["source", "packaged"])
def test_documented_hub_batch_commands_preview_without_storage_or_providers(tree, tmp_path):
    from research_hub.workspace.cli import dispatch_workspace

    payload = [{"batch_id": "native-run", "id": "source-1", "title": "Synthetic source",
                "locator": "https://example.invalid/source", "reading_level": "abstract-snippet",
                "reading_scope": "abstract-snippet", "version": None, "identity_status": "unverified",
                "human_acceptance": "pending", "relevance": "Relevance is not a summary",
                "prior_batch_matches": [{"batch_id": "prior", "id": "old-source"}]}]
    before = deepcopy(payload)
    preview_args, _apply_args = _batch_examples((tree / "SKILL.md").read_text(encoding="utf-8"), payload)
    root = tmp_path / "must-not-be-opened"
    preview_args.root = str(root)
    output = io.StringIO()
    with (
        patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("Storage dispatch forbidden")),
        patch("research_hub.workspace.cli.WorkspaceService", side_effect=AssertionError("Service forbidden")),
        patch("research_hub.workspace.core.sqlite3.connect", side_effect=AssertionError("SQLite forbidden")),
        patch("research_hub.config.get_config", side_effect=AssertionError("Config forbidden")),
        patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")),
        patch("socket.create_connection", side_effect=AssertionError("Network forbidden")),
        redirect_stdout(output),
    ):
        assert dispatch_workspace(preview_args) == 0
    result = json.loads(output.getvalue())["preview"]
    assert result["persisted"] is result["execution_authorized"] is result["project_verified"] is False
    assert set(result["destination_writes"].values()) == {"not-performed"}
    assert result["plans"][0]["record_id"] is None
    assert result["plans"][0]["data"] == before[0]
    assert "summary" not in result["plans"][0]["data"]
    assert payload == before and not root.exists()
    # The apply example is parser-checked above, never dispatched by this test.


def test_guidance_contract_rejects_a_lost_batch_switch():
    entry = (SOURCE / "SKILL.md").read_text(encoding="utf-8")
    _batch_examples(entry, [])
    with pytest.raises(AssertionError, match="source batch contract"):
        _batch_examples(entry.replace("--kind source --batch --dry-run", "--kind source --dry-run"), [])
