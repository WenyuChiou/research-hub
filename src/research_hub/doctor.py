"""Health check for research-hub installation."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    remedy: str = ""


def _load_config_json(config_path: Path | None) -> dict:
    if config_path is None or not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_doctor() -> list[CheckResult]:
    """Run all health checks and return results."""
    from research_hub.config import _resolve_config_path, get_config

    results: list[CheckResult] = []
    config_path = _resolve_config_path()
    config_data = _load_config_json(config_path)

    if config_path and config_path.exists():
        results.append(CheckResult("config", "OK", f"Found at {config_path}"))
    else:
        results.append(
            CheckResult(
                "config",
                "FAIL",
                "No config file found",
                remedy="Run: research-hub init",
            )
        )

    cfg = None
    try:
        cfg = get_config()
        if cfg.root.exists():
            results.append(CheckResult("vault", "OK", str(cfg.root)))
            for subdir in ("raw", ".research_hub"):
                if not (cfg.root / subdir).exists():
                    results.append(
                        CheckResult(
                            f"vault/{subdir}",
                            "WARN",
                            f"Missing {subdir}/",
                            remedy=f"Create: {cfg.root / subdir}",
                        )
                    )
        else:
            results.append(
                CheckResult(
                    "vault",
                    "FAIL",
                    f"Root does not exist: {cfg.root}",
                    remedy="Run: research-hub init",
                )
            )
    except Exception as exc:
        results.append(CheckResult("vault", "FAIL", str(exc)))

    no_zotero_config = bool(config_data.get("no_zotero", False))
    no_zotero_env = os.environ.get("RESEARCH_HUB_NO_ZOTERO", "").lower() in ("1", "true", "yes")
    no_zotero = no_zotero_config or no_zotero_env
    zotero_key = os.environ.get("ZOTERO_API_KEY") or config_data.get("zotero", {}).get("api_key")
    if no_zotero:
        results.append(CheckResult("zotero_key", "OK", "Skipped (analyst mode)"))
    elif zotero_key:
        results.append(CheckResult("zotero_key", "OK", "API key configured"))
    else:
        results.append(
            CheckResult(
                "zotero_key",
                "FAIL",
                "No Zotero API key found",
                remedy="Set ZOTERO_API_KEY env var or run: research-hub init",
            )
        )

    library_id = os.environ.get("ZOTERO_LIBRARY_ID") or config_data.get("zotero", {}).get(
        "library_id", ""
    )
    if not no_zotero and zotero_key and library_id:
        import requests

        try:
            response = requests.head(
                f"https://api.zotero.org/users/{library_id}/items?limit=1",
                headers={"Zotero-API-Key": zotero_key},
                timeout=5,
            )
            if response.status_code == 200:
                results.append(CheckResult("zotero_api", "OK", "API reachable"))
            else:
                results.append(
                    CheckResult("zotero_api", "WARN", f"API returned {response.status_code}")
                )
        except Exception as exc:
            results.append(CheckResult("zotero_api", "WARN", f"Cannot reach API: {exc}"))

    if cfg is not None:
        try:
            dedup_path = cfg.research_hub_dir / "dedup_index.json"
            if dedup_path.exists():
                data = json.loads(dedup_path.read_text(encoding="utf-8"))
                doi_count = len(data.get("doi_to_hits", {}))
                title_count = len(data.get("title_to_hits", {}))
                if doi_count or title_count:
                    results.append(
                        CheckResult(
                            "dedup_index",
                            "OK",
                            f"{doi_count} DOIs, {title_count} titles",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            "dedup_index",
                            "WARN",
                            "Empty",
                            remedy="Run: research-hub dedup rebuild",
                        )
                    )
            else:
                results.append(
                    CheckResult(
                        "dedup_index",
                        "WARN",
                        "Not built yet",
                        remedy="Run: research-hub dedup rebuild",
                    )
                )
        except Exception as exc:
            results.append(CheckResult("dedup_index", "WARN", f"Could not read: {exc}"))
    else:
        results.append(CheckResult("dedup_index", "WARN", "Could not read"))

    if cfg is not None:
        if no_zotero or not zotero_key or not library_id:
            results.append(CheckResult("vault_invariant", "OK", "Skipped (no Zotero probing)"))
        else:
            try:
                bad_keys: list[tuple[Path, str]] = []
                for md_path in cfg.raw.rglob("*.md"):
                    try:
                        text = md_path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    match = re.search(r"^zotero-key:\s*(\S+)", text, re.MULTILINE)
                    if match and match.group(1):
                        bad_keys.append(
                            (md_path, match.group(1).strip().strip('"').strip("'"))
                        )
                if len(bad_keys) > 50:
                    results.append(
                        CheckResult(
                            "vault_invariant",
                            "WARN",
                            f"{len(bad_keys)} notes have zotero-key (probe skipped for >50)",
                        )
                    )
                else:
                    sample = bad_keys[:5]
                    stale: list[tuple[str, str]] = []
                    for md_path, key in sample:
                        try:
                            response = requests.head(
                                f"https://api.zotero.org/users/{library_id}/items/{key}",
                                headers={"Zotero-API-Key": zotero_key},
                                timeout=3,
                            )
                            if response.status_code == 404:
                                stale.append((md_path.name, key))
                        except Exception:
                            break
                    if stale:
                        results.append(
                            CheckResult(
                                "vault_invariant",
                                "WARN",
                                f"{len(stale)} sample notes reference deleted Zotero items",
                                remedy="Run: research-hub dedup invalidate --path <path>",
                            )
                        )
                    else:
                        results.append(
                            CheckResult(
                                "vault_invariant",
                                "OK",
                                f"Sampled {len(sample)} of {len(bad_keys)} notes - all Zotero keys valid",
                            )
                        )
            except Exception as exc:
                results.append(CheckResult("vault_invariant", "WARN", f"Could not check: {exc}"))

        try:
            dedup_path = cfg.research_hub_dir / "dedup_index.json"
            if dedup_path.exists():
                data = json.loads(dedup_path.read_text(encoding="utf-8"))
                stale_paths = 0
                sample_count = 0
                for hits in list(data.get("title_to_hits", {}).values())[:100]:
                    for hit in hits:
                        if hit.get("obsidian_path"):
                            sample_count += 1
                            if not Path(hit["obsidian_path"]).exists():
                                stale_paths += 1
                if stale_paths > 0:
                    results.append(
                        CheckResult(
                            "dedup_consistency",
                            "WARN",
                            f"{stale_paths}/{sample_count} sampled obsidian paths are stale",
                            remedy="Run: research-hub dedup rebuild --obsidian-only",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            "dedup_consistency",
                            "OK",
                            f"Sampled {sample_count} obsidian paths - all valid",
                        )
                    )
            else:
                results.append(CheckResult("dedup_consistency", "OK", "Skipped (no dedup index yet)"))
        except Exception:
            pass

    try:
        from research_hub.notebooklm.cdp_launcher import find_chrome_binary

        chrome = find_chrome_binary()
        if chrome:
            results.append(CheckResult("chrome", "OK", str(chrome)))
        else:
            results.append(
                CheckResult(
                    "chrome",
                    "WARN",
                    "Not found (NotebookLM features unavailable)",
                    remedy="Install Google Chrome",
                )
            )
    except ImportError:
        results.append(
            CheckResult(
                "chrome",
                "WARN",
                "playwright not installed",
                remedy="pip install research-hub-pipeline[playwright]",
            )
        )

    if cfg is not None:
        try:
            session_dir = cfg.research_hub_dir / "nlm_sessions" / "default"
            if session_dir.exists() and any(session_dir.iterdir()):
                results.append(CheckResult("nlm_session", "OK", str(session_dir)))
            else:
                results.append(
                    CheckResult(
                        "nlm_session",
                        "WARN",
                        "No saved session",
                        remedy="Run: research-hub notebooklm login --cdp",
                    )
                )
        except Exception:
            results.append(CheckResult("nlm_session", "WARN", "Could not check"))
    else:
        results.append(CheckResult("nlm_session", "WARN", "Could not check"))

    return results


def print_doctor_report(results: list[CheckResult]) -> int:
    """Print the report and return exit code (0 = no FAIL, 1 = has FAIL)."""
    has_fail = False
    for result in results:
        icon = {"OK": "OK", "WARN": "!!", "FAIL": "XX"}[result.status]
        line = f"  [{icon}] {result.name}: {result.message}"
        if result.remedy:
            line += f"\n        -> {result.remedy}"
        print(line)
        if result.status == "FAIL":
            has_fail = True
    return 1 if has_fail else 0
