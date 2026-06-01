"""Command line entry points for Research Hub."""

from __future__ import annotations

import argparse
import importlib.util
from contextlib import nullcontext, redirect_stdout
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config, require_config
from research_hub.dedup import DedupIndex, build_from_obsidian, build_from_zotero
from research_hub._deprecation import warn_deprecated
from research_hub.errors import ResearchHubError
from research_hub.operations import add_paper, mark_paper, move_paper, remove_paper
from research_hub.pipeline import run_pipeline
from research_hub.pipeline_repair import repair_cluster
from research_hub.security import safe_join, validate_slug, ValidationError
from research_hub.search import SemanticScholarClient, iter_new_results
from research_hub.search.fallback import (
    DEFAULT_BACKENDS,
    FIELD_PRESETS,
    REGION_PRESETS,
    apply_peer_reviewed,
    resolve_backends_for_field,
    resolve_backends_for_region,
)
from research_hub.suggest import PaperInput, suggest_cluster_for_paper, suggest_related_papers
from research_hub.verify import verify_arxiv, verify_doi, verify_paper
from research_hub.vault_search import search_vault
from research_hub.writing import (
    Quote,
    build_inline_citation,
    build_markdown_citation,
    format_paper_meta_from_frontmatter,
    load_all_quotes,
    resolve_paper_meta,
    save_quote,
)
from research_hub import cli_citations as _cli_citations
from research_hub import cli_clusters as _cli_clusters
from research_hub import cli_notebooklm as _cli_notebooklm
from research_hub import cli_search as _cli_search
from research_hub import cli_summarize as _cli_summarize
from research_hub import cli_zotero as _cli_zotero
from research_hub import cli_pipeline as _cli_pipeline
from research_hub import cli_vault as _cli_vault
from research_hub import cli_paper as _cli_paper
from research_hub import cli_maintenance as _cli_maintenance
from research_hub.cli_common import (
    _cli_deprecated_alias,
    _emit_cli_json,
    _json_safe,
    _load_zotero_if_configured,
    _parse_csv_terms,
    _parse_negative_terms,
    _parse_seed_dois,
    _parse_year_range,
    _read_zotero_key_from_frontmatter,
    _stdout_to_stderr,
    _warn_cli_deprecated_alias_from_args,
    _warn_cli_deprecated_alias_from_argv,
)
from research_hub.cli_clusters import (
    _cmd_clusters_analyze,
    _clusters_archive,
    _clusters_audit,
    _clusters_bind,
    _clusters_delete,
    _clusters_list,
    _clusters_merge,
    _clusters_new,
    _clusters_rename,
    _clusters_resolve_collision,
    _clusters_restore_zotero_coll,
    _clusters_scaffold_missing,
    _clusters_set_group,
    _clusters_show,
    _clusters_split,
    _clusters_sync_names,
    _clusters_unarchive,
)
from research_hub.cli_notebooklm import (
    _display_entry,
    _nlm_ask,
    _nlm_download,
    _nlm_generate,
    _nlm_read_briefing,
    _nlm_shard,
    _nlm_upload,
    _notebooklm_bundle,
    _preflight_nlm_session,
)
from research_hub.cli_summarize import (
    _cmd_crystal,
    _cmd_memory,
    _cmd_summarize,
    _vault_summarize_status_migrate,
)
from research_hub.cli_zotero import (
    _zotero_backfill,
    _zotero_gc,
    _zotero_mark_kept,
    _zotero_reparent_clusters,
)
from research_hub.cli_citations import (
    _cite,
    _collect_paper_meta_for_cluster,
    _compose_draft,
    _quote_add,
    _quote_list,
    _quote_remove,
)
from research_hub.cli_search import (
    _cited_by,
    _discover_clean,
    _discover_continue,
    _discover_new,
    _discover_status,
    _discover_variants,
    _emit_papers_input_json,
    _enrich,
    _references,
    _search,
    _suggest,
    _websearch,
)
from research_hub.cli_vault import (
    _bases_emit,
    _cleanup_hub,
    _synthesize,
    _vault_cleanup_frontmatter,
    _vault_graph_colors,
    _vault_hub_backlink_migrate,
    _vault_install_theme,
    _vault_polish_markdown,
    _vault_rebuild_overviews,
    _vault_tag_migrate,
)
from research_hub.cli_pipeline import (
    _auto,
    _cmd_doctor,
    _cmd_ingest,
    _fit_check_apply,
    _fit_check_audit,
    _fit_check_drift,
    _fit_check_emit,
    _import_folder_command,
    _import_folder_dep_precheck,
    _migrate_yaml,
    _pipeline_repair,
    _sync_reconcile,
    _sync_status,
)
from research_hub.cli_paper import (
    _add,
    _autofill_apply,
    _autofill_emit,
    _cmd_paper_add_to_cluster,
    _cmd_paper_find,
    _cmd_paper_gaps,
    _find,
    _fit_check_apply_labels,
    _label,
    _label_bulk,
    _mark,
    _move,
    _paper_command,
    _quarantine,
    _read_paper_frontmatter,
    _remove,
    _update_paper_frontmatter,
    _verify,
)
from research_hub.cli_maintenance import (
    _cleanup_gc,
    _cmd_install,
    _cmd_serve,
    _cmd_where,
    _config_encrypt_secrets,
    _config_set,
    _dashboard,
    _dedup,
    _get_claude_desktop_config_path,
    _install_mcp,
    _package_dxt,
    _rebuild_index,
    _status,
)


_cli_notebooklm.get_config = lambda: get_config()
_cli_notebooklm.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(
    *args,
    **kwargs,
)
_cli_notebooklm._preflight_nlm_session = lambda *args, **kwargs: _preflight_nlm_session(
    *args,
    **kwargs,
)
_cli_clusters.get_config = lambda: get_config()
_cli_search.get_config = lambda: get_config()
_cli_summarize.get_config = lambda: get_config()
_cli_zotero.get_config = lambda: get_config()
_cli_zotero.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(
    *args,
    **kwargs,
)
_cli_search._emit_papers_input_json = lambda results, cluster_slug: _emit_papers_input_json(
    results,
    cluster_slug,
)
_cli_vault.get_config = lambda: get_config()
_cli_vault.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(*args, **kwargs)
_cli_pipeline.get_config = lambda: get_config()
_cli_pipeline.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(*args, **kwargs)
_cli_pipeline.run_pipeline = lambda **kwargs: run_pipeline(**kwargs)
_cli_pipeline.repair_cluster = lambda *args, **kwargs: repair_cluster(*args, **kwargs)
_cli_pipeline._load_zotero_if_configured = lambda: _load_zotero_if_configured()
_cli_paper.get_config = lambda: get_config()
_cli_paper.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(*args, **kwargs)
_cli_paper.require_config = lambda: require_config()
_cli_maintenance.get_config = lambda: get_config()
_cli_maintenance.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(*args, **kwargs)
_cli_maintenance.require_config = lambda: require_config()
_cli_maintenance._get_claude_desktop_config_path = lambda: _get_claude_desktop_config_path()


def _sync_cli_dependencies() -> None:
    """Propagate cli.py's (possibly test-patched) ``get_config`` into the
    extracted ``cli_*`` domain modules. The conftest autouse fixture and many
    tests patch ``research_hub.cli.get_config``; handlers that now live outside
    cli.py bind their own ``get_config`` at import, so without this sync they
    would not see the patch. Called ONCE at the top of ``_main_dispatch``. As
    more modules are extracted (M1b/M2), add one line per module here."""
    _cli_citations.get_config = get_config
    _cli_clusters.get_config = lambda: get_config()
    _cli_notebooklm.get_config = lambda: get_config()
    _cli_notebooklm.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(
        *args,
        **kwargs,
    )
    _cli_notebooklm._preflight_nlm_session = lambda *args, **kwargs: _preflight_nlm_session(
        *args,
        **kwargs,
    )
    _cli_search.get_config = lambda: get_config()
    _cli_summarize.get_config = lambda: get_config()
    _cli_zotero.get_config = lambda: get_config()
    _cli_zotero.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(
        *args,
        **kwargs,
    )
    _cli_search._emit_papers_input_json = lambda results, cluster_slug: _emit_papers_input_json(
        results,
        cluster_slug,
    )
    _cli_vault.get_config = lambda: get_config()
    _cli_vault.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(*args, **kwargs)
    _cli_pipeline.get_config = lambda: get_config()
    _cli_pipeline.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(*args, **kwargs)
    _cli_pipeline.run_pipeline = lambda **kwargs: run_pipeline(**kwargs)
    _cli_pipeline.repair_cluster = lambda *args, **kwargs: repair_cluster(*args, **kwargs)
    _cli_pipeline._load_zotero_if_configured = lambda: _load_zotero_if_configured()
    _cli_paper.get_config = lambda: get_config()
    _cli_paper.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(*args, **kwargs)
    _cli_paper.require_config = lambda: require_config()
    _cli_maintenance.get_config = lambda: get_config()
    _cli_maintenance.ClusterRegistry = lambda *args, **kwargs: ClusterRegistry(*args, **kwargs)
    _cli_maintenance.require_config = lambda: require_config()
    _cli_maintenance._get_claude_desktop_config_path = lambda: _get_claude_desktop_config_path()


_PEER_REVIEWED_HELP = (
    "Peer-reviewed only: drop preprint backends, exclude preprint/report/dataset "
    "doc types, require >=1-backend corroboration. Excludes gray literature "
    "(arXiv/bioRxiv/Zenodo)."
)


