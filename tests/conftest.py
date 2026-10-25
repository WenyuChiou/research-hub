"""Shared pytest fixtures for the Research Hub test suite."""

from __future__ import annotations

import os
import shutil
import socket
import uuid
from pathlib import Path

import pytest


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "stress: stress/load tests (opt-in via pytest tests/stress/)",
    )
    config.addinivalue_line(
        "markers",
        "real_zotero: opt-in test that may reach the real Zotero API (network allowed)",
    )
    config.addinivalue_line(
        "markers",
        "real_authenticity: opt-in test that drives the real authenticity-gate network",
    )


# Markers whose tests are allowed to open EXTERNAL sockets (they opt into live
# external services). Every other test is fenced to loopback + unix only.
_LIVE_NETWORK_MARKERS = ("network", "real_zotero", "real_authenticity")


@pytest.fixture(autouse=True)
def _network_fence(request):
    """v1.0.9 (P0-5): structural network fence — convert the offline-stub
    denylist into a fence.

    By default a test may only reach LOOPBACK (127.0.0.1 / ::1 / localhost — the
    local HTTPServer / REST / dashboard tests bind there) and unix sockets; any
    connect to an EXTERNAL host fails loudly with a pytest-socket
    SocketConnectBlockedError. This means the moment a NEW leak to a real API
    (arXiv, Crossref, Unpaywall, zotero.org, notebooklm) is introduced — or an
    existing stub regresses — the test fails immediately instead of silently
    hitting the wire and flaking on a CI network blip (the failure class behind
    several past green-by-luck CI runs). Tests that genuinely need a live
    external service opt in via one of `_LIVE_NETWORK_MARKERS`.
    """
    import pytest_socket

    if any(request.node.get_closest_marker(m) for m in _LIVE_NETWORK_MARKERS):
        pytest_socket.enable_socket()
    else:
        pytest_socket.socket_allow_hosts(
            ["127.0.0.1", "localhost", "::1"], allow_unix_socket=True,
            # Known loopback names need no DNS, including under --disable-socket.
            resolution_cache={"localhost": {"127.0.0.1", "::1"}},
        )
    try:
        yield
    finally:
        # Fully restore the stdlib socket between tests. NOTE: enable_socket()
        # alone does NOT undo socket_allow_hosts — it reassigns socket.socket but
        # leaves the guarded .connect closure in place; only _remove_restrictions()
        # also restores socket.socket.connect / getaddrinfo. Without this a future
        # @pytest.mark.network test added under tests/ (not tests/evals/) that runs
        # after a fenced test would be wrongly blocked. (pytest-socket >= 0.7.)
        pytest_socket._remove_restrictions()


@pytest.fixture(autouse=True)
def _stub_socket_getfqdn(monkeypatch):
    """v1.0+: globally stub `socket.getfqdn` to return "localhost".

    Python stdlib issue14914: `http.server.HTTPServer.server_bind()` calls
    `socket.getfqdn(host)` to populate `self.server_name`. On macOS GitHub
    Actions runners (and Bonjour/mDNS-equipped environments generally) the
    reverse-DNS lookup of "127.0.0.1" can hang 30+ seconds while mDNS
    queries time out — long enough for `pytest-timeout` to fire and
    fail the test at setup.

    Confirmed master-red across 3 consecutive CI runs (26185448887,
    26191738564, 26192402510) on `test_artifact_delete_endpoint.py`. The
    same construction pattern (`ThreadingHTTPServer(("127.0.0.1", 0), ...)`)
    is used by at least 7 test files:

      tests/test_artifact_delete_endpoint.py
      tests/test_dashboard_executor_e2e.py
      tests/test_dashboard_live_server.py
      tests/test_v030_security.py
      tests/test_v052_rest_api.py
      tests/test_v062_dashboard_stdout_drawer.py
      tests/test_v064_port_in_use.py

    All benefit from this autouse stub. Production code path is
    unchanged — `monkeypatch` reverts on test teardown so non-test
    callers of `socket.getfqdn` see the real implementation.

    See: https://bugs.python.org/issue14914
    """
    monkeypatch.setattr(socket, "getfqdn", lambda *_args, **_kwargs: "localhost")


@pytest.fixture(autouse=True)
def _reset_pdf_hint_flag():
    """v0.77: pdf_attach._HINT_SHOWN is module-level state that survives
    across tests in the same process. Reset before every test so hint-text
    assertions are not order-dependent."""
    try:
        from research_hub.zotero.pdf_attach import _reset_hint_state
        _reset_hint_state()
    except Exception:
        pass
    yield


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


