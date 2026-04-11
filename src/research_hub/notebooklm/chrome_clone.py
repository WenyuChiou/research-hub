"""Clone the user's real Chrome profile into an isolated Playwright session.

Motivation: Google actively blocks Playwright-launched browsers during
the sign-in flow ("This browser or app may have security concerns").
A Playwright-isolated Chrome still triggers the block because
``navigator.webdriver`` and related fingerprints are set.

Workaround: copy the user's existing Chrome profile (which already has
valid Google auth cookies and is trusted by Google) into our session
directory, then launch Playwright with that cloned profile. Google sees
the same auth cookies it issued to the real Chrome session and lets us
in without any new sign-in.

The clone is one-time. Sensitive browser caches (``Cache``,
``Code Cache``, ``GPUCache``, ``Media Cache``, ``ShaderCache``,
``Service Worker``) are excluded to keep the copy small and avoid
locked files.

Chrome MUST be closed before cloning — Windows locks the profile
directory while Chrome is running, and copying a half-flushed SQLite
Cookies file is a good way to corrupt the clone.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


_IGNORE_DIR_NAMES = {
    "Cache",
    "Code Cache",
    "GPUCache",
    "Media Cache",
    "ShaderCache",
    "Service Worker",
    "DawnCache",
    "GrShaderCache",
    "optimization_guide_model_store",
    "Crashpad",
    "Safe Browsing",
    "segmentation_platform",
}


def default_chrome_user_data_dir() -> Path | None:
    """Best-guess location of the user's Chrome User Data directory."""
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidate = Path(local_app) / "Google" / "Chrome" / "User Data"
            if candidate.exists():
                return candidate
    elif sys.platform == "darwin":
        candidate = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
        if candidate.exists():
            return candidate
    else:  # linux
        candidate = Path.home() / ".config" / "google-chrome"
        if candidate.exists():
            return candidate
    return None


def _is_chrome_running(chrome_user_data_dir: Path) -> bool:
    """Return True if a Chrome process currently holds the profile lock."""
    # Windows uses a lockfile named "lockfile" in the user data root.
    # On macOS/Linux it may be "SingletonLock" in the user data root.
    for name in ("lockfile", "SingletonLock", "SingletonCookie"):
        lock = chrome_user_data_dir / name
        if lock.exists():
            return True
    return False


def clone_chrome_profile(
    chrome_user_data_dir: Path,
    session_dir: Path,
    *,
    profile_name: str = "Default",
    overwrite: bool = True,
) -> Path:
    """Copy a Chrome profile into ``session_dir`` as a Playwright user_data_dir.

    The returned path is what to pass as ``user_data_dir`` to
    ``playwright.chromium.launch_persistent_context``. It is the
    PARENT of the profile subdirectory (Chrome-style layout) so
    ``channel="chrome"`` can find its ``Default`` subfolder.

    Raises:
        FileNotFoundError: if the Chrome profile path does not exist
        RuntimeError: if Chrome appears to be running (lock detected)
    """
    if not chrome_user_data_dir.exists():
        raise FileNotFoundError(
            f"Chrome user data dir not found: {chrome_user_data_dir}. "
            "Set --chrome-profile-path or install Chrome."
        )

    src_profile = chrome_user_data_dir / profile_name
    if not src_profile.exists():
        raise FileNotFoundError(
            f"Chrome profile '{profile_name}' not found at {src_profile}. "
            f"Available profiles: {_list_profiles(chrome_user_data_dir)}"
        )

    if _is_chrome_running(chrome_user_data_dir):
        raise RuntimeError(
            "Chrome appears to be running (profile lock detected). "
            "Close ALL Chrome windows before cloning the profile. "
            f"Profile: {chrome_user_data_dir}"
        )

    dst_profile = session_dir / profile_name
    if dst_profile.exists() and overwrite:
        shutil.rmtree(dst_profile, ignore_errors=True)

    session_dir.mkdir(parents=True, exist_ok=True)

    # Also copy "Local State" (top-level file that contains profile metadata)
    local_state = chrome_user_data_dir / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, session_dir / "Local State")

    shutil.copytree(
        src_profile,
        dst_profile,
        ignore=_ignore_unwanted,
        dirs_exist_ok=True,
    )

    return session_dir


def _list_profiles(chrome_user_data_dir: Path) -> list[str]:
    names = []
    for entry in chrome_user_data_dir.iterdir():
        if entry.is_dir() and (entry.name == "Default" or entry.name.startswith("Profile ")):
            names.append(entry.name)
    return sorted(names)


def _ignore_unwanted(src: str, names: list[str]) -> list[str]:
    return [n for n in names if n in _IGNORE_DIR_NAMES]
