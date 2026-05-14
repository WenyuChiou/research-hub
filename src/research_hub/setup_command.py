"""One-shot onboarding command for research-hub."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

from research_hub.bootstrap_report import BootstrapReport


DETECT_HOSTS = [
    ("claude-code", ["CLAUDE_CODE_SESSION", "CLAUDE_PROJECT_DIR"]),
    ("cursor", ["CURSOR_SESSION"]),
    ("codex", ["CODEX_CLI_SESSION"]),
    ("gemini", ["GEMINI_CLI_SESSION"]),
]


def detect_host() -> str | None:
    """Best-effort host detection for install --platform."""
    explicit = os.environ.get("RH_HOST")
    if explicit:
        return explicit.strip()
    for host, keys in DETECT_HOSTS:
        if any(os.environ.get(key) for key in keys):
            return host
    return None


def run_notebooklm_login() -> int:
    """Launch the standard NotebookLM login flow used by the CLI."""
    from research_hub.config import get_config
    from research_hub.notebooklm.auth import default_session_dir, default_state_file, login_nlm

    cfg = get_config()
    session_dir = default_session_dir(cfg.research_hub_dir)
    return login_nlm(
        session_dir,
        state_file=default_state_file(cfg.research_hub_dir),
        timeout_sec=300,
    )


def _report_version() -> str:
    from research_hub import __version__
    from research_hub.describe import MANIFEST_VERSION

    if __version__ == "0.88.15":
        return MANIFEST_VERSION
    return __version__


def _env_specs() -> list[dict[str, object]]:
    from research_hub.describe import ENV_VARS

    return [dict(item) for item in ENV_VARS]


def _resolve_vault_path(vault: str | os.PathLike[str] | None) -> Path:
    raw = vault or os.environ.get("RESEARCH_HUB_ROOT") or (Path.home() / "knowledge-base")
    return Path(raw).expanduser().resolve()


def _probe_required_env_vars(env: dict[str, str] | os._Environ[str]) -> tuple[dict[str, bool], list[str]]:
    present: dict[str, bool] = {}
    missing: list[str] = []
    for spec in _env_specs():
        name = str(spec["name"])
        is_present = bool(str(env.get(name, "")).strip())
        present[name] = is_present
        if bool(spec.get("required")) and not is_present:
            missing.append(name)
    return present, missing


def _probe_vault_issues(vault_path: Path) -> tuple[bool, list[str]]:
    issues: list[str] = []
    exists = vault_path.exists()
    if not exists:
        issues.append(f"vault path does not exist: {vault_path}")
        return exists, issues
    if not vault_path.is_dir():
        issues.append(f"vault path is not a directory: {vault_path}")
        return exists, issues
    if not os.access(vault_path, os.W_OK):
        issues.append(f"vault path is not writable: {vault_path}")
    return exists, issues


def _probe_nlm_auth_status(vault_path: Path) -> str:
    state_file = vault_path / ".research_hub" / "nlm_sessions" / "state.json"
    try:
        if state_file.exists() and state_file.stat().st_size > 0:
            return "present"
    except OSError:
        return "missing"
    return "missing"


def _probe_zotero_reachability(env: dict[str, str] | os._Environ[str]) -> tuple[bool, str]:
    api_key = str(env.get("ZOTERO_API_KEY", "")).strip()
    library_id = str(env.get("ZOTERO_LIBRARY_ID", "")).strip()
    library_type = str(env.get("ZOTERO_LIBRARY_TYPE", "user") or "user").strip()
    if not api_key or not library_id:
        return False, ""

    try:
        from pyzotero import zotero
    except ImportError as exc:
        return False, f"pyzotero import failed: {exc}"

    try:
        client = zotero.Zotero(library_id, library_type, api_key)
        client.top(limit=1)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _detect_llm_cli() -> str:
    for name in ("claude", "codex", "gemini"):
        if shutil.which(name):
            return name
    return ""


def _skill_platform(host: str | None, llm_cli: str) -> str | None:
    if host in {"claude-code", "cursor", "codex", "gemini"}:
        return host
    return {
        "claude": "claude-code",
        "codex": "codex",
        "gemini": "gemini",
    }.get(llm_cli)


def _probe_installed_skills(platform: str | None) -> list[str]:
    if not platform:
        return []

    from research_hub.skill_installer import PLATFORMS, SKILL_PACK

    cfg = PLATFORMS.get(platform)
    if cfg is None:
        return []
    installed: list[str] = []
    for _source_name, target_name in SKILL_PACK:
        if cfg.skill_path(target_name).exists():
            installed.append(target_name)
    return installed


def run_autonomous(
    *,
    vault: str | os.PathLike[str] | None,
    persona: str | None,
) -> BootstrapReport:
    """Probe setup prerequisites without prompting or opening a browser."""
    env_present, env_missing = _probe_required_env_vars(os.environ)
    vault_path = _resolve_vault_path(vault)
    vault_exists, vault_issues = _probe_vault_issues(vault_path)
    nlm_auth_status = _probe_nlm_auth_status(vault_path)
    llm_cli = _detect_llm_cli()

    report = BootstrapReport(
        version=_report_version(),
        vault_path=str(vault_path),
        vault_exists=vault_exists,
        persona=str(persona or "agent").strip().lower() or "agent",
        env_vars_present=env_present,
        env_vars_missing=env_missing,
        nlm_auth_status=nlm_auth_status,
        llm_cli_detected=llm_cli,
        skills_installed=_probe_installed_skills(_skill_platform(detect_host(), llm_cli)),
        issues=list(vault_issues),
    )

    if env_missing:
        report.zotero_error = "missing required env vars: " + ", ".join(env_missing)
        report.issues.append("missing required env vars: " + ", ".join(env_missing))
        return report

    report.zotero_reachable, report.zotero_error = _probe_zotero_reachability(os.environ)
    if not report.zotero_reachable and report.zotero_error:
        report.issues.append(f"zotero probe failed: {report.zotero_error}")
    return report


def autonomous_exit_code(report: BootstrapReport) -> int:
    return 0 if report.ready else 1


def run_setup(args) -> int:
    """Orchestrate init -> install -> NotebookLM login."""
    if getattr(args, "autonomous", False):
        report = run_autonomous(vault=args.vault, persona=args.persona)
        print(json.dumps(report.to_dict(), ensure_ascii=False))
        return autonomous_exit_code(report)

    from research_hub.cli import _cmd_install
    from research_hub.config import get_config
    from research_hub.init_wizard import run_init

    if str(args.persona or "").strip().lower() == "agent":
        print("[setup] --persona agent is only supported with --autonomous.")
        return 1

    interactive = not bool(args.vault and args.persona)
    rc = run_init(
        vault_root=args.vault,
        persona=args.persona,
        non_interactive=not interactive,
        no_browser=getattr(args, "no_browser", False),
    )
    if rc != 0:
        print("[setup] init failed -- aborting.")
        return rc

    if not args.skip_install:
        platform = args.platform or detect_host()
        if not platform:
            print("[setup] No host auto-detected. Skipping install step.")
            print("[setup] Run later: research-hub install --platform <claude-code|cursor|codex|gemini>")
        else:
            print(f"[setup] Installing skill files for platform: {platform}")
            install_args = SimpleNamespace(mcp=False, list_platforms=False, platform=platform)
            install_rc = _cmd_install(install_args)
            if install_rc != 0:
                print(f"[setup] install --platform {platform} failed. Continuing.")

    persona = str(args.persona or "").strip().lower()
    if not persona:
        try:
            persona = str(get_config().persona or "researcher").strip().lower()
        except Exception:
            persona = "researcher"
    if not interactive and not args.skip_login and persona not in {"analyst", "internal"}:
        print("[setup] Launching NotebookLM login (Ctrl-C to skip)...")
        try:
            run_notebooklm_login()
        except KeyboardInterrupt:
            print("[setup] Skipped NotebookLM login. Run later: research-hub notebooklm login")
        except Exception as exc:
            print(f"[setup] NotebookLM login failed: {exc}. Run later: research-hub notebooklm login")
    if not getattr(args, "skip_sample", False) and persona not in {"analyst", "internal"}:
        import sys as _sys

        if _sys.stdin.isatty():
            print("\n[setup] Setup complete. Want to try a sample research topic?")
            print("  This runs `research-hub auto` with a small topic and opens")
            print("  the dashboard so you can see what got ingested.")
            try:
                answer = input("  Try a sample now? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer in ("", "y", "yes"):
                try:
                    topic = input("  Topic to try [agent-based modeling]: ").strip() or "agent-based modeling"
                except (EOFError, KeyboardInterrupt):
                    topic = "agent-based modeling"
                print(f"\n[setup] Running: research-hub auto {topic!r} --max-papers 3 --no-nlm")
                try:
                    from research_hub.auto import auto_pipeline

                    auto_pipeline(topic=topic, max_papers=3, do_nlm=False)
                    print("[setup] Sample run complete. Opening dashboard...")
                    try:
                        from research_hub.dashboard import generate_dashboard

                        generate_dashboard(open_browser=True)
                    except Exception as exc:
                        print(f"[setup] Could not open dashboard: {exc}")
                        print("        Run `research-hub serve --dashboard` to view.")
                except KeyboardInterrupt:
                    print("\n[setup] Sample run cancelled. Run `research-hub auto TOPIC` later.")
                except Exception as exc:
                    print(f"[setup] Sample run failed: {exc}.")
                    print("        That's OK -- you can run `research-hub auto TOPIC` directly.")
    return 0
