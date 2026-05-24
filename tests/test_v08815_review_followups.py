"""v0.88.15 — fix 4 P1 + 4 P2 issues raised in the post-ship code-review
of v0.88.10–v0.88.14.

Each test locks in a specific fix so the issue can't quietly come back.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# v0.88.10 P1 — narrow "is not a valid" non-retryable pattern
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transient_error",
    [
        "the requested URL is not a valid resource",
        "server certificate is not a valid X.509",
        "hostname is not a valid domain name",
        "status code is not a valid integer in response body",
    ],
)
def test_v08815_transient_errors_no_longer_falsely_non_retryable(transient_error: str) -> None:
    """The pre-fix `"is not a valid"` substring matched these transient
    errors and short-circuited retries. v0.88.15 narrows to specific
    SDK validation phrases."""
    from research_hub.notebooklm.upload import _is_non_retryable

    assert _is_non_retryable(transient_error) is False, (
        f"v0.88.15 regression: transient error {transient_error!r} "
        "is matching the non-retryable pattern again"
    )


@pytest.mark.parametrize(
    "sdk_validation_error",
    [
        "SourcesAPI.add_source: 'xyz' is not a valid notebook id",
        "ValueError: 'http://bad' is not a valid source URL",
    ],
)
def test_v08815_genuine_sdk_validation_still_non_retryable(sdk_validation_error: str) -> None:
    """Narrowed patterns still catch real SDK validation messages."""
    from research_hub.notebooklm.upload import _is_non_retryable

    assert _is_non_retryable(sdk_validation_error) is True


# ---------------------------------------------------------------------------
# v0.88.12 P1 — whitespace env var must not authenticate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_env_value,expected_key",
    [
        ("real-key-abc", "real-key-abc"),
        ("  padded-key  ", "padded-key"),
        ("\treal\nkey\t", "real\nkey"),     # tabs at edges stripped, internal preserved
        ("  ", None),                        # whitespace only → anonymous
        ("\t\n\r", None),                    # all-whitespace forms → anonymous
        ("", None),                          # empty → anonymous
    ],
)
def test_v08815_s2_env_var_whitespace_handling(
    monkeypatch, raw_env_value: str, expected_key: str | None
) -> None:
    """v0.88.15: whitespace-only env var must NOT produce a truthy
    api_key. Real keys with edge whitespace are stripped."""
    from research_hub.search.semantic_scholar import SemanticScholarClient

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", raw_env_value)
    client = SemanticScholarClient()
    assert client.api_key == expected_key


def test_v08815_s2_whitespace_does_not_send_x_api_key(monkeypatch) -> None:
    """Whitespace-only env var → no auth header sent (avoids bogus 403)."""
    from research_hub.search.semantic_scholar import SemanticScholarClient

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "   ")
    monkeypatch.delenv("SEMANTIC_SCHOLAR_RPS", raising=False)
    client = SemanticScholarClient()
    assert client._headers() == {}
    # Also: throttle should NOT be lifted (caller is effectively anonymous)
    assert client.delay == 3.0


def test_v08815_s2_explicit_whitespace_arg_also_normalized() -> None:
    """An explicit api_key='  ' kwarg is normalized the same way."""
    from research_hub.search.semantic_scholar import SemanticScholarClient

    client = SemanticScholarClient(api_key="  ")
    assert client.api_key is None


# ---------------------------------------------------------------------------
# v0.88.13 P1 — install_theme reports correct action on first-time --force
# ---------------------------------------------------------------------------


def test_v08815_install_theme_first_time_force_reports_installed(tmp_path: Path) -> None:
    """v0.88.13 pre-fix: first-time install with --force reported
    'overwrote' because dest.exists() was checked AFTER shutil.copy2.
    v0.88.15 captures already_existed BEFORE the copy."""
    from research_hub.vault.install_theme import install_theme

    assert not (tmp_path / ".obsidian" / "snippets" / "research-hub-tech.css").exists()
    result = install_theme(tmp_path, force=True)
    assert result.action == "installed", (
        "first-time --force install must report 'installed', not 'overwrote' "
        "(nothing was actually overwritten)"
    )
    assert result.errors == []


def test_v08815_install_theme_genuine_overwrite_still_reports_overwrote(tmp_path: Path) -> None:
    """Repeat install with --force on an existing file reports 'overwrote'
    (regression guard against the fix swinging too far the other way)."""
    from research_hub.vault.install_theme import install_theme

    install_theme(tmp_path)  # first run creates the file
    result = install_theme(tmp_path, force=True)
    assert result.action == "overwrote"


# ---------------------------------------------------------------------------
# v0.88.13 P2 — partial_uninstall when one side fails
# ---------------------------------------------------------------------------


def test_v08815_uninstall_reports_partial_when_appearance_disable_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """If the CSS file was removed but disabling in appearance.json
    raises (e.g. read-only fs), action should be 'partial_uninstall'
    not 'uninstalled' — the snippet may still load on Obsidian restart."""
    from research_hub.vault import install_theme as mod

    mod.install_theme(tmp_path)  # put it in place

    # Force _ensure_disabled to raise — simulate read-only appearance.json
    monkeypatch.setattr(
        mod, "_ensure_disabled",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("read-only filesystem")),
    )
    result = mod.uninstall_theme(tmp_path)

    # CSS file was removed, but disable failed — partial state
    assert result.action == "partial_uninstall"
    assert any("read-only" in err.lower() for err in result.errors)


# ---------------------------------------------------------------------------
# v0.88.14 P1 — PDF cache short-circuit when disabled
# ---------------------------------------------------------------------------


def test_v08815_pdf_cache_paths_no_io_when_disabled(tmp_path: Path, monkeypatch) -> None:
    """v0.88.15: when caching is disabled, _pdf_cache_paths must NOT
    read the file. Pre-fix it read + hashed every time even though
    the result was discarded."""
    from research_hub import importer

    monkeypatch.setattr(importer, "_PDF_EXTRACT_CACHE_DIR", None)
    nonexistent = tmp_path / "does-not-exist.pdf"
    # If short-circuit works, this returns (None, "") without reading
    cache_path, digest = importer._pdf_cache_paths(nonexistent)
    assert cache_path is None
    assert digest == ""
    # Crucially, no FileNotFoundError was raised


def test_v08815_pdf_cache_paths_still_hashes_when_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    """When caching IS enabled, we still pay the hash cost (correct)."""
    from research_hub import importer

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(importer, "_PDF_EXTRACT_CACHE_DIR", cache_dir)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    cache_path, digest = importer._pdf_cache_paths(pdf)
    assert cache_path is not None
    assert len(digest) == 64  # sha256 hex digest length
    assert cache_path == cache_dir / f"{digest}.txt"


# ---------------------------------------------------------------------------
# v0.88.11 P2 — _strip_archive_header preserves CRLF
# ---------------------------------------------------------------------------


def test_v08815_strip_archive_header_preserves_crlf(tmp_path: Path) -> None:
    """A body with CRLF line endings should keep CRLF after the strip,
    not silently normalize to LF."""
    from research_hub.notebooklm.download import _strip_archive_header

    body = (
        "# Cluster\r\n"
        "Source: https://x\r\n"
        "Downloaded: y\r\n"
        "\r\n"
        "# Real Synthesis\r\n"
        "Body text.\r\n"
    )
    out = _strip_archive_header(body)
    assert "\r\n" in out, "CRLF line endings must be preserved through strip"
    assert "\n" in out
    # No lone LF (would indicate partial CRLF→LF conversion)
    standalone_lf = out.replace("\r\n", "")
    assert "\n" not in standalone_lf, (
        f"strip produced mixed line endings: {out!r}"
    )


def test_v08815_strip_archive_header_keeps_lf_when_lf_input(tmp_path: Path) -> None:
    """LF input keeps LF (no spurious CRLF introduced)."""
    from research_hub.notebooklm.download import _strip_archive_header

    body = (
        "# Cluster\n"
        "Source: x\n"
        "Downloaded: y\n"
        "\n"
        "# Real Synthesis\n"
        "Body.\n"
    )
    out = _strip_archive_header(body)
    assert "\r\n" not in out


# ---------------------------------------------------------------------------
# v0.88.11 P2 — heartbeat refresh logs at debug instead of silent swallow
# ---------------------------------------------------------------------------


def test_v08815_heartbeat_refresh_failure_is_logged(monkeypatch, caplog) -> None:
    """When refresh_and_save raises, the exception is swallowed (best-
    effort) but a debug log line is emitted so multi-shard failures
    leave a diagnostic trail."""
    import logging
    import research_hub.notebooklm.upload as upload_mod

    src = Path(upload_mod.__file__).read_text(encoding="utf-8")
    # Structural test — verify the logger.debug call exists in the
    # heartbeat block and references the exception variable.
    refresh_idx = src.find("refresh_and_save\"")
    assert refresh_idx > 0
    # Find the try/except after that point
    block = src[refresh_idx : refresh_idx + 800]
    assert "logger.debug" in block, (
        "v0.88.15: heartbeat refresh failure must log at debug level, "
        "not silently swallow"
    )
    assert "_refresh_exc" in block or "exc" in block


# ---------------------------------------------------------------------------
# v0.88.12 P2 — dedupe key handles dict items deterministically
# ---------------------------------------------------------------------------


def test_v08815_item_signature_dedupes_dicts_regardless_of_key_order() -> None:
    """v0.88.15: future-proof dedupe — two dicts with same content but
    different key insertion order produce the same signature.
    Pre-fix used `str(item)` which gave different reprs."""
    from research_hub.vault.frontmatter_dedupe import _item_signature

    d1 = {"name": "Smith", "year": 2025}
    d2 = {"year": 2025, "name": "Smith"}
    assert _item_signature(d1) == _item_signature(d2)


def test_v08815_item_signature_strings_unchanged() -> None:
    """String items still produce string signatures (no behavior
    change for the current _DEDUPE_FIELDS string-list use case)."""
    from research_hub.vault.frontmatter_dedupe import _item_signature

    # JSON-serialized string includes the surrounding quotes — that's
    # fine, dedupe correctness only requires consistency
    sig_a = _item_signature("hydrology")
    sig_b = _item_signature("hydrology")
    sig_c = _item_signature("flood")
    assert sig_a == sig_b
    assert sig_a != sig_c


def test_v08815_item_signature_falls_back_on_unhashable(monkeypatch) -> None:
    """Non-JSON-serializable item → fall back to str() rather than raise.
    Migration must never crash mid-walk."""
    from research_hub.vault.frontmatter_dedupe import _item_signature

    class _Weird:
        def __str__(self) -> str:
            return "weird-repr"

    sig = _item_signature(_Weird())
    assert "weird-repr" in sig
