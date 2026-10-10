"""CLI handler for credential-free public source acquisition."""

from __future__ import annotations

import json

from research_hub.source_fetch import fetch_public_source, validate_source_fetch
from research_hub.source_fetch_saved import import_saved_public_source


def _source_fetch(args) -> int:
    result = fetch_public_source(
        doi=args.doi or "",
        url=args.url or "",
        title=args.title or "",
        output_dir=args.output_dir,
    )
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {result.status}")
        print(f"evidence: {result.evidence_level}")
        print(f"identity: {result.identity_status}")
        print(f"result: {result.output_dir}/source-fetch-result.json")
    return 0 if result.status == "available" else 1


def _source_validate(args) -> int:
    report = validate_source_fetch(args.result, output_dir=args.output_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"valid: {str(report['valid']).lower()}")
        print(f"receipt: {report['receipt_sha256'] or '(missing)'}")
        for error in report["errors"]:
            print(f"error: {error}")
    return 0 if report["valid"] else 1


def _source_import_saved(args) -> int:
    result = import_saved_public_source(
        input_manifest=args.input_manifest,
        expected_manifest_sha256=args.manifest_sha256,
        output_dir=args.output_dir,
    )
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {result.status}")
        print(f"evidence: {result.evidence_level}")
        print(f"identity: {result.identity_status}")
        print(f"result: {result.output_dir}/source-fetch-result.json")
    return 0 if result.status == "available" else 1


__all__ = ["_source_fetch", "_source_import_saved", "_source_validate"]
