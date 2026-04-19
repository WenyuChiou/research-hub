"""Back-compat shim: CDP launcher removed in v0.42."""

from __future__ import annotations


def find_chrome_binary() -> None:
    """DEPRECATED: v0.42 uses patchright + channel='chrome'. No-op."""
    return None


def launch_chrome_with_cdp(*args, **kwargs) -> None:
    raise NotImplementedError(
        "launch_chrome_with_cdp() was removed in v0.42. Use "
        "research_hub.notebooklm.browser.launch_nlm_context() "
        "which combines patchright + persistent context + cookie injection."
    )


def stop_cdp(*args, **kwargs) -> None:
    return None
