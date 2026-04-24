"""One-shot onboarding command for research-hub."""

from __future__ import annotations

import os
from types import SimpleNamespace


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
    from research_hub.notebooklm.browser import default_session_dir, default_state_file, login_nlm

    cfg = get_config()
    session_dir = default_session_dir(cfg.research_hub_dir)
    return login_nlm(
        session_dir,
        state_file=default_state_file(cfg.research_hub_dir),
        timeout_sec=300,
    )


def run_setup(args) -> int:
    """Orchestrate init -> install -> NotebookLM login."""
    from research_hub.cli import _cmd_install
    from research_hub.config import get_config
    from research_hub.init_wizard import run_init

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
    if not args.skip_login and persona not in {"analyst", "internal"}:
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
