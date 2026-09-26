"""Offline replay validation for source-fetch evidence bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research_hub.source_fetch_extraction import (
    _crossref_metadata,
    _extract_html,
    _extract_pdf,
    _identity,
)
from research_hub.utils.doi import normalize_doi


def _contained_existing_file(value: object, output_dir: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("artifact path is missing")
    path = Path(value)
    if not path.is_absolute():
        path = output_dir / path
    path = path.resolve()
    try:
        path.relative_to(output_dir)
    except ValueError as exc:
        raise ValueError(f"artifact path escapes output directory: {value}") from exc
    if not path.is_file():
        raise ValueError(f"artifact file is missing: {path}")
    return path


def validate_source_fetch(
    result_path: Path,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Replay and validate a SourceFetchResult without network access."""
    # Imported lazily by the public wrapper, after source_fetch is initialized.
    from research_hub.source_fetch import (
        SCHEMA_VERSION,
        VALIDATION_SCHEMA_VERSION,
        FetchAttempt,
        _hash,
        _is_public_url,
        _now,
        _receipt_hash,
        _receipt_result_fields,
    )

    result_path = Path(result_path).expanduser().resolve()
    root = Path(output_dir).expanduser().resolve() if output_dir else result_path.parent
    errors: list[str] = []
    payload: dict[str, Any] = {}
    try:
        result_path.relative_to(root)
        loaded = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("result root must be a JSON object")
        payload = loaded
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        errors.append(f"result: {type(exc).__name__}: {exc}")
    if payload and payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"result: unsupported schema_version {payload.get('schema_version')!r}"
        )
    if payload:
        recorded_root = Path(str(payload.get("output_dir", ""))).expanduser().resolve()
        if recorded_root != root:
            errors.append("result: output_dir does not match the validated directory")

    attempts_payload = payload.get("attempts", []) if payload else []
    attempts: list[FetchAttempt] = []
    if not isinstance(attempts_payload, list):
        errors.append("attempts: expected a list")
        attempts_payload = []
    for index, item in enumerate(attempts_payload, start=1):
        try:
            if not isinstance(item, dict):
                raise ValueError("attempt is not an object")
            attempt = FetchAttempt(**item)
            attempts.append(attempt)
            if attempt.sequence != index:
                errors.append(
                    f"attempt {index}: non-contiguous sequence {attempt.sequence}"
                )
            if not _is_public_url(attempt.url) or not _is_public_url(attempt.final_url):
                errors.append(f"attempt {index}: URL is not public http(s)")
            if attempt.http_status is not None and not attempt.raw_path:
                errors.append(f"attempt {index}: HTTP response has no raw artifact")
            if attempt.response_truncated != (attempt.outcome == "response-too-large"):
                errors.append(f"attempt {index}: truncation flag/outcome mismatch")
            if attempt.raw_path:
                raw_path = _contained_existing_file(attempt.raw_path, root)
                raw_bytes = raw_path.read_bytes()
                if _hash(raw_bytes) != attempt.raw_sha256:
                    errors.append(f"attempt {index}: raw SHA-256 mismatch")
                if attempt.response_bytes != len(raw_bytes):
                    errors.append(f"attempt {index}: response byte count mismatch")
        except (TypeError, ValueError, OSError) as exc:
            errors.append(f"attempt {index}: {type(exc).__name__}: {exc}")

    extracted_text = ""
    extracted_hash: str | None = None
    extracted_path_value = payload.get("extracted_text_path") if payload else None
    if extracted_path_value:
        try:
            extracted_path = _contained_existing_file(extracted_path_value, root)
            extracted_bytes = extracted_path.read_bytes()
            extracted_hash = _hash(extracted_bytes)
            if extracted_hash != payload.get("extracted_text_sha256"):
                errors.append("extracted text SHA-256 mismatch")
            extracted_text = extracted_bytes.decode("utf-8")
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            errors.append(f"extracted text: {type(exc).__name__}: {exc}")

    request_record = payload.get("request") if payload else None
    if not isinstance(request_record, dict):
        errors.append("request: expected an object")
        request_record = {}
    else:
        if request_record.get("operation") != "source fetch":
            errors.append("request: operation must be 'source fetch'")
        if request_record.get("public_only") is not True:
            errors.append("request: public_only must be true")
        if (
            Path(str(request_record.get("output_dir", ""))).expanduser().resolve()
            != root
        ):
            errors.append("request: output_dir does not match the validated directory")
        request_url = str(request_record.get("url", "") or "")
        if request_url and not _is_public_url(request_url):
            errors.append("request: URL is not public http(s)")
        expected_identity = payload.get("expected_identity") or {}
        normalized_request_identity = {
            "doi": normalize_doi(str(request_record.get("doi", "") or "")),
            "title": str(request_record.get("title", "") or ""),
        }
        if (
            not isinstance(expected_identity, dict)
            or normalized_request_identity != expected_identity
        ):
            errors.append(
                "request: expected_identity does not match normalized request"
            )
    expected_receipt = _receipt_hash(
        request_record,
        attempts,
        extracted_hash,
        _receipt_result_fields(payload),
    )
    if payload and expected_receipt != payload.get("receipt_sha256"):
        errors.append("receipt SHA-256 mismatch")

    selected_raw = payload.get("raw_path") if payload else None
    if extracted_text and selected_raw:
        try:
            raw_path = _contained_existing_file(selected_raw, root)
            raw_bytes = raw_path.read_bytes()
            if _hash(raw_bytes) != payload.get("raw_sha256"):
                errors.append("selected raw SHA-256 mismatch")
            selected_attempt = next(
                (attempt for attempt in attempts if attempt.raw_path == selected_raw),
                None,
            )
            if selected_attempt is None:
                raise ValueError("selected raw artifact is not owned by an attempt")
            selected_index = attempts.index(selected_attempt)
            source_attempt = selected_attempt
            while selected_index > 0:
                previous = attempts[selected_index - 1]
                if (
                    previous.purpose != selected_attempt.purpose
                    or previous.outcome != "redirect"
                ):
                    break
                source_attempt = previous
                selected_index -= 1
            derived_source_url = source_attempt.url
            derived_final_url = selected_attempt.final_url
            if (
                payload.get("source_url") != derived_source_url
                or payload.get("final_url") != derived_final_url
                or not _is_public_url(str(payload.get("source_url", "")))
                or not _is_public_url(str(payload.get("final_url", "")))
            ):
                errors.append("result URL provenance differs from saved attempts")
            content_type = selected_attempt.content_type.lower()
            if "pdf" in content_type or raw_bytes.startswith(b"%PDF-"):
                replay = _extract_pdf(raw_bytes)
            elif "html" in content_type or b"<html" in raw_bytes[:1024].lower():
                replay = _extract_html(raw_bytes, selected_attempt.final_url)
            elif selected_attempt.purpose == "crossref-metadata":
                replay, _ = _crossref_metadata(json.loads(raw_bytes.decode("utf-8")))
            else:
                raise ValueError("selected raw response has no deterministic extractor")
            if replay.text != extracted_text:
                errors.append("re-extracted text differs from saved extracted text")
            if replay.evidence_level != payload.get("evidence_level"):
                errors.append("re-extracted evidence level differs from result")
            replay_identity = {
                "doi": normalize_doi(replay.observed_doi),
                "title": replay.observed_title,
            }
            if replay_identity != payload.get("observed_identity"):
                errors.append("re-extracted identity differs from observed_identity")
            expected_identity = payload.get("expected_identity") or {}
            identity_status = _identity(
                normalize_doi(str(expected_identity.get("doi", ""))),
                str(expected_identity.get("title", "")),
                replay.observed_doi,
                replay.observed_title,
            )
            if identity_status != payload.get("identity_status"):
                errors.append("recomputed identity status differs from result")
            expected_status = (
                "identity-mismatch" if identity_status == "mismatch" else "available"
            )
            if payload.get("status") != expected_status:
                errors.append("result status is inconsistent with replayed identity")
            if replay.locators != payload.get("locators"):
                errors.append("re-extracted locators differ from result")
            if payload.get("source_version") != f"sha256:{_hash(raw_bytes)}":
                errors.append("source_version does not match selected raw response")
        except Exception as exc:
            errors.append(f"re-extraction: {type(exc).__name__}: {exc}")
    elif payload and payload.get("status") in {"available", "identity-mismatch"}:
        errors.append(
            "successful result has no selected raw and extracted text artifacts"
        )

    locators = payload.get("locators", []) if payload else []
    if not isinstance(locators, list):
        errors.append("locators: expected a list")
        locators = []
    for index, locator in enumerate(locators):
        if not isinstance(locator, dict):
            errors.append(f"locator {index}: expected an object")
            continue
        start = locator.get("start")
        end = locator.get("end")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
            or end > len(extracted_text)
        ):
            errors.append(f"locator {index}: invalid character range")

    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "valid": not errors,
        "result_path": str(result_path),
        "output_dir": str(root),
        "checked_at": _now(),
        "receipt_sha256": payload.get("receipt_sha256", "") if payload else "",
        "source_version": payload.get("source_version", "") if payload else "",
        "status": payload.get("status", "") if payload else "",
        "evidence_level": payload.get("evidence_level", "") if payload else "",
        "identity_status": payload.get("identity_status", "") if payload else "",
        "errors": errors,
    }


__all__ = ["validate_source_fetch"]
