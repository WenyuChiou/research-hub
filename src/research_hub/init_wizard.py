"""Interactive setup wizard for first-time research-hub users."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import platformdirs

from research_hub.security import chmod_sensitive
from research_hub.security.secret_box import encrypt


def _check_first_run_readiness(vault: Path, *, persona: str, has_zotero: bool) -> list[tuple[str, str, str]]:
    """Probe lazy-mode prerequisites; return (subsystem, status, detail) rows.

    Status is one of OK / INFO / WARN. Used after init to give the user a
    consolidated readiness picture before they try `auto`.
    """
    rows: list[tuple[str, str, str]] = []

    # Obsidian vault detection (informational -- research-hub still works without it)
    if (vault / ".obsidian").exists():
        rows.append(("obsidian", "OK", f"vault detected at {vault}"))
    else:
        rows.append(("obsidian", "INFO", f"no .obsidian/ in {vault} -- open Obsidian once to render"))

    # patchright + Chrome probe (needed for NotebookLM)
    try:
        from patchright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                browser.close()
            rows.append(("chrome", "OK", "patchright can launch Chrome (channel='chrome')"))
        except Exception as exc:
            rows.append(("chrome", "WARN", f"patchright cannot launch Chrome: {str(exc)[:120]}"))
    except ImportError:
        rows.append(("chrome", "WARN", "patchright not installed -- `pip install research-hub-pipeline[playwright]`"))

    # Zotero (skip for personas that don't use it)
    if has_zotero:
        rows.append(("zotero", "OK", "credentials configured (verified above)"))
    elif persona in {"analyst", "internal"}:
        rows.append(("zotero", "INFO", f"persona={persona} does not use Zotero"))
    else:
        rows.append(("zotero", "WARN", "no Zotero key -- run `research-hub init` again to add"))

    # LLM CLI for --with-crystals (informational -- auto still works without)
    for cli in ("claude", "codex", "gemini"):
        if shutil.which(cli):
            rows.append(("llm-cli", "OK", f"`{cli}` on PATH -- `auto --with-crystals` will work"))
            break
    else:
        rows.append(("llm-cli", "INFO", "no claude/codex/gemini CLI on PATH -- crystals stay manual emit/apply"))

    return rows


def _print_readiness(rows: list[tuple[str, str, str]]) -> None:
    # ASCII-only markers so the output survives cp950 / cp1252 stdout encoding
    # on Windows (UnicodeEncodeError on emoji characters).
    print()
    print("  -- First-run readiness check " + "-" * 30)
    for subsystem, status, detail in rows:
        marker = {"OK": "[OK]  ", "INFO": "[INFO]", "WARN": "[WARN]"}.get(status, "[ ?? ]")
        print(f"  {marker}  {subsystem:<10} {detail}")
    print()


def get_default_config_dir() -> Path:
    return Path(platformdirs.user_config_dir("research-hub", ensure_exists=False))


def get_default_config_path() -> Path:
    return get_default_config_dir() / "config.json"


def _detect_existing_obsidian_vault(vault: Path) -> None:
    """Print a reassurance banner when onboarding into an existing vault."""
    obsidian_dir = vault / ".obsidian"
    if obsidian_dir.exists():
        note_count = len(list(vault.rglob("*.md")))
        print(f"\n  Found existing Obsidian vault at {vault}")
        print(f"    ({note_count} .md files detected)")
        print("    research-hub will add raw/ + hub/ + .research_hub/")
        print("    alongside your existing notes. Nothing is overwritten.\n")


def _print_completion_banner(vault_path: Path, config_path: Path, *, persona: str = "researcher") -> None:
    """Print formatted completion message with next steps."""
    vault_str = str(vault_path)
    config_str = str(config_path)
    normalized_persona = str(persona or "researcher").strip().lower()
    detected_host = "claude-code"
    install_ready = False
    try:
        from research_hub.setup_command import detect_host
        from research_hub.skill_installer import list_platforms

        detected_host = detect_host() or "claude-code"
        install_ready = any(
            key == detected_host and installed for key, _name, installed in list_platforms()
        )
    except Exception:
        detected_host = "claude-code"
        install_ready = False
    if normalized_persona in {"analyst", "internal"}:
        next_steps = [
            ("research-hub import-folder <folder> --cluster <slug>", "Ingest local PDFs/docs into a cluster"),
            ('research-hub auto "your topic" --no-nlm', "Optional paper search without NotebookLM"),
            ("research-hub serve --dashboard", "See the result at http://127.0.0.1:8765/"),
        ]
    else:
        next_steps = [
            ('research-hub plan "your research topic"', "Review and confirm the plan"),
            ('research-hub auto "your research topic"', "Run the full research pipeline"),
            ("research-hub serve --dashboard", "See the result at http://127.0.0.1:8765/"),
        ]
    if not install_ready:
        next_steps.insert(
            0,
            (
                f"research-hub install --platform {detected_host}",
                "Install MCP skill files for your AI host",
            ),
        )

    lines = [
        "",
        "  Setup complete!",
        "",
        f"  Your vault:  {vault_str}",
        f"  Your config: {config_str}",
        "",
        "  Optional readiness check:",
        "    research-hub doctor",
        "",
        "  NEXT STEPS (run in order):",
        "",
    ]
    for idx, (command, detail) in enumerate(next_steps, start=1):
        lines.extend([f"  {idx}. {command}", f"     -> {detail}", ""])
    lines.extend(["  Docs: https://github.com/WenyuChiou/research-hub", ""])
    for line in lines:
        print(line)


def run_init(
    *,
    vault_root: str | None = None,
    zotero_key: str | None = None,
    zotero_library_id: str | None = None,
    non_interactive: bool = False,
    persona: str | None = None,
    no_browser: bool = False,
) -> int:
    """Run the init wizard. Returns 0 on success, 1 on error."""
    interactive = sys.stdin.isatty() and not non_interactive
    valid_personas = {"researcher", "analyst", "humanities", "internal"}

    if persona is None and interactive:
        print("\nDo you use Zotero for managing references? [y/N]")
        print("  y = yes  (researcher / humanities personas)")
        print("  N = no   (analyst / internal personas - Obsidian + NotebookLM only)")
        uses_zotero = input("> ").strip().lower().startswith("y")

        if uses_zotero:
            print("\nWhich researcher type best fits your work?")
            print("  1. Researcher (PhD/academic, broad)")
            print("  2. Humanities researcher (quote-heavy work)")
            answer = input("> ").strip() or "1"
            persona = {"1": "researcher", "2": "humanities"}.get(answer, "researcher")
        else:
            print("\nWhich non-Zotero workflow fits?")
            print("  1. Industry analyst (imports PDFs/MD)")
            print("  2. Internal knowledge management (mixed file types)")
            answer = input("> ").strip() or "1"
            persona = {"1": "analyst", "2": "internal"}.get(answer, "analyst")
    persona = str(persona or "researcher").strip().lower()
    if persona not in valid_personas:
        print("Error: --persona must be one of researcher, analyst, humanities, internal")
        return 1
    no_zotero_persona = persona in {"analyst", "internal"}

    if vault_root:
        vault = Path(vault_root).expanduser().resolve()
    elif interactive:
        default = str(Path.home() / "knowledge-base")
        answer = input(f"Vault root directory [{default}]: ").strip()
        vault = Path(answer or default).expanduser().resolve()
    else:
        print("Error: --vault is required in non-interactive mode")
        return 1

    _detect_existing_obsidian_vault(vault)

    for subdir in ("raw", "hub", "logs", "pdfs", ".research_hub"):
        (vault / subdir).mkdir(parents=True, exist_ok=True)
    chmod_sensitive(vault / ".research_hub", mode=0o700)
    print(f"  Vault root: {vault}")

    if not no_zotero_persona and not zotero_key and interactive:
        print("\n  Zotero API key is needed to sync papers.")
        no_browser_flag = bool(no_browser) if "no_browser" in locals() else False
        if interactive and not no_browser_flag:
            print("  Opening https://www.zotero.org/settings/keys in your browser.")
            print("  Log in, click 'Create new private key', enable Library Read/Write,")
            print("  then copy the key + library ID back here.")
            print("  If Zotero shows 'Access denied', click 'Log In' first, then reopen the keys page.")
            try:
                import webbrowser

                webbrowser.open("https://www.zotero.org/settings/keys")
            except Exception:
                pass
        else:
            print("  Get one at: https://www.zotero.org/settings/keys")
        print("  Note: research-hub auto/ingest will fail without Zotero credentials.")
        print("  If you don't actually use Zotero, abort and re-run init, answering N to the first question.")
        zotero_key = input("  Zotero API key: ").strip() or None
    if not no_zotero_persona and not zotero_library_id and interactive:
        print("  Your Zotero library ID (numeric, from the same settings page):")
        zotero_library_id = input("  Zotero library ID: ").strip() or None

    if no_zotero_persona:
        print(f"  Persona: {persona} -> skipping Zotero (Obsidian + NotebookLM only)")
        zotero_key = None
        zotero_library_id = None

    if not no_zotero_persona and zotero_key and zotero_library_id:
        import requests

        try:
            response = requests.head(
                f"https://api.zotero.org/users/{zotero_library_id}/items?limit=1",
                headers={"Zotero-API-Key": zotero_key},
                timeout=5,
            )
            if response.status_code == 200:
                print("  Zotero credentials: OK")
            else:
                print(f"  Zotero credentials: returned {response.status_code}")
                if interactive:
                    retry = input("    Retry Zotero validation? [y/N]: ").strip().lower()
                    if retry == "y":
                        zotero_key = input("    Re-enter Zotero API key: ").strip() or zotero_key
                        zotero_library_id = input("    Re-enter Zotero library ID: ").strip() or zotero_library_id
                        response2 = requests.head(
                            f"https://api.zotero.org/users/{zotero_library_id}/items?limit=1",
                            headers={"Zotero-API-Key": zotero_key},
                            timeout=5,
                        )
                        if response2.status_code == 200:
                            print("    Zotero credentials: OK")
                        else:
                            print(f"    WARN still {response2.status_code}; continuing offline.")
                    else:
                        print("    WARN continuing offline.")
        except Exception as exc:
            print(f"  Zotero credentials: could not reach api.zotero.org ({exc})")
            if interactive:
                choice = input("    [c]ontinue offline / [a]bort? ").strip().lower() or "c"
                if choice.startswith("a"):
                    return 1

    config_path = get_default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict[str, object] = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            config = {}

    knowledge_base = config.setdefault("knowledge_base", {})
    if isinstance(knowledge_base, dict):
        knowledge_base["root"] = str(vault)
    config["persona"] = persona

    if no_zotero_persona:
        config["no_zotero"] = True
    else:
        config.pop("no_zotero", None)
        if zotero_key:
            zotero = config.setdefault("zotero", {})
            if isinstance(zotero, dict):
                zotero["api_key"] = encrypt(zotero_key, config_path.parent)
        if zotero_library_id:
            zotero = config.setdefault("zotero", {})
            if isinstance(zotero, dict):
                zotero["library_id"] = zotero_library_id

    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    chmod_sensitive(config_path.parent, mode=0o700)
    chmod_sensitive(config_path, mode=0o600)
    print(f"  Config written: {config_path}")

    has_zotero = bool(zotero_key and zotero_library_id and not no_zotero_persona)
    readiness = _check_first_run_readiness(vault, persona=persona, has_zotero=has_zotero)
    _print_readiness(readiness)

    chrome_ok = any(sub == "chrome" and stat == "OK" for sub, stat, _ in readiness)
    if interactive and chrome_ok and persona not in {"analyst", "internal"}:
        print("\n  Launching NotebookLM Google login (Ctrl-C to skip).")
        try:
            from research_hub.setup_command import run_notebooklm_login

            run_notebooklm_login()
        except KeyboardInterrupt:
            print("  Skipped. Run later: research-hub notebooklm login")
        except Exception as exc:
            print(f"  Login failed: {exc}. Run later: research-hub notebooklm login")
    elif interactive and not chrome_ok and persona not in {"analyst", "internal"}:
        answer = input("  Chrome not ready. Run NotebookLM Google login later? [y/N]: ").strip().lower()
        if answer == "y":
            print("  Run: research-hub notebooklm login")

    _print_completion_banner(vault, config_path, persona=persona)
    return 0
