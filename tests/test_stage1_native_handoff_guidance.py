"""Documentation contracts, not host/model execution or token measurements."""
from pathlib import Path

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
