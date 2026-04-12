"""Interactive setup wizard for first-time research-hub users."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import platformdirs


def get_default_config_dir() -> Path:
    return Path(platformdirs.user_config_dir("research-hub", ensure_exists=False))


def get_default_config_path() -> Path:
    return get_default_config_dir() / "config.json"


def run_init(
    *,
    vault_root: str | None = None,
    zotero_key: str | None = None,
    zotero_library_id: str | None = None,
    non_interactive: bool = False,
    persona: str = "researcher",
) -> int:
    """Run the init wizard. Returns 0 on success, 1 on error."""
    interactive = sys.stdin.isatty() and not non_interactive
    is_analyst = persona == "analyst"

    if vault_root:
        vault = Path(vault_root).expanduser().resolve()
    elif interactive:
        default = str(Path.home() / "knowledge-base")
        answer = input(f"Vault root directory [{default}]: ").strip()
        vault = Path(answer or default).expanduser().resolve()
    else:
        print("Error: --vault is required in non-interactive mode")
        return 1

    for subdir in ("raw", "hub", "logs", "pdfs", ".research_hub"):
        (vault / subdir).mkdir(parents=True, exist_ok=True)
    print(f"  Vault root: {vault}")

    if not is_analyst and not zotero_key and interactive:
        print("\n  Zotero API key is needed to sync papers.")
        print("  Get one at: https://www.zotero.org/settings/keys")
        zotero_key = input("  Zotero API key: ").strip() or None
    if not is_analyst and not zotero_library_id and interactive:
        print("  Your Zotero library ID (numeric, from the same settings page):")
        zotero_library_id = input("  Zotero library ID: ").strip() or None

    if is_analyst:
        print("  Persona: analyst -> skipping Zotero (Obsidian + NotebookLM only)")
        zotero_key = None
        zotero_library_id = None

    if not is_analyst and zotero_key and zotero_library_id:
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
                print(
                    f"  Zotero credentials: returned {response.status_code} (may still work)"
                )
        except Exception as exc:
            print(f"  Zotero credentials: could not verify ({exc})")

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

    if is_analyst:
        config["no_zotero"] = True
    else:
        config.pop("no_zotero", None)
        if zotero_key:
            zotero = config.setdefault("zotero", {})
            if isinstance(zotero, dict):
                zotero["api_key"] = zotero_key
        if zotero_library_id:
            zotero = config.setdefault("zotero", {})
            if isinstance(zotero, dict):
                zotero["library_id"] = zotero_library_id

    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  Config written: {config_path}")

    try:
        from research_hub.notebooklm.cdp_launcher import find_chrome_binary

        chrome = find_chrome_binary()
        if chrome:
            print(f"  Chrome detected: {chrome}")
            if interactive:
                answer = input("  Run NotebookLM login now? [y/N]: ").strip().lower()
                if answer == "y":
                    print("  Run: research-hub notebooklm login --cdp")
        else:
            print("  Chrome: not found (install Chrome for NotebookLM features)")
    except ImportError:
        print("  Chrome check: skipped (playwright not installed)")

    if is_analyst:
        print("\n  Setup complete (analyst mode)!")
        print("  Next steps:")
        print("    research-hub doctor")
        print("    research-hub add 10.1234/example  # add by DOI")
    else:
        print("\n  Setup complete!")
        print("  Next steps:")
        print("    research-hub doctor           # verify everything is green")
        print("    research-hub search 'topic'   # find papers")
    return 0
