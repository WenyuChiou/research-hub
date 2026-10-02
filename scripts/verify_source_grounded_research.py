"""Same synthetic inputs at the existing packet validator boundary.

No live sources, identities, paid models, or scientific-quality scoring. Only
HTTP transport/DNS are stubbed; acquisition, extraction, source receipt replay,
packet validation, and (when present) the optional audit validator are real.
"""
from __future__ import annotations

import argparse
import copy
from hashlib import sha256
import inspect
import json
from pathlib import Path
import tempfile

import pytest

from research_hub import source_fetch as sf
from research_hub.evidence_harness import validate_evidence_packet


def packet_hash(packet):
    return sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def build_fixture(root, level, monkeypatch):
    quote = "Synthetic intervention improved the observed sample."
    head = '<html><head><meta name="citation_doi" content="10.1000/synthetic"><meta name="citation_title" content="Synthetic source study"></head><body>'
    if level == "abstract":
        body = f'<section class="abstract">{quote}</section>'
    else:
        body = '<article><h1>Synthetic source study</h1><h2>Introduction</h2><p>' + (
            'Synthetic context describes controlled examples rather than actual research. ' * 12
        ) + '</p><h2>Methods</h2><p>Synthetic methods specify sampling and measurement with validation and bounded uncertainty for the example.</p><h2>Results</h2><p>' + quote + ' Synthetic results remain conditional on the sample and comparison design.</p></article>'
    content = (head + body + '</body></html>').encode()

    class Response:
        status_code = 200
        headers = {"Content-Type": "text/html"}
        url = "https://example.org/synthetic"
        def iter_content(self, chunk_size):
            yield content
        def close(self):
            pass

    class Session:
        class Cookies:
            def clear(self):
                pass
        cookies = Cookies()
        def get(self, url, **kwargs):
            return Response()
        def close(self):
            pass

    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr(sf, "_new_public_session", Session)
    bundle = root / level
    result = sf.fetch_public_source(url=Response.url, doi="10.1000/synthetic",
                                    title="Synthetic source study", output_dir=bundle)
    receipt = bundle / "source-fetch-result.json"
    assert result.evidence_level == level
    assert sf.validate_source_fetch(receipt)["valid"]
    text = Path(result.extracted_text_path).read_text(encoding="utf-8")
    start = text.index(quote)
    source = {"source_id": "s1", "locator": Response.url,
              "identifier": "10.1000/synthetic", "title": "Synthetic source study",
              "authors": ["Synthetic Researcher"], "year": 2026,
              "retrieved_at": "2026-10-02T00:00:00Z", "identity_status": "verified"}
    claim = {"claim_id": "c1", "claim_text": quote,
             "supporting_source_ids": ["s1"], "opposing_source_ids": [],
             "verification_status": "supported", "uncertainty": "Synthetic sample only.",
             "verification_records": [{"source_id": "s1", "status": "supports",
                                        "verifier_output_ref": "review:c1:s1"}]}
    packet = {"schema_version": "1.0", "query": "Synthetic bounded research",
              "sources": [source], "claims": [claim], "contradictions": [], "gaps": [],
              "confidence": "low", "warnings": [], "human_decisions": [],
              "provenance": {"researcher_outputs": ["native:1"], "synthesizer": "no-tool",
                             "validated_at": "2026-10-02T00:00:00Z"}}
    observation = {"observation_id": "o1", "source_id": "s1", "work_id": "doi:10.1000/synthetic",
                   "version_id": "synthetic-publication-v1", "version_review_ref": "review:version:1",
                   "acquisition_ref": "native:1", "status": "available", "evidence_level": level,
                   "source_fetch_result": str(receipt.relative_to(root)),
                   "raw_path": str(Path(result.raw_path).relative_to(root)), "raw_sha256": result.raw_sha256,
                   "text_path": str(Path(result.extracted_text_path).relative_to(root)),
                   "text_sha256": result.extracted_text_sha256, "source_version": result.source_version}
    audit = {"schema_version": "research-source-audit/1.0", "packet_sha256": packet_hash(packet),
             "observations": [observation], "unassessed_claim_ids": [],
             "assessments": [{"claim_id": "c1", "observation_id": "o1",
                              "version_id": observation["version_id"], "required_level": level,
                              "judgment": "supported", "quote": quote, "start": start,
                              "end": start + len(quote), "locator": "Results" if level == "full-text" else "Abstract",
                              "verifier_output_ref": "review:c1:s1"}]}
    return packet, audit


def cases(root, monkeypatch):
    full_packet, full_audit = build_fixture(root, "full-text", monkeypatch)
    abstract_packet, abstract_audit = build_fixture(root, "abstract", monkeypatch)
    output = [("located_full_text", full_packet, full_audit, True),
              ("narrow_supported_abstract", abstract_packet, abstract_audit, True)]
    changes = {
        "abstract_promoted_to_full_text": lambda a: a["assessments"][0].update(required_level="full-text"),
        "wrong_publication_version": lambda a: a["assessments"][0].update(version_id="synthetic-preprint-v2"),
        "fabricated_quote": lambda a: a["assessments"][0].update(quote="An invented numerical effect of 92 percent."),
        "generated_summary_as_source": lambda a: a["observations"][0].update(evidence_level="generated-summary"),
        "unavailable_source_as_support": lambda a: a["observations"][0].update(status="unavailable"),
        "unknown_publication_version": lambda a: a["observations"][0].update(version_id=None, version_review_ref=None),
    }
    for name, change in changes.items():
        packet = copy.deepcopy(abstract_packet if name.startswith("abstract_") else full_packet)
        audit = copy.deepcopy(abstract_audit if name.startswith("abstract_") else full_audit)
        change(audit)
        output.append((name, packet, audit, False))
    return output


def run(root, profile_available):
    root.mkdir(parents=True, exist_ok=True)
    fixture_path = root / "fixture-cases.json"
    if not fixture_path.exists():
        with pytest.MonkeyPatch.context() as mp:
            frozen = cases(root, mp)
        fixture_path.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    frozen = json.loads(fixture_path.read_text(encoding="utf-8"))
    results = []
    for name, packet, audit, expected in frozen:
        kwargs = {"source_audit": audit, "artifact_root": root} if profile_available else {}
        findings = validate_evidence_packet(packet, **kwargs)
        results.append({"case": name, "expected_accept": expected, "accepted": not findings,
                        "findings": findings})
    return {"fixture": "same frozen synthetic source/packet/profile inputs; local binding only",
            "fixture_sha256": sha256(fixture_path.read_bytes()).hexdigest(),
            "profile_available": profile_available, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-dir", type=Path, help="create once/replay identical local fixtures")
    args = parser.parse_args()
    available = "source_audit" in inspect.signature(validate_evidence_packet).parameters
    if args.fixtures_dir:
        output = run(args.fixtures_dir.resolve(), available)
    else:
        with tempfile.TemporaryDirectory(prefix="source-audit-") as temp:
            output = run(Path(temp), available)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
