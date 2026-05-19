"""F8 real fix (diagnosed 2026-05-19).

Root cause: an all-URL cluster (perovskite DOIs -> ScienceDirect)
uploaded 0 sources because every entry was `likely_error_page` (our
local probe can't read the publisher anti-bot wall). The conservative
URL-quality skip is the maintainers' DELIBERATE, tested design
(`test_v0950_url_quality_guard::test_upload_skips_likely_error_page_no_pdf`)
and is left unchanged. `upload_cluster(include_suspect_urls=True)` is
also already tested there. The ONLY gap was: `auto` (the pipeline the
user actually runs) never exposed / threaded the override — it called
`upload_cluster(cluster, cfg, headless=False)` positionally — so there
was no way to rescue an all-suspect cluster through the pipeline.

These tests pin exactly that new surface (the override is now
reachable from `auto`); upload_cluster behaviour itself is covered by
the pre-existing v0950 suite and not duplicated here.
"""

from __future__ import annotations

import inspect


def test_auto_parser_exposes_include_suspect_urls():
    from research_hub.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["auto", "some topic", "--include-suspect-urls"]
    )
    assert args.include_suspect_urls is True


def test_auto_parser_include_suspect_urls_default_false():
    from research_hub.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["auto", "some topic"])
    assert args.include_suspect_urls is False


def test_auto_pipeline_threads_include_suspect_urls_to_upload():
    """`auto_pipeline` must accept the flag AND hand it to
    `upload_cluster` (it previously called upload_cluster positionally
    without it, so the pipeline could never override the skip)."""
    import research_hub.auto as auto_mod

    sig = inspect.signature(auto_mod.auto_pipeline)
    assert "include_suspect_urls" in sig.parameters
    assert sig.parameters["include_suspect_urls"].default is False

    # the upload call site forwards the kwarg (guards against a
    # regression back to the positional `upload_cluster(cluster, cfg,
    # headless=False)` that caused F8).
    # TODO(F8): source-text guard is brittle (false-negative if the
    # call is refactored through a local var). Replace with a
    # mock-based kwarg assertion using the test_v046_auto mock_deps
    # fixture before v1.0.0 ships.
    src = inspect.getsource(auto_mod.auto_pipeline)
    assert "include_suspect_urls=include_suspect_urls" in src
