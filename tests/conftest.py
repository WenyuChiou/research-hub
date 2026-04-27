"""Shared pytest fixtures for the Research Hub test suite."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "stress: stress/load tests (opt-in via pytest tests/stress/)",
    )


@pytest.fixture(autouse=True)
def _block_real_webbrowser_open(monkeypatch):
    """v0.68.5: globally stub `webbrowser.open` for every test.

    Several init_wizard / setup_command interactive tests call into code
    paths that do `webbrowser.open("https://www.zotero.org/settings/keys")`
    or `webbrowser.open("http://...dashboard...")`. Without a global stub,
    a full `pytest` run would launch a real browser tab on every such test
    — observed in CI logs and on the maintainer's machine. The previous
    per-file stub only covered one test.

    Tests that need to ASSERT a webbrowser.open was called can re-patch it
    locally with their own monkeypatch.setattr — the per-test patch wins
    over this autouse one.
    """
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *args, **kwargs: True)


@pytest.fixture
def reset_research_hub_modules():
    """Returns a callable that resets named research_hub.* submodules.

    Usage in a test file's autouse fixture::

        @pytest.fixture(autouse=True)
        def _reset_cached_modules(reset_research_hub_modules):
            reset_research_hub_modules(
                "research_hub.crystal",
                "research_hub.workflows",
            )
    """
    return _reset_research_hub_modules


def _reset_research_hub_modules(*module_names: str) -> None:
    """Force re-import of the named research_hub.* submodules on next access.

    Use this from per-file autouse fixtures when the test patches functions
    via ``mock.patch("research_hub.<sub>.<func>", ...)`` and the production
    code does late imports of those functions.

    GOTCHA (regression v0.37.2, 16-build CI red streak): popping
    ``sys.modules["research_hub.crystal"]`` is NOT enough. The parent package
    ``research_hub`` still has the OLD module bound as an attribute. When
    ``mock.patch`` enters, its ``_importer`` walks
    ``getattr(research_hub_pkg, "crystal")`` first — finds the OLD module
    and patches the function on it. But the production-code's late
    ``from research_hub.<sub> import <func>`` finds ``sys.modules`` empty,
    re-imports from disk → DIFFERENT module object → unpatched real
    function. Result: mock silently bypassed.

    Local Python 3.14 doesn't reproduce this; Python 3.10/3.11/3.12 does.
    Always clear BOTH ``sys.modules[name]`` AND ``delattr(parent, child)``.
    This helper does both.
    """
    import sys

    for name in module_names:
        sys.modules.pop(name, None)
        parent_name, _, child = name.rpartition(".")
        if not parent_name:
            continue
        parent = sys.modules.get(parent_name)
        if parent is not None and hasattr(parent, child):
            try:
                delattr(parent, child)
            except AttributeError:
                pass


@pytest.fixture
def tmp_path() -> Path:
    root = Path.cwd() / ".pytest-work"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def mock_require_config(monkeypatch):
    monkeypatch.setattr("research_hub.cli.get_config", lambda: None)


@pytest.fixture(autouse=True)
def _allow_external_vault_root_in_tests(monkeypatch):
    """v0.40.1: Windows CI workspace is on D:\\ but HOME on C:\\, tripping
    the v0.30 'vault must be under HOME' guard for ANY test using a tmp_path
    based RESEARCH_HUB_ROOT. This affects test_config.py, test_v030_*,
    test_v040_*, etc. — broader than the cli-routing fixture below.

    Set the bypass for every test unconditionally; safe because tests run in
    sandboxed tmp_paths, not against the user's real $HOME.
    """
    monkeypatch.setenv("RESEARCH_HUB_ALLOW_EXTERNAL_ROOT", "1")


@pytest.fixture(autouse=True)
def _auto_mock_require_config(request, monkeypatch):
    """Auto-mock config loading for tests that call cli.main([...]) directly.

    These tests exercise argparse routing and must not depend on whether the
    test environment has a research-hub config installed (CI doesn't).

    Patterns covered:
    - tests/test_cli_*.py (added v0.30-A10 for cli routing tests)
    - tests/test_v0NN_*.py for v030+ feature tests that include CLI dispatch
      (e.g. test_v032_screenshot.py asserts on `main(["dashboard", ...])` and
      hits require_config() in the dispatcher)
    """
    fspath = str(request.node.fspath).replace("\\", "/")
    # v0.40.1: extended to all test_v0NN_*.py files (was: only up to v034).
    # Use a regex-style match instead of enumerating each version.
    import re as _re
    needs_mock = (
        "/tests/test_cli_" in fspath
        or bool(_re.search(r"/tests/test_v0\d+_", fspath))
    )
    if not needs_mock:
        return
    # Patch get_config only — the cli.main dispatcher detects whether it's
    # been swapped (cli.get_config is require_config.__globals__["get_config"])
    # and skips require_config(). Replacing require_config itself would break
    # that detection because lambda has different __globals__.
    monkeypatch.setattr("research_hub.cli.get_config", lambda: None, raising=False)
    # (RESEARCH_HUB_ALLOW_EXTERNAL_ROOT now set globally by
    # _allow_external_vault_root_in_tests above — applies to all tests.)
