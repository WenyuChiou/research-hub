"""Authentication and session management shims for NotebookLM."""

from __future__ import annotations

import asyncio
import inspect
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notebooklm import AuthError, NotebookLMClient
from research_hub.errors import RequiresAuthRefresh


def default_session_dir(research_hub_dir: Path) -> Path:
    """Return the legacy Chromium profile directory for this vault."""
    return research_hub_dir / "nlm_sessions" / "default"


def default_state_file(research_hub_dir: Path) -> Path:
    """Return the Playwright storage state path for this vault."""
    return research_hub_dir / "nlm_sessions" / "state.json"


def _tighten_state_file_perms(target: Path) -> None:
    """Chmod state.json to user-only (G3 P1 #2).

    Pre-fix the parent dir got chmod 0700 via chmod_sensitive but the
    state.json file itself stayed at default umask (0644 on POSIX,
    world-readable). state.json holds Google session cookies; any
    local user could read it and hijack the NLM session. On Windows,
    chmod_sensitive is currently a no-op (G3 P2 #14 will fix that in
    a separate wave); the POSIX path tightens to 0600 immediately.
    """
    if not target.is_file():
        return
    try:
        from research_hub.security import chmod_sensitive
        chmod_sensitive(target, mode=0o600)
    except Exception as exc:
        print(
            f"  [nlm] WARN could not tighten {target} permissions: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def login_nlm(
    user_data_dir: Path,
    *,
    state_file: Path | None = None,
    headless: bool = False,
    timeout_sec: int = 300,
    stable_hold_sec: int = 5,
    wait_file: Path | None = None,
    wait_timeout: int = 300,
    auto_detect: bool = False,
) -> int:
    """Open notebooklm-py's one-time login flow and save storage state.

    Three orchestration modes:
    - default (no flag): interactive ENTER gate in a real terminal (runs
      the upstream ``notebooklm login`` subprocess).
    - ``wait_file=PATH``: file-signal gate (see ``_login_with_wait_file``).
    - ``auto_detect=True``: live-page-poll gate (see
      ``_login_with_auto_detect``). Fully automatic: research-hub drives a
      Chromium browser itself and polls the live ``page.url``; the session
      saves the moment the user lands on the NotebookLM homepage. No ENTER,
      no wait_file touch, no subprocess.
    """
    del headless, timeout_sec, stable_hold_sec
    target = Path(state_file) if state_file is not None else Path(user_data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    if auto_detect:
        # research-hub drives the browser itself and polls the live page
        # URL -- no upstream subprocess (see _login_with_auto_detect).
        rc = _login_with_auto_detect(target, int(wait_timeout))
    else:
        cmd = [sys.executable, "-m", "notebooklm.notebooklm_cli", "login", "--storage", str(target)]
        if wait_file is None:
            rc = subprocess.run(cmd, check=False).returncode
        else:
            rc = _login_with_wait_file(cmd, Path(wait_file), int(wait_timeout), target)
    if rc == 0:
        # G3 P1 #2: tighten newly-created state.json permissions.
        _tighten_state_file_perms(target)
    return rc


def _kill_proc(proc) -> None:
    """terminate -> wait -> kill escalation (POSIX-safe; SIGTERM-ignoring
    children would otherwise leak/zombie)."""
    try:
        proc.terminate()
    except OSError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass


def _login_with_wait_file(
    cmd: list[str],
    wait_file: Path,
    wait_timeout: int,
    state_file: Path,
) -> int:
    """Non-interactive login: replace the upstream `input("press ENTER")`
    gate with a file signal. The user (or an automation wrapper) creates
    *wait_file* once the NotebookLM homepage has loaded; we then write the
    newline that triggers the upstream `context.storage_state(...)` save.
    No terminal / ENTER needed. Fail-closed: if *wait_file* never appears
    within *wait_timeout* seconds, the subprocess is killed and a
    non-zero code is returned (nothing is saved)."""
    # Never inherit a stale signal from a previous run.
    try:
        wait_file.unlink()
    except OSError:
        pass
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    deadline = time.monotonic() + max(1, wait_timeout)
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                # upstream exited on its own (e.g. an error) pre-signal
                return proc.returncode
            if wait_file.exists():
                try:
                    if proc.stdin is not None:
                        proc.stdin.write(b"\n")
                        proc.stdin.flush()
                        proc.stdin.close()
                except OSError:
                    pass
                try:
                    return proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    # The newline was fed and upstream saves storage_state
                    # BEFORE it exits, so the file may already be written
                    # with loose perms even though we report failure.
                    # Tighten defensively (G3 P1 #2 invariant) before
                    # killing the slow-to-exit process.
                    try:
                        _tighten_state_file_perms(state_file)
                    except Exception:  # noqa: BLE001 - best-effort
                        pass
                    _kill_proc(proc)
                    return 1
            time.sleep(1.0)
        # signal never arrived -> fail-closed (nothing saved). Close
        # stdin first so the upstream read sees a clean EOF.
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        _kill_proc(proc)
        return 124
    finally:
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass


# NotebookLM URLs used by the live-poll auto-detect login flow.
_NLM_URL = "https://notebooklm.google.com/"
_NLM_HOST = "notebooklm.google.com"
_GOOGLE_ACCOUNTS_URL = "https://accounts.google.com/"


def _browser_profile_dir() -> Path:
    """Resolve the persistent Chromium profile directory used for NLM login.

    Uses the notebooklm-py SDK's own ``get_browser_profile_dir`` helper so
    research-hub stays in lock-step with whatever profile layout the SDK
    uses; falls back to the documented
    ``~/.notebooklm/profiles/default/browser_profile`` location if the
    helper is unavailable (older SDK).
    """
    try:
        from notebooklm.cli.session import get_browser_profile_dir
        return Path(get_browser_profile_dir())
    except Exception:  # noqa: BLE001 - any SDK breakage falls through
        return (
            Path.home()
            / ".notebooklm"
            / "profiles"
            / "default"
            / "browser_profile"
        )


@contextmanager
def _playwright_event_loop():
    """Restore the default (Proactor) event-loop policy for Playwright on
    Windows for the duration of the ``with`` block.

    notebooklm-py sets ``WindowsSelectorEventLoopPolicy`` globally (it fixes
    an unrelated CLI hang), but Playwright's sync API needs the Proactor
    loop to spawn the browser subprocess. No-op off Windows. Mirrors the
    SDK's own ``_windows_playwright_event_loop`` so we do not depend on a
    private SDK symbol.
    """
    if sys.platform != "win32":
        yield
        return
    original = asyncio.get_event_loop_policy()
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    try:
        yield
    finally:
        asyncio.set_event_loop_policy(original)


def _is_on_notebooklm_homepage(url: str) -> bool:
    """True iff *url* is the live NotebookLM app (not a Google sign-in page).

    While the user is signing in, ``page.url`` sits on ``accounts.google.com``
    (or a NotebookLM ``/login`` interstitial). Once authenticated the page
    settles on the ``notebooklm.google.com`` host. The ``/login`` guard
    rejects the brief interstitial NotebookLM itself serves before bouncing
    to Google.
    """
    return _NLM_HOST in url and "/login" not in url


def _login_with_auto_detect(
    state_file: Path,
    wait_timeout: int,
) -> int:
    """Fully-automatic login: research-hub drives the browser directly.

    Launches a Chromium persistent context (the same stealth flags the
    notebooklm-py SDK uses for its own ``login`` command), navigates to
    the NotebookLM homepage, then polls the LIVE ``page.url``. The moment
    the page settles on the NotebookLM host -- and stays there for a few
    consecutive polls, so a mid-redirect flash never triggers a premature
    save -- the session is captured straight from the live browser context
    via ``storage_state``. No terminal ENTER, no subprocess, no file signal.

    Why not poll the on-disk Cookies SQLite (the pre-fix approach):
    Chromium buffers cookies in memory and flushes them to the profile's
    SQLite store on a lazy timer, so a freshly-signed-in session stays
    invisible on disk for minutes. Polling ``page.url`` reads live browser
    state and has no such race.

    Fail-closed: if the homepage is not reached within *wait_timeout*
    seconds the browser is closed and a non-zero code is returned
    (nothing is saved).
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "  [nlm] Playwright is not installed; cannot run --auto-detect "
            "login.\n        Install it with: pip install 'notebooklm[browser]'",
            file=sys.stderr,
        )
        return 1

    profile_dir = _browser_profile_dir()
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"  [nlm] cannot create browser profile dir: {exc}", file=sys.stderr)
        return 1

    launch_kwargs = {
        "user_data_dir": str(profile_dir),
        "headless": False,
        # Same stealth flags notebooklm-py uses for its own login command.
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--password-store=basic",
        ],
        "ignore_default_args": ["--enable-automation"],
    }
    # The homepage URL must hold for this many consecutive polls before we
    # trust the sign-in -- guards against capturing a transient flash while
    # NotebookLM is still bouncing through a redirect.
    stable_polls_needed = 3
    poll_interval = 1.0

    with _playwright_event_loop():
        playwright = None
        context = None
        try:
            # sync_playwright().start() spawns the Playwright driver
            # process; doing it inside the try means a driver-start
            # failure is caught and surfaced as rc 1, never raised
            # into the CLI.
            playwright = sync_playwright().start()
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(_NLM_URL, timeout=30_000)
            except PlaywrightError:
                # A navigation hiccup is non-fatal: the poll loop below
                # re-reads page.url and recovers once the page settles.
                pass

            print(
                "  [nlm] Browser opened. Sign in to NotebookLM in the window.\n"
                "        The session saves automatically once the homepage "
                "loads -- no ENTER needed.",
            )

            deadline = time.monotonic() + max(1, wait_timeout)
            stable = 0
            while time.monotonic() < deadline:
                try:
                    current_url = page.url
                except PlaywrightError:
                    # Page transiently unavailable (navigating); treat as
                    # "not yet on homepage" and keep polling.
                    current_url = ""
                stable = stable + 1 if _is_on_notebooklm_homepage(current_url) else 0
                if stable >= stable_polls_needed:
                    # Force .google.com cookies for regional users (e.g. a
                    # TW user lands on .google.com.tw); "commit" resolves
                    # once Set-Cookie headers are processed. Mirrors the
                    # SDK's own post-login double-navigation.
                    for url in (_GOOGLE_ACCOUNTS_URL, _NLM_URL):
                        try:
                            page.goto(url, wait_until="commit")
                        except PlaywrightError:
                            pass
                    context.storage_state(path=str(state_file))
                    context.close()
                    return 0
                time.sleep(poll_interval)

            # Homepage never reached within the deadline -> fail-closed.
            context.close()
            return 124
        except Exception as exc:  # noqa: BLE001 - report and fail, never raise
            print(
                f"  [nlm] auto-detect login failed: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            if context is not None:
                try:
                    context.close()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass
            return 1
        finally:
            # Always stop the driver process, whatever path we exit on.
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass


def check_session_health(state_file: Path) -> dict[str, Any]:
    """Return ``ok``, ``reason``, and ``expires_at`` for a storage state."""
    state_file = Path(state_file)
    if not state_file.exists():
        return {"ok": False, "reason": "state.json missing", "expires_at": None}
    try:
        ok = asyncio.run(_probe_state_file(state_file))
        return {"ok": ok, "reason": "ok" if ok else "auth invalid", "expires_at": None}
    except AuthError as exc:
        return {"ok": False, "reason": f"auth error: {exc}", "expires_at": None}
    except Exception as exc:
        return {"ok": False, "reason": f"unexpected error: {exc}", "expires_at": None}


def require_session_health(state_file: Path) -> None:
    """Raise a structured auth-refresh error when NotebookLM auth is stale."""

    health = check_session_health(state_file)
    if health.get("ok"):
        return
    reason = str(health.get("reason") or "auth invalid")
    from research_hub._invocation import recommended_cli_invocation

    command = f"{recommended_cli_invocation()} notebooklm login"
    raise RequiresAuthRefresh(
        service="NotebookLM",
        fix_command=command,
        message=f"NotebookLM session check failed: {reason}. Run: {command}",
    )


async def _probe_state_file(state_file: Path) -> bool:
    client = NotebookLMClient.from_storage(path=str(state_file))
    if inspect.isawaitable(client):
        client = await client
    async with client:
        await client.notebooks.list()
        return True


@dataclass
class ImportResult:
    ok: bool
    files_copied: int = 0
    bytes_copied: int = 0
    error: str = ""


def import_session(
    source_session_dir: Path,
    source_state_file: Path,
    dest_session_dir: Path | None = None,
    dest_state_file: Path | None = None,
    *,
    overwrite: bool = False,
) -> ImportResult:
    """Import a saved NotebookLM session from another vault.

    Supports the legacy four-path call shape used by the CLI. When only two
    paths are supplied, it copies a single storage state file.
    """
    source_session_dir = Path(source_session_dir)
    source_state_file = Path(source_state_file)
    if dest_session_dir is None and dest_state_file is None:
        raise TypeError("dest_state_file is required")
    if dest_state_file is None:
        dest_state_file = Path(source_state_file)
        source_state_file = source_session_dir
        dest_session_dir = None
    else:
        dest_state_file = Path(dest_state_file)
        dest_session_dir = Path(dest_session_dir) if dest_session_dir is not None else None

    if not source_state_file.exists():
        return ImportResult(ok=False, error=f"source state file not found: {source_state_file}")

    files_copied = 0
    bytes_copied = 0
    if dest_session_dir is not None and source_session_dir.exists():
        if dest_session_dir.exists():
            if not overwrite and any(dest_session_dir.iterdir()):
                return ImportResult(
                    ok=False,
                    error=f"dest session at {dest_session_dir} already exists; pass overwrite=True",
                )
            shutil.rmtree(dest_session_dir)
        dest_session_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_session_dir, dest_session_dir)
        copied_files = [path for path in dest_session_dir.rglob("*") if path.is_file()]
        files_copied += len(copied_files)
        bytes_copied += sum(path.stat().st_size for path in copied_files)

    dest_state_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_state_file, dest_state_file)
    files_copied += 1
    bytes_copied += dest_state_file.stat().st_size

    return ImportResult(ok=True, files_copied=files_copied, bytes_copied=bytes_copied)


def login_from_browser(
    state_file: Path,
    *,
    browser: str | None = None,
) -> int:
    """Non-interactive login by importing cookies from an already-logged-in browser.

    Delegates to the upstream ``notebooklm.notebooklm_cli login --browser-cookies``
    path (which uses rookiepy to extract Google cookies without launching Playwright).
    Requires ``rookiepy`` to be installed: ``pip install 'research-hub[browser-auth]'``.

    Precedence (in CLI dispatch):
        --import-from > --from-browser > interactive default

    Args:
        state_file: Path where the storage state JSON will be written.
        browser: Specific browser to read cookies from (e.g. ``"chrome"``,
            ``"firefox"``, ``"edge"``). Pass ``None`` for auto-detection
            (rookiepy tries all installed browsers). Do NOT pass ``"auto"`` —
            that is the CLI-layer sentinel; callers should normalise it to None.

    Returns:
        The upstream subprocess return code (0 = success, non-zero = failure).
        On failure the caller should print an actionable hint referencing
        ``pip install 'research-hub[browser-auth]'``.
    """
    state_file = Path(state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m", "notebooklm.notebooklm_cli",
        "login",
        "--storage", str(state_file),
        "--browser-cookies",
    ]
    # Append the specific browser name only when one is requested; bare
    # --browser-cookies means "auto-detect" to the upstream CLI.
    if browser is not None:
        cmd.append(browser)
    rc = subprocess.run(cmd, check=False).returncode
    if rc == 0:
        _tighten_state_file_perms(state_file)
    return rc


def is_session_logged_in(state_file: Path) -> bool:
    """Compatibility helper around ``check_session_health``."""
    return bool(check_session_health(state_file).get("ok"))
