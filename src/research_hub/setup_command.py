"""One-shot onboarding command for research-hub."""

from __future__ import annotations

import json
import os
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
    """Launch the lowest-friction NotebookLM login flow used by setup."""
    from research_hub.config import get_config
    from research_hub.notebooklm.auth import default_session_dir, default_state_file, login_nlm

    cfg = get_config()
    session_dir = default_session_dir(cfg.research_hub_dir)
    return login_nlm(
        session_dir,
        state_file=default_state_file(cfg.research_hub_dir),
        timeout_sec=300,
        wait_timeout=300,
        auto_detect=True,
    )


def _print_setup_next_steps(*, persona: str, login_needed: bool) -> None:
    """Print a short first-run checklist after setup finishes."""
    print("\n[setup] Next steps:")
    print("  1. Check readiness: research-hub doctor")
    if login_needed:
        print("  2. If NotebookLM login did not complete: research-hub notebooklm login --auto-detect")
        print("  3. Optional run (network/model calls and writes possible): research-hub auto \"agent-based modeling\" --max-papers 3 --no-nlm")
    elif persona in {"analyst", "internal"}:
        print("  2. Import local files: research-hub import-folder ./papers --cluster first-review")
        print("  3. Open dashboard: research-hub serve --dashboard")
    else:
        print("  2. Optional run (network/model calls and writes possible): research-hub auto \"agent-based modeling\" --max-papers 3 --no-nlm")
        print("  3. Open dashboard: research-hub serve --dashboard")


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
    """Return the same LLM CLI readiness signal used by runtime workflows."""
    from research_hub.llm_cli import detect_llm_cli

    return detect_llm_cli() or ""


