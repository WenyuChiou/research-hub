"""ARCH-2 contract tests: locks the two load-bearing invariants of the cli.py
god-file split so future milestones (M1b/M2) can't silently break them.

1. Re-export contract: external modules import private symbols from
   research_hub.cli; the split MUST keep them importable from there.
2. get_config sync: handlers moved into cli_* domain modules bind their own
   get_config at import, but the conftest autouse fixture + many tests patch
   research_hub.cli.get_config. _sync_cli_dependencies() (called once at the
   top of _main_dispatch) propagates the patch into the domain modules.
"""

from __future__ import annotations


def test_cli_reexports_externally_imported_symbols():
    # describe.py imports build_parser; mcp_server.py imports _cite;
    # setup_command.py imports _cmd_install; __main__.py imports main.
    from research_hub.cli import build_parser, _cite, _cmd_install, main

    assert all(callable(x) for x in (build_parser, _cite, _cmd_install, main))


def test_sync_propagates_get_config_into_domain_modules():
    from research_hub import cli
    from research_hub import cli_citations

    orig_cli = cli.get_config
    orig_cit = cli_citations.get_config

    def _sentinel():
        return "SENTINEL_CFG"

    try:
        # simulate a test (or the conftest autouse fixture) patching cli.get_config
        cli.get_config = _sentinel
        cli._sync_cli_dependencies()
        # the moved cite/quote/compose handlers now see the patched get_config
        assert cli_citations.get_config is _sentinel
    finally:
        cli.get_config = orig_cli
        cli_citations.get_config = orig_cit