@pytest.fixture(autouse=True)
def _block_real_patchright(monkeypatch):
    """v1.0: globally stub sync_playwright for every test.

    patchright's sync_playwright() blocks inside Windows C-level
    WaitForSingleObject (asyncio IOCP poller) when Playwright tries to
    connect to the browser process.  That C-level call is not interruptible
    by pytest-timeout's thread method, so a single test that reaches the
    real sync_playwright hangs the entire test runner.

    Any test that needs to *assert* specific patchright behavior (e.g.
    test_doctor_chrome_not_found) applies its own monkeypatch.setattr for
    sync_playwright after this fixture runs — the per-test patch wins.
    run_doctor()'s own except-clause converts RuntimeError to an INFO
    result, which every existing assertion accepts (OK or INFO).
    """
    try:
        import patchright.sync_api as _patchright_api
    except ImportError:
        return

    class _FakeChromium:
        def launch(self, *args, **kwargs):
            raise RuntimeError("patchright browser blocked in test suite")

    class _FakePlaywright:
        def __init__(self):
            self.chromium = _FakeChromium()  # instance-level; safe for per-test mutation

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(_patchright_api, "sync_playwright", lambda: _FakePlaywright())


@pytest.fixture(autouse=True)
def _block_real_authenticity_head(monkeypatch):
    """Default authenticity HEAD checks to success in legacy tests.

    The dedicated authenticity tests override this fixture per-test to assert
    404, offline, and cache behavior without letting old ingest tests perform
    real network calls for fixture DOIs like 10.1000/example.
    """
    from types import SimpleNamespace

    monkeypatch.setattr(
        "requests.head",
        lambda *args, **kwargs: SimpleNamespace(status_code=200),
    )


# v0.71.0: test files in this set explicitly verify Zotero write paths
# (using FakeZotero, mocked get_client, or run_backfill). The autouse
# below leaves their env alone so they can exercise the real code path
# under their own mocks. Other tests get RESEARCH_HUB_NO_ZOTERO=1 set by
# the autouse to prevent accidental writes to the maintainer's library
# — observed in this PR creating 3 spurious `test-topic` collections.
_ZOTERO_WRITE_TEST_MODULES = frozenset({
    "test_v068_4_no_duplicate_zotero_collections",
    "test_v061_zotero_backfill",
    "test_v062_cluster_delete_cascade",
    "test_v062_note_enrich",
    "test_v041_pipeline_ingest_fixes",
    "test_pipeline_e2e",
    "test_pipeline",  # exercises run_pipeline against FakeZotero
    "test_clusters_rename_zotero",
    "test_cluster_rename_triple_sync",
    "test_vault_sync",
    "test_v030_security",  # asserts pipeline routes to cluster collection
    "test_v073_parallel_search",
    "test_v073_batched_zotero",
    "test_v073_parallel_summarize",
    "test_v074_drift_prevention",
    "test_v074_batch_collection",
    "test_v075_name_drift",
    "test_v075_collision_prevention",
    "test_v075_zotero_gc",
    "test_v075_test_isolation",
    "test_v075_enrich_existing",
    "test_v075_pdf_attach",
    "test_v076_pdf_chain",
    "test_v076_full_auto",
    "test_v076_pdf_coverage_check",
    "test_v078_html_entity",
    "test_v079_metadata_normalization",
    "test_v079_anonymous_author_warning",
    "test_v079_zotero_trash_protection",
    "test_v080_pdf_imported_file",
    "test_v080_abstract_recovery_in_ingest",
    "test_v080_resummarize",
    "test_v080_summary_thin_check",
    "test_v081_summary_block_and_orphan_skip",
})


