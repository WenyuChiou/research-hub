"""Maintenance / setup CLI handlers for Research Hub (ARCH-2 split from cli.py)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config, require_config
from research_hub.dedup import DedupIndex, build_from_obsidian, build_from_zotero
from research_hub.cli_common import _emit_cli_json


_ALLOWED_CONFIG_KEYS = frozenset({
    "ezproxy_cookies_path",
    "ezproxy_url_template",
    "unpaywall_email",
    "zotero.unpaywall_email",
    "persona",
})


def _config_encrypt_secrets() -> int:
    from research_hub.config import _resolve_config_path
    from research_hub.security.secret_box import encrypt, is_encrypted

    config_path = _resolve_config_path()
    if config_path is None or not config_path.exists():
        print("No config file found")
        return 1
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read config: {exc}", file=sys.stderr)
        return 1
    zotero = data.get("zotero")
    if not isinstance(zotero, dict):
        print("No secrets found to encrypt")
        return 0
    changed = False
    api_key = zotero.get("api_key")
    if isinstance(api_key, str) and api_key and not is_encrypted(api_key):
        encrypted = encrypt(api_key, config_path.parent)
        if encrypted != api_key:
            zotero["api_key"] = encrypted
            changed = True
    if not changed:
        print("No plaintext secrets found")
        return 0
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Encrypted secrets in {config_path}")
    return 0


def _config_set(key: str, value: str, force: bool = False) -> int:
    from research_hub import config as hub_config

    parts = [part.strip() for part in key.split(".") if part.strip()]
    if not parts:
        print("Config key must not be empty", file=sys.stderr)
        return 2

    canonical_key = ".".join(parts)
    if not force and canonical_key not in _ALLOWED_CONFIG_KEYS:
        print(
            f"Refusing to set unknown config key '{canonical_key}'.\n"
            f"Allowed keys: {sorted(_ALLOWED_CONFIG_KEYS)}\n"
            f"Pass --force to override (you might be making a typo).",
            file=sys.stderr,
        )
        return 2

    config_path = hub_config._resolve_config_path() or hub_config.CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    except Exception as exc:
        print(f"Could not read config: {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("Config file must contain a top-level JSON object", file=sys.stderr)
        return 1

    cursor = data
    walked: list[str] = []
    for part in parts[:-1]:
        walked.append(part)
        current = cursor.get(part)
        if current is None:
            current = {}
            cursor[part] = current
        if not isinstance(current, dict):
            print(f"Cannot set nested key under non-object: {'.'.join(walked)}", file=sys.stderr)
            return 2
        cursor = current
    cursor[parts[-1]] = value

    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    hub_config._config = None
    hub_config._config_path = None
    print(f"Set {key} in {config_path}")
    return 0


def _package_dxt(out_path: Path) -> int:
    from research_hub import __version__
    from research_hub.dxt import build_dxt

    path = build_dxt(out_path, __version__)
    print(f"Wrote {path}")
    return 0


def _rebuild_index() -> int:
    cfg = get_config()
    index = DedupIndex()
    for hit in build_from_obsidian(cfg.raw):
        index.add(hit)
    if cfg.zotero_library_id:
        from research_hub.zotero.client import get_client

        zot = get_client()
        for hit in build_from_zotero(zot, cfg.zotero_library_id):
            index.add(hit)
    index.save(cfg.research_hub_dir / "dedup_index.json")
    return 0


def _dedup(args) -> int:
    cfg = get_config()
    path = cfg.research_hub_dir / "dedup_index.json"
    index = DedupIndex.load(path)
    emit_json = bool(getattr(args, "json", False))

    if args.dedup_command == "invalidate":
        if not args.doi and not args.path:
            print("Provide --doi or --path")
            return 1
        removed = 0
        if args.doi:
            removed += index.invalidate_doi(args.doi)
        if args.path:
            removed += index.invalidate_obsidian_path(args.path)
        index.save(path)
        print(f"Removed {removed} entries")
        return 0

    if args.dedup_command == "rebuild":
        if args.obsidian_only:
            index.rebuild_from_obsidian(cfg.raw)
        else:
            from research_hub.zotero.client import get_client

            new = DedupIndex.empty()
            for hit in build_from_obsidian(cfg.raw):
                new.add(hit)
            try:
                zot = get_client()
                for hit in build_from_zotero(zot, cfg.zotero_library_id):
                    new.add(hit)
            except Exception as exc:
                print(f"  [warn] Zotero rebuild failed: {exc}")
                print("  Use --obsidian-only to skip Zotero")
            index = new
        index.save(path)
        print(f"Index rebuilt: {len(index.doi_to_hits)} DOIs, {len(index.title_to_hits)} titles")
        return 0

    if args.dedup_command == "compact":
        has_zotero_hits = any(
            hit.source == "zotero" and hit.zotero_key
            for mapping in (index.doi_to_hits, index.title_to_hits)
            for hits in mapping.values()
            for hit in hits
        )
        zot = None
        if has_zotero_hits:
            from research_hub.zotero.client import get_client

            zot = get_client()
        compacted, report = index.compact(cfg.raw, zot, dry_run=not args.apply)
        if args.apply:
            compacted.save(path)
        if emit_json:
            _emit_cli_json(
                "dedup compact",
                0,
                {
                    "path": str(path),
                    "apply": bool(args.apply),
                    "report": report,
                },
            )
            return 0
        verb = "Would remove" if not args.apply else "Removed"
        print(f"{verb} {len(report.removed_zotero_keys)} stale Zotero hit(s)")
        print(f"Index compacted: {report.after_doi_keys} DOIs, {report.after_title_keys} titles")
        return 0

    return 1


def _status(cluster: str | None = None) -> int:
    from research_hub.vault.progress import print_status_table

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    print_status_table(cfg.raw, registry, one_cluster=cluster)
    return 0


def _dashboard(
    open_browser: bool,
    watch: bool = False,
    refresh: int = 10,
    rich_bibtex: bool = False,
    sample: bool = False,
    screenshot: str | None = None,
    out: str | None = None,
    out_dir: str | None = None,
    scale: float = 2.0,
    viewport_width: int = 1440,
    viewport_height: int = 900,
    full_page: bool = False,
    markdown_summary: bool = False,
    markdown_summary_out: str | None = None,
    emit_json: bool = False,
) -> int:
    if markdown_summary:
        from pathlib import Path as _Path

        from research_hub.clusters import ClusterRegistry
        from research_hub.dashboard.markdown_summary import write_dashboard_markdown_summary
        from research_hub.dashboard.markdown_summary import _cluster_stats as _dashboard_cluster_stats

        cfg = require_config()
        out_p = _Path(markdown_summary_out) if markdown_summary_out else None
        path = write_dashboard_markdown_summary(cfg, out_path=out_p)
        if emit_json:
            registry = ClusterRegistry(cfg.clusters_file)
            clusters = [cluster for cluster in registry.list() if (cluster.slug or "").strip()]
            totals = {
                "cluster_count": len(clusters),
                "papers": 0,
                "unread": 0,
                "pending_summary": 0,
                "clusters_with_brief": 0,
            }
            for cluster in clusters:
                stats = _dashboard_cluster_stats(Path(cfg.root), cluster.slug)
                totals["papers"] += int(stats["papers"])
                totals["unread"] += int(stats["unread"])
                totals["pending_summary"] += int(stats["pending_summary"])
                totals["clusters_with_brief"] += int(bool(stats["brief_exists"]))
            _emit_cli_json(
                "dashboard",
                0,
                {
                    "markdown_summary": True,
                    "path": path,
                    "stats": totals,
                },
            )
            return 0
        print(f"Wrote markdown summary: {path}")
        return 0

    if sample:
        from research_hub.sample_vault import generate_sample_dashboard

        out_path = generate_sample_dashboard(open_browser=open_browser, rich_bibtex=rich_bibtex)
        print("SAMPLE PREVIEW - this vault is read-only and temporary.")
        print(f"Dashboard written to {out_path}")
        if open_browser:
            print("Opening in browser...")
        return 0

    if screenshot:
        from research_hub.dashboard.screenshot import (
            PlaywrightNotInstalled,
            screenshot_all,
            screenshot_dashboard,
        )

        try:
            cfg = require_config()
            if screenshot == "all":
                if not out_dir:
                    print("ERROR: --out-dir required with --screenshot all", file=sys.stderr)
                    return 2
                paths = screenshot_all(
                    cfg,
                    out_dir=Path(out_dir),
                    scale=scale,
                    viewport_width=viewport_width,
                    viewport_height=viewport_height,
                    full_page=full_page,
                )
                for path in paths:
                    print(f"wrote {path}")
                return 0
            if not out:
                print("ERROR: --out required with single-tab --screenshot", file=sys.stderr)
                return 2
            path = screenshot_dashboard(
                cfg,
                tab=screenshot,
                out=Path(out),
                scale=scale,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                full_page=full_page,
            )
            print(f"wrote {path}")
            return 0
        except PlaywrightNotInstalled as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    if watch:
        from research_hub.dashboard import watch_dashboard

        watch_dashboard(
            open_browser=open_browser,
            refresh_seconds=refresh,
            rich_bibtex=rich_bibtex,
        )
        return 0

    from research_hub.dashboard import generate_dashboard
    from research_hub.vault.graph_config import refresh_graph_from_vault

    cfg = get_config()
    out_path = generate_dashboard(open_browser=open_browser, rich_bibtex=rich_bibtex)
    group_count = None
    graph_refresh_error = ""
    try:
        group_count = refresh_graph_from_vault(cfg)
        if not emit_json:
            print(f"Graph colors refreshed ({group_count} groups)")
    except Exception as exc:
        graph_refresh_error = str(exc)
        if not emit_json:
            print(f"WARNING: graph color refresh failed: {exc}", file=sys.stderr)
    if emit_json:
        _emit_cli_json(
            "dashboard",
            0,
            {
                "markdown_summary": False,
                "path": out_path,
                "graph_groups": group_count,
                "graph_refresh_error": graph_refresh_error,
                "open_browser": open_browser,
            },
        )
        return 0
    print(f"Dashboard written to {out_path}")
    if open_browser:
        print("Opening in browser...")
    return 0


def _resolve_api_token(args) -> str | None:
    """Resolve the dashboard API token (G3 P2 #15).

    Priority: --api-token-file (read 0600 file) > --api-token (argv,
    discouraged — leaks to ps/tasklist) > $RESEARCH_HUB_API_TOKEN.
    The file path is the recommended form for shared hosts; argv is
    kept for back-compat but emits a one-line stderr nudge.
    """
    token_file = getattr(args, "api_token_file", None)
    if token_file:
        try:
            tfp = Path(token_file).expanduser()
            tok = tfp.read_text(encoding="utf-8").strip()
            # G3 P2 #15 (code-review follow-up): warn if the token file
            # is group/world-readable on POSIX — defeats the purpose of
            # moving the token off the argv. Best-effort; Windows ACL
            # bits don't map to st_mode so this is POSIX-only.
            if not sys.platform.startswith("win"):
                try:
                    mode = tfp.stat().st_mode
                    if mode & 0o077:
                        print(
                            f"  [serve] WARN {tfp} is group/world-readable "
                            f"(mode {oct(mode & 0o777)}); chmod 600 it so "
                            f"other users can't read the API token.",
                            file=sys.stderr,
                        )
                except OSError:
                    pass
            return tok or None
        except OSError as exc:
            print(
                f"  [serve] WARN --api-token-file {token_file} unreadable "
                f"({type(exc).__name__}: {exc}); falling back to "
                f"--api-token / env.",
                file=sys.stderr,
            )
    argv_token = (getattr(args, "api_token", "") or "").strip()
    if argv_token:
        print(
            "  [serve] NOTE --api-token on the command line is visible to "
            "other users via ps/tasklist. Prefer --api-token-file for "
            "shared hosts.",
            file=sys.stderr,
        )
        return argv_token
    env_token = os.environ.get("RESEARCH_HUB_API_TOKEN", "").strip()
    return env_token or None


def _cmd_serve(args, cfg) -> int:
    api_token = _resolve_api_token(args)
    if args.dashboard and args.allow_external:
        print("+" + "-" * 62 + "+")
        print("| DASHBOARD BOUND TO 0.0.0.0" + " " * 34 + "|")
        print("|" + " " * 62 + "|")
        print("| Anyone on your network can:" + " " * 32 + "|")
        print("| - View your research data" + " " * 34 + "|")
        print("| - Execute whitelisted CLI commands" + " " * 24 + "|")
        print("|" + " " * 62 + "|")
        print("| Use only on trusted networks (home LAN, VPN)." + " " * 15 + "|")
        print("|" + " " * 62 + "|")
        if args.yes:
            print("| Continuing immediately because --yes was passed." + " " * 15 + "|")
        else:
            print("| Continuing in 5 seconds - Ctrl+C to abort." + " " * 17 + "|")
        print("+" + "-" * 62 + "+")
        if not args.yes:
            time.sleep(5)
    if args.dashboard:
        from research_hub.dashboard.http_server import serve_dashboard

        serve_dashboard(
            cfg,
            host=args.host,
            port=args.port,
            allow_external=args.allow_external,
            open_browser=not args.no_browser,
            api_token=api_token,
        )
        return 0

    from research_hub.mcp_server import main as mcp_main

    mcp_main()
    return 0


def _get_claude_desktop_config_path() -> Path:
    import platform

    if platform.system() == "Windows":
        config_dir = Path.home() / "AppData" / "Roaming" / "Claude"
    elif platform.system() == "Darwin":
        config_dir = Path.home() / "Library" / "Application Support" / "Claude"
    else:
        config_dir = Path.home() / ".config" / "claude"
    return config_dir / "claude_desktop_config.json"


def _install_mcp(config_path: Path | None = None) -> int:
    """Auto-write research-hub MCP server entry to Claude Desktop config."""
    config_path = config_path or _get_claude_desktop_config_path()

    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            config = {}

    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        config["mcpServers"] = servers

    if "research-hub" in servers:
        print(f"research-hub already configured in {config_path}")
        print("  No changes made.")
        return 0

    servers["research-hub"] = {
        "command": "research-hub",
        "args": ["serve"],
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"MCP server added to {config_path}")
    print("  Restart Claude Desktop to activate.")
    print("  Then ask Claude: 'list my research clusters'")
    return 0


def _cmd_install(args, cfg=None) -> int:
    if getattr(args, "mcp", False):
        return _install_mcp()

    from research_hub.skill_installer import install_skill, list_platforms

    if args.list_platforms:
        for key, name, installed in list_platforms():
            status = "installed" if installed else "not installed"
            print(f"  {key:15s} {name:20s} [{status}]")
        print("  Other MCP/REST hosts can use research-hub without this installer; load SKILL.md manually when needed.")
        return 0
    if not args.platform:
        print("Specify --platform or use --list to see options.")
        return 1
    paths = install_skill(args.platform)
    # v0.53: install_skill now returns a LIST (skill pack), not a single path.
    # Stay compatible with old callers that expected a string.
    if isinstance(paths, str):
        paths = [paths]
    for p in paths:
        print(f"Installed {p}")
    print(f"  -> {len(paths)} skill(s) installed for {args.platform}")
    return 0


def _cmd_where(args) -> int:
    """Print config/vault/data locations without external API calls."""
    from research_hub.config import _resolve_config_path, get_config

    config_path = _resolve_config_path()
    print()

    if not config_path:
        print("  Config:   (not found)")
        print("  Vault:    (not configured)")
        print()
        print("  Run: research-hub init")
        return 1

    print(f"  Config:   {config_path}")

    try:
        cfg = get_config()
    except Exception as exc:
        print(f"  Vault:    (error: {exc})")
        return 1

    vault = Path(cfg.root)
    print(f"  Vault:    {vault}")

    raw = Path(cfg.raw)
    note_count = len(list(raw.rglob("*.md"))) if raw.exists() else 0

    clusters_file = Path(cfg.research_hub_dir) / "clusters.yaml"
    cluster_count = 0
    if clusters_file.exists():
        try:
            cluster_count = len(ClusterRegistry(clusters_file).list())
        except Exception:
            pass

    print(f"  Notes:    {note_count} papers across {cluster_count} cluster(s)")

    hub = Path(cfg.hub)
    crystal_count = len(list(hub.rglob("crystals/*.md"))) if hub.exists() else 0
    if crystal_count:
        print(f"  Crystals: {crystal_count} pre-computed answers")

    mcp_config = _get_claude_desktop_config_path()
    if mcp_config.exists():
        try:
            mcp_data = json.loads(mcp_config.read_text(encoding="utf-8"))
            if "research-hub" in mcp_data.get("mcpServers", {}):
                print(f"  MCP:      {mcp_config} (configured)")
            else:
                print(f"  MCP:      {mcp_config} (not configured - run: research-hub install --mcp)")
        except Exception:
            print(f"  MCP:      {mcp_config} (error reading)")
    else:
        print("  MCP:      (not found - run: research-hub install --mcp)")

    dashboard = Path(cfg.research_hub_dir) / "dashboard.html"
    if dashboard.exists():
        print(f"  Dashboard: {dashboard}")

    if raw.exists():
        print()
        print("  Vault folders:")
        for cluster_dir in sorted(raw.iterdir()):
            if cluster_dir.is_dir():
                paper_count = len(list(cluster_dir.glob("*.md")))
                topics_dir = cluster_dir / "topics"
                topic_count = len(list(topics_dir.glob("*.md"))) if topics_dir.exists() else 0
                extra = f" + {topic_count} sub-topics" if topic_count else ""
                print(f"    raw/{cluster_dir.name}/  ({paper_count} papers{extra})")

    print()
    return 0


def _cleanup_gc(*, do_bundles, do_debug, do_artifacts,
                keep_bundles, debug_older_than_days, keep_artifacts, apply) -> int:
    from research_hub.cleanup import collect_garbage, format_bytes

    cfg = get_config()
    report = collect_garbage(
        cfg,
        do_bundles=do_bundles,
        do_debug_logs=do_debug,
        do_artifacts=do_artifacts,
        keep_bundles=keep_bundles,
        debug_older_than_days=debug_older_than_days,
        keep_artifacts=keep_artifacts,
        apply=apply,
    )
    verb = "Deleted" if apply else "Would delete"
    print(f"{verb} {report.dirs_deleted} dirs + {report.files_deleted} files "
          f"({format_bytes(report.total_bytes)}):")
    for candidate in report.bundles:
        print(f"  bundle:    {candidate.cluster}/{candidate.path.name}  "
              f"({format_bytes(candidate.size_bytes)})")
    for candidate in report.debug_logs:
        print(f"  debug:     {candidate.path.name}  "
              f"({format_bytes(candidate.size_bytes)})")
    for candidate in report.artifacts:
        print(f"  artifact:  {candidate.cluster}/{candidate.path.name}  "
              f"({format_bytes(candidate.size_bytes)})")
    if not apply and report.total_bytes > 0:
        print("\nRun with --apply to actually delete.")
    return 0
