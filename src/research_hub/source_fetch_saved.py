"""Truthful offline import of previously saved public source bytes."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path, PurePath
import stat
from typing import Any

from research_hub.source_fetch import (
    SCHEMA_VERSION,
    FetchAttempt,
    SourceFetchResult,
    _artifact_path,
    _hash,
    _is_public_url,
    _now,
    _receipt_hash,
    _receipt_result_fields,
    _suffix,
    _write_once,
)
from research_hub.source_fetch_extraction import (
    _extract_html,
    _extract_pdf,
    _extract_text,
    _is_text_content_type,
    _source_identity,
)
from research_hub.utils.doi import normalize_doi


INPUT_SCHEMA_VERSION = "saved-public-source-input/v1"
_MAX_MANIFEST_BYTES = 256 * 1024
_MAX_RAW_BYTES = 50 * 1024 * 1024
_REQUIRED_KEYS = {
    "schema_version",
    "url",
    "final_url",
    "doi",
    "title",
    "raw_path",
    "raw_sha256",
    "content_type",
}
_OPTIONAL_KEYS = {"original_acquired_at"}


def _bounded_string(
    value: object, field: str, maximum: int, *, empty: bool = True
) -> str:
    if not isinstance(value, str) or (not empty and not value) or len(value) > maximum:
        qualifier = "non-empty " if not empty else ""
        raise ValueError(
            f"manifest {field} must be a {qualifier}string of at most {maximum} characters"
        )
    return value


def _validate_timestamp(value: object) -> str | None:
    if value is None:
        return None
    text = _bounded_string(value, "original_acquired_at", 128, empty=False)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "manifest original_acquired_at must be an ISO-8601 timestamp or null"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError("manifest original_acquired_at must include a timezone")
    return text


def validate_saved_input_manifest(payload: object) -> dict[str, Any]:
    """Validate the strict v1 manifest without touching its referenced file."""
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be a JSON object")
    keys = set(payload)
    missing = _REQUIRED_KEYS - keys
    extra = keys - _REQUIRED_KEYS - _OPTIONAL_KEYS
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {sorted(missing)}")
        if extra:
            details.append(f"unexpected {sorted(extra)}")
        raise ValueError("manifest fields are invalid: " + "; ".join(details))
    if payload.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise ValueError(f"manifest schema_version must be {INPUT_SCHEMA_VERSION!r}")
    url = _bounded_string(payload.get("url"), "url", 4096, empty=False).strip()
    final_url = _bounded_string(
        payload.get("final_url"), "final_url", 4096, empty=False
    ).strip()
    if not _is_public_url(url) or not _is_public_url(final_url):
        raise ValueError("manifest URLs must be credential-free public http(s) URLs")
    doi = _bounded_string(payload.get("doi"), "doi", 512).strip()
    title = _bounded_string(payload.get("title"), "title", 4096).strip()
    raw_path = _bounded_string(payload.get("raw_path"), "raw_path", 4096, empty=False)
    path = PurePath(raw_path)
    if (
        path.is_absolute()
        or path.drive
        or not path.parts
        or any(
            part in {"", ".", ".."} for part in raw_path.replace("\\", "/").split("/")
        )
    ):
        raise ValueError("manifest raw_path must be a contained relative path")
    raw_sha256 = _bounded_string(
        payload.get("raw_sha256"), "raw_sha256", 64, empty=False
    )
    if (
        len(raw_sha256) != 64
        or raw_sha256 != raw_sha256.lower()
        or any(char not in "0123456789abcdef" for char in raw_sha256)
    ):
        raise ValueError(
            "manifest raw_sha256 must be 64 lowercase hexadecimal characters"
        )
    content_type = _bounded_string(
        payload.get("content_type"), "content_type", 256, empty=False
    )
    if any(ord(char) < 32 or char in "\r\n" for char in content_type):
        raise ValueError("manifest content_type contains invalid characters")
    content_type = content_type.strip()
    if not content_type:
        raise ValueError(
            "manifest content_type must remain non-empty after normalization"
        )
    original_acquired_at = _validate_timestamp(payload.get("original_acquired_at"))
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "url": url,
        "final_url": final_url,
        "doi": normalize_doi(doi),
        "title": title,
        "raw_path": raw_path,
        "raw_sha256": raw_sha256,
        "content_type": content_type,
        "original_acquired_at": original_acquired_at,
    }


def _is_reparse_point(path: Path) -> bool:
    info = path.lstat()
    attributes = getattr(info, "st_file_attributes", 0)
    return path.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _contained_regular_file(base: Path, relative: str) -> Path:
    current = base
    for part in PurePath(relative).parts:
        current = current / part
        try:
            reparse = _is_reparse_point(current)
        except OSError as exc:
            raise ValueError(f"manifest raw_path is missing: {relative}") from exc
        if reparse:
            raise ValueError(
                f"manifest raw_path contains a symlink or reparse point: {relative}"
            )
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(base.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("manifest raw_path escapes the manifest directory") from exc
    if not resolved.is_file():
        raise ValueError("manifest raw_path is not a regular file")
    return resolved


def _read_bounded(path: Path, maximum: int, label: str) -> bytes:
    # Check ancestors without resolving links, then bind the opened object to
    # the checked file identity. Nonblocking POSIX opens cannot hang on a FIFO
    # substituted after lstat; Windows opens the reparse object itself.
    for component in (path, *path.parents):
        if _is_reparse_point(component):
            raise ValueError(f"{label} contains a symlink or reparse point")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        handle = create(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            descriptor = msvcrt.open_osfhandle(handle, flags)
        except BaseException:
            close(handle)
            raise
    else:
        descriptor = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or not before.st_ino
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise ValueError(f"{label} changed before opening or is not a regular file")
        for component in (path, *path.parents):
            if _is_reparse_point(component):
                raise ValueError(f"{label} contains a symlink or reparse point")
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError(f"{label} changed during reading")
    if len(data) > maximum:
        raise ValueError(f"{label} exceeds the {maximum}-byte limit")
    return data


def _extract(data: bytes, content_type: str, final_url: str):
    lowered = content_type.lower()
    if "pdf" in lowered or data.startswith(b"%PDF-"):
        return _extract_pdf(data)
    if "html" in lowered or b"<html" in data[:1024].lower():
        return _extract_html(data, final_url)
    if _is_text_content_type(lowered):
        return _extract_text(data, final_url)
    raise ValueError(f"unsupported content type: {content_type}")


def import_saved_public_source(
    *, input_manifest: Path, expected_manifest_sha256: str, output_dir: Path
) -> SourceFetchResult:
    """Import declared public source bytes without making a network request."""
    manifest_path = Path(input_manifest).expanduser().absolute()
    if _is_reparse_point(manifest_path) or not manifest_path.is_file():
        raise ValueError("input manifest must be a regular non-reparse file")
    manifest_bytes = _read_bounded(manifest_path, _MAX_MANIFEST_BYTES, "input manifest")
    manifest_path = manifest_path.resolve(strict=True)
    expected_hash = expected_manifest_sha256.strip().lower()
    if len(expected_hash) != 64 or any(
        char not in "0123456789abcdef" for char in expected_hash
    ):
        raise ValueError(
            "expected_manifest_sha256 must be 64 lowercase hexadecimal characters"
        )
    manifest_hash = _hash(manifest_bytes)
    if manifest_hash != expected_hash:
        raise ValueError("input manifest SHA-256 mismatch")
    try:
        manifest = validate_saved_input_manifest(
            json.loads(manifest_bytes.decode("utf-8"))
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"input manifest is not valid UTF-8 JSON: {exc}") from exc
    raw_input = _contained_regular_file(manifest_path.parent, manifest["raw_path"])
    raw_bytes = _read_bounded(raw_input, _MAX_RAW_BYTES, "saved source")
    if _hash(raw_bytes) != manifest["raw_sha256"]:
        raise ValueError("saved source SHA-256 mismatch")

    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    started_at = _now()
    parser_error: str | None = None
    terminal_status = "parse-error"
    extracted = None
    try:
        extracted = _extract(raw_bytes, manifest["content_type"], manifest["final_url"])
    except PermissionError as exc:
        terminal_status = "inaccessible"
        parser_error = f"saved-public-source: PermissionError: {exc}"
    except Exception as exc:  # parser failures are truthful terminal evidence
        parser_error = f"saved-public-source: {type(exc).__name__}: {exc}"

    output.mkdir(parents=True, exist_ok=False)
    provenance_path, provenance_hash = _write_once(
        _artifact_path(output, "raw", "001-saved-input-provenance.json"), manifest_bytes
    )
    suffix = _suffix(manifest["content_type"], raw_bytes)
    raw_path, raw_hash = _write_once(
        _artifact_path(output, "raw", f"002-saved-public-source.{suffix}"), raw_bytes
    )
    finished_at = _now()
    attempts = [
        FetchAttempt(
            sequence=1,
            purpose="saved-input-provenance",
            url=manifest["url"],
            final_url=manifest["final_url"],
            requested_at=started_at,
            received_at=finished_at,
            http_status=None,
            content_type="application/json",
            outcome="imported",
            response_bytes=len(manifest_bytes),
            raw_path=provenance_path,
            raw_sha256=provenance_hash,
        ),
        FetchAttempt(
            sequence=2,
            purpose="saved-public-source",
            url=manifest["url"],
            final_url=manifest["final_url"],
            requested_at=started_at,
            received_at=finished_at,
            http_status=None,
            content_type=manifest["content_type"],
            outcome="parsed" if extracted is not None else terminal_status,
            response_bytes=len(raw_bytes),
            raw_path=raw_path,
            raw_sha256=raw_hash,
            error=parser_error,
        ),
    ]
    request = {
        "operation": "source import-saved",
        "doi": manifest["doi"],
        "url": manifest["url"],
        "title": manifest["title"],
        "output_dir": str(output),
        "public_only": True,
    }
    saved_diagnostics = {
        "manifest_sha256": manifest_hash,
        "manifest_schema_version": INPUT_SCHEMA_VERSION,
        "original_acquired_at": manifest["original_acquired_at"],
        "import_started_at": started_at,
        "import_completed_at": finished_at,
        "imported_at": finished_at,
        "original_http_acquisition_verified": False,
    }
    if extracted is None:
        result = SourceFetchResult(
            schema_version=SCHEMA_VERSION,
            request=request,
            receipt_sha256="",
            status=terminal_status,
            evidence_level="metadata",
            source_url=manifest["url"],
            final_url=manifest["final_url"],
            retrieved_at=finished_at,
            expected_identity={"doi": manifest["doi"], "title": manifest["title"]},
            observed_identity={"doi": "", "title": ""},
            identity_status="unverified",
            source_version=f"sha256:{raw_hash}",
            attempts=attempts,
            raw_path=None,
            raw_sha256=None,
            extracted_text_path=None,
            extracted_text_sha256=None,
            locators=[],
            errors=[parser_error or "saved source parsing failed"],
            output_dir=str(output),
            diagnostics={"saved_import": saved_diagnostics},
        )
    else:
        text_path, text_hash = _write_once(
            _artifact_path(output, "extracted", "source.txt"),
            extracted.text.encode("utf-8"),
        )
        identity_status = _source_identity(
            manifest["doi"], manifest["title"], extracted
        )
        diagnostics = dict(extracted.diagnostics)
        diagnostics["saved_import"] = saved_diagnostics
        result = SourceFetchResult(
            schema_version=SCHEMA_VERSION,
            request=request,
            receipt_sha256="",
            status="identity-mismatch"
            if identity_status == "mismatch"
            else "available",
            evidence_level=extracted.evidence_level,
            source_url=manifest["url"],
            final_url=manifest["final_url"],
            retrieved_at=finished_at,
            expected_identity={"doi": manifest["doi"], "title": manifest["title"]},
            observed_identity={
                "doi": normalize_doi(extracted.observed_doi),
                "title": extracted.observed_title,
            },
            identity_status=identity_status,
            source_version=f"sha256:{raw_hash}",
            attempts=attempts,
            raw_path=raw_path,
            raw_sha256=raw_hash,
            extracted_text_path=text_path,
            extracted_text_sha256=text_hash,
            locators=extracted.locators,
            output_dir=str(output),
            diagnostics=diagnostics,
        )
    result.receipt_sha256 = _receipt_hash(
        request, attempts, result.extracted_text_sha256, _receipt_result_fields(result)
    )
    _write_once(
        _artifact_path(output, "source-fetch-result.json"),
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2).encode("utf-8"),
    )
    return result


__all__ = ["INPUT_SCHEMA_VERSION", "import_saved_public_source"]