@pytest.fixture(autouse=True)
def _block_real_zotero_writes(request, monkeypatch):
    """v0.71.0: stub `_ensure_zotero_collection` to a no-op for tests NOT
    in the Zotero-write allowlist above.

    Why not just set RESEARCH_HUB_NO_ZOTERO=1? That env var has production
    side effects: dashboard rendering inspects it (see
    dashboard/context.py:136 and dashboard/data.py:56) and hides the
    diagnostics tab when set, which broke ~10 dashboard tests. Patching
    only the single helper that actually leaks (`_ensure_zotero_collection`)
    is surgical: it can't accidentally turn on production code paths for
    NO_ZOTERO mode.

    Without this autouse, any test that calls `auto_pipeline` with a mock
    cluster missing `zotero_collection_key` will hit the guard and create
    a REAL Zotero collection on the maintainer's library — observed in
    this PR creating 3 spurious `test-topic` collections.

    Allowlist `_ZOTERO_WRITE_TEST_MODULES` skips this stub for files that
    DELIBERATELY exercise `_ensure_zotero_collection` under their own
    FakeZotero / MagicMock isolation.
    """
    module_stem = request.module.__name__.rsplit(".", 1)[-1]
    if module_stem in _ZOTERO_WRITE_TEST_MODULES:
        return  # Test owns its own Zotero isolation.

    def _noop_ensure_zotero_collection(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "research_hub.auto._ensure_zotero_collection",
        _noop_ensure_zotero_collection,
    )


@pytest.fixture(autouse=True)
def _block_real_zotero(monkeypatch, request):
    """Refuse real Zotero client construction inside tests unless opted in."""
    if "ALLOW_REAL_ZOTERO" in os.environ:
        return
    if request.node.get_closest_marker("real_zotero"):
        return

    def _refuse(*_args, **_kwargs):
        raise RuntimeError(
            "Tests must not touch the real Zotero account. "
            "Mock zotero.client.get_client / ZoteroDualClient. "
            "Set ALLOW_REAL_ZOTERO=1 env var or @pytest.mark.real_zotero to bypass."
        )

    monkeypatch.setattr("research_hub.zotero.client.get_client", _refuse)
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient.__init__", _refuse)
    # v0.77 hotfix: pipeline.py / auto.py / doctor.py / clusters.py /
    # zotero/{enrich,gc,pdf_attach}.py all `from research_hub.zotero.client
    # import get_client` at module level — that binds get_client into the
    # importing module's namespace, so monkeypatching the source module is
    # not enough. Patch every known import site so the guard actually fires.
    for module_path in (
        "research_hub.pipeline.get_client",
        "research_hub.auto.get_client",
        "research_hub.doctor.get_client",
        "research_hub.clusters.get_client",
    ):
        try:
            monkeypatch.setattr(module_path, _refuse)
        except AttributeError:
            # Module hasn't imported get_client at the top level (or not yet
            # loaded); the source-module patch above is the safety net.
            pass


# A test module referencing any of these "drives the authenticity gate itself"
# (it mocks the resolve / Crossref layer and asserts specific verdicts), so it
# is excluded from the offline stub below. ``research_hub.authenticity`` is
# deliberately broad: it also catches modules that merely import a constant/tool
# from that module (e.g. ``QUARANTINE_DIR``). Over-excluding such a test is
# harmless -- it just doesn't get the offline stub (its ``run_pipeline`` is
# mocked, or the existing ``_block_real_authenticity_head`` fixture covers its
# network) -- whereas under-excluding a real gate test would break it.
# Conservative on purpose.
_AUTHENTICITY_GATE_INTERNALS = (
    "_resolve_head_with_retry",
    "_resolve_identifier",
    "research_hub.authenticity",
    "CrossrefVerifyCache",
    "DoiResolveCache",
)
_authenticity_gate_module_cache: dict[str, bool] = {}


def _module_drives_authenticity_gate(module) -> bool:
    """True if a test module exercises the authenticity gate's internals itself
    (and thus drives its own DOI-resolve / Crossref network). Detected by source
    inspection so new gate tests are auto-excluded without a filename list.
    Cached per module to avoid re-reading source for every test."""
    name = getattr(module, "__name__", "")
    if name not in _authenticity_gate_module_cache:
        import inspect

        try:
            source = inspect.getsource(module)
        except (OSError, TypeError):
            source = ""
        _authenticity_gate_module_cache[name] = any(
            sym in source for sym in _AUTHENTICITY_GATE_INTERNALS
        )
    return _authenticity_gate_module_cache[name]


