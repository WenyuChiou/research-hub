"""Security helpers for research-hub."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:/\-]{1,256}$")
_FORBIDDEN_SEGMENTS = {"", ".", ".."}


class ValidationError(ValueError):
    """Raised when untrusted input fails validation."""


def validate_slug(value: object, *, field: str = "slug") -> str:
    """Validate that a string is safe for use as a slug/path segment."""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string, got {type(value).__name__}")
    if value != value.strip():
        raise ValidationError(f"{field} has leading/trailing whitespace")
    slug = value.lower()
    if slug != value:
        raise ValidationError(f"{field}={value!r} invalid: must be lowercase")
    if not SLUG_RE.fullmatch(slug):
        raise ValidationError(
            f"{field}={value!r} invalid: must match {SLUG_RE.pattern} (lowercase a-z, 0-9, _, -)"
        )
    return slug


def validate_identifier(value: object, *, field: str = "identifier") -> str:
    """Validate a DOI/arXiv-style identifier."""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string, got {type(value).__name__}")
    if not IDENTIFIER_RE.fullmatch(value):
        raise ValidationError(
            f"{field}={value!r} invalid: contains characters outside [A-Za-z0-9._:/-]"
        )
    return value


def safe_join(root: Path, *segments: str) -> Path:
    """Join untrusted path segments to root without allowing traversal."""
    root_resolved = Path(root).resolve()
    for seg in segments:
        if not isinstance(seg, str):
            raise ValidationError(f"path segment must be string, got {type(seg).__name__}")
        if seg in _FORBIDDEN_SEGMENTS:
            raise ValidationError(f"path segment {seg!r} not allowed")
        if "/" in seg or "\\" in seg or "\x00" in seg:
            raise ValidationError(f"path segment {seg!r} contains separators")
        if seg.startswith(".") and seg in {".", ".."}:
            raise ValidationError(f"path segment {seg!r} not allowed")
    candidate = root_resolved.joinpath(*segments).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValidationError(f"path {candidate} escapes root {root_resolved}") from exc
    return candidate


def chmod_sensitive(path: Path, *, mode: int) -> None:
    """Best-effort chmod for sensitive files/directories."""
    if sys.platform.startswith("win"):
        return
    try:
        os.chmod(str(path), mode)
    except OSError:
        pass


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write text atomically via tmp file + replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(content, encoding=encoding)
        os.replace(str(tmp), str(path))
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


__all__ = [
    "SLUG_RE",
    "IDENTIFIER_RE",
    "ValidationError",
    "validate_slug",
    "validate_identifier",
    "safe_join",
    "chmod_sensitive",
    "atomic_write_text",
]
