"""Offline replay validation for source-fetch evidence bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research_hub.source_fetch_extraction import (
    _crossref_metadata,
    _extract_html,
    _extract_pdf,
    _extract_text,
    _is_text_content_type,
    _source_identity,
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


def _valid_aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


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

    diagnostics = payload.get("diagnostics", {})
    if "diagnostics" in payload and not isinstance(diagnostics, dict):
        errors.append("diagnostics: expected an object")

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
    operation = (
        request_record.get("operation") if isinstance(request_record, dict) else None
    )
    if not isinstance(request_record, dict):
        errors.append("request: expected an object")
        request_record = {}
    else:
        if not isinstance(operation, str) or operation not in {
            "source fetch",
            "source import-saved",
        }:
            errors.append(
                "request: operation must be 'source fetch' or 'source import-saved'"
            )
        if operation == "source import-saved" and set(request_record) != {
            "operation",
            "doi",
            "url",
            "title",
            "output_dir",
            "public_only",
        }:
            errors.append(
                "request: fields do not match the SourceFetchResult request contract"
            )
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

    if operation != "source import-saved" and any(
        attempt.purpose in ("saved-input-provenance", "saved-public-source")
        for attempt in attempts
    ):
        errors.append(
            "request: saved import attempts require source import-saved operation"
        )
    if payload and payload.get("status") not in ("available", "identity-mismatch"):
        if (
            payload.get("evidence_level") != "metadata"
            or payload.get("identity_status") != "unverified"
            or payload.get("observed_identity") not in ({}, {"doi": "", "title": ""})
            or payload.get("locators", []) != []
            or any(
                payload.get(field) is not None
                for field in (
                    "raw_path",
                    "raw_sha256",
                    "extracted_text_path",
                    "extracted_text_sha256",
                )
            )
        ):
            errors.append(
                "terminal result must retain metadata, unverified identity and no selected extraction"
            )

    parser_diagnostics = diagnostics
    if operation == "source import-saved":
        parser_diagnostics = dict(diagnostics) if isinstance(diagnostics, dict) else {}
        saved_import = parser_diagnostics.pop("saved_import", None)
        if not isinstance(saved_import, dict):
            errors.append("saved import: diagnostics.saved_import must be an object")
            saved_import = {}
        expected_saved_keys = {
            "manifest_sha256",
            "manifest_schema_version",
            "original_acquired_at",
            "import_started_at",
            "import_completed_at",
            "imported_at",
            "original_http_acquisition_verified",
        }
        if set(saved_import) != expected_saved_keys:
            errors.append("saved import: diagnostic fields are invalid")
        if saved_import.get("original_http_acquisition_verified") is not False:
            errors.append(
                "saved import: original HTTP acquisition must remain unverified"
            )
        if not _valid_aware_timestamp(
            saved_import.get("import_started_at")
        ) or not _valid_aware_timestamp(saved_import.get("import_completed_at")):
            errors.append(
                "saved import: import timestamps must be timezone-aware ISO-8601 values"
            )
        if payload.get("retrieved_at") != saved_import.get("import_completed_at"):
            errors.append(
                "saved import: retrieved_at must record import completion time"
            )
        if saved_import.get("imported_at") != saved_import.get("import_completed_at"):
            errors.append(
                "saved import: imported_at must record import completion time"
            )
        if len(attempts) != 2:
            errors.append("saved import: exactly two owned attempts are required")
        elif (
            attempts[0].purpose != "saved-input-provenance"
            or attempts[1].purpose != "saved-public-source"
            or attempts[0].http_status is not None
            or attempts[1].http_status is not None
            or attempts[0].content_type != "application/json"
            or attempts[0].outcome != "imported"
            or attempts[1].outcome not in ("parsed", "parse-error", "inaccessible")
        ):
            errors.append(
                "saved import: attempt purposes or non-HTTP outcomes are invalid"
            )
        for attempt in attempts:
            if attempt.requested_at != saved_import.get(
                "import_started_at"
            ) or attempt.received_at != saved_import.get("import_completed_at"):
                errors.append(
                    "saved import: attempt timestamps differ from import diagnostics"
                )
                break
        try:
            if len(attempts) < 2:
                raise ValueError("saved import attempts are missing")
            provenance_bytes = _contained_existing_file(
                attempts[0].raw_path, root
            ).read_bytes()
            provenance_hash = _hash(provenance_bytes)
            if provenance_hash != saved_import.get("manifest_sha256"):
                errors.append("saved import: provenance manifest SHA-256 mismatch")
            from research_hub.source_fetch_saved import (
                INPUT_SCHEMA_VERSION,
                _extract,
                _read_bounded,
                validate_saved_input_manifest,
            )

            manifest = validate_saved_input_manifest(
                json.loads(provenance_bytes.decode("utf-8"))
            )
            if saved_import.get("manifest_schema_version") != INPUT_SCHEMA_VERSION:
                errors.append("saved import: manifest schema diagnostic mismatch")
            selected_attempt = attempts[1]
            if attempts[0].raw_path == selected_attempt.raw_path:
                errors.append(
                    "saved import: provenance and source must be distinct artifacts"
                )
            if manifest["raw_sha256"] != selected_attempt.raw_sha256:
                errors.append(
                    "saved import: manifest raw SHA-256 differs from saved source"
                )
            if manifest["content_type"] != selected_attempt.content_type:
                errors.append(
                    "saved import: manifest content type differs from saved source"
                )
            if (
                manifest["url"] != selected_attempt.url
                or manifest["final_url"] != selected_attempt.final_url
            ):
                errors.append(
                    "saved import: declared URL provenance differs from saved source attempt"
                )
            if manifest["original_acquired_at"] != saved_import.get(
                "original_acquired_at"
            ):
                errors.append(
                    "saved import: original acquisition time differs from manifest"
                )
            if manifest["doi"] != request_record.get("doi") or manifest[
                "title"
            ] != request_record.get("title"):
                errors.append("saved import: expected identity differs from manifest")
            if manifest["url"] != request_record.get("url"):
                errors.append("saved import: request URL differs from manifest")
            if (
                payload.get("source_url") != manifest["url"]
                or payload.get("final_url") != manifest["final_url"]
            ):
                errors.append("saved import: result URLs differ from manifest")
            # Terminal evidence is replayed too: a rehashed parse-error must
            # never certify full text or verified identity without extraction.
            source_bytes = _read_bounded(
                _contained_existing_file(selected_attempt.raw_path, root),
                50 * 1024 * 1024,
                "saved source",
            )
            replay_error = None
            replay_status = None
            try:
                _extract(source_bytes, manifest["content_type"], manifest["final_url"])
            except PermissionError as exc:
                replay_status = "inaccessible"
                replay_error = f"saved-public-source: PermissionError: {exc}"
            except Exception as exc:
                replay_status = "parse-error"
                replay_error = f"saved-public-source: {type(exc).__name__}: {exc}"
            if replay_error is not None:
                if (
                    payload.get("status") != replay_status
                    or selected_attempt.outcome != replay_status
                    or selected_attempt.error != replay_error
                    or payload.get("errors") != [replay_error]
                    or payload.get("evidence_level") != "metadata"
                    or payload.get("identity_status") != "unverified"
                    or payload.get("observed_identity") != {"doi": "", "title": ""}
                    or payload.get("locators") != []
                    or parser_diagnostics != {}
                    or any(
                        payload.get(field) is not None
                        for field in (
                            "raw_path",
                            "raw_sha256",
                            "extracted_text_path",
                            "extracted_text_sha256",
                        )
                    )
                ):
                    errors.append(
                        "saved import: terminal evidence differs from parser replay"
                    )
            elif (
                payload.get("status") not in ("available", "identity-mismatch")
                or selected_attempt.outcome != "parsed"
                or selected_attempt.error is not None
                or payload.get("errors") != []
                or payload.get("raw_path") != selected_attempt.raw_path
                or payload.get("raw_sha256") != selected_attempt.raw_sha256
                or not payload.get("extracted_text_path")
                or not payload.get("extracted_text_sha256")
            ):
                errors.append(
                    "saved import: successful parser replay requires selected extraction artifacts"
                )
            if payload.get("source_version") != f"sha256:{selected_attempt.raw_sha256}":
                errors.append("saved import: source version differs from owned source")
        except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"saved import: {type(exc).__name__}: {exc}")
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
            if selected_attempt.purpose == "crossref-metadata":
                replay, _ = _crossref_metadata(json.loads(raw_bytes.decode("utf-8")))
            elif "pdf" in content_type or raw_bytes.startswith(b"%PDF-"):
                replay = _extract_pdf(raw_bytes)
            elif "html" in content_type or b"<html" in raw_bytes[:1024].lower():
                replay = _extract_html(raw_bytes, selected_attempt.final_url)
            elif _is_text_content_type(content_type):
                replay = _extract_text(raw_bytes, selected_attempt.final_url)
            else:
                raise ValueError("selected raw response has no deterministic extractor")
            if replay.text != extracted_text:
                errors.append("re-extracted text differs from saved extracted text")
            if replay.evidence_level != payload.get("evidence_level"):
                errors.append("re-extracted evidence level differs from result")
            if (
                operation == "source import-saved"
                and isinstance(parser_diagnostics, dict)
                and replay.diagnostics != parser_diagnostics
            ) or (
                operation == "source fetch"
                and isinstance(diagnostics, dict)
                and diagnostics
                and replay.diagnostics != diagnostics
            ):
                errors.append("re-extracted diagnostics differ from result")
            replay_identity = {
                "doi": normalize_doi(replay.observed_doi),
                "title": replay.observed_title,
            }
            if replay_identity != payload.get("observed_identity"):
                errors.append("re-extracted identity differs from observed_identity")
            expected_identity = payload.get("expected_identity") or {}
            identity_status = _source_identity(
                normalize_doi(str(expected_identity.get("doi", ""))),
                str(expected_identity.get("title", "")),
                replay,
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
    elif payload and payload.get("status") in ("available", "identity-mismatch"):
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
