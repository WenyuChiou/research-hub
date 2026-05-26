"""EZproxy support for institutional PDF access.

Opt-in. Users set ``cfg.ezproxy_url_template`` (a Python format template
like ``https://login.ezproxy.youruniversity.edu/login?qurl={encoded_url}``)
and run ``research-hub ezproxy login`` once to capture cookies. After that,
``paper attach-pdfs`` can wrap publisher URLs through the proxy, falling back
to the original URL on any proxy failure.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


@dataclass
class EZproxyConfig:
    """Resolved EZproxy settings for a HubConfig-like object."""

    url_template: str
    cookies_path: Path

    @property
    def enabled(self) -> bool:
        return bool(self.url_template) and self.cookies_path.exists()


def resolve_config(cfg: Any) -> EZproxyConfig:
    """Read EZproxy settings from a HubConfig-like object."""

    try:
        template = (getattr(cfg, "ezproxy_url_template", "") or "").strip()
    except Exception:
        template = ""
    try:
        raw_path = getattr(cfg, "ezproxy_cookies_path", "") or ""
    except Exception:
        raw_path = ""
    try:
        cookies_path = Path(raw_path).expanduser() if raw_path else None
    except Exception:
        cookies_path = None
    if cookies_path is None:
        try:
            base = Path(getattr(cfg, "research_hub_dir", ".")).expanduser()
        except Exception:
            base = Path(".")
        cookies_path = base / "ezproxy_cookies.json"
    return EZproxyConfig(url_template=template, cookies_path=cookies_path)


def wrap_url(original_url: str, template: str) -> str:
    """Wrap an absolute publisher URL through an EZproxy template."""

    try:
        if not template or "{encoded_url}" not in template:
            return original_url
        return template.format(encoded_url=quote(original_url, safe=""))
    except Exception:
        return original_url


def load_cookies(cookies_path: Path) -> dict[str, str]:
    """Load Playwright storage-state cookies as a ``{name: value}`` dict."""

    try:
        if not cookies_path.exists():
            return {}
        import json

        data = json.loads(cookies_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cookies = data.get("cookies", []) if isinstance(data, dict) else []
    out: dict[str, str] = {}
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if isinstance(name, str) and isinstance(value, str):
            out[name] = value
    return out


def login(
    cookies_path: Path,
    *,
    url_template: str = "",
    sentinel_url: str = "https://ieeexplore.ieee.org/",
    profile_dir: Path | None = None,
) -> int:
    """Open a persistent browser context and save EZproxy cookies on close."""

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "  [ezproxy] Playwright is not installed; cannot open browser login.\n"
            "            Install it with: pip install 'research-hub-pipeline[playwright]'",
            file=sys.stderr,
        )
        return 1

    from research_hub.notebooklm.auth import _playwright_event_loop
    from research_hub.notebooklm.auth import _tighten_state_file_perms

    cookies_path = Path(cookies_path).expanduser()
    profile = Path(profile_dir).expanduser() if profile_dir is not None else cookies_path.parent / "ezproxy_profile"
    try:
        cookies_path.parent.mkdir(parents=True, exist_ok=True)
        profile.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"  [ezproxy] cannot create browser profile dir: {exc}", file=sys.stderr)
        return 1

    homepage = wrap_url(sentinel_url, url_template) if url_template else sentinel_url
    launch_kwargs = {
        "user_data_dir": str(profile),
        "headless": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--password-store=basic",
        ],
        "ignore_default_args": ["--enable-automation"],
    }

    with _playwright_event_loop():
        playwright = None
        context = None
        try:
            playwright = sync_playwright().start()
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(homepage, timeout=30_000)
            except PlaywrightError:
                pass
            print(
                "  [ezproxy] Browser opened. Complete institutional SSO, verify access,\n"
                "            then close the browser window to save cookies.",
            )
            while True:
                try:
                    if not context.pages:
                        break
                except PlaywrightError:
                    break
                time.sleep(1.0)
            context.storage_state(path=str(cookies_path))
            _tighten_state_file_perms(cookies_path)
            print(f"  [ezproxy] Saved cookies to {cookies_path}")
            return 0
        except Exception as exc:  # noqa: BLE001 - login must fail closed
            print(f"  [ezproxy] login failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        finally:
            try:
                if context is not None:
                    context.close()
            except Exception:
                pass
            try:
                if playwright is not None:
                    playwright.stop()
            except Exception:
                pass