def build_parser() -> argparse.ArgumentParser:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version
    try:
        _version = _pkg_version("research-hub-pipeline")
    except PackageNotFoundError:
        _version = "unknown"

    parser = argparse.ArgumentParser(
        prog="research-hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Start here ->\n\n"
            "  $ research-hub init           # interactive setup wizard\n"
            "  $ research-hub doctor         # optional readiness check\n"
            "  $ research-hub where          # show vault + config paths\n"
            "  $ research-hub plan \"your research topic\"\n"
            "  $ research-hub auto \"your research topic\"\n"
            "  $ research-hub serve --dashboard  # open live dashboard\n"
            "  $ research-hub dashboard --sample  # preview without accounts\n\n"
            "Docs: https://github.com/WenyuChiou/research-hub\n"
        ),
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"research-hub {_version}",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init",
        help="Interactive setup wizard for first-time users",
    )
    init_parser.add_argument("--vault", default=None, help="Vault root directory")
    init_parser.add_argument(
        "--sample",
        action="store_true",
        help="Copy the bundled sample vault and skip all account/tool probes",
    )
    init_parser.add_argument("--zotero-key", default=None, help="Zotero API key")
    init_parser.add_argument(
        "--zotero-library-id",
        default=None,
        help="Zotero library ID",
    )
    init_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip prompts; require all values via flags",
    )
    init_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser pages during onboarding prompts",
    )
    init_parser.add_argument(
        "--persona",
        choices=["researcher", "analyst", "humanities", "internal"],
        default=None,
        help="researcher|humanities use Zotero; analyst|internal skip Zotero",
    )
    init_parser.add_argument(
        "--field",
        choices=sorted(FIELD_PRESETS.keys()),
        help="Field-aware onboarding wizard mode",
    )
    init_parser.add_argument("--cluster", help="Pre-fill cluster slug")
    init_parser.add_argument("--name", help="Pre-fill cluster display name")
    init_parser.add_argument("--query", help="Pre-fill search query")
    init_parser.add_argument("--definition", help="Pre-fill cluster definition")

    setup_parser = subparsers.add_parser(
        "setup",
        help="One-shot onboarding: init + install --platform + NotebookLM login",
    )
    setup_parser.add_argument("--vault", default=None, help="Vault root directory")
    setup_parser.add_argument(
        "--persona",
        choices=["researcher", "analyst", "humanities", "internal", "agent"],
        default=None,
        help="Persona to initialize",
    )
    setup_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex", "cursor", "gemini"],
        default=None,
        help="Override auto-detected AI host for install",
    )
    setup_parser.add_argument("--skip-install", action="store_true")
    setup_parser.add_argument("--skip-login", action="store_true")
    setup_parser.add_argument("--skip-sample", action="store_true")
    setup_parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Non-interactive bootstrap: probe env + vault + auth + emit JSON report (v0.89)",
    )
    setup_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser pages during onboarding prompts",
    )

    tidy_parser = subparsers.add_parser(
        "tidy",
        help="One-shot maintenance: doctor autofix + dedup rebuild + bases refresh + cleanup preview (v0.46)",
    )
    tidy_parser.add_argument(
        "--apply-cleanup",
        action="store_true",
        help="Apply the cleanup preview (default: dry-run only)",
    )
    tidy_parser.add_argument(
        "--cluster",
        default=None,
        help="Restrict the bases refresh step to one cluster slug",
    )

    subparsers.add_parser("doctor", help="Health check for research-hub installation")
    doctor_parser = next(
        action for action in subparsers.choices.values() if action.prog.endswith(" doctor")
    )
    doctor_parser.add_argument(
        "--autofix",
        action="store_true",
        help="Backfill mechanical frontmatter gaps before running checks",
    )
    doctor_parser.add_argument(
        "--strict",
        action="store_true",
        help="Show all frontmatter WARNs including expected legacy gaps "
             "(missing DOI on pre-v0.31 imports, empty Summary/Methodology sections). "
             "Default hides them as a single INFO line.",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    config_parser = subparsers.add_parser("config", help="Config maintenance commands")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser(
        "encrypt-secrets",
        help="Encrypt plaintext sensitive values in config.json",
    )
    config_set = config_sub.add_parser("set", help="Set a config field")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_set.add_argument(
        "--force",
        action="store_true",
        help="Allow setting a key not in the allowlist (use for new fields)",
    )

    ezproxy_parser = subparsers.add_parser(
        "ezproxy",
        help="Institutional EZproxy support for paywalled PDF downloads",
    )
    ezproxy_sub = ezproxy_parser.add_subparsers(dest="ezproxy_command", required=True)
    ezproxy_login = ezproxy_sub.add_parser(
        "login",
        help="Open a browser, complete institutional SSO, save cookies",
    )
    ezproxy_login.add_argument(
        "--sentinel-url",
        default="https://ieeexplore.ieee.org/",
        help="Publisher URL to load (proxied) so you can verify access before closing the window",
    )
    ezproxy_sub.add_parser("status", help="Show configured template + cookie file state")

    examples_parser = subparsers.add_parser(
        "examples",
        help="Browse and copy bundled cluster examples",
    )
    examples_sub = examples_parser.add_subparsers(dest="examples_command")
    examples_sub.add_parser("list", help="List bundled example clusters")
    examples_show = examples_sub.add_parser("show", help="Show one example's full definition")
    examples_show.add_argument("name")
    examples_copy = examples_sub.add_parser("copy", help="Copy an example into your clusters")
    examples_copy.add_argument("name")
    examples_copy.add_argument("--cluster", help="Override the cluster slug")

    install_parser = subparsers.add_parser(
        "install",
        help="Install research-hub skill for AI coding assistants",
    )
    install_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex", "cursor", "gemini"],
        default=None,
        help="Target platform",
    )
    install_parser.add_argument(
        "--list",
        dest="list_platforms",
        action="store_true",
        help="List supported platforms and install status",
    )
    install_parser.add_argument(
        "--mcp",
        action="store_true",
        help="Auto-configure Claude Desktop MCP server connection",
    )

    subparsers.add_parser(
        "where",
        help="Show where research-hub stores config, vault, and data",
    )

    dxt_parser = subparsers.add_parser(
        "package-dxt",
        help="Build a .dxt MCP extension archive for Claude Desktop",
    )
    dxt_parser.add_argument("--out", type=Path, default=Path("research-hub.dxt"))

    describe_parser = subparsers.add_parser(
        "describe",
        help="Emit JSON manifest of CLI subcommands, MCP tools, env vars, skills (v0.89)",
    )
    describe_parser.add_argument(
        "--filter",
        choices=["subcommands", "mcp_tools", "env_vars", "skills", "personae"],
        default=None,
        help="Emit only one subtree of the manifest",
    )
    describe_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Compatibility flag; describe emits JSON by default",
    )
    describe_parser.add_argument(
        "--pretty",
        action="store_true",
        default=False,
        help="Indent JSON output for human inspection",
    )

    ask_parser = subparsers.add_parser(
        "ask",
        help="Ask a natural-language question about a cluster (task-level, v0.33+)",
    )
    ask_parser.add_argument("cluster", help="Cluster slug")
    ask_parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Natural-language question (optional; omitting returns digest)",
    )
    ask_parser.add_argument(
        "--detail",
        choices=["tldr", "gist", "full"],
        default="gist",
        help="Answer detail level (default: gist)",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start MCP stdio server or live dashboard HTTP server",
    )
    serve_parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Run the live dashboard HTTP server instead of MCP stdio",
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument(
        "--allow-external",
        action="store_true",
        help="Allow binding non-loopback host (power-user only)",
    )
    serve_parser.add_argument("--no-browser", action="store_true")
    serve_parser.add_argument(
        "--api-token",
        default="",
        help=(
            "Bearer token for /api/v1/* requests. NOTE: visible to other "
            "users via ps/tasklist on shared hosts — prefer "
            "--api-token-file. Falls back to RESEARCH_HUB_API_TOKEN. "
            "Without a token, the REST API is restricted to 127.0.0.1 only."
        ),
    )
    serve_parser.add_argument(
        "--api-token-file",
        default=None,
        help=(
            "Path to a file whose contents are the bearer token (G3 P2 "
            "#15). Recommended over --api-token on shared hosts since the "
            "token never appears in the process argument list. Store the "
            "file mode 0600."
        ),
    )
    serve_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the external-bind warning delay when used with --allow-external",
    )

    run_parser = subparsers.add_parser("run", help="Run the research pipeline")
    run_parser.add_argument("--topic", default=None, help="Pipeline topic context")
    run_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to process")
    run_parser.add_argument("--dry-run", action="store_true", help="Validate config and inputs only")
    run_parser.add_argument("--cluster", default=None, help="Cluster slug for ingestion")
    run_parser.add_argument("--query", default=None, help="Query text")
    run_parser.add_argument(
        "--no-fit-check-auto-labels",
        action="store_true",
        help="Skip auto-labeling papers from fit-check score after ingest",
    )
    run_parser.add_argument(
        "--allow-library-duplicates",
        action="store_true",
        help="Bypass Zotero library duplicate blocking and allow re-ingest",
    )
    run_parser.add_argument(
        "--with-pdfs",
        action="store_true",
        help="Attach open-access PDFs from arXiv/Unpaywall after ingest",
    )

    auto_parser = subparsers.add_parser(
        "auto",
        help="One-command pipeline: topic ??cluster ??search ??ingest ??NotebookLM",
    )
    auto_parser.add_argument("topic", help="Free-text topic to search for")
    auto_parser.add_argument("--cluster", default=None,
                             help="Use existing cluster slug instead of slugifying topic")
    auto_parser.add_argument("--cluster-name", default=None,
                             help="Display name for new cluster (default: title-case of topic)")
    auto_parser.add_argument("--max-papers", type=int, default=8)
    auto_parser.add_argument(
        "--year",
        default=None,
        metavar="RANGE",
        help=(
            "Year range filter for the search step, e.g. '2024-2025', "
            "'2024-' (2024 and later), or '-2024' (up to 2024). Same syntax "
            "as the standalone `search --year` flag. Unset = no year filter."
        ),
    )
    auto_parser.add_argument("--field", default=None,
                             choices=["cs", "bio", "med", "physics", "math", "social", "econ", "chem", "astro", "edu", "general"],
                             help="Field preset for backend selection")
    auto_parser.add_argument(
        "--peer-reviewed",
        action="store_true",
        help=_PEER_REVIEWED_HELP,
    )
    auto_parser.add_argument(
        "--include-suspect-urls",
        action="store_true",
        help="Upload URL sources even if the URL-quality pre-check flags "
             "them likely_error_page (e.g. publisher/anti-bot pages our "
             "local probe can't read). NotebookLM fetches URLs server-side, "
             "so this rescues clusters that would otherwise upload 0 sources "
             "(F8). Use this when an `auto` run reports the 0-sources "
             "upload error. Default conservative skip is unchanged.",
    )
    auto_parser.add_argument("--no-nlm", action="store_true",
                             help="Skip NotebookLM bundle/upload/generate/download")
    auto_parser.add_argument("--with-crystals", action="store_true",
                             help="Also generate crystals via detected LLM CLI")
    auto_parser.add_argument(
        "--with-summary",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Run `summarize --apply` after ingest to fill per-paper "
            "Key Findings / Methodology / Relevance (default: on). Use "
            "--no-with-summary to skip per-paper summarization."
        ),
    )
    auto_parser.add_argument(
        "--full-auto",
        action="store_true",
        help=(
            "Enable --with-crystals (--with-pdfs and --with-summary are "
            "already on by default; use --no-with-pdfs / --no-with-summary "
            "to disable them). NotebookLM upload also stays ON by default — "
            "pair with --no-nlm if you want fully local automation without "
            "the browser step (NLM upload uses patchright + Google login)."
        ),
    )
    auto_parser.add_argument(
        "--no-cluster-overview", action="store_true",
        help="Skip the v0.71.0 LLM-driven cluster overview auto-fill",
    )
    auto_parser.add_argument("--no-fit-check", action="store_true",
                             help="Skip the fail-closed LLM-judge fit-check between search and ingest")
    auto_parser.add_argument("--fit-check-threshold", type=int, default=4,
                             help=(
                                 "Minimum 0-5 score for a paper to pass fit-check "
                                 "(default: 4 = clearly related; pass --fit-check-threshold 3 "
                                 "for the older lax default that accepts tangentially-related papers)"
                             ))
    auto_parser.add_argument(
        "--zotero-batch-size",
        type=int,
        default=50,
        help="Number of Zotero items to create per batch during ingest (default: 50)",
    )
    auto_parser.add_argument("--llm-cli", default=None,
                             help="Force a specific LLM CLI for --with-crystals / fit-check (default: auto-detect)")
    auto_parser.add_argument(
        "--no-llm-fit-check",
        action="store_true",
        default=False,
        dest="no_llm_fit_check",
        help="Use rule-based term-overlap fit-check instead of LLM (no CLI needed).",
    )
    auto_parser.add_argument("--dry-run", action="store_true",
                             help="Print plan without executing")
    auto_parser.add_argument(
        "--show",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Open the dashboard in your browser after successful run (default: on)",
    )
    auto_parser.add_argument(
        "--append",
        action="store_true",
        help="Allow adding more papers to an existing non-empty cluster",
    )
    auto_parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass non-empty cluster guard",
    )
    auto_parser.add_argument(
        "--batch-label",
        default=None,
        help="Optional explicit batch label for the ingest sub-collection",
    )
    auto_parser.add_argument(
        "--with-pdfs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Attach open-access PDFs from arXiv/OpenAlex/Unpaywall/Crossref "
            "to the Zotero items after ingest (default: on). Use "
            "--no-with-pdfs to skip the PDF-attach pass."
        ),
    )
    auto_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    plan_parser = subparsers.add_parser(
        "plan",
        help="Convert a freeform intent into a structured auto-pipeline plan (no execution)",
    )
    plan_parser.add_argument("intent", help="Freeform user intent (e.g., 'I want to learn harness engineering')")
    plan_parser.add_argument("--json", action="store_true",
                             help="Print plan as JSON instead of human-readable text")

    ingest_parser = subparsers.add_parser("ingest", help="Run ingestion")
    ingest_parser.add_argument("--cluster", default=None, help="Cluster slug for ingestion")
    ingest_parser.add_argument("--query", default=None, help="Query text")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Validate config and inputs only")
    ingest_parser.add_argument(
        "--no-fit-check-auto-labels",
        action="store_true",
        help="Skip auto-labeling papers from fit-check score after ingest",
    )
    ingest_parser.add_argument(
        "--allow-library-duplicates",
        action="store_true",
        help="Bypass Zotero library duplicate blocking and allow re-ingest",
    )
    ingest_parser.add_argument(
        "--fit-check",
        action="store_true",
        help=(
            "Require a valid .fit_check_rejected.json sidecar from a prior `fit-check apply` run, "
            "and enforce the threshold during ingest"
        ),
    )
    ingest_parser.add_argument(
        "--fit-check-threshold",
        type=int,
        default=3,
        help="Minimum score (0-5) to keep a paper when --fit-check is on",
    )
    ingest_parser.add_argument(
        "--batch-label",
        default=None,
        help="Optional explicit batch label for the ingest sub-collection",
    )
    ingest_parser.add_argument(
        "--with-pdfs",
        action="store_true",
        help="Attach open-access PDFs from arXiv/Unpaywall after ingest",
    )
    ingest_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    import_folder_parser = subparsers.add_parser(
        "import-folder",
        help="Walk a folder and ingest local files as document notes",
    )
    import_folder_parser.add_argument("folder", help="Path to source folder (recursive)")
    import_folder_parser.add_argument("--cluster", required=True, help="Target cluster slug")
    import_folder_parser.add_argument(
        "--extensions",
        default="pdf,md,txt,docx,url",
        help="Comma-separated file extensions to ingest",
    )
    import_folder_parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-import even if content hash matches an existing imported note",
    )
    import_folder_parser.add_argument(
        "--use-graphify",
        action="store_true",
        help="Run graphify post-processing if graphify_bridge is available",
    )
    import_folder_parser.add_argument(
        "--graphify-graph",
        metavar="PATH",
        default=None,
        help=(
            "Path to pre-built graphify-out/graph.json. Adds subtopics frontmatter "
            "to imported notes based on Leiden community detection from the graph. "
            "Run `/graphify <folder>` in Claude Code first to produce graph.json."
        ),
    )
    import_folder_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without writing notes",
    )
    import_folder_parser.add_argument(
        "--with-zotero",
        action="store_true",
        default=False,
        help="Also write imported files into the cluster Zotero collection",
    )
    import_folder_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the Obsidian-only confirmation prompt",
    )
    import_folder_parser.add_argument(
        "--batch-label",
        default=None,
        help="Optional label for the manifest and Zotero batch sub-collection",
    )
    import_folder_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    for parser_with_verify in (run_parser, ingest_parser):
        parser_with_verify.add_argument(
            "--no-verify",
            dest="verify",
            action="store_false",
            default=True,
            help="Skip DOI/arxiv HTTP verification (default: verify on)",
        )

    subparsers.add_parser("index", help="Rebuild dedup_index.json from Zotero and Obsidian")

    dedup_parser = subparsers.add_parser(
        "dedup",
        help="Manage the dedup index (invalidate stale entries, rebuild)",
    )
    dedup_subparsers = dedup_parser.add_subparsers(dest="dedup_command", required=True)
    invalidate_parser = dedup_subparsers.add_parser(
        "invalidate",
        help="Remove a DOI or path from the dedup index",
    )
    invalidate_parser.add_argument("--doi", default=None)
    invalidate_parser.add_argument("--path", default=None, help="Obsidian path to invalidate")
    rebuild_parser = dedup_subparsers.add_parser(
        "rebuild",
        help="Rebuild the dedup index",
    )
    rebuild_parser.add_argument(
        "--obsidian-only",
        action="store_true",
        help="Only rescan Obsidian (skip Zotero - useful when API is down)",
    )
    compact_parser = dedup_subparsers.add_parser(
        "compact",
        help="Drop stale Obsidian paths and Zotero 404 hits from the dedup index",
    )
    compact_group = compact_parser.add_mutually_exclusive_group()
    compact_group.add_argument("--dry-run", dest="apply", action="store_false", help="Preview only (default)")
    compact_group.add_argument("--apply", dest="apply", action="store_true", help="Write the compacted index")
    compact_parser.set_defaults(apply=False)
    compact_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    quarantine_parser = subparsers.add_parser(
        "quarantine",
        help="Inspect and restore authenticity-gate quarantine entries",
    )
    quarantine_subparsers = quarantine_parser.add_subparsers(
        dest="quarantine_command",
        required=True,
    )
    quarantine_list = quarantine_subparsers.add_parser(
        "list",
        help="List quarantined candidates",
    )
    quarantine_list.add_argument("--cluster", default=None, help="Restrict to a cluster")
    quarantine_show = quarantine_subparsers.add_parser(
        "show",
        help="Show a quarantined candidate JSON payload",
    )
    quarantine_show.add_argument("slug")
    quarantine_show.add_argument("--cluster", default=None)
    quarantine_restore = quarantine_subparsers.add_parser(
        "restore",
        help="Restore a quarantined candidate to papers_input.json",
    )
    quarantine_restore.add_argument("slug")
    quarantine_restore.add_argument("--cluster", required=True)

    clusters_parser = subparsers.add_parser("clusters", help="Manage topic clusters")
    clusters_subparsers = clusters_parser.add_subparsers(dest="clusters_command", required=True)
    clusters_subparsers.add_parser("list", help="List clusters")
    set_group_p = clusters_subparsers.add_parser(
        "set-group", help="Assign a cluster to a named group for organised navigation"
    )
    set_group_p.add_argument("slug", help="Cluster slug")
    set_group_p.add_argument(
        "group", nargs="?", default="", help="Group name (omit to clear)"
    )
    coverage_p = clusters_subparsers.add_parser("coverage", help="Show cluster coverage/health metrics")
    coverage_p.add_argument("--min-coverage", type=int, default=0, dest="min_coverage")
    coverage_p.add_argument(
        "--sort",
        choices=["coverage", "papers", "recency"],
        default="coverage",
    )
    show_parser = clusters_subparsers.add_parser("show", help="Show cluster details")
    show_parser.add_argument("slug")
    new_parser = clusters_subparsers.add_parser("new", help="Create a new cluster")
    new_parser.add_argument("--query", required=True)
    new_parser.add_argument("--name", default=None)
    new_parser.add_argument("--slug", default=None)
    bind_parser = clusters_subparsers.add_parser(
        "bind", help="Link a cluster to Zotero/Obsidian/NotebookLM"
    )
    bind_parser.add_argument("slug")
    bind_parser.add_argument(
        "--zotero", dest="zotero_key", default=None, help="Zotero collection key"
    )
    bind_parser.add_argument(
        "--obsidian", dest="obsidian_folder", default=None, help="Obsidian sub-folder"
    )
    bind_parser.add_argument(
        "--notebooklm",
        dest="notebooklm_notebook",
        default=None,
        help="NotebookLM notebook name",
    )
    bind_parser.add_argument(
        "--no-sync-zotero",
        action="store_true",
        help="Do not sync the Zotero collection name to the vault cluster name",
    )
    bind_parser.add_argument(
        "--force-shared",
        action="store_true",
        help="Allow duplicate zotero_collection_key binding intentionally",
    )
    rename_parser = clusters_subparsers.add_parser("rename", help="Rename a cluster")
    rename_parser.add_argument("slug")
    rename_parser.add_argument("--name", required=True)
    rename_parser.add_argument(
        "--no-sync-zotero",
        action="store_true",
        help="Do not sync the Zotero collection name",
    )
    archive_parser = clusters_subparsers.add_parser("archive", help="Mark a cluster archived")
    archive_parser.add_argument("slug")
    unarchive_parser = clusters_subparsers.add_parser("unarchive", help="Mark a cluster active")
    unarchive_parser.add_argument("slug")
    delete_parser = clusters_subparsers.add_parser("delete", help="Delete a cluster")
    delete_parser.add_argument("slug")
    delete_parser.add_argument("--dry-run", action="store_true")
    delete_parser.add_argument("--apply", action="store_true", help="Apply the delete instead of previewing it")
    delete_parser.add_argument("--force", action="store_true", help="Confirm deletion of a non-empty cluster")
    delete_parser.add_argument(
        "--delete-zotero-collection",
        action="store_true",
        help="Also delete the now-empty Zotero collection container",
    )
    delete_parser.add_argument(
        "--purge-zotero-items",
        action="store_true",
        default=False,
        help=(
            "DESTRUCTIVE: delete each parent item from the cluster's Zotero collection "
            "(items go to Zotero trash, recoverable until trash is emptied; Zotero "
            "cascade-deletes child attachments incl. PDFs when the parent is trashed). "
            "Strictly scoped to this cluster's own collection key -- parent and sibling "
            "collections are never enumerated or touched. Requires --apply to execute; "
            "dry-run prints the item list and totals without making any deletions."
        ),
    )
    merge_parser = clusters_subparsers.add_parser("merge", help="Merge two clusters")
    merge_parser.add_argument("source", help="Source cluster slug (will be removed)")
    merge_parser.add_argument("--into", required=True, dest="target", help="Target cluster slug")
    split_parser = clusters_subparsers.add_parser("split", help="Split a cluster")
    split_parser.add_argument("source", help="Source cluster slug")
    split_parser.add_argument("--query", required=True, help="Keywords for the new sub-cluster")
    split_parser.add_argument("--new-name", required=True, help="Display name for new cluster")
    analyze_parser = clusters_subparsers.add_parser(
        "analyze",
        help="Analyze a cluster and produce split suggestions",
    )
    analyze_parser.add_argument("--cluster", required=True)
    analyze_parser.add_argument("--split-suggestion", action="store_true")
    analyze_parser.add_argument("--min-community-size", type=int, default=8)
    analyze_parser.add_argument("--max-communities", type=int, default=8)
    analyze_parser.add_argument(
        "--out",
        default=None,
        help="Output markdown path (default: docs/cluster_autosplit_<slug>.md)",
    )
    rebind_parser = clusters_subparsers.add_parser(
        "rebind", help="Detect orphan papers and propose cluster bindings"
    )
    rebind_parser.add_argument("--emit", action="store_true", help="Emit a rebind proposal report to stdout")
    rebind_parser.add_argument("--apply", type=Path, help="Apply moves from a previously emitted report file")
    rebind_parser.add_argument(
        "--auto-create-new",
        action="store_true",
        help="When applying, also create NEW clusters proposed in the report from topic folders with >=5 orphans",
    )
    rebind_parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Actually move files (default is dry-run)",
    )
    clusters_subparsers.add_parser(
        "scaffold-missing",
        help="Find clusters with no hub/<slug>/ scaffold and create it. Idempotent.",
    )
    audit_parser = clusters_subparsers.add_parser(
        "audit",
        help="Run drift + collision + test-pattern checks (subset of doctor)",
    )
    audit_parser.add_argument(
        "--cluster",
        default=None,
        help="Audit only this cluster slug (default: all)",
    )
    audit_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )
    restore_p = clusters_subparsers.add_parser(
        "restore-zotero-coll",
        help="Restore a cluster's Zotero collection from trash (clear deleted flag)",
    )
    restore_p.add_argument("--cluster", default=None, help="Single cluster slug (default: scan all)")
    restore_p.add_argument("--apply", action="store_true", help="Apply restore (default: preview)")
    sync_names = clusters_subparsers.add_parser(
        "sync-names",
        help="Detect and fix cluster.name drift between vault and Zotero",
    )
    sync_names.add_argument("--cluster", default=None, help="Only this cluster slug (default: all)")
    sync_names.add_argument("--apply", action="store_true", help="Apply fixes (default: preview only)")
    sync_names.add_argument(
        "--direction",
        choices=["vault-to-zotero", "zotero-to-vault"],
        default="vault-to-zotero",
        help="Source of truth (default: vault)",
    )
    resolve_parser = clusters_subparsers.add_parser(
        "resolve-collision",
        help="Fix two clusters sharing one zotero_collection_key",
    )
    resolve_parser.add_argument("slug")
    resolve_parser.add_argument("--new", action="store_true", help="Create a fresh Zotero collection for this slug and migrate items")
    resolve_parser.add_argument("--into", dest="target_slug", default=None, help="Drop this slug's Zotero binding; keep it on target")
    resolve_parser.add_argument("--apply", action="store_true")
    resolve_parser.add_argument(
        "--force-shared",
        action="store_true",
        help="Required when using --into",
    )

    # v0.67: Phase 2 of the Codex skills brief - shell entry point for the
    # research workspace manifest layer. Skills do the AI part; this CLI
    # bootstraps the skeleton, audits the schema, and points at the AI prompt.
    context_parser = subparsers.add_parser(
        "context",
        help="Manage the .research/ workspace manifest (init/audit/compress)",
    )
    context_subparsers = context_parser.add_subparsers(
        dest="context_command", required=True
    )
    context_init_p = context_subparsers.add_parser(
        "init", help="Bootstrap an empty .research/ skeleton (idempotent)"
    )
    context_init_p.add_argument(
        "--vault", default=None,
        help="Project root (default: research-hub vault root)",
    )
    context_audit_p = context_subparsers.add_parser(
        "audit", help="Audit .research/ for required fields, freshness, dataset paths",
    )
    context_audit_p.add_argument("--vault", default=None)
    context_compress_p = context_subparsers.add_parser(
        "compress",
        help="Point at the research-context-compressor AI skill (or --print-prompt)",
    )
    context_compress_p.add_argument("--vault", default=None)
    context_compress_p.add_argument(
        "--print-prompt", action="store_true",
        help="Emit the canonical compression prompt for piping into an AI CLI",
    )

    topic_parser = subparsers.add_parser(
        "topic",
        help="Manage cluster topic overview + sub-topic notes",
    )
    topic_subparsers = topic_parser.add_subparsers(dest="topic_command")
    topic_scaffold = topic_subparsers.add_parser("scaffold", help="Create the overview template file")
    topic_scaffold.add_argument("--cluster", required=True)
    topic_scaffold.add_argument("--force", action="store_true", help="Overwrite if exists")
    topic_digest = topic_subparsers.add_parser("digest", help="Emit the cluster digest for an AI to read")
    topic_digest.add_argument("--cluster", required=True)
    topic_digest.add_argument("--out", help="Write digest to this file instead of stdout")
    topic_show = topic_subparsers.add_parser("show", help="Print the current overview markdown")
    topic_show.add_argument("--cluster", required=True)
    topic_propose = topic_subparsers.add_parser(
        "propose",
        help="Emit the sub-topic proposal prompt for an AI",
    )
    topic_propose.add_argument("--cluster", required=True)
    topic_propose.add_argument("--target-count", type=int, default=5)
    topic_propose.add_argument("--out")
    topic_assign = topic_subparsers.add_parser("assign", help="Assign papers to sub-topics")
    topic_assign_sub = topic_assign.add_subparsers(dest="assign_command")
    topic_assign_emit = topic_assign_sub.add_parser("emit", help="Emit the assignment prompt")
    topic_assign_emit.add_argument("--cluster", required=True)
    topic_assign_emit.add_argument("--subtopics", required=True, help="Path to proposed JSON")
    topic_assign_emit.add_argument("--out")
    topic_assign_apply = topic_assign_sub.add_parser(
        "apply",
        help="Apply AI assignments to paper frontmatter",
    )
    topic_assign_apply.add_argument("--cluster", required=True)
    topic_assign_apply.add_argument("--assignments", required=True, help="Path to assignments JSON")
    topic_build = topic_subparsers.add_parser(
        "build",
        help="Generate topics/NN_<slug>.md files from frontmatter",
    )
    topic_build.add_argument("--cluster", required=True)
    topic_list = topic_subparsers.add_parser(
        "list",
        help="List existing sub-topic notes with paper counts",
    )
    topic_list.add_argument("--cluster", required=True)

    remove_parser = subparsers.add_parser("remove", help="Remove a paper from the vault")
    remove_parser.add_argument("identifier", help="DOI or note filename slug")
    remove_parser.add_argument("--zotero", action="store_true", help="Also delete from Zotero")
    remove_parser.add_argument("--dry-run", action="store_true")

    mark_parser = subparsers.add_parser("mark", help="Update reading status of a paper")
    mark_parser.add_argument("slug", nargs="?", default=None, help="Note filename slug")
    mark_parser.add_argument(
        "--status", required=True, choices=["unread", "reading", "deep-read", "cited"]
    )
    mark_parser.add_argument("--cluster", default=None, help="Bulk-mark all notes in cluster")

    move_parser = subparsers.add_parser("move", help="Move a paper to a different cluster")
    move_parser.add_argument("slug", help="Note filename slug")
    move_parser.add_argument("--to", required=True, dest="to_cluster", help="Target cluster slug")

    add_parser = subparsers.add_parser(
        "add",
        help="Fetch a paper by DOI/arXiv ID and ingest it (one-shot)",
    )
    add_parser.add_argument("identifier", help="DOI or arXiv ID")
    add_parser.add_argument("--cluster", default=None, help="Target cluster slug")
    add_parser.add_argument(
        "--no-zotero",
        action="store_true",
        help="Data analyst mode: skip Zotero, Obsidian only",
    )
    add_parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip DOI verification",
    )

    find_parser = subparsers.add_parser("find", help="Search within vault notes")
    find_parser.add_argument("query", nargs="?", default="", help="Search query")
    find_parser.add_argument("--cluster", default=None)
    find_parser.add_argument(
        "--status", default=None, choices=["unread", "reading", "deep-read", "cited"]
    )
    find_parser.add_argument("--full", action="store_true", help="Full-text search (slower)")
    find_parser.add_argument("--json", action="store_true")
    find_parser.add_argument("--limit", type=int, default=20)
    find_parser.add_argument("--label", help="Only return papers with this label")
    find_parser.add_argument("--label-not", help="Only return papers WITHOUT this label")

    label_parser = subparsers.add_parser("label", help="Manage a paper's labels")
    label_parser.add_argument("slug", help="Paper slug (filename stem)")
    label_parser.add_argument("--set", default="", help="Comma-separated labels to set (replaces existing)")
    label_parser.add_argument("--add", default="", help="Comma-separated labels to add")
    label_parser.add_argument("--remove", default="", help="Comma-separated labels to remove")
    label_parser.add_argument("--fit-score", type=int, help="Set fit_score")
    label_parser.add_argument("--fit-reason", help="Set fit_reason")

    bulk_parser = subparsers.add_parser("label-bulk", help="Apply labels from a JSON file")
    bulk_parser.add_argument("--from-json", required=True, help="Path to labels.json")

    search_parser = subparsers.add_parser("search", help="Search for academic papers")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.add_argument("--year", help="Year range, e.g. 2024-2025 or 2024- or -2024")
    search_parser.add_argument("--min-citations", type=int, default=0)
    search_backend_group = search_parser.add_mutually_exclusive_group()
    search_backend_group.add_argument(
        "--backend",
        default=None,
        help="Comma-separated list of backends",
    )
    search_backend_group.add_argument(
        "--field",
        choices=sorted(FIELD_PRESETS.keys()),
        default=None,
        help="Backend preset for a research field",
    )
    search_backend_group.add_argument(
        "--region",
        choices=sorted(REGION_PRESETS.keys()),
        default=None,
        help="Backend preset by language/region (en, jp, kr, cjk)",
    )
    search_parser.add_argument(
        "--exclude-type",
        default="",
        help="Comma-separated list of doc types to exclude (e.g. 'book-chapter,report,paratext')",
    )
    search_parser.add_argument(
        "--peer-reviewed",
        action="store_true",
        help=_PEER_REVIEWED_HELP,
    )
    search_parser.add_argument(
        "--exclude",
        default="",
        help="Comma-or-space-separated negative keywords. Drop papers whose title or abstract contains any.",
    )
    search_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum confidence (0.0..1.0). 0.5=found by 1 backend, 0.75=2 backends, 1.0=3+",
    )
    search_parser.add_argument(
        "--backend-trace",
        action="store_true",
        help="Print per-backend hit counts before merge",
    )
    search_parser.add_argument(
        "--rank-by",
        choices=["smart", "citation", "year"],
        default="smart",
        help="Ranking strategy. smart = 2*confidence + recency + relevance (default). citation = legacy v0.15 behavior. year = recency only.",
    )
    search_parser.add_argument(
        "--adversarial",
        action="store_true",
        help="Adversarial recall: search several LLM-generated query phrasings, "
        "union the results, and print a recall-confidence verdict to stderr. "
        "Trades speed for completeness — use when a missed paper is costly.",
    )
    search_parser.add_argument(
        "--max-variants",
        type=int,
        default=5,
        help="With --adversarial: max alternative query phrasings to search (default 5).",
    )
    search_parser.add_argument(
        "--screen",
        action="store_true",
        help="Apply the fit-check BM25 relevance gate to the results. Tags "
        "each paper with a relevance score + keep/screened-out verdict and "
        "prints a screening summary; does NOT drop papers (recall-preserving). "
        "Composable with --adversarial / --rank-by / --json. With "
        "--to-papers-input the summary still prints to stderr but the emitted "
        "JSON carries no relevance annotations.",
    )
    search_parser.add_argument("--json", action="store_true", help="Emit JSON array")
    search_parser.add_argument(
        "--to-papers-input",
        action="store_true",
        help="Emit a papers_input.json document (stdout) for piping into ingest",
    )
    search_parser.add_argument(
        "--cluster",
        help="Populate sub_category with this cluster slug (used with --to-papers-input)",
    )
    search_parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify each DOI against doi.org before printing (adds 1-2s per result)",
    )
    search_parser.add_argument(
        "--enrich",
        action="store_true",
        help="Treat positional `query` as a newline-or-comma-separated candidate list "
        "(DOIs / arxiv IDs / titles) and resolve each via backend.get_paper. "
        "Use '-' to read candidates from stdin.",
    )

    websearch_parser = subparsers.add_parser(
        "websearch",
        help="Search the general web for docs, blogs, news, and GitHub pages",
    )
    websearch_parser.add_argument("query")
    websearch_parser.add_argument(
        "--provider",
        default="auto",
        choices=["auto", "tavily", "brave", "google_cse", "ddg"],
    )
    websearch_parser.add_argument("--limit", type=int, default=10)
    websearch_parser.add_argument("--max-age-days", type=int, default=None)
    websearch_parser.add_argument("--domain", default=None)
    websearch_parser.add_argument("--json", action="store_true")
    websearch_parser.add_argument(
        "--ingest-into",
        default=None,
        help="Import top hits into the given cluster via temporary .url files",
    )

    enrich_parser = subparsers.add_parser(
        "enrich",
        help="Resolve candidate identifiers (DOI / arxiv ID / title) to full paper records",
    )
    enrich_parser.add_argument(
        "candidates",
        nargs="*",
        help="Identifiers to resolve. Use '-' to read from stdin (one per line).",
    )
    enrich_parser.add_argument("--backend", default="openalex,arxiv,semantic-scholar")
    enrich_parser.add_argument("--json", action="store_true", default=True)
    enrich_parser.add_argument("--to-papers-input", action="store_true")
    enrich_parser.add_argument("--cluster", help="Populate sub_category when --to-papers-input")

    references_parser = subparsers.add_parser(
        "references",
        help="List papers cited by the given paper (its bibliography)",
    )
    references_parser.add_argument("identifier", help="DOI, arXiv ID, or S2 paper ID")
    references_parser.add_argument("--limit", type=int, default=20)
    references_parser.add_argument("--json", action="store_true")

    citations_parser = subparsers.add_parser(
        "cited-by",
        help="List papers that cite the given paper",
    )
    citations_parser.add_argument("identifier", help="DOI, arXiv ID, or S2 paper ID")
    citations_parser.add_argument("--limit", type=int, default=20)
    citations_parser.add_argument("--json", action="store_true")

    suggest_parser = subparsers.add_parser(
        "suggest",
        help="Suggest which cluster a new paper belongs to and related existing notes",
    )
    suggest_parser.add_argument(
        "identifier",
        help="DOI, arxiv ID, or quoted paper title",
    )
    suggest_parser.add_argument(
        "--top", type=int, default=5,
        help="Maximum number of related-paper suggestions (default 5)",
    )
    suggest_parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON instead of human output",
    )

    cite_parser = subparsers.add_parser(
        "cite",
        help="Export BibTeX / BibLaTeX / RIS / CSL-JSON for a paper or cluster",
    )
    cite_parser.add_argument(
        "identifier",
        nargs="?",
        default=None,
        help="DOI or raw-note filename stem (omit when using --cluster)",
    )
    cite_parser.add_argument(
        "--cluster",
        default=None,
        help="Export every paper in this cluster folder",
    )
    cite_parser.add_argument(
        "--format",
        dest="content_format",
        choices=["bibtex", "biblatex", "ris", "csljson"],
        default="bibtex",
    )
    cite_parser.add_argument(
        "--out",
        default=None,
        help="Write to this file instead of stdout",
    )
    cite_parser.add_argument(
        "--inline",
        action="store_true",
        help="Print an inline citation like (Lamparth et al., 2024)",
    )
    cite_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print a markdown citation with DOI link",
    )
    cite_parser.add_argument(
        "--style",
        choices=("apa", "chicago", "mla", "latex"),
        default="apa",
        help="Citation style for --inline (default apa)",
    )

    quote_parser = subparsers.add_parser("quote", help="Capture and manage saved paper quotes")
    quote_parser.add_argument("quote_target", nargs="*", help="Slug, or commands: list | remove <slug>")
    quote_parser.add_argument("--page", default=None, help="Page number for the captured quote")
    quote_parser.add_argument("--text", default=None, help="Quoted passage text")
    quote_parser.add_argument("--context", default="", help="Optional context note")
    quote_parser.add_argument("--cluster", default=None, help="Filter list output to one cluster slug")
    quote_parser.add_argument("--at", default=None, help="Quote captured_at timestamp to remove")

    compose_parser = subparsers.add_parser(
        "compose-draft",
        help="Assemble captured quotes into a markdown draft",
    )
    compose_parser.add_argument("--cluster", required=True, help="Cluster slug")
    compose_parser.add_argument(
        "--outline",
        default=None,
        help='Semicolon-separated section headings, e.g. "Intro;Methods;Results"',
    )
    compose_parser.add_argument(
        "--quotes",
        default=None,
        help="Comma-separated paper slugs to restrict which quotes are included",
    )
    compose_parser.add_argument(
        "--style",
        choices=("apa", "chicago", "mla", "latex"),
        default="apa",
        help="Citation style (default: apa)",
    )
    compose_parser.add_argument(
        "--no-bibliography",
        dest="include_bibliography",
        action="store_false",
        default=True,
        help="Omit the References section at the end",
    )
    compose_parser.add_argument(
        "--out",
        default=None,
        help="Output path (default: <vault>/drafts/...)",
    )

    status_parser = subparsers.add_parser("status", help="Show per-cluster reading progress")
    status_parser.add_argument("--cluster", default=None, help="Show only this cluster")

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Generate a personal HTML dashboard for the vault",
    )
    dashboard_parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="Open the dashboard in your default browser after generation",
    )
    dashboard_parser.add_argument(
        "--watch",
        action="store_true",
        help="Re-render the dashboard whenever vault state files change",
    )
    dashboard_parser.add_argument(
        "--refresh",
        type=int,
        default=10,
        help="Browser auto-refresh interval in seconds when --watch is set (default 10)",
    )
    dashboard_parser.add_argument(
        "--rich-bibtex",
        action="store_true",
        help=(
            "Fetch rich BibTeX entries from Zotero for every paper (slow: "
            "~1s/paper). Default uses an instant frontmatter fallback that "
            "is sufficient for most citations."
        ),
    )
    dashboard_parser.add_argument(
        "--sample",
        action="store_true",
        help="Open a bundled temporary sample vault dashboard (no accounts required)",
    )
    dashboard_parser.add_argument(
        "--screenshot",
        metavar="TAB",
        default=None,
        help=(
            "Capture TAB as PNG via Playwright headless. Tabs: overview, library, "
            "briefings, writing, diagnostics, manage, all. Legacy alias: crystal -> overview."
        ),
    )
    dashboard_parser.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help="Output PNG path for single-tab --screenshot",
    )
    dashboard_parser.add_argument(
        "--out-dir",
        metavar="DIR",
        default=None,
        help="Output directory for --screenshot all",
    )
    dashboard_parser.add_argument(
        "--scale",
        type=float,
        default=2.0,
        help="Device pixel ratio (default: 2.0 for Retina-grade)",
    )
    dashboard_parser.add_argument(
        "--viewport-width",
        type=int,
        default=1440,
        help="Viewport width before scaling (default: 1440)",
    )
    dashboard_parser.add_argument(
        "--viewport-height",
        type=int,
        default=900,
        help="Viewport height before scaling (default: 900)",
    )
    dashboard_parser.add_argument(
        "--full-page",
        action="store_true",
        help="Capture the entire scrolled page instead of the visible viewport",
    )
    dashboard_parser.add_argument(
        "--markdown-summary",
        action="store_true",
        help="v0.88 #11: write `.research_hub/dashboard-summary.md` — an "
             "Obsidian-internal mobile-friendly version with paper counts, "
             "ingest backlog, and doctor status. Linkable from `_HOME.md`.",
    )
    dashboard_parser.add_argument(
        "--markdown-summary-out",
        metavar="PATH",
        default=None,
        help="Override the markdown summary output path (default: "
             "`<vault>/.research_hub/dashboard-summary.md`)",
    )
    dashboard_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    vault_parser = subparsers.add_parser("vault", help="Vault maintenance commands")
    vault_subparsers = vault_parser.add_subparsers(dest="vault_command", required=True)
    vault_graph_colors = vault_subparsers.add_parser(
        "graph-colors",
        help="Refresh managed Obsidian graph color groups",
    )
    vault_graph_colors.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild research-hub-managed graph color groups",
    )
    vault_polish = vault_subparsers.add_parser(
        "polish-markdown",
        help="Upgrade paper notes to v0.42 Obsidian callout + block-ID conventions",
    )
    vault_polish.add_argument(
        "--cluster",
        default=None,
        help="Restrict to a single cluster slug (default: all clusters)",
    )
    vault_polish.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report changes without writing (default)",
    )
    vault_polish.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Actually write changes to disk",
    )

    vault_rebuild = vault_subparsers.add_parser(
        "rebuild-overviews",
        help="Re-run populate_overview + ensure_moc for every cluster (v0.87.1)",
    )
    vault_rebuild.add_argument(
        "--cluster",
        default=None,
        help="Restrict to a single cluster slug (default: walk all clusters)",
    )
    vault_rebuild.add_argument(
        "--force",
        action="store_true",
        help="Bypass the overview rebuild debounce marker",
    )
    vault_rebuild.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )
    vault_tag_migrate = vault_subparsers.add_parser(
        "tag-migrate",
        help="Backfill topic:<slug> tag into existing paper-note frontmatter (v0.87.1)",
    )
    vault_tag_migrate.add_argument(
        "--cluster",
        default=None,
        help="Restrict to a single cluster slug (default: walk all clusters)",
    )
    vault_tag_migrate.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report changes without writing (default)",
    )
    vault_tag_migrate.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Actually write the new tag into frontmatter",
    )
    vault_tag_migrate.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    vault_hub_backlink = vault_subparsers.add_parser(
        "hub-backlink-migrate",
        help="Backfill ## Hub backlink section into existing paper notes (v0.88 #5)",
    )
    vault_hub_backlink.add_argument(
        "--cluster",
        default=None,
        help="Restrict to a single cluster slug (default: walk all clusters)",
    )
    vault_hub_backlink.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report changes without writing (default)",
    )
    vault_hub_backlink.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Actually write the Hub section into note bodies",
    )
    vault_hub_backlink.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )
    vault_summary_migrate = vault_subparsers.add_parser(
        "summarize-status-migrate",
        help="Backfill summarize_status frontmatter for paper notes (v0.87.2)",
    )
    vault_summary_migrate.add_argument(
        "--cluster",
        default=None,
        help="Restrict to a single cluster slug (default: walk all clusters)",
    )
    vault_summary_migrate.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report changes without writing (default)",
    )
    vault_summary_migrate.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Actually write summarize_status frontmatter",
    )
    vault_summary_migrate.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    # v0.88.13: install-theme — copy a bundled Obsidian CSS snippet into
    # the user's vault and enable it. Discoverable shortcut so users
    # don't have to manually copy from the repo's assets/themes/ dir.
    vault_install_theme = vault_subparsers.add_parser(
        "install-theme",
        help="Install a bundled Obsidian CSS theme (v0.88.13)",
    )
    vault_install_theme.add_argument(
        "--theme",
        default="research-hub-tech",
        choices=("research-hub-tech",),
        help="Which bundled theme to install (default: research-hub-tech)",
    )
    vault_install_theme.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing snippet file at the target path",
    )
    vault_install_theme.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the snippet file + disable it in appearance.json",
    )

    # v0.88.12: cleanup-frontmatter — backfill the v0.88.4 list-dedupe
    # across pre-existing paper notes whose frontmatter was never re-
    # written since v0.88.4 shipped.
    vault_cleanup_fm = vault_subparsers.add_parser(
        "cleanup-frontmatter",
        help="Dedupe list-valued frontmatter fields (cluster_queries, tags, collections, aliases) — v0.88.12",
    )
    vault_cleanup_fm.add_argument(
        "--cluster",
        default=None,
        help="Restrict to a single cluster slug (default: walk all clusters)",
    )
    vault_cleanup_fm.add_argument(
        "--dedupe-lists",
        action="store_true",
        default=True,
        help="Dedupe list-valued fields (currently the only supported cleanup, default ON)",
    )
    vault_cleanup_fm.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report changes without writing (default)",
    )
    vault_cleanup_fm.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Actually write deduped frontmatter back to disk",
    )
    vault_cleanup_fm.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    bases_parser = subparsers.add_parser("bases", help="Obsidian Bases (.base) generator")
    bases_sub = bases_parser.add_subparsers(dest="bases_command", required=True)
    bases_emit = bases_sub.add_parser("emit", help="Emit or refresh a cluster's .base file")
    bases_emit.add_argument("--cluster", required=True)
    bases_emit.add_argument("--stdout", action="store_true", help="Print to stdout instead of writing")
    bases_emit.add_argument("--force", action="store_true", help="Overwrite existing .base file")
    bases_emit.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    migrate_parser = subparsers.add_parser(
        "migrate-yaml", help="Patch legacy notes to v0.3.x YAML spec"
    )
    migrate_parser.add_argument(
        "--assign-cluster",
        default=None,
        help="Bulk-assign all matched notes to this cluster slug",
    )
    migrate_parser.add_argument(
        "--folder",
        default=None,
        help="Restrict to this subfolder under raw/",
    )
    migrate_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing topic_cluster values",
    )
    migrate_parser.add_argument(
        "--dry-run", action="store_true", help="Report without writing"
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Run verification checks (repo integrity or paper identifier)",
    )
    verify_parser.add_argument("--doi", default=None, help="Verify a single DOI")
    verify_parser.add_argument("--arxiv", default=None, help="Verify a single arXiv ID")
    verify_parser.add_argument(
        "--paper",
        default=None,
        help="Verify by fuzzy title match against Semantic Scholar",
    )
    verify_parser.add_argument(
        "--paper-year",
        type=int,
        default=None,
        help="Optional year constraint when --paper is used",
    )
    verify_parser.add_argument(
        "--paper-author",
        action="append",
        default=None,
        help="Optional author surname(s) when --paper is used (can repeat)",
    )

    cleanup_parser = subparsers.add_parser("cleanup", help="GC accumulated files (v0.46) + wikilink dedup")
    cleanup_parser.add_argument("--bundles", action="store_true",
                                help="GC stale .research_hub/bundles/ dirs")
    cleanup_parser.add_argument("--keep-bundles", type=int, default=2,
                                help="Per-cluster bundle dirs to keep (default 2)")
    cleanup_parser.add_argument("--debug-logs", action="store_true",
                                help="GC nlm-debug-*.jsonl older than --debug-older-than days")
    cleanup_parser.add_argument("--debug-older-than", type=int, default=30,
                                help="Delete debug logs older than N days (default 30)")
    cleanup_parser.add_argument("--artifacts", action="store_true",
                                help="GC ask-*.md / brief-*.txt beyond --keep-artifacts")
    cleanup_parser.add_argument("--keep-artifacts", type=int, default=10)
    cleanup_parser.add_argument("--all", action="store_true",
                                help="Shorthand for --bundles --debug-logs --artifacts")
    cleanup_parser.add_argument("--wikilinks", action="store_true",
                                help="(v0.45 behaviour) De-dupe wikilinks in hub pages")
    cleanup_parser.add_argument("--dry-run", action="store_true", default=True,
                                help="Report without deleting (default)")
    cleanup_parser.add_argument("--apply", dest="dry_run", action="store_false",
                                help="Actually delete files")

    synth_parser = subparsers.add_parser(
        "synthesize", help="Generate cluster synthesis pages"
    )
    synth_parser.add_argument(
        "--cluster", default=None, help="Only synthesize this cluster slug"
    )
    synth_parser.add_argument(
        "--graph-colors",
        action="store_true",
        help="Also update .obsidian/graph.json cluster colors",
    )

    sync_parser = subparsers.add_parser("sync", help="Cross-system sync status and reconcile")
    sync_sub = sync_parser.add_subparsers(dest="sync_command", required=True)
    sync_status = sync_sub.add_parser("status", help="Show drift across Zotero/Obsidian/NotebookLM")
    sync_status.add_argument("--cluster", default=None)
    sync_reconcile = sync_sub.add_parser("reconcile", help="Fix Zotero-to-Obsidian drift")
    sync_reconcile.add_argument("--cluster", required=True)
    sync_reconcile.add_argument("--dry-run", action="store_true")
    sync_reconcile.add_argument("--execute", action="store_true")

    pipeline_parser = subparsers.add_parser("pipeline", help="Pipeline maintenance commands")
    pipeline_sub = pipeline_parser.add_subparsers(dest="pipeline_command", required=True)
    pipeline_repair = pipeline_sub.add_parser("repair", help="Repair pipeline orphans for a cluster")
    pipeline_repair.add_argument("--cluster", required=True)
    pipeline_repair.add_argument("--dry-run", action="store_true", default=True)
    pipeline_repair.add_argument("--execute", action="store_true")

    zotero_parser = subparsers.add_parser("zotero", help="Zotero maintenance commands")
    zotero_sub = zotero_parser.add_subparsers(dest="zotero_command", required=True)
    zotero_backfill = zotero_sub.add_parser("backfill", help="Backfill Zotero tags and notes")
    zotero_scope = zotero_backfill.add_mutually_exclusive_group()
    zotero_scope.add_argument("--cluster", default=None, help="Only backfill one cluster slug")
    zotero_scope.add_argument(
        "--all-clusters",
        action="store_true",
        default=True,
        help="Backfill all clusters (default)",
    )
    zotero_backfill.add_argument("--tags", action=argparse.BooleanOptionalAction, default=True)
    zotero_backfill.add_argument("--notes", action=argparse.BooleanOptionalAction, default=True)
    zotero_backfill.add_argument("--apply", action="store_true", help="Write changes")
    gc_parser = zotero_sub.add_parser("gc", help="Garbage-collect empty/test/orphan Zotero collections")
    gc_parser.add_argument("--apply", action="store_true")
    gc_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation only for collections matching empty + test-pattern + orphan",
    )
    gc_parser.add_argument(
        "--no-test-pattern",
        action="store_true",
        help="Skip test-pattern matching",
    )
    gc_parser.add_argument("--age-days", type=int, default=30)
    gc_parser.add_argument(
        "--respect-kept",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip collections listed in .research_hub/zotero_kept_collections.json "
             "(default on; the file is curated by `zotero mark-kept`)",
    )

    mark_kept_parser = zotero_sub.add_parser(
        "mark-kept",
        help="Mark Zotero collections as kept-by-user so `gc --respect-kept` skips them",
    )
    mark_kept_scope = mark_kept_parser.add_mutually_exclusive_group(required=True)
    mark_kept_scope.add_argument(
        "--all-orphans",
        action="store_true",
        help="Mark every currently-orphan Zotero collection as kept",
    )
    mark_kept_scope.add_argument(
        "--collection",
        action="append",
        metavar="KEY",
        help="Mark a specific Zotero collection key as kept (repeatable)",
    )
    mark_kept_scope.add_argument(
        "--remove",
        action="append",
        metavar="KEY",
        help="Remove a key from the kept list (repeatable)",
    )
    mark_kept_scope.add_argument(
        "--list",
        action="store_true",
        help="Print the current kept-collection list and exit",
    )
    mark_kept_parser.add_argument(
        "--show-counts",
        action="store_true",
        help="With --list, enrich keys with collection name + item count via Zotero API (v0.88 #10)",
    )
    mark_kept_parser.add_argument(
        "--by-pattern",
        default=None,
        metavar="REGEX",
        help="With --list, filter rows whose collection name matches the regex (case-insensitive). Implies --show-counts.",
    )
    mark_kept_parser.add_argument(
        "--note",
        default=None,
        help="Optional human note recorded with the kept list",
    )

    reparent_parser = zotero_sub.add_parser(
        "reparent-clusters",
        help="Nest existing cluster Zotero collections under a parent ('mother') collection",
    )
    reparent_parser.add_argument(
        "--parent",
        default=None,
        metavar="NAME",
        help="Name of the parent collection (default: cfg.zotero_parent_collection, "
             "i.e. 'research-hub' unless overridden in config)",
    )
    reparent_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Execute the reparenting (default: dry-run only)",
    )

    nlm_parser = subparsers.add_parser("notebooklm", help="NotebookLM operations")
    nlm_sub = nlm_parser.add_subparsers(dest="notebooklm_command", required=True)
    nlm_login = nlm_sub.add_parser(
        "login",
        help="Authenticate NotebookLM",
        description=(
            "Authenticate NotebookLM. Five paths: (1) default interactive Google "
            "sign-in in a real terminal (press ENTER when the NotebookLM homepage "
            "loads); (2) --import-from <other-vault> copies a logged-in session "
            "from another vault; (3) --from-browser [browser] imports cookies via "
            "rookiepy (requires the research-hub[browser-auth] extra; rookiepy has "
            "no prebuilt wheel for Python 3.14); (4) --wait-file PATH — sign in "
            "in the browser then create PATH (no terminal/ENTER; scriptable); "
            "(5) --auto-detect — fully automatic, research-hub polls the "
            "patchright Chromium cookies and saves when notebooklm.google.com "
            "appears (no terminal, no wait-file, no click.confirm response)."
        ),
        epilog=(
            "Examples:\n"
            "  research-hub notebooklm login\n"
            "  research-hub notebooklm login --import-from <other-vault>\n"
            "  research-hub notebooklm login --from-browser chrome\n"
            "  research-hub notebooklm login --auto-detect"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    nlm_login.add_argument(
        "--import-from",
        default=None,
        metavar="VAULT_PATH",
        help="v0.70.1: copy a logged-in NotebookLM session profile from another vault "
             "instead of running the interactive Google sign-in. VAULT_PATH points at "
             "the OTHER vault root (the one already logged in). Skips the browser dance.",
    )
    nlm_login.add_argument(
        "--overwrite",
        action="store_true",
        help="With --import-from: replace the current vault's logged-in session if one exists.",
    )
    nlm_login.add_argument(
        "--wait-file",
        default=None,
        metavar="PATH",
        help="Non-interactive: instead of pressing ENTER, sign in in the "
             "browser window then create this file (e.g. `touch PATH`, or an "
             "automation wrapper does it). research-hub polls for it and "
             "saves the session automatically. No terminal/ENTER needed.",
    )
    nlm_login.add_argument(
        "--wait-timeout",
        type=int,
        default=300,
        metavar="SECONDS",
        help="With --wait-file or --auto-detect: max seconds to wait for "
             "the detection signal before failing closed (default: 300; "
             "nothing is saved on timeout).",
    )
    nlm_login.add_argument(
        "--auto-detect",
        action="store_true",
        help="Fully automatic: research-hub polls the patchright Chromium "
             "profile's cookies for notebooklm.google.com once the browser "
             "opens. When you sign in and land on the NotebookLM homepage, "
             "the session is saved automatically. No terminal/ENTER, no "
             "wait-file touch, no click.confirm response needed.",
    )
    nlm_login.add_argument(
        "--from-browser",
        nargs="?",
        const="auto",
        default=None,
        metavar="BROWSER",
        choices=[
            "auto", "arc", "brave", "chrome", "chromium", "edge", "firefox",
            "ie", "librewolf", "octo", "opera", "opera-gx", "safari",
            "vivaldi", "zen",
        ],
        help=(
            "Non-interactive login: import Google cookies from an already-logged-in "
            "browser via rookiepy (no Playwright popup, no terminal ENTER needed). "
            "Optionally specify a browser: chrome, firefox, edge, brave, arc, "
            "chromium, safari, vivaldi, zen, librewolf, opera, opera-gx, ie, octo. "
            "Omit the value (bare --from-browser) for auto-detection. "
            "Requires: pip install 'research-hub[browser-auth]'. "
            "Precedence: --import-from > --from-browser > interactive login."
        ),
    )
    nlm_keepalive = nlm_sub.add_parser(
        "keepalive",
        help="Rotate and persist NLM session cookies to prevent idle expiry",
    )
    nlm_keepalive.add_argument(
        "--loop",
        action="store_true",
        default=False,
        help="Run continuously, sleeping --interval seconds between calls (for nohup use)",
    )
    nlm_keepalive.add_argument(
        "--interval",
        type=int,
        default=900,
        metavar="SEC",
        help=(
            "Seconds between keepalive calls in --loop mode "
            "(default: 900 = 15 min; floor: 600 = 10 min). Google's "
            "PSIDTS cookies expire every ~3-4 hours, so the cadence must "
            "stay well below that — the old hour-defaults left tiny safety "
            "margin and routinely lost races on flaky networks."
        ),
    )
    nlm_keepalive.add_argument(
        "--install-windows-task",
        action="store_true",
        default=False,
        help=(
            "Build and print the schtasks command that registers a Windows Scheduled Task "
            "running 'python -m research_hub notebooklm keepalive' every --interval-minutes m. "
            "Without --yes this is a DRY-RUN only (prints command, registers nothing)."
        ),
    )
    nlm_keepalive.add_argument(
        "--uninstall-windows-task",
        action="store_true",
        default=False,
        help=(
            "Remove the Windows Scheduled Task registered by --install-windows-task. "
            "Without --yes this is a DRY-RUN only."
        ),
    )
    nlm_keepalive.add_argument(
        "--interval-minutes",
        type=int,
        default=15,
        metavar="MINUTES",
        help=(
            "Minutes between task runs when registering the Scheduled Task "
            "(default: 15). Uses /SC MINUTE under the hood — minute-cadence "
            "is required because PSIDTS expires every ~3-4 hours, so an "
            "hourly cadence (the old default) left ~3 retries per expiry "
            "window and routinely lost races on flaky networks."
        ),
    )
    # Back-compat alias: --interval-hours is deprecated in favour of
    # --interval-minutes but kept as a wrapper so existing automation
    # scripts don't break on upgrade. Multiplied to minutes at dispatch.
    nlm_keepalive.add_argument(
        "--interval-hours",
        type=int,
        default=None,
        metavar="HOURS",
        help=(
            "Deprecated alias for --interval-minutes (multiplied by 60). "
            "Prefer --interval-minutes; see its help text for why "
            "minute-cadence is required."
        ),
    )
    nlm_keepalive.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help=(
            "Confirm system mutation for --install-windows-task / --uninstall-windows-task. "
            "Without this flag those options only print the schtasks command."
        ),
    )
    nlm_bundle = nlm_sub.add_parser("bundle", help="Export a drag-drop folder for NotebookLM")
    nlm_bundle.add_argument("--cluster", required=True)
    nlm_bundle.add_argument(
        "--download-pdfs",
        action="store_true",
        help="Fetch missing PDFs from arxiv/Unpaywall before falling back to URL",
    )
    nlm_upload = nlm_sub.add_parser("upload", help="Auto-upload bundle to NotebookLM")
    nlm_upload.add_argument("--cluster", required=True)
    nlm_upload.add_argument("--dry-run", action="store_true")
    nlm_upload.add_argument("--headless", action="store_true", default=False)
    nlm_upload.add_argument("--visible", dest="headless", action="store_false")
    nlm_upload.add_argument("--create-if-missing", action="store_true", default=True)
    nlm_upload.add_argument(
        "--over-cap-strategy",
        choices=["fail", "top-n-recent", "top-n-cited", "fit-score", "shard"],
        default="fail",
        help="How to handle clusters above NotebookLM's 50-source cap (default: fail)",
    )
    nlm_upload.add_argument(
        "--shard-size",
        type=int,
        default=50,
        help="Sources per NotebookLM shard when --over-cap-strategy shard is used",
    )
    nlm_upload.add_argument(
        "--include-suspect-urls",
        action="store_true",
        default=False,
        help=(
            "Upload URL sources even when the pre-upload quality check flags them as "
            "likely error pages (default: skip and record in report.errors). "
            "A warning is still appended to the report."
        ),
    )
    nlm_shard = nlm_sub.add_parser("shard", help="Split a cluster into NotebookLM source-cap shards")
    nlm_shard.add_argument("--cluster", required=True)
    nlm_shard.add_argument("--strategy", choices=["recent", "cited", "fit"], required=True)
    nlm_shard.add_argument("--shard-size", type=int, default=50)
    nlm_shard.add_argument("--dry-run", action="store_true")
    nlm_shard.add_argument("--headless", action="store_true", default=False)
    nlm_shard.add_argument("--visible", dest="headless", action="store_false")
    nlm_download = nlm_sub.add_parser(
        "download",
        help="Download a generated NotebookLM artifact (briefing) back to the vault",
    )
    nlm_download.add_argument("--cluster", required=True)
    nlm_download.add_argument(
        "--type",
        choices=["brief", "slide-deck"],
        default="brief",
        help="Artifact type to download (v0.87: brief, slide-deck; audio/mind-map/video planned for v0.87.1)",
    )
    nlm_download.add_argument(
        "--slide-format",
        choices=["pdf", "pptx"],
        default="pdf",
        help="When --type slide-deck, choose file format (default: pdf)",
    )
    nlm_download.add_argument("--headless", action="store_true", default=False)
    nlm_download.add_argument("--visible", dest="headless", action="store_false")
    nlm_download.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )
    nlm_read_brief = nlm_sub.add_parser(
        "read-briefing",
        help="Print the most recently downloaded briefing for a cluster",
    )
    nlm_read_brief.add_argument("--cluster", required=True)
    nlm_generate = nlm_sub.add_parser("generate", help="Trigger NotebookLM artifact generation")
    nlm_generate.add_argument("--cluster", required=True)
    nlm_generate.add_argument(
        "--type",
        choices=["brief", "audio", "mind-map", "video", "slide-deck", "all"],
        default="brief",
    )
    nlm_generate.add_argument("--headless", action="store_true", default=False)
    nlm_generate.add_argument("--visible", dest="headless", action="store_false")
    nlm_ask = nlm_sub.add_parser(
        "ask",
        help="Ask an ad-hoc question against a cluster's NotebookLM notebook",
    )
    nlm_ask.add_argument("--cluster", required=True)
    nlm_ask.add_argument("--question", required=True)
    nlm_ask.add_argument("--headless", action="store_true", default=True)
    nlm_ask.add_argument("--visible", dest="headless", action="store_false")
    nlm_ask.add_argument("--timeout", type=int, default=120)

    fit_parser = subparsers.add_parser("fit-check", help="Multi-gate fit-check for clusters")
    fit_sub = fit_parser.add_subparsers(dest="fit_check_command")

    fit_emit = fit_sub.add_parser("emit", help="Emit the Gate 1 scoring prompt for an AI")
    fit_emit.add_argument("--cluster", required=True)
    fit_emit.add_argument("--candidates", required=True)
    fit_emit.add_argument("--definition")
    fit_emit.add_argument("--out")
    fit_emit.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    fit_apply = fit_sub.add_parser("apply", help="Apply AI scores and emit accepted papers")
    fit_apply.add_argument("--cluster", required=True)
    fit_apply.add_argument("--candidates", required=True)
    fit_apply.add_argument("--scored", required=True)
    fit_apply.add_argument("--threshold", type=int, default=3)
    fit_apply.add_argument(
        "--auto-threshold",
        action="store_true",
        help="Compute threshold as median(scores) - 1 (clamped [2, 5])",
    )
    fit_apply.add_argument("--out")
    fit_apply.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    fit_audit = fit_sub.add_parser("audit", help="Parse the latest briefing for off-topic flags")
    fit_audit.add_argument("--cluster", required=True)

    fit_drift = fit_sub.add_parser("drift", help="Emit a drift-check prompt")
    fit_drift.add_argument("--cluster", required=True)
    fit_drift.add_argument("--threshold", type=int, default=3)
    fit_apply_labels = fit_sub.add_parser(
        "apply-labels",
        help="Tag rejected papers as deprecated from the sidecar",
    )
    fit_apply_labels.add_argument("--cluster", required=True)

    autofill_parser = subparsers.add_parser(
        "autofill",
        help="Auto-fill paper note body content via AI emit/apply",
    )
    autofill_sub = autofill_parser.add_subparsers(dest="autofill_command")
    autofill_emit = autofill_sub.add_parser("emit", help="Emit autofill prompt for an AI")
    autofill_emit.add_argument("--cluster", required=True)
    autofill_emit.add_argument("--out")
    autofill_apply = autofill_sub.add_parser("apply", help="Apply AI-supplied content to paper notes")
    autofill_apply.add_argument("--cluster", required=True)
    autofill_apply.add_argument("--scored", required=True, help="Path to AI-produced JSON")

    crystal_parser = subparsers.add_parser("crystal", help="Manage pre-computed canonical crystals")
    crystal_sub = crystal_parser.add_subparsers(dest="crystal_command")
    crystal_emit = crystal_sub.add_parser("emit", help="Emit a crystal-generation prompt for an AI")
    crystal_emit.add_argument("--cluster", required=True)
    crystal_emit.add_argument("--questions", help="Comma-separated question slugs to emit")
    crystal_emit.add_argument("--out")
    crystal_emit.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )
    crystal_apply = crystal_sub.add_parser("apply", help="Apply AI-generated crystals")
    crystal_apply.add_argument("--cluster", required=True)
    crystal_apply.add_argument("--scored", required=True, help="Path to JSON produced by AI")
    crystal_apply.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )
    crystal_list = crystal_sub.add_parser("list", help="List crystals for a cluster")
    crystal_list.add_argument("--cluster", required=True)
    crystal_read = crystal_sub.add_parser("read", help="Read a specific crystal")
    crystal_read.add_argument("--cluster", required=True)
    crystal_read.add_argument("--slug", required=True)
    crystal_read.add_argument("--level", choices=["tldr", "gist", "full"], default="gist")
    crystal_check = crystal_sub.add_parser("check", help="Check crystal staleness")
    crystal_check.add_argument("--cluster", required=True)

    summarize_parser = subparsers.add_parser(
        "summarize",
        help="Fill per-paper Key Findings + Methodology + Relevance via LLM CLI",
    )
    summarize_parser.add_argument("--cluster", required=True)
    summarize_parser.add_argument(
        "--llm-cli",
        help="Override the auto-detected LLM CLI on PATH; built-ins include claude, codex, gemini, opencode, aichat, cursor, plus custom adapters",
    )
    summarize_parser.add_argument(
        "--apply",
        action="store_true",
        help="Write summaries back to Obsidian + Zotero (default: print prompt + JSON only)",
    )
    summarize_parser.add_argument(
        "--no-zotero",
        action="store_true",
        help="Skip Zotero child-note write (Obsidian-only)",
    )
    summarize_parser.add_argument(
        "--no-obsidian",
        action="store_true",
        help="Skip Obsidian markdown write (Zotero-only)",
    )
    summarize_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    memory_parser = subparsers.add_parser("memory", help="Manage structured cluster memory registries")
    memory_sub = memory_parser.add_subparsers(dest="memory_command")
    memory_emit = memory_sub.add_parser("emit", help="Emit a memory-extraction prompt for an AI")
    memory_emit.add_argument("--cluster", required=True)
    memory_apply = memory_sub.add_parser("apply", help="Apply AI-generated cluster memory")
    memory_apply.add_argument("--cluster", required=True)
    memory_apply.add_argument("--scored", required=True, help="Path to JSON produced by AI")
    memory_list = memory_sub.add_parser("list", help="List memory records for a cluster")
    memory_list.add_argument("--cluster", required=True)
    memory_list.add_argument("--kind", choices=["entities", "claims", "methods"])
    memory_read = memory_sub.add_parser("read", help="Read the full cluster memory registry")
    memory_read.add_argument("--cluster", required=True)

    paper_parser = subparsers.add_parser("paper", help="Paper curation operations")
    paper_sub = paper_parser.add_subparsers(dest="paper_command")
    lookup_doi_p = paper_sub.add_parser("lookup-doi", help="Look up and write DOI metadata from Crossref")
    lookup_doi_p.add_argument("slug", nargs="?", help="Paper slug (omit with --batch)")
    lookup_doi_p.add_argument("--cluster", help="Cluster slug for --batch mode")
    lookup_doi_p.add_argument("--batch", action="store_true", help="Process every paper missing DOI in a cluster")
    find_p = paper_sub.add_parser(
        "find",
        help="Search papers by title, DOI, or author across all clusters",
    )
    find_p.add_argument("query", help="Search query string")
    find_p.add_argument("--cluster", default=None, help="Restrict to one cluster slug")
    find_p.add_argument("--by", choices=["title", "doi", "author", "any"], default="any")
    add_to_cluster_p = paper_sub.add_parser(
        "add-to-cluster",
        help="Add a paper to a second cluster via topic_cluster frontmatter",
    )
    add_to_cluster_p.add_argument("slug_or_doi", help="Paper filename stem or DOI")
    add_to_cluster_p.add_argument("--cluster", required=True, dest="target_cluster")
    add_to_cluster_p.add_argument("--dry-run", action="store_true")
    gaps_p = paper_sub.add_parser(
        "gaps",
        help="Identify research gaps for a cluster using LLM analysis",
    )
    gaps_p.add_argument("--cluster", required=True, help="Cluster slug to analyze")
    gaps_p.add_argument(
        "--compare",
        default=None,
        dest="compare_cluster",
        help="Second cluster slug for cross-cluster gap analysis",
    )
    gaps_p.add_argument(
        "--no-llm",
        action="store_true",
        help="Only emit the prompt file without invoking an LLM CLI",
    )
    gaps_p.add_argument(
        "--llm-cli",
        default=None,
        help="Force a specific LLM CLI (auto-detected by default)",
    )
    prune_p = paper_sub.add_parser("prune", help="Move or delete labeled papers")
    prune_p.add_argument("--cluster", required=True)
    prune_p.add_argument("--label", default="deprecated")
    prune_p.add_argument("--archive", action="store_true", default=True, help="Move to raw/_archive/<cluster>/ (default)")
    prune_p.add_argument("--delete", action="store_true", help="Hard-delete instead of archive")
    prune_p.add_argument("--zotero", action="store_true", help="Also delete Zotero items (only with --delete)")
    prune_p.add_argument("--dry-run", action="store_true")
    unarch_p = paper_sub.add_parser("unarchive", help="Restore an archived paper back to active cluster")
    unarch_p.add_argument("--cluster", required=True)
    unarch_p.add_argument("--slug", required=True)
    bulk_relabel_p = paper_sub.add_parser("bulk-relabel", help="Replace a label across paper notes")
    bulk_relabel_p.add_argument("--from", dest="from_label", required=True)
    bulk_relabel_p.add_argument("--to", dest="to_label", required=True)
    bulk_relabel_p.add_argument("--cluster", default=None)
    bulk_relabel_group = bulk_relabel_p.add_mutually_exclusive_group()
    bulk_relabel_group.add_argument("--dry-run", dest="apply", action="store_false", help="Preview only (default)")
    bulk_relabel_group.add_argument("--apply", dest="apply", action="store_true", help="Write notes and Zotero tags")
    bulk_relabel_p.set_defaults(apply=False)
    bulk_relabel_p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )
    bulk_move_p = paper_sub.add_parser("bulk-move", help="Move selected papers to another cluster")
    slug_group = bulk_move_p.add_mutually_exclusive_group(required=True)
    slug_group.add_argument("--slugs", default=None, help="Comma-separated paper slugs")
    slug_group.add_argument("--slugs-file", default=None, help="File with one slug per line or comma-separated slugs")
    bulk_move_p.add_argument("--to-cluster", required=True)
    bulk_move_group = bulk_move_p.add_mutually_exclusive_group()
    bulk_move_group.add_argument("--dry-run", dest="apply", action="store_false", help="Preview only (default)")
    bulk_move_group.add_argument("--apply", dest="apply", action="store_true", help="Move files and update Zotero")
    bulk_move_p.set_defaults(apply=False)
    bulk_move_p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )
    bulk_delete_p = paper_sub.add_parser("bulk-delete", help="Delete papers whose frontmatter tags include a tag")
    bulk_delete_p.add_argument("--by-tag", required=True)
    bulk_delete_group = bulk_delete_p.add_mutually_exclusive_group()
    bulk_delete_group.add_argument("--dry-run", dest="apply", action="store_false", help="Preview only (default)")
    bulk_delete_group.add_argument("--apply", dest="apply", action="store_true", help="Delete notes and move Zotero items to trash")
    bulk_delete_p.set_defaults(apply=False)
    bulk_delete_p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )

    retype_p = paper_sub.add_parser(
        "retype",
        help=(
            "Change a paper's Zotero itemType (v0.88.2): creates a new item "
            "of the target type, copies shared fields, trashes the old item, "
            "and updates the Obsidian note's zotero-key. Works around the "
            "Zotero API's PATCH-itemType ban."
        ),
    )
    retype_p.add_argument("--slug", required=True, help="Paper slug (frontmatter file stem)")
    retype_p.add_argument(
        "--to-type",
        required=True,
        help="Target Zotero itemType (e.g. conferencePaper, dataset, bookSection, report)",
    )
    retype_group = retype_p.add_mutually_exclusive_group()
    retype_group.add_argument("--dry-run", dest="apply", action="store_false", help="Preview only (default)")
    retype_group.add_argument("--apply", dest="apply", action="store_true", help="Actually create + trash + rewrite frontmatter")
    retype_p.set_defaults(apply=False)
    retype_p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report on stdout (v0.89)",
    )
    enrich_existing = paper_sub.add_parser(
        "enrich-existing",
        help="Re-fetch DOI metadata to fill empty Zotero/Obsidian fields",
    )
    enrich_existing.add_argument("--cluster", required=True)
    enrich_existing.add_argument("--limit", type=int, default=0, help="0 = no limit")
    enrich_existing.add_argument("--apply", action="store_true")
    enrich_existing.add_argument("--rate-limit", type=float, default=2.0)
    attach_pdfs_p = paper_sub.add_parser(
        "attach-pdfs",
        help="Find OA PDFs and attach them to Zotero as local imported_file items",
    )
    attach_pdfs_p.add_argument("--cluster", required=True)
    attach_pdfs_p.add_argument("--limit", type=int, default=0)
    attach_pdfs_p.add_argument("--apply", action="store_true")
    attach_pdfs_p.add_argument("--rate-limit", type=float, default=2.0)
    attach_pdfs_p.add_argument(
        "--keep-url-fallback",
        action="store_true",
        help="When PDF download fails, fall back to an imported_url link-only attachment",
    )
    attach_pdfs_p.add_argument(
        "--max-pdf-size",
        type=int,
        dest="max_pdf_size_mb",
        default=25,
        help="Reject PDF downloads larger than this many megabytes (default: 25)",
    )
    attach_pdfs_p.add_argument(
        "--include-publisher-link",
        action="store_true",
        help="When no PDF found, attach a linked publisher-page bookmark (clickable from Zotero)",
    )
    upgrade_pdfs_p = paper_sub.add_parser(
        "upgrade-pdfs",
        help="Convert imported_url PDF attachments to imported_file by downloading and re-uploading them",
    )
    upgrade_pdfs_p.add_argument("--cluster", required=True)
    upgrade_pdfs_p.add_argument("--limit", type=int, default=0, help="0 = no limit")
    upgrade_pdfs_p.add_argument("--apply", action="store_true")
    resummarize_p = paper_sub.add_parser(
        "resummarize",
        help="Re-run summarize only for notes whose Summary block still contains [TODO]",
    )
    resummarize_p.add_argument("--cluster", required=True)
    resummarize_p.add_argument("--apply", action="store_true")
    resummarize_p.add_argument("--llm-cli", default=None)
    paper_summarize_p = paper_sub.add_parser(
        "summarize",
        help="Run the v0.87.2 summarize_status pending queue",
    )
    paper_summarize_p.add_argument("--pending", action="store_true")
    paper_summarize_p.add_argument("--cluster", default=None)
    paper_summarize_p.add_argument(
        "--cli",
        default="claude",
        help="LLM CLI to invoke; built-ins include claude, codex, gemini, opencode, aichat, cursor, plus custom adapters",
    )
    paper_summarize_p.add_argument("--max-papers", type=int, default=None)
    paper_summarize_p.add_argument("--dry-run", action="store_true")

    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover papers for a cluster (search + fit-check wrapper)",
    )
    discover_sub = discover_parser.add_subparsers(dest="discover_command")

    new_p = discover_sub.add_parser("new", help="Run search + emit fit-check prompt, stash for continue")
    new_p.add_argument("--cluster", required=True)
    new_p.add_argument("--query", required=True)
    new_p.add_argument("--year", help="Year range e.g. 2024-2025")
    new_p.add_argument("--min-citations", type=int, default=0)
    discover_backend_group = new_p.add_mutually_exclusive_group()
    discover_backend_group.add_argument("--backend", default=None)
    discover_backend_group.add_argument(
        "--field",
        choices=sorted(FIELD_PRESETS.keys()),
        default=None,
    )
    discover_backend_group.add_argument(
        "--region",
        choices=sorted(REGION_PRESETS.keys()),
        default=None,
    )
    new_p.add_argument("--exclude-type", default="")
    new_p.add_argument("--exclude", default="")
    new_p.add_argument("--min-confidence", type=float, default=0.0)
    new_p.add_argument("--rank-by", choices=["smart", "citation", "year"], default="smart")
    new_p.add_argument("--limit", type=int, default=50)
    new_p.add_argument("--definition", help="Cluster definition")
    new_p.add_argument("--from-variants", help="Path to a JSON file with query variations from `discover variants`")
    new_p.add_argument(
        "--auto-variants",
        action="store_true",
        default=True,
        help="Auto-derive query variations from cluster seed_keywords + definition (default: on; --from-variants takes precedence)",
    )
    new_p.add_argument(
        "--no-auto-variants",
        dest="auto_variants",
        action="store_false",
        help="Disable automatic query-variation derivation",
    )
    new_p.add_argument(
        "--expand-semantic",
        action="store_true",
        default=True,
        help="Expand candidates via S2 recommendations at lower confidence (default: on)",
    )
    new_p.add_argument(
        "--no-expand-semantic",
        dest="expand_semantic",
        action="store_false",
        help="Disable Semantic Scholar recommendations expansion",
    )
    new_p.add_argument(
        "--per-backend-factor",
        type=int,
        default=None,
        help="Per-backend search limit multiplier (default: 4, the module constant)",
    )
    new_p.add_argument(
        "--expand-auto",
        action="store_true",
        help="Auto-pick top 3 keyword results as seeds for citation expansion",
    )
    new_p.add_argument("--expand-from", default="", help="Comma-separated DOIs to use as citation expansion seeds")
    new_p.add_argument("--expand-hops", type=int, default=1, help="Citation expansion hops (default 1, bounded)")
    new_p.add_argument("--seed-dois", default="", help="Comma-separated DOIs to inject as seeds")
    new_p.add_argument("--seed-dois-file", help="File with one DOI per line")
    new_p.add_argument("--include-existing", action="store_true", help="Do NOT dedup against existing cluster papers")
    new_p.add_argument("--prompt-out", help="Write fit-check prompt to file (default: stdout)")

    continue_p = discover_sub.add_parser("continue", help="Apply AI scores, emit papers_input.json")
    continue_p.add_argument("--cluster", required=True)
    continue_p.add_argument("--scored", required=True, help="Path to AI-produced scored JSON")
    continue_p.add_argument("--threshold", type=int)
    continue_p.add_argument("--auto-threshold", action="store_true")
    continue_p.add_argument("--out", help="Write papers_input.json here (default: stash dir)")

    status_p = discover_sub.add_parser("status", help="Show discover stage for a cluster")
    status_p.add_argument("--cluster", required=True)

    clean_p = discover_sub.add_parser("clean", help="Remove stashed discover state")
    clean_p.add_argument("--cluster", required=True)

    variants_p = discover_sub.add_parser("variants", help="Emit a query-variation prompt for an AI to consume")
    variants_p.add_argument("--cluster", required=True)
    variants_p.add_argument("--query", required=True)
    variants_p.add_argument("--count", type=int, default=4)
    variants_p.add_argument("--out", help="Write to file instead of stdout")

    return parser