def _skill_platform(host: str | None, llm_cli: str) -> str | None:
    if host in {"claude-code", "cursor", "codex", "gemini"}:
        return host
    return {
        "claude": "claude-code",
        "codex": "codex",
        "cursor": "cursor",
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


def _outcome(status: str, detail: str, next_step: str) -> dict[str, str]:
    return {"status": status, "detail": detail, "next_step": next_step}


def _print_outcomes(outcomes: dict[str, dict[str, str]]) -> None:
    print("\n[setup] Step outcomes (not overall readiness; exit code retains legacy behavior):")
    for name, outcome in outcomes.items():
        print(f"  {name}: {outcome['status']} -- {outcome['detail']}")
        if outcome["next_step"]:
            print(f"    Next: {outcome['next_step']}")


def _run_setup_stage(name, outcomes, action):
    """Report an aborted init/install stage, then preserve its original exception."""
    try:
        return action()
    except (Exception, KeyboardInterrupt, SystemExit) as exc:
        cancelled = isinstance(exc, (KeyboardInterrupt, EOFError)) or (
            isinstance(exc, SystemExit) and exc.code in (None, 0)
        )
        outcomes[name] = _outcome(
            "cancelled" if cancelled else "failed",
            "Stage exited before returning a completion result; partial changes may exist.",
            "Inspect the error and any partial changes before rerunning research-hub setup.",
        )
        try:
            _print_outcomes(outcomes)
        except (Exception, KeyboardInterrupt, SystemExit):
            # A broken output stream must not replace the original stage failure.
            pass
        raise


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

    report.components = {
        "environment": _outcome("failed" if env_missing else "passed",
            "Required variable presence only; values are not validated.", "research-hub doctor"),
        "vault": _outcome("failed" if vault_issues else "passed",
            "Path existence, directory and write-access checks only; no write attempted.",
            "research-hub init --vault <path>" if vault_issues else "research-hub doctor"),
        "notebooklm_auth": _outcome("unknown",
            f"Local state path: {nlm_auth_status}; authentication was not verified.",
            "research-hub notebooklm login --auto-detect"),
        "llm_cli": _outcome("unknown", "CLI detected; invocation/auth not tested." if llm_cli
            else "No supported CLI detected; invocation/auth not tested.", "research-hub doctor"),
        "skills": _outcome("unknown", "Installed paths only; host discovery/invocation not verified.",
            "Confirm skill discovery in your selected host."),
        "zotero": _outcome("skipped", "Required environment variables missing; no request attempted.",
            "Configure required variables, then rerun research-hub setup --autonomous."),
    }
    if env_missing:
        report.zotero_error = "missing required env vars: " + ", ".join(env_missing)
        report.issues.append("missing required env vars: " + ", ".join(env_missing))
        return report

    report.zotero_reachable, report.zotero_error = _probe_zotero_reachability(os.environ)
    report.components["zotero"] = _outcome(
        "passed" if report.zotero_reachable else "failed",
        "Read probe returned successfully; write access not tested." if report.zotero_reachable
        else "Read probe did not succeed; this does not establish the cause.",
        "research-hub doctor",
    )
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

    outcomes = {
        "init": _outcome("unknown", "Not completed.", "research-hub setup"),
        "install": _outcome("skipped", "Not run by setup (not requested or not reached).", "research-hub install --platform <host>"),
        "notebooklm_login": _outcome("skipped", "Not run by setup (not requested or not reached).", "research-hub notebooklm login --auto-detect"),
    }
    outcomes["sample"] = _outcome("skipped", "Not run by setup (not requested or not reached).", "research-hub auto TOPIC --max-papers 3 --no-nlm")
    outcomes["dashboard"] = _outcome("skipped", "Not run by setup; no confirmed successful sample.", "research-hub serve --dashboard")
    interactive = not bool(args.vault and args.persona)
    if interactive:
        outcomes["notebooklm_login"] = _outcome("unknown", "Delegated to interactive init; its login outcome is not returned.", "research-hub notebooklm login --auto-detect")
    rc = _run_setup_stage("init", outcomes, lambda: run_init(
        vault_root=args.vault,
        persona=args.persona,
        non_interactive=not interactive,
        no_browser=getattr(args, "no_browser", False),
    ))
    if rc != 0:
        outcomes["init"] = _outcome("failed", f"Init returned {rc}; later steps not attempted.", "research-hub init")
        _print_outcomes(outcomes)
        print("[setup] init failed -- aborting.")
        return rc

    outcomes["init"] = _outcome("passed", "Init command returned zero; not overall readiness.", "research-hub doctor")
    if not args.skip_install:
        platform = args.platform or detect_host()
        if not platform:
            outcomes["install"] = _outcome("skipped", "No host selected or detected.", "research-hub install --platform <host>")
            print("[setup] No host auto-detected. Skipping install step.")
            print("[setup] Run later for supported installer targets: research-hub install --platform <claude-code|cursor|codex|gemini>")
            print("[setup] MCP/REST hosts can attach research-hub without a skill installer.")
        else:
            print(f"[setup] Installing skill files for platform: {platform}")
            install_args = SimpleNamespace(mcp=False, list_platforms=False, platform=platform)
            install_rc = _run_setup_stage("install", outcomes, lambda: _cmd_install(install_args))
            outcomes["install"] = _outcome("passed" if install_rc == 0 else "failed",
                f"Installer returned {install_rc}; host discovery/invocation not tested.",
                f"research-hub install --platform {platform}")
            if install_rc != 0:
                print(f"[setup] install --platform {platform} failed. Continuing.")

    persona = str(args.persona or "").strip().lower()
    if not persona:
        try:
            persona = str(get_config().persona or "researcher").strip().lower()
        except Exception:
            persona = "researcher"
    login_needed = not interactive and not args.skip_login and persona not in {"analyst", "internal"}
    if login_needed:
        print("[setup] Launching NotebookLM login (Ctrl-C to skip)...")
        try:
            login_rc = run_notebooklm_login()
            outcomes["notebooklm_login"] = _outcome("passed" if login_rc == 0 else "failed",
                f"Login command returned {login_rc}; no subsequent authenticated request was tested.",
                "research-hub notebooklm login --auto-detect")
            if login_rc != 0:
                print("[setup] NotebookLM login did not complete.")
                print("[setup] Run later: research-hub notebooklm login --auto-detect")
        except KeyboardInterrupt:
            outcomes["notebooklm_login"] = _outcome("cancelled", "Login interrupted by user.", "research-hub notebooklm login --auto-detect")
            print("[setup] Skipped NotebookLM login. Run later: research-hub notebooklm login --auto-detect")
        except Exception as exc:
            outcomes["notebooklm_login"] = _outcome("failed", "Login raised an exception.", "research-hub notebooklm login --auto-detect")
            print(f"[setup] NotebookLM login failed: {exc}. Run later: research-hub notebooklm login --auto-detect")
    outcomes["sample"] = _outcome("skipped", "Not requested, non-interactive terminal, or persona excluded.", "research-hub auto TOPIC --max-papers 3 --no-nlm")
    outcomes["dashboard"] = _outcome("skipped", "No confirmed successful sample run.", "research-hub serve --dashboard")
    if not getattr(args, "skip_sample", False) and persona not in {"analyst", "internal"}:
        import sys as _sys

        if _sys.stdin.isatty():
            print("\n[setup] Want to try a sample research topic?")
            print("  Optional: may use network/models and write data; --no-nlm only disables NotebookLM.")
            try:
                answer = input("  Try a sample now? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
                outcomes["sample"] = _outcome("cancelled", "Sample prompt interrupted.", "research-hub auto TOPIC")
            if answer in ("", "y", "yes"):
                try:
                    topic = input("  Topic to try [agent-based modeling]: ").strip() or "agent-based modeling"
                    print(f"\n[setup] Running: research-hub auto {topic!r} --max-papers 3 --no-nlm")
                    from research_hub.auto import auto_pipeline

                    sample = auto_pipeline(topic=topic, max_papers=3, do_nlm=False)
                    sample_ok = getattr(sample, "ok", None)
                    status = "passed" if sample_ok is True else "failed" if sample_ok is False else "unknown"
                    outcomes["sample"] = _outcome(status, "Pipeline-reported result; not scientific quality validation.", "Inspect the run report before retrying; partial writes may exist.")
                    if sample_ok is True:
                        print("[setup] Sample pipeline reported success. Opening dashboard...")
                        try:
                            from research_hub.dashboard import generate_dashboard

                            generate_dashboard(open_browser=True)
                            outcomes["dashboard"] = _outcome("passed", "Dashboard command returned; browser display not verified.", "research-hub serve --dashboard")
                        except KeyboardInterrupt:
                            outcomes["dashboard"] = _outcome("cancelled", "Dashboard command interrupted; sample result unchanged.", "research-hub serve --dashboard")
                        except Exception as exc:
                            outcomes["dashboard"] = _outcome("failed", "Dashboard command raised an exception.", "research-hub serve --dashboard")
                            print(f"[setup] Could not open dashboard: {exc}")
                    else:
                        print("[setup] Sample success not confirmed; dashboard not opened.")
                except (EOFError, KeyboardInterrupt):
                    outcomes["sample"] = _outcome("cancelled", "Sample interrupted; any partial writes were not rolled back.", "Inspect the run report before retrying.")
                    print("\n[setup] Sample run cancelled. Run `research-hub auto TOPIC` later.")
                except Exception as exc:
                    outcomes["sample"] = _outcome("failed", "Sample raised an exception; partial writes may exist.", "Inspect the run report before retrying.")
                    print(f"[setup] Sample run failed: {exc}.")
            elif outcomes["sample"]["status"] != "cancelled":
                outcomes["sample"] = _outcome("skipped", "Sample declined.", "research-hub auto TOPIC")
    _print_outcomes(outcomes)
    _print_setup_next_steps(persona=persona, login_needed=login_needed)
    return 0
