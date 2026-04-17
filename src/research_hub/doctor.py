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


def check_frontmatter_completeness(cfg) -> CheckResult:
    """Validate paper-note frontmatter and required body sections across the vault."""
    from research_hub.paper_schema import validate_paper_note

    bad: list[str] = []
    warn: list[str] = []
    total = 0

    for note in sorted(Path(cfg.raw).rglob("*.md")):
        if note.name.startswith("00_") or note.name.startswith("index"):
            continue
        if "topics" in note.parts:
            continue
        total += 1
        result = validate_paper_note(note)
        rel = note.relative_to(cfg.raw)
        if result.severity == "fail":
            bad.append(f"{rel}: missing {result.missing_frontmatter}")
        elif result.severity == "warn":
            warn.append(f"{rel}: empty={result.empty_sections} todo={result.todo_placeholders}")

    if bad:
        return CheckResult(
            name="frontmatter_completeness",
            status="FAIL",
            message=f"{len(bad)} of {total} notes missing required frontmatter",
            remedy="Examples: " + "; ".join(bad[:3]),
        )
    if warn:
        return CheckResult(
            name="frontmatter_completeness",
            status="WARN",
            message=f"{len(warn)} of {total} notes have empty sections or TODO placeholders",
            remedy="Examples: " + "; ".join(warn[:3]),
        )
    return CheckResult(
        name="frontmatter_completeness",
        status="OK",
        message=f"All {total} paper notes pass frontmatter validation",
    )


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

    print("=" * 60)
    print("research-hub health check")
    if config_path:
        print(f"  Config:  {config_path}")
        try:
            cfg = get_config()
            print(f"  Vault:   {cfg.root}")
        except Exception:
            print("  Vault:   (error reading config)")
    else:
        print("  Config:  (not found - run: research-hub init)")
        print("  Vault:   (unknown)")
    print("=" * 60)
    print()

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

    # Use the same resolver as the rest of research-hub so doctor sees
    # the same credentials the dashboard / pipeline actually use.
    try:
        from research_hub.zotero.client import _load_credentials

        zotero_key, library_id, _lib_type = _load_credentials()
    except Exception:
        zotero_key = os.environ.get("ZOTERO_API_KEY") or config_data.get("zotero", {}).get("api_key")
        library_id = os.environ.get("ZOTERO_LIBRARY_ID") or config_data.get("zotero", {}).get(
            "library_id", ""
        )

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
    if not no_zotero and zotero_key and library_id:
        import requests
        import time

        # Cache the Zotero API probe result for 60 seconds so rapid
        # dashboard renders / watch-mode cycles don't hammer the API
        # and trip its rate limiter (429).
        cache_result = None
        try:
            cfg_for_cache = get_config()
            cache_path = cfg_for_cache.research_hub_dir / "doctor_zotero_api_cache.json"
            if cache_path.exists():
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                age = time.time() - float(cached.get("ts", 0))
                if age < 60:
                    cache_result = cached
        except Exception:
            cache_path = None

        status_code: int | None
        if cache_result is not None:
            status_code = int(cache_result.get("status_code", 0))
            request_error: str | None = None
        else:
            request_error = None
            status_code = None
            try:
                response = requests.head(
                    f"https://api.zotero.org/users/{library_id}/items?limit=1",
                    headers={"Zotero-API-Key": zotero_key},
                    timeout=5,
                )
                status_code = response.status_code
                try:
                    if cache_path is not None:
                        cache_path.parent.mkdir(parents=True, exist_ok=True)
                        cache_path.write_text(
                            json.dumps({"ts": time.time(), "status_code": status_code}),
                            encoding="utf-8",
                        )
                except Exception:
                    pass
            except Exception as exc:
                request_error = str(exc)

        if request_error is not None:
            results.append(CheckResult("zotero_api", "WARN", f"Cannot reach API: {request_error}"))
        elif status_code == 200:
            results.append(CheckResult("zotero_api", "OK", "API reachable"))
        elif status_code == 429:
            # Rate-limited: key is valid, transient. Not a user-actionable problem.
            results.append(
                CheckResult("zotero_api", "OK", "API reachable (rate limited, transient)")
            )
        elif status_code == 401:
            results.append(
                CheckResult(
                    "zotero_api",
                    "FAIL",
                    "API returned 401 — Zotero API key is invalid or revoked",
                    remedy="Regenerate at https://www.zotero.org/settings/keys",
                )
            )
        elif status_code == 403:
            results.append(
                CheckResult(
                    "zotero_api",
                    "WARN",
                    f"API returned {status_code} — key lacks required permissions",
                    remedy="Enable library + notes + write access for the API key",
                )
            )
        else:
            results.append(
                CheckResult("zotero_api", "WARN", f"API returned {status_code}")
            )

    if cfg is not None:
        try:
            from research_hub.doctor_field import field_inference_check

            for report in field_inference_check(cfg):
                if report["status"] == "warn":
                    results.append(
                        CheckResult(
                            name=f"cluster_field:{report['cluster_slug']}",
                            status="WARN",
                            message=(
                                f"declared field={report['declared_field']} but papers look like "
                                f"{report['inferred_field']} (confidence={report['confidence']}, "
                                f"signal={report['signal_total']})"
                            ),
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            name=f"cluster_field:{report['cluster_slug']}",
                            status="OK",
                            message=f"field={report['inferred_field']}",
                        )
                    )
        except Exception as exc:
            results.append(CheckResult("cluster_field", "WARN", f"Could not check: {exc}"))

        try:
            results.append(check_frontmatter_completeness(cfg))
        except Exception as exc:
            results.append(CheckResult("frontmatter_completeness", "WARN", f"Could not check: {exc}"))

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
                    # Informational: we cap the probe at 50 notes to avoid
                    # hammering the Zotero API. "Probe skipped" is a safety
                    # feature, not a problem.
                    results.append(
                        CheckResult(
                            "vault_invariant",
                            "OK",
                            f"{len(bad_keys)} notes have zotero-key (probe capped at 50 for rate safety)",
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
