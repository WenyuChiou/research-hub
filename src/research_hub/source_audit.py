"""Optional, offline source-passage binding beside strict evidence packet v1.

Hashes and quote presence establish local artifact consistency, not semantic
support, publication authenticity, or scientific adequacy. No source is fetched.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def evidence_packet_sha256(packet: dict[str, Any]) -> str:
    encoded = json.dumps(packet, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def validate_source_audit(
    packet: dict[str, Any], audit: dict[str, Any], *, artifact_root: Path | None,
) -> list[dict[str, str]]:
    """Validate a research-source-audit/1.0 profile using contained artifacts."""
    schema = json.loads((Path(__file__).with_name("schemas") /
                         "research-source-audit-1.0.json").read_text(encoding="utf-8"))
    findings: list[dict[str, str]] = []

    def report(path: str, message: str) -> None:
        findings.append({"path": "$.source_audit" + path, "message": message})

    for error in sorted(Draft202012Validator(schema).iter_errors(audit),
                        key=lambda item: tuple(str(part) for part in item.path)):
        path = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in error.path)
        report(path, error.message)
    if findings:
        return findings
    if audit["packet_sha256"] != evidence_packet_sha256(packet):
        report(".packet_sha256", "audit is stale or bound to a different packet")
    if artifact_root is None:
        report("", "artifact_root is required for local source binding")
        return findings
    root = Path(artifact_root).resolve()

    def contained(value: str | None) -> Path:
        if not value:
            raise ValueError("artifact path is missing")
        path = (root / value).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("artifact path escapes artifact_root") from exc
        if not path.is_file():
            raise ValueError("artifact file is missing")
        return path

    sources = {s["source_id"]: s for s in packet.get("sources", []) if isinstance(s, dict)}
    claims = {c["claim_id"]: c for c in packet.get("claims", []) if isinstance(c, dict)}
    observations: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    receipts: dict[str, dict[str, Any]] = {}
    for index, observation in enumerate(audit["observations"]):
        path = f".observations[{index}]"
        oid = observation["observation_id"]
        if oid in observations:
            report(path, "duplicate observation ID")
        observations[oid] = observation
        source = sources.get(observation["source_id"])
        if source is None:
            report(path, "observation references an unknown packet source")
        try:
            for prefix in ("raw", "text"):
                if observation[f"{prefix}_path"] is not None:
                    data = contained(observation[f"{prefix}_path"]).read_bytes()
                    if sha256(data).hexdigest() != observation[f"{prefix}_sha256"]:
                        report(path, f"{prefix} SHA-256 mismatch")
                    if prefix == "text":
                        texts[oid] = data.decode("utf-8")
            if observation["raw_path"] is not None and observation["source_version"] != (
                "sha256:" + str(observation["raw_sha256"])
            ):
                report(path, "source_version differs from captured raw bytes")
            if observation["source_fetch_result"] is not None:
                from research_hub.source_fetch import validate_source_fetch
                receipt_path = contained(observation["source_fetch_result"])
                replay = validate_source_fetch(receipt_path)
                if not replay["valid"]:
                    report(path, "source-fetch receipt replay failed: " + "; ".join(replay["errors"]))
                    continue  # Never inspect malformed, unvalidated receipt fields.
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                receipts[oid] = receipt
                receipt_status = ("available" if receipt.get("status") == "available" else "unavailable")
                if observation["status"] != receipt_status:
                    report(path, "status differs from source-fetch receipt")
                for key in ("evidence_level", "source_version", "raw_sha256"):
                    if observation[key] != (receipt.get(key) or None):
                        report(path, f"{key} differs from source-fetch receipt")
                if observation["text_sha256"] != receipt.get("extracted_text_sha256"):
                    report(path, "text SHA-256 differs from source-fetch receipt")
                for key, receipt_key in (("raw_path", "raw_path"), ("text_path", "extracted_text_path")):
                    if observation[key] is not None:
                        recorded = Path(str(receipt.get(receipt_key) or ""))
                        if not recorded.is_absolute():
                            recorded = receipt_path.parent / recorded
                        if contained(observation[key]) != recorded.resolve():
                            report(path, f"{key} differs from source-fetch artifact")
                if receipt.get("identity_status") != "verified" and source and source.get("identity_status") == "verified":
                    report(path, "packet identity is stronger than source-fetch identity")
                if source:
                    from research_hub.utils.doi import normalize_doi
                    identifier = str(source.get("identifier") or "")
                    identity = receipt.get("observed_identity" if receipt_status == "available" else "expected_identity", {})
                    if normalize_doi(identifier).startswith("10.") and normalize_doi(identifier) != identity.get("doi"):
                        report(path, "source-fetch DOI differs from packet source")
                    observed_title = identity.get("title", "")
                    if " ".join(observed_title.lower().split()) != " ".join(source["title"].lower().split()):
                        report(path, "source-fetch title differs from packet source")
        except (OSError, ValueError, TypeError, UnicodeDecodeError) as exc:
            report(path, f"source artifact unavailable: {exc}")

    assessed: set[str] = set()
    decisive_pairs: dict[str, set[tuple[str, str]]] = {"supported": set(), "contradicted": set()}
    levels = {"metadata": 0, "abstract": 1, "full-text": 2}
    for index, assessment in enumerate(audit["assessments"]):
        path = f".assessments[{index}]"
        cid = assessment["claim_id"]
        assessed.add(cid)
        claim = claims.get(cid)
        observation = observations.get(assessment["observation_id"])
        if claim is None or observation is None:
            report(path, "assessment references an unknown claim or observation")
            continue
        sid = observation["source_id"]
        linked = claim.get("supporting_source_ids", []) + claim.get("opposing_source_ids", [])
        if sid not in linked:
            report(path, "assessment source is not linked to the packet claim")
        if assessment["judgment"] != "unverifiable":
            if not observation["version_id"] or not observation["version_review_ref"] or assessment["version_id"] != observation["version_id"]:
                report(path, "known same publication version and version review are required")
            text = texts.get(assessment["observation_id"], "")
            start, end = assessment["start"], assessment["end"]
            if start is None or end is None or not assessment["quote"] or not (0 <= start < end <= len(text)) or text[start:end] != assessment["quote"]:
                report(path, "exact located quote is absent from saved source text")
            if not assessment["locator"]:
                report(path, "source section/page locator is required")
            receipt = receipts.get(assessment["observation_id"])
            if receipt and start is not None and end is not None:
                if not any(loc.get("start", -1) <= start < end <= loc.get("end", -1)
                           and str(loc.get("value")) == assessment["locator"]
                           for loc in receipt.get("locators", [])):
                    report(path, "quote range/locator differs from source-fetch locators")
        judgment = assessment["judgment"]
        if judgment in {"supported", "contradicted"}:
            role = "supporting_source_ids" if judgment == "supported" else "opposing_source_ids"
            statuses = {"supported", "mixed"} if judgment == "supported" else {"contradicted", "mixed"}
            if claim.get("verification_status") not in statuses or sid not in claim.get(role, []):
                report(path, f"{judgment} assessment disagrees with packet status/source role ({role})")
            if observation["status"] != "available":
                report(path, f"unavailable or unknown material cannot establish {judgment} judgment")
            if levels.get(observation["evidence_level"], -1) < levels[assessment["required_level"]]:
                report(path, "actual source level is below the claim's required evidence level")
            if not observation["raw_path"] or not observation["text_path"]:
                report(path, f"{judgment} assessment requires saved raw and text artifacts")
            if sources.get(sid, {}).get("identity_status") != "verified":
                report(path, f"{judgment} assessment requires verified packet source identity")
            expected_verdict = "supports" if judgment == "supported" else "does_not_support"
            if not any(record.get("source_id") == sid and record.get("status") == expected_verdict
                       and record.get("verifier_output_ref") == assessment["verifier_output_ref"]
                       for record in claim.get("verification_records", [])):
                report(path, "assessment is not bound to its packet verifier record")
            decisive_pairs[judgment].add((cid, sid))
    unassessed = set(audit["unassessed_claim_ids"])
    if (assessed | unassessed) != set(claims) or (assessed & unassessed):
        report(".unassessed_claim_ids", "every packet claim must be assessed or explicitly unassessed, never both")
    for cid, claim in claims.items():
        status = claim.get("verification_status")
        required_roles = []
        if status in {"supported", "mixed"}:
            required_roles.append(("supported", "supporting_source_ids"))
        if status in {"contradicted", "mixed"}:
            required_roles.append(("contradicted", "opposing_source_ids"))
        for judgment, role in required_roles:
            linked_sources = claim.get(role, [])
            if not linked_sources:
                report(".assessments", f"{status} claim requires at least one {role} link: {cid}")
            for sid in linked_sources:
                if (cid, sid) not in decisive_pairs[judgment]:
                    report(".assessments", f"{status} claim lacks source-bound {judgment} assessment: {cid}/{sid}")
    return findings