@pytest.fixture(autouse=True)
def _stub_authenticity_network(monkeypatch, request):
    """Run the authenticity gate OFFLINE by default (stub only its network).

    ``run_pipeline(dry_run=False)`` invokes
    ``research_hub.authenticity.verify_authenticity``, which corroborates DOIs
    via real HTTP: ``_resolve_head_with_retry`` (a ``requests.head`` DOI probe
    with retry/backoff) and ``CrossrefBackend._request``. In tests that leaks a
    live network call which, on a CI network blip, hangs until pytest-timeout
    kills it -- the 2026-06-01 master CI flake (``test_v041_pipeline_ingest_fixes``
    / ``test_v062_note_enrich`` timed out at urllib3 while local + PR CI were
    green).

    We stub ONLY the two network entry points, NOT ``verify_authenticity``
    itself, so the real gate logic still runs: local rejections (e.g. L0
    ``no_identifier`` for a paper with no DOI/arXiv id) stay intact, while DOI
    resolution + Crossref corroboration take the gate's own designed
    network-blip path (``transient`` -> fail-open accept) instead of touching
    the wire. This keeps assertions like ``missing-doi L0:no_identifier``
    (test_pipeline_e2e) valid AND makes the ingest tests deterministic.

    Excluded: tests that drive the gate's network layer themselves -- detected
    by source inspection for references to gate internals
    (``_resolve_head_with_retry`` / ``_resolve_identifier`` /
    ``research_hub.authenticity`` / ``CrossrefVerifyCache`` / ``DoiResolveCache``).
    Those mock requests/Crossref at their own level and assert specific verdicts,
    so this mid-level stub would bypass theirs. ``@pytest.mark.real_authenticity``
    also opts out. A test's own ``monkeypatch.setattr`` overrides this anyway
    (autouse runs first).
    """
    if request.node.get_closest_marker("real_authenticity"):
        return
    if _module_drives_authenticity_gate(request.module):
        return

    # DOI HEAD probe -> (status_code=None, transient=True): the gate treats this
    # as "check-unavailable" and fails open (does not brand the DOI fake).
    monkeypatch.setattr(
        "research_hub.authenticity._resolve_head_with_retry",
        lambda url, **_kwargs: (None, True),
    )
    # Crossref corroboration: replace ONLY authenticity's CrossrefBackend
    # reference (not the shared search-backend class) with an offline subclass,
    # so search-backend tests that drive CrossrefBackend._request with canned
    # responses (e.g. test_pipeline_e2e stage 3) are unaffected.
    import research_hub.search.crossref as _crossref

    class _OfflineCrossref(_crossref.CrossrefBackend):
        def _request(self, *args, **kwargs):
            return None

    monkeypatch.setattr(
        "research_hub.authenticity.CrossrefBackend", _OfflineCrossref
    )


@pytest.fixture(autouse=True)
def _stub_url_quality_probe(request, monkeypatch):
    """v1.0.9: the URL-quality classifier's active probe (``_probe_url`` →
    ``requests.get`` for ambiguous publisher URLs) runs a real HTTP GET whenever
    a bundled note has a URL but no local PDF. Stub it offline by default so the
    unit suite makes ZERO external connects (the network fence would block it and
    the classifier fail-safes to "unknown" anyway, but stubbing avoids the
    blocked-connect warning + DNS). Tests that drive the classifier itself
    (test_v0950_url_quality_guard) opt out so they exercise the real _probe_url
    under their own mocks.
    """
    module_stem = request.module.__name__.rsplit(".", 1)[-1]
    if module_stem == "test_v0950_url_quality_guard":
        return
    try:
        import research_hub.notebooklm.url_quality as _uq
    except Exception:
        return
    monkeypatch.setattr(
        _uq,
        "_probe_url",
        lambda url, *, timeout=8: _uq.UrlQuality("unknown", "probe_stubbed_in_tests", ""),
    )


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
def _force_writable_tempdir(monkeypatch):
    """Point subprocess-created temp files at a writable workspace path.

    Windows sandboxing in this environment intermittently denies writes under
    the default user temp dir during `venv -> ensurepip`, which breaks the
    extras-install smoke test even though the package metadata is fine.
    """
    temp_root = Path.cwd() / ".pytest-work" / "_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TMP", str(temp_root))
    monkeypatch.setenv("TEMP", str(temp_root))
    monkeypatch.setenv("TMPDIR", str(temp_root))


@pytest.fixture(autouse=True)
def _isolate_live_home_manifest_test(request, monkeypatch, tmp_path):
    """Keep the live-home manifest integrity test from depending on the
    maintainer's real ~/knowledge-base contents."""
    module_stem = request.module.__name__.rsplit(".", 1)[-1]
    if module_stem != "test_manifest_integrity":
        return
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))


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
