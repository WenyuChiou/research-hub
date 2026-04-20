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


def _print_completion_banner(vault_path: Path, config_path: Path) -> None:
    """Print formatted completion message with next steps."""
    vault_str = str(vault_path)
    config_str = str(config_path)

    lines = [
        "",
        "  Setup complete!",
        "",
        f"  Your vault:  {vault_str}",
        f"  Your config: {config_str}",
        "",
        "  NEXT STEPS (run in order):",
        "",
        "  1. research-hub doctor",
        "     -> Verify all green before continuing",
        "",
        "  2. research-hub add <DOI> --cluster <name>",
        "     -> Add your first paper (creates cluster automatically)",
        "",
        "  3. research-hub serve --dashboard",
        "     -> Opens live dashboard at http://127.0.0.1:8765/",
        "",
        "  4. research-hub install --mcp",
        "     -> Auto-configure Claude Desktop (optional)",
        "",
        "  Docs: https://github.com/WenyuChiou/research-hub",
        "",
    ]
    for line in lines:
        print(line)


def run_init(
    *,
    vault_root: str | None = None,
    zotero_key: str | None = None,
    zotero_library_id: str | None = None,
    non_interactive: bool = False,
    persona: str | None = None,
) -> int:
    """Run the init wizard. Returns 0 on success, 1 on error."""
    interactive = sys.stdin.isatty() and not non_interactive
    valid_personas = {"researcher", "analyst", "humanities", "internal"}

    if persona is None and interactive:
        print("What's your primary use case?")
        print("  1. Researcher (PhD/academic, uses Zotero)")
        print("  2. Humanities researcher (uses Zotero, quote-heavy work)")
        print("  3. Industry analyst (no Zotero, imports PDFs/MD)")
        print("  4. Internal knowledge management (no Zotero, mixed file types)")
        answer = input("> ").strip()
        persona = {"1": "researcher", "2": "humanities", "3": "analyst", "4": "internal"}.get(answer, "researcher")
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
        print("  Get one at: https://www.zotero.org/settings/keys")
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
                    choice = input("    [r]etry / [c]ontinue offline / [a]bort? ").strip().lower() or "c"
                    if choice.startswith("a"):
                        print("  Aborted by user.")
                        return 1
                    if choice.startswith("r"):
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
                            print(
                                f"    Still {response2.status_code}; continuing offline. "
                                "Run `research-hub init` again to retry."
                            )
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
    if interactive and chrome_ok:
        answer = input("  Run NotebookLM Google login now? [y/N]: ").strip().lower()
        if answer == "y":
            print("  Run: research-hub notebooklm login")

    _print_completion_banner(vault, config_path)
    return 0
