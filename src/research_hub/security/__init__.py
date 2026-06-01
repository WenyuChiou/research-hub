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


_WINDOWS_ACL_WARNED = False


def _windows_principal() -> str:
    """Best-resolvable name for the current user.

    A domain-qualified ``DOMAIN\\USER`` resolves more reliably under
    unusual process tokens (e.g. the Playwright/Chromium subprocess
    spawned by the NLM-login flow) than a bare username, which is
    where the v1.0.0 deny-all incident originated. Falls back to the
    bare name when ``USERDOMAIN`` is absent.
    """
    import getpass

    name = os.environ.get("USERNAME") or getpass.getuser()
    domain = os.environ.get("USERDOMAIN")
    return f"{domain}\\{name}" if domain else name


def _acl_is_dir(path: Path, mode: int) -> bool:
    """True if ``path`` should be hardened as a directory.

    Uses the live filesystem when the path exists, else infers from
    the POSIX ``mode`` the caller passed (dirs get 0o700 — execute
    bits set; files get 0o600 — none).
    """
    try:
        if path.exists():
            return path.is_dir()
    except OSError:
        pass
    return bool(mode & 0o111)


def _acl_grant_argv(path: Path, principal: str, *, is_dir: bool) -> list[str]:
    """icacls argv that strips inheritance and grants the owner access.

    Arg order is mandated by icacls itself: ``/inheritance:r`` MUST
    precede ``/grant``; reversing them makes icacls reject
    ``/inheritance:r`` as an invalid parameter (verified empirically).
    Directories get an INHERITABLE ``(OI)(CI)`` ACE so files written
    into them afterwards are never born without owner access — the
    absence of this is what bricked ``clusters.yaml`` (deny-all).
    """
    perms = "(OI)(CI)(F)" if is_dir else "(F)"
    return ["icacls", str(path), "/inheritance:r", "/grant:r", f"{principal}:{perms}"]


def _acl_reset_argv(path: Path, *, is_dir: bool) -> list[str]:
    """icacls argv that restores inherited ACEs (the fail-safe path)."""
    argv = ["icacls", str(path), "/reset"]
    if is_dir:
        argv.append("/T")
    return argv


def _acl_grant_present(icacls_stdout: str, principal: str) -> bool:
    """Whether an `icacls <path>` listing shows the owner was granted.

    icacls echoes the full path before the ACEs and exits 0 even when
    ``/grant:r`` silently no-ops (the EMPTY-DACL deny-all failure), so
    a loose name substring would false-match the path itself —
    sensitive files live under ``C:\\Users\\<name>\\`` so the bare
    account name is ALWAYS in the echoed path even when the DACL is
    empty. An ACE renders the account as ``[DOMAIN\\]name:(...)``;
    ``name:(`` cannot occur in a path (``:`` / ``(`` are illegal in
    Windows filenames), so it uniquely identifies a real granted ACE.
    """
    name = principal.split("\\")[-1].strip().lower()
    return bool(name) and f"{name}:(" in icacls_stdout.lower()


