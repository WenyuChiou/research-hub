"""Idle keepalive for NotebookLM sessions.

Periodically refreshes the short-lived freshness cookies (``__Secure-1PSIDTS``
/ ``__Secure-3PSIDTS``) so Google does not revoke an idle session. Google's
PSIDTS cookies expire every ~3-4 hours; the long-lived ``SID``/``PSID``
cookies last ~1 year. If a minute-cadence keepalive actually rotates PSIDTS
ahead of expiry, the practical session lifetime is bounded by the
long-lived cookies, not the short ones.

Refresh contract
----------------
``refresh_and_persist_session`` (the primary API) calls the SDK's public
``fetch_tokens_with_domains`` — which actually fetches CSRF + session_id
tokens from the NotebookLM homepage as a side-effect of cookie rotation.
This is observable proof: if tokens come back, the cookies are good. The
older ``rotate_and_persist_session`` wrapper used the SDK's private
``_rotate_cookies`` poke which returned success without verifying that the
session was still alive — every "success" in the logs could have been a
no-op against a revoked session.

Honest scope note
-----------------
- ``refresh_and_persist_session`` makes one network call to Google. If the
  session is already revoked server-side it returns a ``RefreshResult`` with
  ``ok=False`` and an actionable reason; ``keepalive_once`` then returns
  non-zero so a scheduler can surface the failure.
- The Windows Scheduled Task registration (``--install-windows-task``) is
  gated behind an explicit ``--yes`` flag. Without ``--yes`` the exact
  ``schtasks`` command is only printed.
- The task runs via a console-script (if pip-installed) or a generated wrapper
  ``.cmd`` file (if running from a source checkout) to guarantee PYTHONPATH is
  set correctly. No elevated privileges (no /RL HIGHEST) are required.
- Google can still hard-expire long-lived SID/PSID cookies or revoke on a
  security event; keepalive does not defeat revocation. Combine with
  ``notebooklm login --auto-detect`` for re-auth when that happens.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from research_hub._invocation import recommended_cli_invocation

if TYPE_CHECKING:
    pass

_TASK_NAME = "ResearchHubNLMKeepalive"

# Cookies whose expiry/value we track to PROVE keepalive rotation worked.
# Names match the SDK's MINIMUM_REQUIRED_COOKIES expectations
# (``__Secure-1PSIDTS`` / ``__Secure-3PSIDTS``) plus the rarer RTS variants
# the older handoff named — we log them when present.
_FRESHNESS_COOKIE_NAMES = (
    "__Secure-1PSIDTS",
    "__Secure-3PSIDTS",
    "__Secure-1PSIDRTS",
    "__Secure-3PSIDRTS",
)


@dataclass
class RefreshResult:
    """Outcome of one ``refresh_and_persist_session`` call.

    ``ok`` is grounded in *observable* token extraction: if the SDK's public
    ``fetch_tokens_with_domains`` returned a (csrf, session_id) tuple then the
    session was still acceptable to NotebookLM at the moment of refresh. The
    metadata fields let a scheduler / operator confirm that the freshness
    cookies actually moved forward (otherwise "ok" would be silent no-op).
    """

    ok: bool
    reason: str = ""
    before_metadata: dict[str, str] = field(default_factory=dict)
    after_metadata: dict[str, str] = field(default_factory=dict)
    changed: list[str] = field(default_factory=list)


def _read_short_cookie_metadata(state_file: Path) -> dict[str, str]:
    """Return ``{cookie_name: "expiry=<unix-ts> | absent"}`` for the freshness
    cookies. NEVER includes cookie values — those are secrets — only names
    and expiry timestamps so before/after diff logs are safe to print.
    """
    if not state_file.exists():
        return {name: "absent" for name in _FRESHNESS_COOKIE_NAMES}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {name: "unreadable" for name in _FRESHNESS_COOKIE_NAMES}
    cookies = data.get("cookies", []) if isinstance(data, dict) else []
    by_name: dict[str, dict] = {
        str(c.get("name", "")): c for c in cookies if isinstance(c, dict)
    }
    out: dict[str, str] = {}
    for name in _FRESHNESS_COOKIE_NAMES:
        cookie = by_name.get(name)
        if cookie is None:
            out[name] = "absent"
            continue
        # storage_state format uses "expires" (Playwright) or "expiry"
        expiry = cookie.get("expires", cookie.get("expiry", "?"))
        out[name] = f"expiry={expiry}"
    return out


# ---------------------------------------------------------------------------
# Core: rotate + persist
# ---------------------------------------------------------------------------


def refresh_and_persist_session(state_file: Path) -> RefreshResult:
    """Refresh the NLM session via the SDK's *public* token-fetch path.

    This replaces the older ``rotate_and_persist_session`` (still available
    as a thin back-compat wrapper, below) which used the SDK's *private*
    ``_rotate_cookies`` poke. The private poke is a fire-and-forget rotation
    nudge with no verification — it could return success against a revoked
    session, masking the real failure until the next downstream call broke.

    The public ``fetch_tokens_with_domains`` actually GETs the NotebookLM
    homepage, extracts (csrf_token, session_id), and persists the resulting
    rotated cookies. If tokens come back, the cookies are observably good.

    Best-effort vs. exceptions: this function NEVER raises. Any failure ends
    up in ``RefreshResult(ok=False, reason=...)`` so a scheduler can decide
    whether to surface or retry.
    """
    before = _read_short_cookie_metadata(state_file)
    try:
        from notebooklm.auth import fetch_tokens_with_domains
    except Exception as exc:  # noqa: BLE001
        return RefreshResult(
            ok=False,
            reason=f"sdk-import-failed: {type(exc).__name__}: {exc}",
            before_metadata=before,
            after_metadata=before,
        )
    try:
        # fetch_tokens_with_domains is async; run in a fresh loop. It
        # internally builds the jar, GETs notebooklm.google.com to obtain
        # tokens, and persists the refreshed cookies back to state_file.
        asyncio.run(fetch_tokens_with_domains(path=state_file))
    except Exception as exc:  # noqa: BLE001
        after = _read_short_cookie_metadata(state_file)
        return RefreshResult(
            ok=False,
            reason=f"{type(exc).__name__}: {exc}",
            before_metadata=before,
            after_metadata=after,
            changed=[n for n in before if before.get(n) != after.get(n)],
        )
    # Optional cosmetic: keep file permissions tight (user-only). Failures
    # here are not refresh failures.
    try:
        from research_hub.notebooklm.auth import _tighten_state_file_perms
        _tighten_state_file_perms(state_file)
    except Exception:  # noqa: BLE001
        pass
    after = _read_short_cookie_metadata(state_file)
    changed = [name for name in before if before.get(name) != after.get(name)]
    return RefreshResult(
        ok=True,
        reason="ok",
        before_metadata=before,
        after_metadata=after,
        changed=changed,
    )


def rotate_and_persist_session(state_file: Path) -> bool:
    """Back-compat shim around :func:`refresh_and_persist_session`.

    Older callers (including some tests) expect a bool return. This wrapper
    runs the new public-API refresh and collapses the structured result to
    ``True``/``False``. New code should call ``refresh_and_persist_session``
    directly to get the metadata diff and a structured reason string.
    """
    result = refresh_and_persist_session(state_file)
    if not result.ok:
        print(
            f"[nlm-keepalive] WARN refresh_and_persist_session failed "
            f"({result.reason}); session may be stale.",
            file=sys.stderr,
        )
    return result.ok


# ---------------------------------------------------------------------------
# keepalive_once
# ---------------------------------------------------------------------------


def keepalive_once(cfg: Any) -> int:
    """Run one keepalive cycle: refresh the session and verify cookies moved.

    Sequence (per Codex review of the old design):

    1. Resolve the state file from *cfg*.
    2. Call :func:`refresh_and_persist_session` **first**. The SDK's public
       token-fetch already verifies that NotebookLM accepted the cookies —
       a pre-health gate would just block the only refresh attempt and
       guarantee a stale session loops forever.
    3. If refresh failed, log an actionable hint and return 1.
    4. Log the before/after freshness-cookie metadata diff so an operator
       can confirm rotation actually moved expiries forward (the old
       implementation silently no-op'd here).

    Args:
        cfg: A ``HubConfig``-like object exposing ``research_hub_dir: Path``.

    Returns:
        0 on success, non-zero on failure.
    """
    try:
        from research_hub.notebooklm.auth import default_state_file

        inv = recommended_cli_invocation()
        state_file = default_state_file(cfg.research_hub_dir)
        result = refresh_and_persist_session(state_file)
        if not result.ok:
            print(
                f"[nlm-keepalive] WARN refresh failed: {result.reason} -- "
                f"run: {inv} notebooklm login --auto-detect",
                file=sys.stderr,
            )
            return 1
        # Surface the metadata diff so the operator can SEE the rotation
        # actually happened (the old code logged "success" against revoked
        # sessions for months).
        changed_str = ", ".join(result.changed) if result.changed else "(no expiry change)"
        print(
            f"[nlm-keepalive] OK refresh: changed={changed_str}",
            file=sys.stderr,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(
            f"[nlm-keepalive] WARN keepalive_once failed unexpectedly "
            f"({type(exc).__name__}: {exc}).",
            file=sys.stderr,
        )
        return 1


# ---------------------------------------------------------------------------
# CLI dispatch helpers (called from cli.py)
# ---------------------------------------------------------------------------


def _keepalive_loop(cfg: Any, interval_sec: int, sleep_fn=None) -> int:
    """Run keepalive indefinitely, sleeping *interval_sec* between calls.

    Designed for long-running ``nohup`` supervision. Stops only on SIGINT /
    KeyboardInterrupt (returns 0).

    Args:
        cfg: HubConfig-like object.
        interval_sec: Seconds between keepalive calls. Floor is 600 (10 min).
        sleep_fn: Callable used for sleeping; defaults to ``time.sleep``.
                  Injectable for tests.

    Returns:
        0 (stops cleanly on keyboard interrupt).
    """
    if sleep_fn is None:
        sleep_fn = time.sleep
    # PSIDTS expires ~every 3-4 hours. A 1-hour floor (the old default)
    # rotated 3-4 times before expiry which gave little safety margin and
    # routinely lost races on slow networks. Floor at 10 min (600 s) for
    # accidental-abuse prevention while letting the schtasks default of
    # 15 min give us ~14 chances per expiry window.
    interval_sec = max(600, interval_sec)
    print(
        f"[nlm-keepalive] Starting loop (interval={interval_sec}s). "
        "Press Ctrl-C to stop.",
        file=sys.stderr,
    )
    try:
        while True:
            rc = keepalive_once(cfg)
            if rc != 0:
                print(
                    "[nlm-keepalive] keepalive_once returned non-zero; "
                    "sleeping before retry.",
                    file=sys.stderr,
                )
            sleep_fn(interval_sec)
    except KeyboardInterrupt:
        print("[nlm-keepalive] Loop stopped by user.", file=sys.stderr)
    return 0


def _resolve_task_command(cfg: Any) -> tuple[str, Path | None]:
    """Resolve the task command and optional wrapper .cmd path.

    Determines whether the keepalive task should be run via an installed
    console-script or via a generated wrapper ``.cmd`` file (for source-checkout
    installs where ``research-hub`` is not on PATH).

    Strategy
    --------
    1. If the recommended invocation is the installed console-script,
       use it directly.  No wrapper file is needed.
    2. Otherwise (source checkout): derive the repo root from this module's
       location (``parents[3]``), validate it, write a ``.cmd`` wrapper that
       sets ``PYTHONPATH=src`` and invokes ``sys.executable -m research_hub
       notebooklm keepalive``.

    Args:
        cfg: HubConfig-like object exposing ``research_hub_dir: Path``.

    Returns:
        A ``(task_command_str, wrapper_path_or_None)`` tuple.
        *task_command_str* is the quoted string suitable for schtasks ``/TR``.
        *wrapper_path_or_None* is the ``.cmd`` path that will be/was written,
        or ``None`` when the console-script path is used.
    """
    invocation = recommended_cli_invocation()
    if invocation == "research-hub":
        console_script = shutil.which("research-hub") or "research-hub"
        # Installed path — run directly; no wrapper needed.
        task_cmd = f'"{console_script}" notebooklm keepalive'
        return task_cmd, None

    # Source-checkout path: derive repo root from this file's location.
    # keepalive.py lives at src/research_hub/notebooklm/keepalive.py
    # parents[3] is therefore the repo root containing src/.
    module_path = Path(__file__).resolve()
    repo_root = module_path.parents[3]
    src_dir = repo_root / "src" / "research_hub"
    if not src_dir.is_dir():
        warnings.warn(
            f"[nlm-keepalive] Could not verify repo root at {repo_root!r} "
            f"(expected {src_dir!r} to exist). "
            "Falling back to cwd. The task may fail if cwd is wrong.",
            RuntimeWarning,
            stacklevel=2,
        )
        repo_root = Path.cwd()

    exe = sys.executable
    wrapper_path = Path(cfg.research_hub_dir) / "nlm_keepalive.cmd"
    wrapper_contents = (
        "@echo off\n"
        f'cd /d "{repo_root}"\n'
        "set PYTHONPATH=src\n"
        f'"{exe}" -m research_hub notebooklm keepalive\n'
    )
    task_cmd = f'"{wrapper_path}"'
    return task_cmd, wrapper_path


def _build_schtasks_argv(interval_minutes: int, task_cmd: str) -> list[str]:
    """Build the ``schtasks /Create`` argv for the keepalive Scheduled Task.

    Minute-cadence (/SC MINUTE) by design: PSIDTS expires every ~3-4 hours,
    so hourly was barely enough — a 15-minute cadence gives ~14 retries per
    expiry window and absorbs flaky-network failures gracefully.

    The ``/TR`` (task run) value must be a single string containing the full
    command so that schtasks registers it correctly.

    Note: no ``/RL HIGHEST`` is included — elevated privileges are not required
    for a user-level scheduled task and would break on non-admin accounts.

    Args:
        interval_minutes: How often to run the task (minutes).
        task_cmd: The resolved task command string (from ``_resolve_task_command``).

    Returns:
        List of strings suitable for ``subprocess.run``.
    """
    return [
        "schtasks",
        "/Create",
        "/F",
        "/TN", _TASK_NAME,
        "/TR", task_cmd,
        "/SC", "MINUTE",
        "/MO", str(interval_minutes),
    ]


def _build_schtasks_uninstall_argv() -> list[str]:
    """Build the ``schtasks /Delete`` argv for removing the keepalive task."""
    return [
        "schtasks",
        "/Delete",
        "/F",
        "/TN", _TASK_NAME,
    ]


def run_install_windows_task(
    interval_minutes: int,
    *,
    dry_run: bool,
    uninstall: bool = False,
    cfg: Any = None,
) -> int:
    """Register or remove the Windows Scheduled Task for keepalive.

    SYSTEM MUTATION: only executed when ``dry_run=False``.  When ``dry_run``
    is True, the exact ``schtasks`` command is printed and nothing is registered
    or written to disk (the wrapper ``.cmd`` is NOT created in dry-run mode).

    Args:
        interval_minutes: Minutes between task runs (only used for install).
            The schtasks command uses ``/SC MINUTE`` so this is literally
            the ``/MO`` value. Default in the CLI is 15.
        dry_run: If True, print only; never mutate system state (no schtasks
            call, no wrapper file written).
        uninstall: If True, remove instead of create.
        cfg: HubConfig-like object (required for install; used to determine
            wrapper .cmd location and repo root).  May be None for uninstall
            when no wrapper path lookup is needed.

    Returns:
        0 on success, 1 on failure or non-Windows.
    """
    import platform

    if platform.system() != "Windows":
        print(
            "[nlm-keepalive] --install-windows-task / --uninstall-windows-task "
            "is Windows-only. On non-Windows, use a cron job or similar scheduler.",
            file=sys.stderr,
        )
        return 1

    if uninstall:
        argv = _build_schtasks_uninstall_argv()
        action_desc = f"Remove Scheduled Task '{_TASK_NAME}'"
        wrapper_path: Path | None = None
        if cfg is not None:
            # Best-effort: locate the wrapper to delete it on apply.
            wrapper_path = Path(cfg.research_hub_dir) / "nlm_keepalive.cmd"

        if dry_run:
            msg = (
                f"[nlm-keepalive] DRY-RUN — would run:\n  {' '.join(argv)}\n"
                f"  ({action_desc})"
            )
            if wrapper_path and wrapper_path.exists():
                msg += f"\n  Would also delete wrapper: {wrapper_path}"
            msg += "\nRe-run with --yes to execute."
            print(msg, file=sys.stderr)
            print(" ".join(argv))
            return 0

        import subprocess
        result = subprocess.run(argv, check=False)
        if result.returncode == 0:
            print(f"[nlm-keepalive] {action_desc} — OK.", file=sys.stderr)
            if wrapper_path and wrapper_path.exists():
                try:
                    wrapper_path.unlink()
                    print(
                        f"[nlm-keepalive] Deleted wrapper: {wrapper_path}",
                        file=sys.stderr,
                    )
                except OSError as exc:
                    print(
                        f"[nlm-keepalive] WARN could not delete wrapper "
                        f"{wrapper_path}: {exc}",
                        file=sys.stderr,
                    )
        else:
            print(
                f"[nlm-keepalive] schtasks exited {result.returncode}. "
                "Check Task Scheduler permissions.",
                file=sys.stderr,
            )
        return result.returncode

    # Install path.
    task_cmd, wrapper_path = _resolve_task_command(cfg)
    argv = _build_schtasks_argv(interval_minutes, task_cmd)
    action_desc = (
        f"Register Scheduled Task '{_TASK_NAME}' "
        f"(every {interval_minutes}m via schtasks)"
    )

    if dry_run:
        msg_lines = [
            f"[nlm-keepalive] DRY-RUN — would run:\n  {' '.join(argv)}",
            f"  ({action_desc})",
        ]
        if wrapper_path is not None:
            # Show what the wrapper would contain without writing it.
            exe = sys.executable
            repo_root = Path(__file__).resolve().parents[3]
            src_dir = repo_root / "src" / "research_hub"
            if not src_dir.is_dir():
                repo_root = Path.cwd()
            wrapper_contents = (
                "@echo off\n"
                f'cd /d "{repo_root}"\n'
                "set PYTHONPATH=src\n"
                f'"{exe}" -m research_hub notebooklm keepalive\n'
            )
            msg_lines.append(
                f"\n  Wrapper .cmd (would be written to {wrapper_path}):\n"
                + "\n".join(f"    {line}" for line in wrapper_contents.splitlines())
            )
        else:
            msg_lines.append(f"  (console-script: {task_cmd}; no wrapper file needed)")
        msg_lines.append("Re-run with --yes to execute.")
        print("\n".join(msg_lines), file=sys.stderr)
        print(" ".join(argv))
        return 0

    import subprocess
    # Write wrapper .cmd first (if source-checkout path).
    if wrapper_path is not None:
        exe = sys.executable
        repo_root = Path(__file__).resolve().parents[3]
        src_dir = repo_root / "src" / "research_hub"
        if not src_dir.is_dir():
            repo_root = Path.cwd()
        wrapper_contents = (
            "@echo off\n"
            f'cd /d "{repo_root}"\n'
            "set PYTHONPATH=src\n"
            f'"{exe}" -m research_hub notebooklm keepalive\n'
        )
        wrapper_path.parent.mkdir(parents=True, exist_ok=True)
        wrapper_path.write_text(wrapper_contents, encoding="utf-8")
        print(f"[nlm-keepalive] Wrote wrapper: {wrapper_path}", file=sys.stderr)

    result = subprocess.run(argv, check=False)
    if result.returncode == 0:
        print(f"[nlm-keepalive] {action_desc} — OK.", file=sys.stderr)
    else:
        print(
            f"[nlm-keepalive] schtasks exited {result.returncode}. "
            "Check Task Scheduler permissions.",
            file=sys.stderr,
        )
    return result.returncode
