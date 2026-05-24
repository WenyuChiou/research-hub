"""Idle keepalive for NotebookLM sessions.

Periodically rotates and persists the stored cookies so Google does not revoke
an idle session (typically within 12–24 h without activity).

Honest scope note
-----------------
- ``rotate_and_persist_session`` makes one network call to accounts.google.com.
  If the session cookies are already revoked server-side it will silently fail
  (best-effort, never raises) and ``keepalive_once`` returns non-zero so a
  scheduler can surface the failure.
- The Windows Scheduled Task registration (``--install-windows-task``) is
  gated behind an explicit ``--yes`` flag. Without ``--yes`` the exact
  ``schtasks`` command is only printed — nothing is registered; no wrapper file
  is created either.
- The task runs via a console-script (if pip-installed) or a generated wrapper
  ``.cmd`` file (if running from a source checkout) to guarantee PYTHONPATH is
  set correctly. No elevated privileges (no /RL HIGHEST) are required.
- Google can still hard-expire long-lived SID/PSID cookies (~1 year) or revoke
  on a security event; keepalive does not prevent that. Combine with
  ``notebooklm login --from-browser`` for easy re-auth.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from research_hub._invocation import recommended_cli_invocation

if TYPE_CHECKING:
    pass

_TASK_NAME = "ResearchHubNLMKeepalive"


# ---------------------------------------------------------------------------
# Core: rotate + persist
# ---------------------------------------------------------------------------


def rotate_and_persist_session(state_file: Path) -> bool:
    """Rotate the stored NotebookLM cookies and persist them back to *state_file*.

    Best-effort: any exception (missing API, network error, file I/O) is caught
    and causes this function to return ``False``.  It NEVER raises.

    Steps:
    1. ``build_httpx_cookies_from_storage`` — load the cookie jar from state.json.
    2. Create an ``httpx.AsyncClient`` seeded with those cookies.
    3. ``_rotate_cookies(client, storage_path=state_file)`` — POST to
       accounts.google.com RotateCookies (best-effort; no-op if env-var disabled).
    4. ``save_cookies_to_storage(client.cookies, state_file)`` — persist the
       refreshed jar atomically (upstream uses a threading.Lock).
    5. ``_tighten_state_file_perms`` — keep permissions strict (user-only).

    Returns ``True`` on success, ``False`` on any failure.
    """
    try:
        import httpx
        from notebooklm.auth import (
            _rotate_cookies,  # noqa: PLC2701 — private but stable keepalive API
            build_httpx_cookies_from_storage,
            save_cookies_to_storage,
        )

        from research_hub.notebooklm.auth import _tighten_state_file_perms

        jar = build_httpx_cookies_from_storage(state_file)

        async def _do_rotate() -> httpx.Cookies:
            async with httpx.AsyncClient(cookies=jar, follow_redirects=True) as client:
                await _rotate_cookies(client, storage_path=state_file)
                return client.cookies

        rotated_jar = asyncio.run(_do_rotate())
        save_cookies_to_storage(rotated_jar, state_file)
        _tighten_state_file_perms(state_file)
        return True
    except Exception as exc:  # noqa: BLE001
        # Best-effort: never raise; callers check the return value.
        print(
            f"[nlm-keepalive] WARN rotate_and_persist_session failed "
            f"({type(exc).__name__}: {exc}); session may be stale.",
            file=sys.stderr,
        )
        return False


# ---------------------------------------------------------------------------
# keepalive_once
# ---------------------------------------------------------------------------


def keepalive_once(cfg: Any) -> int:
    """Run one keepalive cycle.

    1. Resolve the state file from *cfg*.
    2. ``check_session_health`` — if the session is revoked, print an actionable
       WARN and return 1 (non-zero so schedulers surface the failure; never raise).
    3. If healthy, call ``rotate_and_persist_session`` and re-probe before success.

    Args:
        cfg: A ``HubConfig``-like object exposing ``research_hub_dir: Path``.

    Returns:
        0 on success, non-zero on failure.
    """
    try:
        from research_hub.notebooklm.auth import (
            check_session_health,
            default_state_file,
        )

        inv = recommended_cli_invocation()
        state_file = default_state_file(cfg.research_hub_dir)
        health = check_session_health(state_file)
        if not health.get("ok"):
            reason = health.get("reason", "unknown")
            print(
                f"[nlm-keepalive] WARN NLM session revoked server-side "
                f"(reason: {reason}) -- run: {inv} notebooklm login --auto-detect",
                file=sys.stderr,
            )
            return 1

        ok = rotate_and_persist_session(state_file)
        if not ok:
            return 1

        post_health = check_session_health(state_file)
        if not post_health.get("ok"):
            print(
                "[nlm-keepalive] WARN keepalive: cookies rotated but session is "
                "no longer valid (likely server-side re-auth required); "
                f"run {inv} notebooklm login --auto-detect",
                file=sys.stderr,
            )
            return 1
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
        interval_sec: Seconds between keepalive calls. Floor is 3600.
        sleep_fn: Callable used for sleeping; defaults to ``time.sleep``.
                  Injectable for tests.

    Returns:
        0 (stops cleanly on keyboard interrupt).
    """
    if sleep_fn is None:
        sleep_fn = time.sleep
    interval_sec = max(3600, interval_sec)
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


def _build_schtasks_argv(interval_hours: int, task_cmd: str) -> list[str]:
    """Build the ``schtasks /Create`` argv for the keepalive Scheduled Task.

    The ``/TR`` (task run) value must be a single string containing the full
    command so that schtasks registers it correctly.

    Note: no ``/RL HIGHEST`` is included — elevated privileges are not required
    for a user-level scheduled task and would break on non-admin accounts.

    Args:
        interval_hours: How often to run the task (hours).
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
        "/SC", "HOURLY",
        "/MO", str(interval_hours),
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
    interval_hours: int,
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
        interval_hours: Hours between task runs (only used for install).
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
    argv = _build_schtasks_argv(interval_hours, task_cmd)
    action_desc = (
        f"Register Scheduled Task '{_TASK_NAME}' "
        f"(every {interval_hours}h via schtasks)"
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
