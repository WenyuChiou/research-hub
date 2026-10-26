"""Interactive setup wizard for first-time research-hub users."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import platformdirs

from research_hub.security import chmod_sensitive
from research_hub.security.secret_box import encrypt
from research_hub.vault.graph_config import update_from_clusters_file


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

    # Presence is a passive hint, not a browser launch or authentication probe.
    # Driver startup itself may need IPC, so do not run it during local init.
    try:
        browser_package = importlib.util.find_spec("patchright")
    except (ImportError, ValueError):
        rows.append(("chrome", "WARN", "optional browser package presence unverified; NotebookLM setup can wait"))
    else:
        if browser_package is not None:
            rows.append(("chrome", "INFO", "optional browser package found; browser launch and NotebookLM authentication unverified"))
        else:
            rows.append(("chrome", "WARN", "optional browser package absent; NotebookLM setup can wait"))

    # Zotero (skip for personas that don't use it)
    if has_zotero:
        rows.append(("zotero", "INFO", "credentials configured; check access with `research-hub doctor`"))
    elif persona in {"analyst", "internal"}:
        rows.append(("zotero", "INFO", f"persona={persona} does not use Zotero"))
    else:
        rows.append(("zotero", "INFO", "not connected; local import is available; connect later with `research-hub init`"))

    # CLI presence is not proof of model access.
    for cli in ("claude", "codex", "gemini"):
        if shutil.which(cli):
            rows.append(("llm-cli", "INFO", f"`{cli}` on PATH; model access not verified"))
            break
    else:
        rows.append(("llm-cli", "INFO", "no supported LLM CLI on PATH -- crystals stay manual emit/apply"))

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


def _print_completion_banner(
    vault_path: Path, config_path: Path, *, persona: str = "researcher",
    has_zotero: bool = False, zotero_verified: bool = False,
) -> None:
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
    next_steps = [
        ("research-hub import-folder <folder> --cluster <slug> --extensions md,txt",
         "Import a selected local folder for reading; no accounts or Zotero writes"),
        ("research-hub serve --dashboard", "Browse local notes at http://127.0.0.1:8765/"),
    ]
    if has_zotero and zotero_verified and normalized_persona not in {"analyst", "internal"}:
        next_steps.extend([
            ('research-hub plan "your research topic"', "Review and confirm the plan"),
            ('research-hub auto "your research topic" --no-nlm',
             "Optional Zotero pipeline; first check doctor results and authorize its writes"),
        ])
    if not install_ready:
        next_steps.append(
            (
                f"research-hub install --platform {detected_host}",
                "Optional: install MCP skill files for your AI host",
            ),
        )

    lines = [
        "",
        "  Vault/config initialization complete; other components may still need setup.",
        "",
        f"  Your vault:  {vault_str}",
        f"  Your config: {config_str}",
        "",
        "  Before connected workflows, inspect each readiness result:",
        "    research-hub doctor",
        "    Config/session files and exit code 0 do not prove service access.",
        "",
        "  Zotero is an optional reference manager for saving and organizing papers.",
        ("  Zotero settings are saved; access is not verified by configuration alone."
         if has_zotero else
         "  Zotero is not connected; local reading does not need it."),
        ("  To opt into Zotero, choose: research-hub init --persona researcher"
         if normalized_persona in {"analyst", "internal"} else
         "  Connect later: research-hub init --persona " + normalized_persona),
        "  NotebookLM is optional; connect later: research-hub notebooklm login --auto-detect",
        "  For local PDF/DOCX import, install research-hub-pipeline[import].",
        "",
        "  NEXT STEPS (choose the workflow you need):",
        "",
    ]
    for idx, (command, detail) in enumerate(next_steps, start=1):
        lines.extend([f"  {idx}. {command}", f"     -> {detail}", ""])
    lines.extend(["  Docs: https://github.com/WenyuChiou/research-hub", ""])
    for line in lines:
        print(line)


def _print_sample_completion_banner(vault_path: Path) -> None:
    home_path = vault_path / "_HOME.md"
    print()
    print(f"  Sample vault ready at {vault_path}")
    print(f"  Open {home_path} in Obsidian to explore")
    print("  Or run: python -m research_hub describe")
    print(f"  To use real Zotero/NLM, run: research-hub setup --vault {vault_path}")
    print()


def run_init(
    *,
    vault_root: str | None = None,
    zotero_key: str | None = None,
    zotero_library_id: str | None = None,
    non_interactive: bool = False,
    persona: str | None = None,
    no_browser: bool = False,
    sample: bool = False,
) -> int:
    """Run the init wizard. Returns 0 on success, 1 on error."""
    interactive = sys.stdin.isatty() and not non_interactive
    valid_personas = {"researcher", "analyst", "humanities", "internal"}

    if sample:
        from research_hub.sample_vault import copy_sample_vault
        from research_hub.vault.hub_overview import populate_all_overviews

        if vault_root:
            vault = Path(vault_root).expanduser().resolve()
        elif interactive:
            default = str(Path.home() / "knowledge-base")
            answer = input(f"Sample vault directory [{default}]: ").strip()
            vault = Path(answer or default).expanduser().resolve()
        else:
            vault = (Path.home() / "knowledge-base").expanduser().resolve()
        vault.parent.mkdir(parents=True, exist_ok=True)
        # P0 guard (v0.89.1): copy_sample_vault() shutil.rmtree's any
        # non-None destination that exists. Without this check, a user
        # who points --sample at their real vault (e.g. ~/knowledge-base
        # with 49 ingested papers) silently loses everything. Refuse to
        # clobber non-empty destinations; the user must pass an empty
        # path or a new one.
        if vault.exists() and any(vault.iterdir()):
            print(f"[init --sample] {vault} is not empty.")
            print("  Pass an empty path or a new one to avoid clobbering your work.")
            print("  (init --sample REPLACES the destination -- it does not merge.)")
            return 1
        copy_sample_vault(vault)
        populate_all_overviews(
            SimpleNamespace(
                root=vault,
                clusters_file=vault / ".research_hub" / "clusters.yaml",
            ),
            force_rebuild=True,
        )
        _print_sample_completion_banner(vault)
        return 0

    config_path = get_default_config_path()
    config: dict[str, object] = {}
    try:
        try:
            config_path.stat()
        except FileNotFoundError:
            pass
        else:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("Config must be a JSON object")
            for section in ("knowledge_base", "zotero"):
                if section in config and not isinstance(config[section], dict):
                    raise ValueError(f"{section} must be a JSON object")
            saved_root = config.get("knowledge_base", {}).get("root")
            if "root" in config.get("knowledge_base", {}) and (
                not isinstance(saved_root, str) or not saved_root.strip()
            ):
                raise ValueError("Saved vault root must be a nonempty path string")
            if config.get("persona") is not None and not isinstance(config["persona"], str):
                raise ValueError("Saved persona must be a string")
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"Error: cannot reuse existing config {config_path} ({type(exc).__name__}); "
              "existing settings were not changed.")
        print("  Check the file permissions and JSON structure before retrying.")
        return 1

    saved_root = config.get("knowledge_base", {}).get("root")
    saved_zotero = config.get("zotero", {})
    if persona is None:
        persona = config.get("persona")
    if persona is None and interactive:
        print("\nZotero is an optional reference manager for saving and organizing papers.")
        print("Do you use Zotero for managing references? [y/N]")
        print("  y = yes  (researcher / humanities personas)")
        print("  N = no   (analyst / internal personas - local files; integrations optional)")
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
    elif saved_root:
        vault = Path(saved_root).expanduser().resolve()
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
    clusters_file = vault / ".research_hub" / "clusters.yaml"
    try:
        graph_update = update_from_clusters_file(vault, clusters_file)
        print(f"  [init] Wrote .obsidian/graph.json with {graph_update.color_groups_written} color groups")
    except Exception as exc:
        print(f"  [init] WARN could not write .obsidian/graph.json: {exc}", file=sys.stderr)

    if not no_zotero_persona:
        zotero_library_id = zotero_library_id or saved_zotero.get("library_id")

    connect_zotero = False
    if not no_zotero_persona and not zotero_key and not saved_zotero.get("api_key") and interactive:
        print("\n  Zotero is an optional reference manager for saving and organizing papers.")
        print("  Local import works without it; Zotero-backed auto/ingest needs credentials.")
        connect_zotero = input("  Connect Zotero now? [y/N]: ").strip().lower() == "y"
    if connect_zotero:
        if not no_browser:
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
        print("  Leave the key blank to set up later and use local import now.")
        zotero_key = input("  Zotero API key: ").strip() or None
    if not no_zotero_persona and (zotero_key or saved_zotero.get("api_key")) and not zotero_library_id and interactive:
        print("  Your Zotero library ID (numeric, from the same settings page):")
        zotero_library_id = input("  Zotero library ID: ").strip() or None

    if no_zotero_persona:
        print(f"  Persona: {persona} -> skipping Zotero (local files; integrations optional)")
        zotero_key = None
        zotero_library_id = None

    zotero_verified = False
    if not no_zotero_persona and zotero_key and zotero_library_id:
        import requests

        try:
            response = requests.head(
                f"https://api.zotero.org/users/{zotero_library_id}/items?limit=1",
                headers={"Zotero-API-Key": zotero_key},
                timeout=5,
            )
            if response.status_code == 200:
                zotero_verified = True
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
                            zotero_verified = True
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

    config_path.parent.mkdir(parents=True, exist_ok=True)

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

    stored_zotero = config.get("zotero", {})
    has_zotero = bool(
        isinstance(stored_zotero, dict) and stored_zotero.get("api_key")
        and stored_zotero.get("library_id") and not no_zotero_persona
    )
    readiness = _check_first_run_readiness(vault, persona=persona, has_zotero=has_zotero)
    _print_readiness(readiness)

    browser_package_present = any(sub == "chrome" and stat in {"OK", "INFO"} for sub, stat, _ in readiness)
    if interactive and browser_package_present and not no_browser and persona not in {"analyst", "internal"}:
        print("\n  NotebookLM is optional and sends selected sources to Google's service.")
        connect_nlm = input("  Connect NotebookLM now? [y/N]: ").strip().lower() == "y"
    else:
        connect_nlm = False
    if connect_nlm:
        print("  Launching NotebookLM Google login (Ctrl-C to skip).")
        try:
            from research_hub.setup_command import run_notebooklm_login

            run_notebooklm_login()
        except KeyboardInterrupt:
            print("  Skipped. Run later: research-hub notebooklm login --auto-detect")
        except Exception as exc:
            print(f"  Login failed: {exc}. Run later: research-hub notebooklm login --auto-detect")
    _print_completion_banner(
        vault, config_path, persona=persona,
        has_zotero=has_zotero, zotero_verified=zotero_verified,
    )
    return 0
