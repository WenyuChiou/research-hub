"""Evidence-agent role contracts and deterministic packet validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


@dataclass(frozen=True)
class ResearchAgentProfile:
    role: str
    tools: tuple[str, ...]
    output: str
    may_write: bool = False


ROLE_PROFILES = {
    "discovery_researcher": ResearchAgentProfile(
        "Discovery Researcher", ("web", "files", "scholarly_api"), "prose+source-locators"
    ),
    "evidence_verifier": ResearchAgentProfile(
        "Evidence Verifier", ("files", "scholarly_api"), "identity-and-claim-findings"
    ),
    "contradiction_falsifier": ResearchAgentProfile(
        "Contradiction/Falsifier", ("web", "files", "scholarly_api"), "counterevidence-prose"
    ),
    "reproducibility_reviewer": ResearchAgentProfile(
        "Reproducibility Reviewer", ("files",), "reproducibility-findings"
    ),
    "no_tool_synthesizer": ResearchAgentProfile(
        "No-tool Synthesizer", (), "ResearchEvidencePacket"
    ),
}


def filter_agent_results(results: list[Any]) -> list[dict[str, Any]]:
    """Drop null and explicitly failed parallel results before synthesis."""

    return [
        result
        for result in results
        if isinstance(result, dict) and result and result.get("ok", True) is not False
    ]


def validate_evidence_packet(packet: dict[str, Any]) -> list[dict[str, str]]:
    schema_path = Path(__file__).with_name("schemas") / "research-evidence-packet-1.0.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    findings: list[dict[str, str]] = []
    for error in sorted(
        validator.iter_errors(packet),
        key=lambda item: tuple(str(part) for part in item.path),
    ):
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.path
        )
        findings.append({"path": path, "message": error.message})

    sources = [source for source in packet.get("sources", []) if isinstance(source, dict)]
    source_ids = [source.get("source_id") for source in sources]
    source_by_id = {source.get("source_id"): source for source in sources}
    duplicate_source_ids = sorted({source_id for source_id in source_ids if source_ids.count(source_id) > 1})
    if duplicate_source_ids:
        findings.append({"path": "$.sources", "message": "duplicate source IDs: " + ", ".join(duplicate_source_ids)})
    claims = [claim for claim in packet.get("claims", []) if isinstance(claim, dict)]
    claim_ids = [claim.get("claim_id") for claim in claims]
    duplicate_claim_ids = sorted({claim_id for claim_id in claim_ids if claim_ids.count(claim_id) > 1})
    if duplicate_claim_ids:
        findings.append({"path": "$.claims", "message": "duplicate claim IDs: " + ", ".join(duplicate_claim_ids)})
    for index, claim in enumerate(packet.get("claims", [])):
        if not isinstance(claim, dict):
            continue
        linked = set(claim.get("supporting_source_ids", [])) | set(claim.get("opposing_source_ids", []))
        unknown = sorted(linked - set(source_ids))
        if unknown:
            findings.append(
                {
                    "path": f"$.claims[{index}]",
                    "message": "claim references unknown sources: " + ", ".join(unknown),
                }
            )
        if claim.get("verification_status") == "supported" and not claim.get("supporting_source_ids"):
            findings.append(
                {
                    "path": f"$.claims[{index}].verification_status",
                    "message": "supported claims require at least one supporting source",
                }
            )
        if claim.get("verification_status") == "supported":
            records = {
                record.get("source_id"): record.get("status")
                for record in claim.get("verification_records", [])
                if isinstance(record, dict)
            }
            for source_id in claim.get("supporting_source_ids", []):
                source = source_by_id.get(source_id, {})
                if source.get("identity_status") != "verified":
                    findings.append(
                        {
                            "path": f"$.claims[{index}].supporting_source_ids",
                            "message": f"supported claim relies on non-verified source: {source_id}",
                        }
                    )
                if records.get(source_id) != "supports":
                    findings.append(
                        {
                            "path": f"$.claims[{index}].verification_records",
                            "message": f"evidence verifier did not confirm claim support: {source_id}",
                        }
                    )
    return findings


def synthesize_evidence_packet(
    *,
    query: str,
    researcher_results: list[Any],
    sources: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    contradictions: list[str] | None = None,
    gaps: list[str] | None = None,
    confidence: str = "low",
    warnings: list[str] | None = None,
    human_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """No-tool synthesis boundary: structure completed prose, then validate."""

    successful = filter_agent_results(researcher_results)
    packet = {
        "schema_version": "1.0",
        "query": query,
        "sources": sources,
        "claims": claims,
        "contradictions": contradictions or [],
        "gaps": gaps or [],
        "confidence": confidence,
        "provenance": {
            "researcher_outputs": [
                str(result.get("evidence_ref") or result.get("source") or f"result:{index}")
                for index, result in enumerate(successful)
            ],
            "synthesizer": "no-tool",
            "validated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "warnings": warnings or [],
        "human_decisions": human_decisions or [],
    }
    findings = validate_evidence_packet(packet)
    return {"ok": not findings, "packet": packet, "findings": findings}
