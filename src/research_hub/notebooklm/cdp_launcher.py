"""Launch a real Chrome instance with CDP enabled, for Playwright to attach to.

Google aggressively blocks browsers launched via Playwright's standard
``launch_persistent_context`` path because Playwright sets
``navigator.webdriver = true`` and other automation fingerprints that
Google's sign-in flow detects. Even ``channel='chrome'`` with a cloned
profile fails.

The workaround is to launch Chrome the NORMAL way (as a subprocess
with the ``--remote-debugging-port`` flag), then have Playwright
``connect_over_cdp`` to that running Chrome. Because Chrome is launched
as a normal user app and Playwright only SPEAKS TO IT via the
DevTools Protocol, Chrome itself never marks its context as automated.
Google sees a perfectly ordinary Chrome and lets the sign-in flow
through.

Chrome for Testing builds and recent Chrome stables all support CDP
via the ``--remote-debugging-port`` flag. No extra install required
beyond having Chrome on the system.

Windows Chrome paths commonly checked:

    C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe
    C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe
    %LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CDPEndpoint:
    cdp_url: str
    user_data_dir: Path
    process: subprocess.Popen | None
    chrome_binary: str


def find_chrome_binary() -> str | None:
    """Return the first Chrome executable path that exists on this OS."""
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
    elif sys.platform == "darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    else:
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/snap/bin/chromium"),
        ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _find_free_port(preferred: int = 9222) -> int:
    """Return `preferred` if free, otherwise an OS-picked port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_cdp_ready(port: int, timeout_sec: int = 15) -> str:
    """Poll ``http://127.0.0.1:<port>/json/version`` until it responds.

    Returns the ``webSocketDebuggerUrl`` field, which Playwright needs
    for ``connect_over_cdp``.
    """
    deadline = time.time() + timeout_sec
    url = f"http://127.0.0.1:{port}/json/version"
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                import json as _json

                data = _json.loads(response.read().decode("utf-8"))
                ws = data.get("webSocketDebuggerUrl")
                if ws:
                    return ws
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_err = exc
        time.sleep(0.3)
    raise RuntimeError(
        f"Chrome CDP endpoint did not become ready on port {port} within {timeout_sec}s "
        f"(last error: {last_err})"
    )


def launch_chrome_with_cdp(
    user_data_dir: Path,
    *,
    chrome_binary: str | None = None,
    headless: bool = False,
    preferred_port: int = 9222,
    startup_url: str | None = None,
    extra_args: list[str] | None = None,
) -> CDPEndpoint:
    """Launch Chrome as a subprocess with remote debugging enabled.

    Returns a ``CDPEndpoint`` with ``cdp_url`` suitable for
    ``playwright.chromium.connect_over_cdp(cdp_url)``. The returned
    ``process`` is a live subprocess — callers should kill it when
    finished.

    The ``user_data_dir`` is isolated from the user's default Chrome
    profile, so running research-hub does NOT require closing the
    user's everyday Chrome. Google auth cookies persist across runs
    within this isolated profile.
    """
    binary = chrome_binary or find_chrome_binary()
    if binary is None:
        raise FileNotFoundError(
            "Could not find Chrome binary. Install Chrome or pass chrome_binary="
        )

    user_data_dir.mkdir(parents=True, exist_ok=True)
    port = _find_free_port(preferred_port)

    args: list[str] = [
        binary,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=GlobalMediaControls",
        "--disable-sync",
    ]
    if headless:
        args.append("--headless=new")
    if extra_args:
        args.extend(extra_args)
    if startup_url:
        args.append(startup_url)

    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        ws = _wait_for_cdp_ready(port, timeout_sec=20)
    except Exception:
        process.terminate()
        raise

    return CDPEndpoint(
        cdp_url=ws,
        user_data_dir=user_data_dir,
        process=process,
        chrome_binary=binary,
    )


def stop_cdp(endpoint: CDPEndpoint) -> None:
    """Terminate the Chrome subprocess launched by ``launch_chrome_with_cdp``."""
    if endpoint.process is None:
        return
    try:
        endpoint.process.terminate()
        try:
            endpoint.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            endpoint.process.kill()
    except Exception:
        pass
