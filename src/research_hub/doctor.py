"""Health check for research-hub installation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


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

    zotero_key = os.environ.get("ZOTERO_API_KEY") or config_data.get("zotero", {}).get("api_key")
    if zotero_key:
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
    if zotero_key and library_id:
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
                entries = data.get("doi_entries", data.get("entries", []))
                results.append(CheckResult("dedup_index", "OK", f"{len(entries)} entries"))
            else:
                results.append(
                    CheckResult(
                        "dedup_index",
                        "WARN",
                        "Not built yet",
                        remedy="Run: research-hub index",
                    )
                )
        except Exception:
            results.append(CheckResult("dedup_index", "WARN", "Could not read"))
    else:
        results.append(CheckResult("dedup_index", "WARN", "Could not read"))

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
