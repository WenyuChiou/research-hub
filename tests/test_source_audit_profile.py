"""Optional profile checks the real source/packet/native ingest seams offline."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from research_hub.evidence_harness import validate_evidence_packet
from research_hub.source_audit import evidence_packet_sha256
from scripts.verify_source_grounded_research import build_fixture, cases
from tests.test_native_research_handoff import handoff_env  # noqa: F401
from tests.test_pipeline import _paper


def audit_findings(packet, audit, root):
    return validate_evidence_packet(packet, source_audit=audit, artifact_root=root)


def test_same_input_source_regressions_use_production_acquisition_and_validators(tmp_path, monkeypatch):
    for name, packet, audit, expected_accept in cases(tmp_path, monkeypatch):
        # Legacy v1 remains compatible; its pass never established passages.
        assert validate_evidence_packet(packet) == [], name
        findings = audit_findings(packet, audit, tmp_path)
        assert (not findings) is expected_accept, (name, findings)


def test_native_capture_and_identifier_free_source_remain_supported(tmp_path, monkeypatch):
    packet, audit = build_fixture(tmp_path, "full-text", monkeypatch)
    packet["sources"][0]["identifier"] = None
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    audit["observations"][0]["source_fetch_result"] = None
    audit["observations"][0]["work_id"] = "archive:synthetic-collection:record-7"
    assert audit_findings(packet, audit, tmp_path) == []


@pytest.mark.parametrize("mutation, expected", [
    (lambda p, a: a.update(packet_sha256="0" * 64), "stale"),
    (lambda p, a: a["observations"][0].update(text_sha256="0" * 64), "text SHA-256 mismatch"),
    (lambda p, a: a["observations"][0].update(raw_sha256="0" * 64), "raw SHA-256 mismatch"),
    (lambda p, a: a["observations"].append(copy.deepcopy(a["observations"][0])), "duplicate observation"),
    (lambda p, a: a["assessments"][0].update(verifier_output_ref="different:review"), "packet verifier"),
    (lambda p, a: a["assessments"][0].update(locator="Wrong section"), "range/locator"),
    (lambda p, a: a["assessments"][0].update(judgment="partial"), "lacks source-bound support"),
    (lambda p, a: a["assessments"][0].update(judgment="contradicted"), "opposing_source_ids"),
    (lambda p, a: a["observations"][0].update(raw_path="../outside.html"), "escapes artifact_root"),
    (lambda p, a: a.update(unassessed_claim_ids=["c1"]), "never both"),
    (lambda p, a: a["assessments"][0].update(claim_id="unknown"), "unknown claim"),
])
def test_profile_rejects_stale_mismatched_and_unbound_evidence(tmp_path, monkeypatch, mutation, expected):
    packet, audit = build_fixture(tmp_path, "full-text", monkeypatch)
    mutation(packet, audit)
    findings = audit_findings(packet, audit, tmp_path)
    assert any(expected in item["message"] for item in findings), findings


def test_profile_replays_actual_receipt_and_detects_raw_tampering(tmp_path, monkeypatch):
    packet, audit = build_fixture(tmp_path, "full-text", monkeypatch)
    raw = tmp_path / audit["observations"][0]["raw_path"]
    raw.write_bytes(raw.read_bytes() + b"tampered")
    messages = [f["message"] for f in audit_findings(packet, audit, tmp_path)]
    assert any("receipt replay failed" in message for message in messages)
    assert any("raw SHA-256 mismatch" in message for message in messages)


@pytest.mark.parametrize("native, level, status", [
    (False, "abstract", "available"),
    (True, "generated-summary", "available"),
    (True, "full-text", "unavailable"),
])
def test_contradiction_requires_actual_available_source_at_required_level(tmp_path, monkeypatch, native, level, status):
    packet, audit = build_fixture(tmp_path, "abstract", monkeypatch)
    claim = packet["claims"][0]
    claim.update(verification_status="contradicted", supporting_source_ids=[], opposing_source_ids=["s1"])
    claim["verification_records"][0]["status"] = "does_not_support"
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    audit["assessments"][0].update(judgment="contradicted", required_level="full-text")
    audit["observations"][0].update(evidence_level=level, status=status)
    if native:
        audit["observations"][0].update(source_fetch_result=None, raw_path=None, raw_sha256=None)
    assert audit_findings(packet, audit, tmp_path)


@pytest.mark.parametrize("judgment", [None, "unverifiable"])
def test_definitive_contradiction_cannot_be_unassessed(tmp_path, monkeypatch, judgment):
    packet, audit = build_fixture(tmp_path, "full-text", monkeypatch)
    claim = packet["claims"][0]
    claim.update(verification_status="contradicted", supporting_source_ids=[], opposing_source_ids=["s1"])
    claim["verification_records"][0]["status"] = "does_not_support"
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    if judgment:
        audit["assessments"][0]["judgment"] = judgment
    else:
        audit["assessments"] = []
        audit["unassessed_claim_ids"] = ["c1"]
    assert any("source-bound contradicted assessment" in f["message"]
               for f in audit_findings(packet, audit, tmp_path))
    claim["verification_status"] = "unverified"
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    assert audit_findings(packet, audit, tmp_path) == []


def test_mixed_packet_requires_both_bound_support_and_opposition(tmp_path, monkeypatch):
    packet, audit = build_fixture(tmp_path, "full-text", monkeypatch)
    packet["claims"][0]["verification_status"] = "mixed"
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    assert any("opposing_source_ids" in f["message"] for f in audit_findings(packet, audit, tmp_path))
    packet["claims"][0]["opposing_source_ids"] = ["s1"]
    packet["claims"][0]["verification_records"].append({
        "source_id": "s1", "status": "does_not_support", "verifier_output_ref": "review:opposition"})
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    opposition = copy.deepcopy(audit["assessments"][0])
    opposition.update(judgment="contradicted", verifier_output_ref="review:opposition")
    audit["assessments"].append(opposition)
    assert audit_findings(packet, audit, tmp_path) == []


def test_malformed_source_fetch_receipt_is_a_finding_not_an_exception(tmp_path, monkeypatch):
    packet, audit = build_fixture(tmp_path, "full-text", monkeypatch)
    receipt = tmp_path / audit["observations"][0]["source_fetch_result"]
    receipt.write_text("[]", encoding="utf-8")
    findings = audit_findings(packet, audit, tmp_path)
    assert any("receipt replay failed" in f["message"] for f in findings)


def test_fourth_load_bearing_claim_remains_in_denominator(tmp_path, monkeypatch):
    packet, audit = build_fixture(tmp_path, "full-text", monkeypatch)
    for i in range(2, 5):
        claim = copy.deepcopy(packet["claims"][0])
        claim["claim_id"] = f"c{i}"
        packet["claims"].append(claim)
        if i <= 3:
            assessment = copy.deepcopy(audit["assessments"][0])
            assessment["claim_id"] = f"c{i}"
            audit["assessments"].append(assessment)
    audit["unassessed_claim_ids"] = ["c4"]
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    assert any("c4/s1" in f["message"] for f in audit_findings(packet, audit, tmp_path))
    packet["claims"][3]["verification_status"] = "unverified"
    packet["claims"][3]["uncertainty"] = "Fourth source is beyond the declared read bound."
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    assert audit_findings(packet, audit, tmp_path) == []


def test_partial_abstract_assessment_preserves_useful_unverified_claim(tmp_path, monkeypatch):
    packet, audit = build_fixture(tmp_path, "abstract", monkeypatch)
    packet["claims"][0]["verification_status"] = "unverified"
    audit["assessments"][0].update(judgment="partial", required_level="full-text")
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    assert audit_findings(packet, audit, tmp_path) == []


def test_unknown_unassessed_and_empty_denominators_do_not_invent_support(tmp_path, monkeypatch):
    packet, audit = build_fixture(tmp_path, "abstract", monkeypatch)
    packet["claims"][0]["verification_status"] = "unverified"
    audit["assessments"] = []
    audit["unassessed_claim_ids"] = ["c1"]
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    assert audit_findings(packet, audit, tmp_path) == []
    packet["claims"] = []
    audit["unassessed_claim_ids"] = []
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    # Structural validity of an empty packet is not a coverage score.
    assert audit_findings(packet, audit, tmp_path) == []


def test_actual_rate_limited_receipt_is_unverifiable_not_empty_success(tmp_path, monkeypatch):
    from research_hub import source_fetch as sf
    from tests.test_source_fetch import FakeResponse, FakeSession

    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr(sf, "_new_public_session", lambda: FakeSession(
        lambda url, **kwargs: FakeResponse(b"quota reached", status=429, url=url)))
    bundle = tmp_path / "rate-limited"
    result = sf.fetch_public_source(url="https://example.org/synthetic",
                                    doi="10.1000/synthetic", title="Synthetic source study",
                                    output_dir=bundle)
    assert result.status == "rate-limited"
    assert result.extracted_text_path is None
    assert sf.validate_source_fetch(bundle / "source-fetch-result.json")["valid"]
    # The existing packet's unknown state and sidecar's failure survive replay.
    packet, audit = build_fixture(tmp_path, "abstract", monkeypatch)
    packet["sources"][0]["identity_status"] = "unavailable"
    packet["claims"][0]["verification_status"] = "unverified"
    audit["packet_sha256"] = evidence_packet_sha256(packet)
    audit["observations"][0].update(
        version_id=None, version_review_ref=None, status="unavailable",
        evidence_level=result.evidence_level,
        source_fetch_result="rate-limited/source-fetch-result.json",
        raw_path=None, raw_sha256=None, text_path=None, text_sha256=None,
        source_version=result.source_version or None,
    )
    audit["assessments"][0].update(judgment="unverifiable", version_id=None,
                                  quote=None, start=None, end=None, locator=None)
    assert audit_findings(packet, audit, tmp_path) == []
    assert audit["observations"][0]["status"] == "unavailable"
    assert packet["claims"][0]["verification_status"] == "unverified"


def test_optional_profile_schema_and_missing_root_fail_closed(tmp_path, monkeypatch):
    packet, audit = build_fixture(tmp_path, "abstract", monkeypatch)
    assert any("artifact_root" in f["message"] for f in validate_evidence_packet(packet, source_audit=audit))
    audit["unexpected"] = True
    assert audit_findings(packet, audit, tmp_path)
    packet["source_audit"] = audit
    assert validate_evidence_packet(packet)  # strict v1 still rejects extra fields


def test_native_handoff_retains_versions_reversal_and_exact_replay(handoff_env, tmp_path, capsys):
    from research_hub import cli

    cfg, created, notes = handoff_env
    paper = _paper("Synthetic version-aware source", "synthetic-version-aware", "10.1000/version")
    observations = [
        {"source_id": "s1", "work_id": "work:1", "version_id": "arxiv:v1",
         "decision_ref": "include:1", "acquisition_ref": "native:query:1"},
        {"source_id": "s2", "work_id": "work:1", "version_id": "arxiv:v2",
         "decision_ref": "exclude:2", "previous_decision_ref": "include:1",
         "reason": "Correction changes the result", "affected_claim_ids": ["c1"],
         "dependent_claim_status": "stale"},
    ]
    paper["source_records"] = observations
    paper["provenance"] = {"producer": "host-native", "needs": ["N1", "N2"],
                           "searches": [{"need_id": "N1", "status": "executed"},
                                        {"need_id": "N2", "status": "unavailable"}],
                           "completion": "partial"}
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps({"papers": [paper]}), encoding="utf-8")
    args = ["ingest", "--input", str(path), "--cluster", "native-review", "--no-verify", "--json"]
    before = {str(p): p.read_bytes() for p in cfg.root.rglob("*") if p.is_file()}
    assert cli.main(args + ["--dry-run"]) == 0
    capsys.readouterr()
    assert {str(p): p.read_bytes() for p in cfg.root.rglob("*") if p.is_file()} == before
    assert not created and not notes
    assert cli.main(args) == 0
    capsys.readouterr()
    note = cfg.raw / "native-review" / "synthetic-version-aware.md"
    text = note.read_bytes()
    metadata = yaml.safe_load(text.decode().split("---", 2)[1])
    assert metadata["source_records"] == observations
    assert metadata["provenance"]["completion"] == "partial"
    assert metadata["provenance"]["searches"][1]["status"] == "unavailable"
    assert cli.main(args) == 0
    capsys.readouterr()
    assert note.read_bytes() == text
    assert len(created) == 1


def test_shared_instruction_contract_and_packaged_reference_links():
    root = Path(__file__).resolve().parents[1]
    protocol = (root / "skills/research-hub/references/research-protocol.md").read_text()
    audit = (root / "skills/research-hub/references/source-claim-audit.md").read_text()
    for term in ("Unrestricted geography stays unrestricted", "suggested region is not a filter",
                 "method-only paper cannot fill", "Planned queries do not count as executed",
                 "HTTP 429, timeout", "empty denominator", "publication readiness"):
        assert term.lower() in protocol.lower()
    assert "Quote presence only proves binding" in audit
    for skill in ("research-hub", "literature-triage-matrix", "notebooklm-brief-verifier",
                  "gap-to-topic", "research-workflow-orchestrator"):
        content = (root / "skills" / skill / "SKILL.md").read_text()
        assert "research-protocol.md" in content and "source-claim-audit.md" in content
        assert content == (root / "src/research_hub/skills_data" / skill / "SKILL.md").read_text()


@pytest.mark.parametrize("legacy", [False, True])
def test_documented_installed_probe_checks_capability_not_version(tmp_path, legacy):
    import os
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    text = (root / "skills/research-hub/references/source-claim-audit.md").read_text()
    code = text.split("python - <<'PY'\n", 1)[1].split("\nPY", 1)[0]
    package_root = root / "src"
    if legacy:
        package_root = tmp_path / "legacy"
        package = package_root / "research_hub"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text('__version__ = "1.2.0"\n')
        (package / "evidence_harness.py").write_text('def validate_evidence_packet(packet):\n    return []\n')
    env = dict(os.environ, PYTHONPATH=str(package_root), PYTHONDONTWRITEBYTECODE="1", HOME=str(tmp_path))
    run = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert run.returncode == (1 if legacy else 0), run.stderr
    assert ("False" if legacy else "True") in run.stdout
    assert "source-audit/1.0 available:" in run.stdout