def _main_dispatch(args, parser) -> int:
    # v0.90.0 W11 (G4 #20) fix: bare `research-hub` (no subcommand) prints
    # help and exits 0 BEFORE any config probing — fresh users with no
    # config.json should see the subcommand list, not a config-missing
    # error. Code-review caught the previous placement (after require_config)
    # which still crashed for fresh installs. Explicit `research-hub run`
    # still routes to the pipeline below.
    if args.command is None:
        parser.print_help()
        return 0

    # Propagate any test-patched get_config into the extracted cli_* modules
    # before dispatching to a handler that may live outside cli.py.
    _sync_cli_dependencies()

    _warn_cli_deprecated_alias_from_args(args)

    exempt_commands = {"init", "setup", "doctor", "install", "examples", "where", "config", "ezproxy", "package-dxt", "describe", "context"}

    if args.command not in exempt_commands and get_config is require_config.__globals__["get_config"]:
        require_config()

    if args.command == "run":
        run_kwargs = {
            "dry_run": getattr(args, "dry_run", False),
            "cluster_slug": getattr(args, "cluster", None),
            "query": getattr(args, "query", None),
            "verify": getattr(args, "verify", True),
            "allow_library_duplicates": getattr(args, "allow_library_duplicates", False),
            "fit_check": getattr(args, "fit_check", False),
            "fit_check_threshold": getattr(args, "fit_check_threshold", 3),
            "no_fit_check_auto_labels": getattr(args, "no_fit_check_auto_labels", False),
            "batch_label": getattr(args, "batch_label", None),
            "allow_archived_cluster": bool(getattr(args, "cluster", None)),
        }
        if getattr(args, "with_pdfs", False):
            run_kwargs["with_pdfs"] = True
        rc = run_pipeline(**run_kwargs)
        if rc == 0 and getattr(args, "fit_check", False) and not getattr(args, "no_fit_check_auto_labels", False):
            from research_hub.paper import apply_fit_check_to_labels

            cfg = get_config()
            result = apply_fit_check_to_labels(cfg, args.cluster)
            print(f"auto-labeled {len(result['tagged'])} paper(s) as deprecated from fit-check sidecar")
        return rc
    if args.command == "init":
        if args.field:
            from research_hub.onboarding import run_field_wizard

            cfg = get_config()
            result = run_field_wizard(
                cfg,
                field=args.field,
                cluster_slug=args.cluster,
                cluster_name=args.name,
                query=args.query,
                definition=args.definition,
                non_interactive=args.non_interactive,
            )
            print(f"Created cluster {result.cluster_slug} with {result.candidate_count} candidates")
            print()
            print("Next steps:")
            for step in result.next_steps:
                print(f"  {step}")
            return 0
        from research_hub.init_wizard import run_init

        return run_init(
            vault_root=args.vault,
            zotero_key=args.zotero_key,
            zotero_library_id=args.zotero_library_id,
            non_interactive=args.non_interactive,
            persona=args.persona,
            no_browser=args.no_browser,
            sample=args.sample,
        )
    if args.command == "tidy":
        from research_hub.tidy import run_tidy

        report = run_tidy(
            apply_cleanup=args.apply_cleanup,
            print_progress=True,
            cluster_slug=args.cluster,
        )
        failed = [s for s in report.steps if not s.ok]
        return 0 if not failed else 1

    if args.command == "doctor":
        return _cmd_doctor(args, emit_json=getattr(args, "json", False))
    if args.command == "config":
        if args.config_command == "encrypt-secrets":
            return _config_encrypt_secrets()
        if args.config_command == "set":
            return _config_set(args.key, args.value, force=getattr(args, "force", False))
        parser.error("config requires a subcommand")
        return 2
    if args.command == "ezproxy":
        from research_hub.ezproxy import login as ezproxy_login
        from research_hub.ezproxy import resolve_config

        cfg = get_config()
        ezcfg = resolve_config(cfg)
        if args.ezproxy_command == "login":
            return ezproxy_login(
                ezcfg.cookies_path,
                url_template=ezcfg.url_template,
                sentinel_url=args.sentinel_url,
            )
        if args.ezproxy_command == "status":
            print(f"ezproxy_url_template: {ezcfg.url_template or '(unset)'}")
            print(f"cookies_path: {ezcfg.cookies_path}")
            print(f"cookies file exists: {ezcfg.cookies_path.exists()}")
            print(f"enabled: {ezcfg.enabled}")
            return 0
        parser.error("ezproxy requires a subcommand")
        return 2
    if args.command == "examples":
        from research_hub.examples import copy_example_as_cluster, list_examples, load_example

        if args.examples_command == "list":
            for ex in list_examples():
                print(f"  {ex['slug']:35s} ({ex['field']:7s}) - {ex['name']}")
            return 0
        if args.examples_command == "show":
            try:
                ex = load_example(args.name)
            except FileNotFoundError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(json.dumps(ex, indent=2, ensure_ascii=False))
            return 0
        if args.examples_command == "copy":
            cfg = get_config()
            try:
                slug = copy_example_as_cluster(cfg, args.name, cluster_slug=args.cluster)
                ex = load_example(args.name)
            except (FileNotFoundError, ValueError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(f"copied {args.name} as cluster {slug}")
            print(
                f"next: research-hub discover new --cluster {slug} --query '{ex['query']}' --field {ex['field']}"
            )
            return 0
        parser.error("examples requires a subcommand")
        return 2
    if args.command == "install":
        return _cmd_install(args)
    if args.command == "setup":
        from research_hub.setup_command import run_setup

        return run_setup(args)
    if args.command == "where":
        return _cmd_where(args)
    if args.command == "package-dxt":
        return _package_dxt(args.out)
    if args.command == "describe":
        from research_hub.describe import describe_manifest

        print(describe_manifest(filter=args.filter, pretty=args.pretty, parser=parser))
        return 0
    if args.command == "ask":
        cfg = require_config()
        from research_hub.workflows import ask_cluster as _ask
        result = _ask(cfg, args.cluster, question=args.question, detail=args.detail)
        import json as _json
        print(_json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.command == "serve":
        cfg = get_config()
        return _cmd_serve(args, cfg)
    if args.command == "plan":
        from research_hub.planner import plan_to_dict, plan_workflow
        try:
            cfg = get_config()
        except Exception:
            cfg = None
        plan = plan_workflow(args.intent, cfg=cfg)
        if args.json:
            import json as _json
            print(_json.dumps(plan_to_dict(plan), ensure_ascii=False, indent=2))
            return 0
        print()
        print(f"  intent: {plan.intent_summary}")
        print()
        print(f"  suggested topic:    {plan.suggested_topic}")
        print(f"  suggested cluster:  {plan.suggested_cluster_slug}")
        print(f"  max_papers:         {plan.suggested_max_papers}")
        print(f"  do_nlm:             {plan.suggested_do_nlm}")
        print(f"  do_crystals:        {plan.suggested_do_crystals}")
        print(f"  persona:            {plan.suggested_persona}")
        print(f"  field:              {plan.suggested_field or '(auto default)'}")
        print(f"  est. duration:      ~{plan.estimated_duration_sec}s")
        if plan.existing_cluster_match:
            print(f"  existing cluster:   {plan.existing_cluster_match} ({plan.existing_cluster_paper_count} papers)")
        for w in plan.warnings:
            print(f"  [WARN] {w}")
        if plan.clarifying_questions:
            print()
            print("  Please confirm before running:")
            for i, q in enumerate(plan.clarifying_questions, 1):
                print(f"    {i}. {q}")
        print()
        args_flat = plan.next_call.get("args", {})
        cluster_arg = f'--cluster {args_flat["cluster_slug"]} ' if args_flat.get("cluster_slug") else ""
        field_arg = f'--field {args_flat["field"]} ' if args_flat.get("field") else ""
        crystals_arg = "--with-crystals " if args_flat.get("do_crystals") else ""
        no_nlm_arg = "--no-nlm " if not args_flat.get("do_nlm", True) else ""
        print("  When ready, run:")
        print(f'    research-hub auto "{args_flat.get("topic", "")}" '
              f'{cluster_arg}{field_arg}--max-papers {args_flat.get("max_papers", 8)} '
              f'{no_nlm_arg}{crystals_arg}'.rstrip())
        print()
        return 0
    if args.command == "auto":
        if args.full_auto:
            # --with-pdfs and --with-summary are on by default since the
            # BooleanOptionalAction flips; we intentionally do NOT force
            # them to True here so an explicit --no-with-pdfs or
            # --no-with-summary is respected even under --full-auto.
            args.with_crystals = True
        # Parse --year RANGE → (year_from, year_to). None on either side
        # = unbounded; both None = no year filter applied.
        year_from, year_to = (
            _parse_year_range(args.year) if getattr(args, "year", None) else (None, None)
        )
        return _auto(
            topic=args.topic,
            cluster_slug=args.cluster,
            cluster_name=args.cluster_name,
            max_papers=args.max_papers,
            field=args.field,
            do_nlm=not args.no_nlm,
            do_crystals=args.with_crystals,
            do_cluster_overview=not args.no_cluster_overview,
            do_fit_check=not args.no_fit_check,
            fit_check_threshold=args.fit_check_threshold,
            no_llm_fit_check=args.no_llm_fit_check,
            zotero_batch_size=args.zotero_batch_size,
            llm_cli=args.llm_cli,
            dry_run=args.dry_run,
            peer_reviewed=args.peer_reviewed,
            include_suspect_urls=args.include_suspect_urls,
            append=args.append,
            force=args.force,
            show=args.show,
            batch_label=args.batch_label,
            with_pdfs=args.with_pdfs,
            with_summary=args.with_summary,
            year_from=year_from,
            year_to=year_to,
            emit_json=args.json,
        )
    if args.command == "ingest":
        return _cmd_ingest(args, emit_json=args.json)
    if args.command == "quarantine":
        return _quarantine(args)
    if args.command == "import-folder":
        dep_error = _import_folder_dep_precheck(args)
        if dep_error is not None:
            if getattr(args, "json", False):
                _emit_cli_json(
                    "import-folder",
                    dep_error,
                    {
                        "folder": args.folder,
                        "cluster_slug": args.cluster,
                        "error": "dependency precheck failed",
                    },
                )
            return dep_error
        return _import_folder_command(args)
    if args.command == "fit-check":
        if args.fit_check_command == "emit":
            return _fit_check_emit(
                args.cluster,
                args.candidates,
                args.definition,
                args.out,
                emit_json=getattr(args, "json", False),
            )
        if args.fit_check_command == "apply":
            return _fit_check_apply(
                args.cluster,
                args.candidates,
                args.scored,
                args.threshold,
                args.auto_threshold,
                args.out,
                emit_json=getattr(args, "json", False),
            )
        if args.fit_check_command == "audit":
            return _fit_check_audit(args.cluster)
        if args.fit_check_command == "drift":
            return _fit_check_drift(args.cluster, args.threshold)
        if args.fit_check_command == "apply-labels":
            return _fit_check_apply_labels(args.cluster)
        parser.error("fit-check requires a subcommand")
        return 2
    if args.command == "autofill":
        if args.autofill_command == "emit":
            return _autofill_emit(args.cluster, args.out)
        if args.autofill_command == "apply":
            return _autofill_apply(args.cluster, args.scored)
        parser.error("autofill requires a subcommand")
        return 2
    if args.command == "crystal":
        if not args.crystal_command:
            parser.error("crystal requires a subcommand")
            return 2
        return _cmd_crystal(args, get_config(), emit_json=getattr(args, "json", False))
    if args.command == "summarize":
        return _cmd_summarize(args, get_config(), emit_json=getattr(args, "json", False))
    if args.command == "memory":
        if not args.memory_command:
            parser.error("memory requires a subcommand")
            return 2
        return _cmd_memory(args, get_config())
    if args.command == "discover":
        if args.discover_command == "new":
            return _discover_new(args)
        if args.discover_command == "continue":
            return _discover_continue(args)
        if args.discover_command == "status":
            return _discover_status(args)
        if args.discover_command == "clean":
            return _discover_clean(args)
        if args.discover_command == "variants":
            return _discover_variants(args)
        parser.error("discover requires a subcommand")
        return 2
    if args.command == "index":
        return _rebuild_index()
    if args.command == "dedup":
        return _dedup(args)
    if args.command == "context":
        from research_hub.context_cli import dispatch as _context_dispatch
        try:
            cfg = get_config()
        except Exception:
            cfg = None
        return _context_dispatch(args, cfg)
    if args.command == "clusters":
        if args.clusters_command == "coverage":
            from research_hub.clusters import compute_coverage

            cfg = require_config()
            rows = compute_coverage(cfg)
            if args.sort == "papers":
                rows.sort(key=lambda row: row.paper_count, reverse=True)
            elif args.sort == "recency":
                rows.sort(key=lambda row: row.latest_mtime, reverse=True)
            else:
                rows.sort(key=lambda row: row.coverage_score)

            print(f"{'cluster':<30} {'papers':>6} {'pending':>7} {'coverage':>9}")
            print("-" * 57)
            for row in rows:
                flag = (
                    " (!)"
                    if args.min_coverage > 0 and row.coverage_score < args.min_coverage
                    else ""
                )
                print(
                    f"{row.slug:<30} {row.paper_count:>6} "
                    f"{row.pending_summary:>7} {row.coverage_score:>8}%{flag}"
                )
            print(f"\n{len(rows)} cluster(s) shown.")
            return 0
        if args.clusters_command == "list":
            return _clusters_list()
        if args.clusters_command == "set-group":
            return _clusters_set_group(args.slug, getattr(args, "group", ""))
        if args.clusters_command == "show":
            return _clusters_show(args.slug)
        if args.clusters_command == "new":
            return _clusters_new(args.query, args.name, args.slug)
        if args.clusters_command == "bind":
            return _clusters_bind(
                args.slug,
                args.zotero_key,
                args.obsidian_folder,
                args.notebooklm_notebook,
                sync_zotero=not args.no_sync_zotero,
                force_shared=args.force_shared,
            )
        if args.clusters_command == "rename":
            return _clusters_rename(args.slug, args.name, sync_zotero=not args.no_sync_zotero)
        if args.clusters_command == "archive":
            return _clusters_archive(args.slug)
        if args.clusters_command == "unarchive":
            return _clusters_unarchive(args.slug)
        if args.clusters_command == "delete":
            from research_hub.clusters import (
                cascade_delete_cluster,
                enumerate_collection_items_for_purge,
            )

            cfg = get_config()
            purge_items = getattr(args, "purge_zotero_items", False)
            preview = cascade_delete_cluster(
                cfg,
                args.slug,
                apply=False,
                delete_zotero_collection=args.delete_zotero_collection,
            )
            print(preview.summary())
            if purge_items:
                # Enumerate the Zotero items that WOULD be purged (dry-run always safe)
                try:
                    items_to_purge = enumerate_collection_items_for_purge(cfg, args.slug)
                except Exception as _exc:
                    items_to_purge = []
                    print(f"  (could not enumerate Zotero items: {_exc})")
                if items_to_purge:
                    print()
                    print("  Zotero items that would be purged (--purge-zotero-items):")
                    pdf_total = 0
                    for it in items_to_purge:
                        doi_str = f" | DOI:{it['doi']}" if it["doi"] else ""
                        pdf_str = f" | {it['pdf_count']} PDF attachment(s)"
                        print(f"    - {it['title']}{doi_str}{pdf_str}")
                        pdf_total += it["pdf_count"]
                    print(f"  Total: {len(items_to_purge)} item(s), {pdf_total} PDF attachment(s)")
                    print("  items go to Zotero trash (recoverable until trash emptied); Zotero cascade-deletes child attachments automatically")
                else:
                    print("  (no Zotero items to purge, or collection key not set)")
            print("")
            if args.apply:
                if preview.has_data() and not args.force:
                    print("Cluster is not empty. Re-run with --apply --force.")
                    return 2
                applied = cascade_delete_cluster(
                    cfg,
                    args.slug,
                    apply=True,
                    delete_zotero_collection=args.delete_zotero_collection,
                    purge_zotero_items=purge_items,
                )
                print(applied.summary())
                return 0
            if preview.has_data():
                print("Preview only. Re-run with --apply --force to delete this non-empty cluster.")
            else:
                print("Preview only. Re-run with --apply to delete this cluster.")
            return 0
        if args.clusters_command == "merge":
            return _clusters_merge(args.source, args.target)
        if args.clusters_command == "split":
            return _clusters_split(args.source, args.query, args.new_name)
        if args.clusters_command == "analyze":
            return _cmd_clusters_analyze(args, get_config())
        if args.clusters_command == "rebind":
            from research_hub.cluster_rebind import apply_rebind, emit_rebind_prompt

            cfg = require_config()
            if args.emit:
                print(emit_rebind_prompt(cfg))
                return 0
            if args.apply:
                result = apply_rebind(
                    cfg,
                    args.apply,
                    dry_run=not args.no_dry_run,
                    auto_create_new=args.auto_create_new,
                )
                mode = "DRY-RUN" if not args.no_dry_run else "APPLIED"
                print(
                    f"[{mode}] moved={len(result.moved)} skipped={len(result.skipped)} errors={len(result.errors)}"
                )
                if result.log_path:
                    print(f"Log: {result.log_path}")
                return 0 if not result.errors else 1
            print("Specify --emit or --apply <path>", file=sys.stderr)
            return 2
        if args.clusters_command == "scaffold-missing":
            return _clusters_scaffold_missing()
        if args.clusters_command == "audit":
            return _clusters_audit(args.cluster, emit_json=getattr(args, "json", False))
        if args.clusters_command == "restore-zotero-coll":
            return _clusters_restore_zotero_coll(args.cluster, args.apply)
        if args.clusters_command == "sync-names":
            return _clusters_sync_names(args.cluster, args.apply, args.direction)
        if args.clusters_command == "resolve-collision":
            return _clusters_resolve_collision(
                args.slug,
                new=args.new,
                target_slug=args.target_slug,
                apply=args.apply,
                force_shared=args.force_shared,
            )
    if args.command == "topic":
        from research_hub.topic import (
            SubtopicProposal,
            apply_assignments,
            build_subtopic_notes,
            emit_assign_prompt,
            emit_propose_prompt,
            get_topic_digest,
            list_subtopics,
            read_overview,
            scaffold_overview,
        )

        cfg = get_config()
        if args.topic_command == "scaffold":
            try:
                path = scaffold_overview(cfg, args.cluster, force=args.force)
            except FileExistsError as exc:
                print(str(exc), file=sys.stderr)
                print("hint: use --force to overwrite", file=sys.stderr)
                return 1
            print(f"wrote {path}")
            return 0
        if args.topic_command == "digest":
            digest = get_topic_digest(cfg, args.cluster)
            markdown = digest.to_markdown()
            if args.out:
                Path(args.out).write_text(markdown, encoding="utf-8")
                print(f"wrote {args.out} ({digest.paper_count} papers)")
            else:
                print(markdown)
            return 0
        if args.topic_command == "show":
            content = read_overview(cfg, args.cluster)
            if content is None:
                print("no overview (run: research-hub topic scaffold --cluster ...)", file=sys.stderr)
                return 1
            print(content)
            return 0
        if args.topic_command == "propose":
            prompt = emit_propose_prompt(cfg, args.cluster, target_count=args.target_count)
            if args.out:
                Path(args.out).write_text(prompt, encoding="utf-8")
                print(f"wrote {args.out}")
            else:
                print(prompt)
            return 0
        if args.topic_command == "assign":
            if args.assign_command == "emit":
                data = json.loads(Path(args.subtopics).read_text(encoding="utf-8"))
                subtopics = [SubtopicProposal(**item) for item in data.get("subtopics", data)]
                prompt = emit_assign_prompt(cfg, args.cluster, subtopics)
                if args.out:
                    Path(args.out).write_text(prompt, encoding="utf-8")
                    print(f"wrote {args.out}")
                else:
                    print(prompt)
                return 0
            if args.assign_command == "apply":
                data = json.loads(Path(args.assignments).read_text(encoding="utf-8"))
                assignments = data.get("assignments", data)
                report = apply_assignments(cfg, args.cluster, assignments)
                for slug, count in sorted(report.items()):
                    print(f"  {slug}: {count} subtopic(s)")
                return 0
            topic_command_parser = next(
                action
                for action in parser._subparsers._group_actions[0].choices.values()
                if action.prog.endswith(" topic")
            )
            topic_assign = next(
                action
                for action in topic_command_parser._subparsers._group_actions[0].choices.values()
                if action.prog.endswith(" topic assign")
            )
            topic_assign.print_help()
            return 2
        if args.topic_command == "build":
            written = build_subtopic_notes(cfg, args.cluster)
            for path in written:
                print(f"wrote {path}")
            return 0
        if args.topic_command == "list":
            descriptors = list_subtopics(cfg, args.cluster)
            if not descriptors:
                print(f"no sub-topics for cluster {args.cluster}")
                return 0
            print(f"{'slug':<25} {'title':<35} papers")
            for descriptor in descriptors:
                print(f"{descriptor.slug:<25} {descriptor.title:<35} {descriptor.paper_count}")
            return 0
        topic_parser = next(
            action
            for action in parser._subparsers._group_actions[0].choices.values()
            if action.prog.endswith(" topic")
        )
        topic_parser.print_help()
        return 2
    if args.command == "remove":
        return _remove(args.identifier, args.zotero, args.dry_run)
    if args.command == "mark":
        return _mark(args.slug, args.status, args.cluster)
    if args.command == "move":
        return _move(args.slug, args.to_cluster)
    if args.command == "add":
        return _add(args.identifier, args.cluster, args.no_zotero, args.no_verify)
    if args.command == "label":
        return _label(args)
    if args.command == "label-bulk":
        return _label_bulk(args.from_json)
    if args.command == "paper":
        return _paper_command(args)
    if args.command == "quote":
        target = list(args.quote_target or [])
        if target == ["list"]:
            return _quote_list(args.cluster)
        if len(target) == 2 and target[0] == "remove":
            if not args.at:
                print("Usage: research-hub quote remove <slug> --at <iso-timestamp>")
                return 2
            return _quote_remove(target[1], args.at)
        if len(target) != 1 or not args.page or not args.text:
            print("Usage: research-hub quote <slug> --page 12 --text \"...\" [--context \"...\"]")
            return 2
        return _quote_add(target[0], args.page, args.text, args.context)
    if args.command == "compose-draft":
        return _compose_draft(
            args.cluster,
            args.outline,
            args.quotes,
            args.style,
            args.include_bibliography,
            args.out,
        )
    if args.command == "find":
        return _find(
            args.query,
            args.cluster,
            args.status,
            args.full,
            args.json,
            args.limit,
            args.label,
            args.label_not,
        )
    if args.command == "search":
        if args.region:
            backends = resolve_backends_for_region(args.region)
        elif args.field:
            backends = resolve_backends_for_field(args.field)
        elif args.backend:
            backends = tuple(b.strip() for b in args.backend.split(",") if b.strip())
        else:
            backends = DEFAULT_BACKENDS
        exclude_types = _parse_csv_terms(args.exclude_type)
        min_confidence = args.min_confidence
        if args.peer_reviewed:
            backends, exclude_types, min_confidence = apply_peer_reviewed(
                backends,
                exclude_types,
                min_confidence,
            )
        exclude_terms = _parse_negative_terms(args.exclude)
        if args.enrich:
            candidates = ["-"] if args.query == "-" else [item.strip() for item in re.split(r"[\n,]+", args.query) if item.strip()]
            return _enrich(
                candidates=candidates,
                backends=backends,
                to_papers_input=args.to_papers_input,
                cluster_slug=args.cluster,
            )
        year_from, year_to = _parse_year_range(args.year)
        return _search(
            args.query,
            args.limit,
            verify=args.verify,
            year_from=year_from,
            year_to=year_to,
            min_citations=args.min_citations,
            backends=backends,
            exclude_types=exclude_types,
            exclude_terms=exclude_terms,
            min_confidence=min_confidence,
            rank_by=args.rank_by,
            backend_trace=args.backend_trace,
            emit_json=args.json,
            to_papers_input=args.to_papers_input,
            cluster_slug=args.cluster,
            adversarial=args.adversarial,
            max_variants=args.max_variants,
            screen=args.screen,
        )
    if args.command == "websearch":
        return _websearch(
            args.query,
            args.limit,
            provider=args.provider,
            max_age_days=args.max_age_days,
            domain=args.domain,
            emit_json=args.json,
            ingest_into=args.ingest_into,
        )
    if args.command == "enrich":
        return _enrich(
            candidates=args.candidates,
            backends=tuple(b.strip() for b in args.backend.split(",") if b.strip()),
            to_papers_input=args.to_papers_input,
            cluster_slug=args.cluster,
        )
    if args.command == "references":
        return _references(args.identifier, args.limit, args.json)
    if args.command == "cited-by":
        return _cited_by(args.identifier, args.limit, args.json)
    if args.command == "suggest":
        return _suggest(args.identifier, args.top, args.json)
    if args.command == "cite":
        return _cite(
            args.identifier,
            args.cluster,
            args.content_format,
            args.out,
            inline=args.inline,
            markdown=args.markdown,
            style=args.style,
        )
    if args.command == "status":
        return _status(cluster=args.cluster)
    if args.command == "dashboard":
        return _dashboard(
            args.open_browser,
            watch=args.watch,
            refresh=args.refresh,
            rich_bibtex=args.rich_bibtex,
            sample=args.sample,
            screenshot=args.screenshot,
            out=args.out,
            out_dir=args.out_dir,
            scale=args.scale,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            full_page=args.full_page,
            markdown_summary=getattr(args, "markdown_summary", False),
            markdown_summary_out=getattr(args, "markdown_summary_out", None),
            emit_json=getattr(args, "json", False),
        )
    if args.command == "vault":
        if args.vault_command == "graph-colors":
            return _vault_graph_colors(refresh=args.refresh)
        if args.vault_command == "polish-markdown":
            return _vault_polish_markdown(cluster=args.cluster, dry_run=args.dry_run)
        if args.vault_command == "rebuild-overviews":
            return _vault_rebuild_overviews(
                cluster_slug=args.cluster,
                force_rebuild=args.force,
                emit_json=getattr(args, "json", False),
            )
        if args.vault_command == "tag-migrate":
            return _vault_tag_migrate(
                cluster_slug=args.cluster,
                dry_run=args.dry_run,
                emit_json=getattr(args, "json", False),
            )
        if args.vault_command == "hub-backlink-migrate":
            return _vault_hub_backlink_migrate(
                cluster_slug=args.cluster,
                dry_run=args.dry_run,
                emit_json=getattr(args, "json", False),
            )
        if args.vault_command == "summarize-status-migrate":
            return _vault_summarize_status_migrate(
                cluster_slug=args.cluster,
                dry_run=args.dry_run,
                emit_json=getattr(args, "json", False),
            )
        if args.vault_command == "cleanup-frontmatter":
            return _vault_cleanup_frontmatter(
                cluster_slug=args.cluster,
                dry_run=args.dry_run,
                emit_json=getattr(args, "json", False),
            )
        if args.vault_command == "install-theme":
            return _vault_install_theme(
                theme=args.theme,
                force=args.force,
                uninstall=args.uninstall,
            )
    if args.command == "bases":
        if args.bases_command == "emit":
            return _bases_emit(
                cluster_slug=args.cluster,
                stdout=args.stdout,
                force=args.force,
                emit_json=getattr(args, "json", False),
            )
    if args.command == "sync":
        if args.sync_command == "status":
            return _sync_status(cluster_slug=args.cluster)
        if args.sync_command == "reconcile":
            return _sync_reconcile(cluster_slug=args.cluster, execute=args.execute)
    if args.command == "pipeline":
        if args.pipeline_command == "repair":
            return _pipeline_repair(cluster_slug=args.cluster, execute=args.execute)
    if args.command == "zotero":
        if args.zotero_command == "backfill":
            return _zotero_backfill(args)
        if args.zotero_command == "gc":
            return _zotero_gc(
                apply=args.apply,
                yes=args.yes,
                no_test_pattern=args.no_test_pattern,
                age_days=args.age_days,
                respect_kept=args.respect_kept,
            )
        if args.zotero_command == "mark-kept":
            return _zotero_mark_kept(
                all_orphans=args.all_orphans,
                add_keys=args.collection,
                remove_keys=args.remove,
                show_list=args.list,
                note=args.note,
                show_counts=getattr(args, "show_counts", False),
                by_pattern=getattr(args, "by_pattern", None),
            )
        if args.zotero_command == "reparent-clusters":
            cfg = get_config()
            parent = args.parent if args.parent is not None else getattr(cfg, "zotero_parent_collection", "research-hub")
            return _zotero_reparent_clusters(parent=parent, apply=args.apply)
    if args.command == "migrate-yaml":
        return _migrate_yaml(
            assign_cluster=args.assign_cluster,
            folder=args.folder,
            force=args.force,
            dry_run=args.dry_run,
        )
    if args.command == "verify":
        return _verify(args)
    if args.command == "cleanup":
        if args.wikilinks:
            return _cleanup_hub(dry_run=args.dry_run)
        do_bundles = args.bundles or args.all
        do_debug = args.debug_logs or args.all
        do_artifacts = args.artifacts or args.all
        if not (do_bundles or do_debug or do_artifacts):
            # Backwards-compat: bare `cleanup` keeps doing the wikilink dedup
            return _cleanup_hub(dry_run=args.dry_run)
        return _cleanup_gc(
            do_bundles=do_bundles,
            do_debug=do_debug,
            do_artifacts=do_artifacts,
            keep_bundles=args.keep_bundles,
            debug_older_than_days=args.debug_older_than,
            keep_artifacts=args.keep_artifacts,
            apply=not args.dry_run,
        )
    if args.command == "synthesize":
        return _synthesize(cluster=args.cluster, graph_colors=args.graph_colors)
    if args.command == "notebooklm":
        if args.notebooklm_command == "login":
            if args.wait_timeout != 300 and args.wait_file is None and not args.auto_detect:
                parser.error("--wait-timeout requires --wait-file or --auto-detect")
            if args.auto_detect and args.wait_file is not None:
                parser.error("--auto-detect and --wait-file are mutually exclusive")
            if args.auto_detect and (args.import_from or args.from_browser is not None):
                parser.error(
                    "--auto-detect cannot be combined with --import-from or --from-browser",
                )
            from pathlib import Path as _Path

            from research_hub._invocation import recommended_cli_invocation
            from research_hub.notebooklm.auth import (
                default_session_dir,
                default_state_file,
                login_nlm,
            )

            cfg = get_config()
            session_dir = default_session_dir(cfg.research_hub_dir)
            inv = recommended_cli_invocation()
            # Precedence: --import-from > --from-browser > interactive default.
            #
            # v0.70.1: --import-from short-circuits the interactive flow by
            # copying a logged-in session profile from another vault.
            if args.import_from:
                from research_hub.notebooklm.auth import import_session
                src_vault = _Path(args.import_from).expanduser().resolve()
                src_research_hub = src_vault / ".research_hub"
                src_session = default_session_dir(src_research_hub)
                src_state = default_state_file(src_research_hub)
                dest_state = default_state_file(cfg.research_hub_dir)
                result = import_session(
                    src_session, src_state,
                    session_dir, dest_state,
                    overwrite=args.overwrite,
                )
                if not result.ok:
                    print(f"[notebooklm login --import-from] FAILED: {result.error}", file=sys.stderr)
                    return 1
                mb = result.bytes_copied / (1024 * 1024)
                print(
                    f"[notebooklm login --import-from] copied logged-in session "
                    f"({result.files_copied} files, {mb:.0f} MB) from {src_vault}"
                )
                print("Verify with: research-hub notebooklm bundle --cluster <slug>")
                return 0
            # v1.0.0: --from-browser uses rookiepy to import cookies from an
            # already-logged-in browser — no Playwright popup, no terminal ENTER.
            if args.from_browser is not None:
                from research_hub.notebooklm.auth import login_from_browser
                dest_state = default_state_file(cfg.research_hub_dir)
                browser_arg = None if args.from_browser == "auto" else args.from_browser
                rc = login_from_browser(dest_state, browser=browser_arg)
                if rc == 0:
                    print("[notebooklm login --from-browser] Login successful.")
                    print("Verify with: research-hub notebooklm keepalive")
                else:
                    version_info = sys.version_info
                    if hasattr(version_info, "major"):
                        version_tuple = (version_info.major, version_info.minor)
                    else:
                        version_tuple = (version_info[0], version_info[1])
                    rookiepy_missing = importlib.util.find_spec("rookiepy") is None
                    if rookiepy_missing and version_tuple >= (3, 14):
                        print(
                            "--from-browser needs rookiepy, which has no prebuilt wheel "
                            f"for Python {version_tuple[0]}.{version_tuple[1]} "
                            "(building it needs a Rust toolchain). Non-interactive "
                            "cookie import is unavailable on this Python. Use one of: "
                            f"(1) interactive login in a terminal: `{inv} notebooklm login --auto-detect` "
                            "then press ENTER; (2) copy a logged-in session: "
                            f"`{inv} notebooklm login --import-from <other-vault>`.",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            "[notebooklm login --from-browser] FAILED (exit code "
                            f"{rc}). If rookiepy is not installed, run:\n"
                            "  pip install 'research-hub[browser-auth]'",
                            file=sys.stderr,
                        )
                return rc
            return login_nlm(
                session_dir,
                state_file=default_state_file(cfg.research_hub_dir),
                wait_file=args.wait_file,
                wait_timeout=args.wait_timeout,
                auto_detect=args.auto_detect,
            )
        if args.notebooklm_command == "bundle":
            return _notebooklm_bundle(args.cluster, download_pdfs=args.download_pdfs)
        if args.notebooklm_command == "upload":
            return _nlm_upload(
                args.cluster,
                args.dry_run,
                args.headless,
                args.create_if_missing,
                over_cap_strategy=args.over_cap_strategy,
                shard_size=args.shard_size,
                include_suspect_urls=args.include_suspect_urls,
            )
        if args.notebooklm_command == "shard":
            return _nlm_shard(
                args.cluster,
                args.strategy,
                args.shard_size,
                args.dry_run,
                args.headless,
            )
        if args.notebooklm_command == "download":
            return _nlm_download(
                args.cluster,
                args.type,
                args.headless,
                slide_format=getattr(args, "slide_format", "pdf"),
                emit_json=getattr(args, "json", False),
            )
        if args.notebooklm_command == "read-briefing":
            return _nlm_read_briefing(args.cluster)
        if args.notebooklm_command == "generate":
            return _nlm_generate(args.cluster, args.type, args.headless)
        if args.notebooklm_command == "ask":
            return _nlm_ask(
                args.cluster,
                question=args.question,
                headless=args.headless,
                timeout_sec=args.timeout,
            )
        if args.notebooklm_command == "keepalive":
            from research_hub.notebooklm.keepalive import (
                _keepalive_loop,
                keepalive_once,
                run_install_windows_task,
            )
            cfg = get_config()
            if args.install_windows_task or args.uninstall_windows_task:
                # Prefer the explicit --interval-minutes; if the deprecated
                # --interval-hours was passed explicitly, multiply to
                # minutes. Default falls through to args.interval_minutes
                # (which itself defaults to 15).
                if args.interval_hours is not None:
                    interval_minutes = args.interval_hours * 60
                else:
                    interval_minutes = args.interval_minutes
                return run_install_windows_task(
                    interval_minutes,
                    dry_run=not args.yes,
                    uninstall=args.uninstall_windows_task,
                    cfg=cfg,
                )
            if args.loop:
                return _keepalive_loop(cfg, interval_sec=args.interval)
            return keepalive_once(cfg)

    parser.error(f"Unknown command: {args.command}")
    return 2


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if any(token in {"-h", "--help"} for token in raw_argv):
        _warn_cli_deprecated_alias_from_argv(raw_argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _main_dispatch(args, parser)
    except ResearchHubError as exc:
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": exc.to_dict(),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