def _restrict_windows_acl(path: Path, *, mode: int = 0o600) -> None:
    """Restrict a path to the current user via icacls (G3 P2 #14).

    Pre-v0.91.0 `chmod_sensitive` was a silent no-op on Windows, so
    `config.json` (encrypted Zotero key), `.secret_box.key` (the
    Fernet key sitting NEXT TO the ciphertext), and NLM `state.json`
    (Google session cookies) inherited the parent's ACL — readable by
    any other account on a shared box. We strip inheritance and grant
    Full control to the current user only.

    v1.0.0 fail-safe rewrite (deny-all incident): the pre-v1.0 form
    ``icacls <p> /inheritance:r /grant:r <bare-user>:(F)`` could leave
    a path with an EMPTY DACL — deny-all, unreadable even by the
    owner — when the bare principal failed to resolve under an unusual
    process token, AND directories got a non-inheritable ACE so files
    born into them afterwards had no owner ACE at all. icacls still
    exits 0 in both cases, so the old rc-only guard never fired and
    the whole vault bricked (`clusters.yaml` unreadable → every CLI
    command silently failed). This now fails OPEN, not CLOSED:
      1. directories get an inheritable ``(OI)(CI)(F)`` owner ACE;
      2. after applying, the DACL is verified to still grant the
         current user — if not (or icacls failed/raised), the path is
         rolled back to inherited ACEs via ``icacls /reset`` so the
         owner is never locked out, and we warn ONCE per process.
    Worst case is therefore "secrets not OS-hardened + one warning",
    never "tool bricked".
    """
    import subprocess

    # Skip real ACL mutation under any test context. icacls
    # /inheritance:r on a directory removes the inherited ACEs the test
    # harness needs to rmtree + recreate `.pytest-work/...` across runs,
    # causing FileExistsError / PermissionError on the next mkdir.
    #
    # v0.91.1 hotfix: `"pytest" in sys.modules` ALONE is insufficient —
    # e2e tests spawn a real `python -m research_hub` SUBPROCESS where
    # pytest is NOT imported, so the guard didn't fire and icacls locked
    # `.pytest-work/.../clusters.yaml` on clean CI Windows runners
    # (v0.91.0 CI failure). `PYTEST_CURRENT_TEST` IS inherited by
    # subprocesses (pytest sets it in os.environ; subprocess.run passes
    # the parent env by default), so it covers the spawned-CLI case.
    # `RESEARCH_HUB_SKIP_ACL_HARDENING` is an explicit operator/CI
    # escape hatch. Production behaviour (user-only ACL on real
    # config/secret/cookie files) is unchanged.
    if (
        "pytest" in sys.modules
        or os.environ.get("PYTEST_CURRENT_TEST")
        or os.environ.get("RESEARCH_HUB_SKIP_ACL_HARDENING")
    ):
        return

    is_dir = _acl_is_dir(path, mode)

    def _fail_open(detail: str) -> None:
        """Restore inherited ACEs so the owner is never locked out."""
        global _WINDOWS_ACL_WARNED
        try:
            subprocess.run(
                _acl_reset_argv(path, is_dir=is_dir),
                capture_output=True,
                text=True,
                errors="replace",
                timeout=30,
            )
        except Exception:  # noqa: BLE001 - best-effort rollback
            pass
        if not _WINDOWS_ACL_WARNED:
            _WINDOWS_ACL_WARNED = True
            print(
                f"  [security] WARN could not OS-restrict {path} "
                f"({detail}); reverted to inherited ACL — secrets are "
                f"NOT OS-protected on this Windows host.",
                file=sys.stderr,
            )

    try:
        principal = _windows_principal()
        result = subprocess.run(
            _acl_grant_argv(path, principal, is_dir=is_dir),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
        )
        verify = subprocess.run(
            ["icacls", str(path)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0 or not _acl_grant_present(
            verify.stdout, principal
        ):
            _fail_open(
                f"icacls rc={result.returncode}, owner grant absent "
                f"after apply: {result.stderr.strip()[:120]}"
            )
    except Exception as exc:  # noqa: BLE001 - best-effort hardening
        _fail_open(f"{type(exc).__name__}: {exc}")


def chmod_sensitive(path: Path, *, mode: int) -> None:
    """Best-effort permission tightening for sensitive files/dirs.

    POSIX: os.chmod to the requested mode. Windows (G3 P2 #14):
    icacls inheritance-strip + user-only Full control, since chmod
    is a no-op there. `mode` is POSIX-only on the numeric value, but
    its execute bits are used to tell directory (0o700) from file
    (0o600) intent so directories get an inheritable owner ACE.
    """
    if sys.platform.startswith("win"):
        _restrict_windows_acl(path, mode=mode)
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
