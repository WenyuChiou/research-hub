"""Screenshot the dashboard via headless Playwright."""

from __future__ import annotations

import logging
from pathlib import Path

from research_hub.dashboard import generate_dashboard

logger = logging.getLogger(__name__)


# The live dashboard uses radio-driven tabs. "crystal" is kept as a legacy alias
# for the overview tab because crystal summaries render inside overview.
TAB_TARGETS: dict[str, str] = {
    "overview": "overview",
    "library": "library",
    "briefings": "briefings",
    "writing": "writing",
    "diagnostics": "diagnostics",
    "manage": "manage",
    "crystal": "overview",
}

VALID_TABS = set(TAB_TARGETS) | {"all"}


class PlaywrightNotInstalled(RuntimeError):
    """Playwright is missing; user must install the extra and Chromium."""


def screenshot_dashboard(
    cfg,
    *,
    tab: str = "overview",
    out: Path,
    scale: float = 2.0,
    viewport_width: int = 1440,
    viewport_height: int = 900,
    full_page: bool = False,
) -> Path:
    """Render dashboard.html headless and capture a selected tab as PNG."""
    if tab not in VALID_TABS:
        raise ValueError(f"tab={tab!r} invalid. Must be one of: {sorted(VALID_TABS)}")
    if scale <= 0:
        raise ValueError("scale must be > 0")
    if viewport_width <= 0 or viewport_height <= 0:
        raise ValueError("viewport dimensions must be > 0")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PlaywrightNotInstalled(
            "Screenshot requires playwright. Install:\n"
            "  pip install 'research-hub-pipeline[playwright]'\n"
            "  playwright install chromium"
        ) from exc

    dashboard_html = generate_dashboard(open_browser=False)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=scale,
            )
            page = context.new_page()
            page.goto(Path(dashboard_html).resolve().as_uri(), wait_until="domcontentloaded")

            if tab != "all":
                target = TAB_TARGETS[tab]
                selector = f"label[for='dash-tab-{target}']"
                try:
                    page.click(selector, timeout=2000)
                except Exception:
                    logger.warning("could not click tab selector %s; continuing", selector)
                page.wait_for_timeout(300)

            page.screenshot(path=str(out), full_page=full_page)
        finally:
            browser.close()

    logger.info(
        "wrote %s (tab=%s, scale=%s, %dx%d)",
        out,
        tab,
        scale,
        viewport_width,
        viewport_height,
    )
    return out


def screenshot_all(
    cfg,
    *,
    out_dir: Path,
    scale: float = 2.0,
    viewport_width: int = 1440,
    viewport_height: int = 900,
    full_page: bool = False,
    name_prefix: str = "dashboard-",
) -> list[Path]:
    """Capture one PNG per dashboard tab into ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for tab in ("overview", "library", "briefings", "writing", "diagnostics", "manage"):
        target = out_dir / f"{name_prefix}{tab}.png"
        paths.append(
            screenshot_dashboard(
                cfg,
                tab=tab,
                out=target,
                scale=scale,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                full_page=full_page,
            )
        )
    return paths


__all__ = [
    "PlaywrightNotInstalled",
    "TAB_TARGETS",
    "VALID_TABS",
    "screenshot_all",
    "screenshot_dashboard",
]
