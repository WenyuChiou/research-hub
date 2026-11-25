"""Fail-closed CI change classifier for WenyuChiou/research-hub.

Inspects the real base-to-head diff for pull requests or before-to-after diff for
master pushes and routes CI jobs to one of four scopes:

- docs:   docs/README/openwiki and pure docs contract tests
- skills: skills/ and src/research_hub/skills_data/ changes (+ optional docs)
- code:   known Python/web source and test changes (selective workspace UI)
- full:   dependency/CI infra, verify/** pushes, unknown paths, or diff errors
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

OID_RE = re.compile(r"^[0-9a-f]{40}$")

DOCS_EXACT = frozenset({
    "README.md",
    "README.zh-TW.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "UPGRADE.md",
    "LICENSE",
    "SECURITY.md",
    "tests/test_readme_entry_paths.py",
    "tests/test_v089_readme_machine_parseable.py",
    "tests/test_workspace_docs.py",
    "tests/test_summary_doc_contract.py",
    "tests/test_mcp_tools_doc_coverage.py",
    "tests/test_native_summary_platform_docs.py",
    "tests/test_v040_onboarding.py",
    "tests/test_v091_w6_rationalize.py",
})
DOCS_PREFIXES = ("docs/", "openwiki/")

SKILLS_EXACT = frozenset({
    ".claude-plugin/plugin.json",
    "tests/test_skills_data_parity.py",
    "tests/test_skill_structure.py",
    "tests/test_frontmatter_schema.py",
    "tests/test_v066_skill_schema.py",
    "tests/test_v066_research_workspace_docs.py",
    "tests/test_v068_3_version_sync.py",
    "tests/test_v068_legacy_knowledge_base_alias.py",
    "tests/test_skill_installer.py",
    "tests/test_triage_single_paper_routing.py",
    "tests/test_discovery_observations.py",
    "tests/test_check_claims_schema.py",
    "tests/test_gap_preliminary_directions.py",
    "tests/test_adversarial_recall_evidence.py",
    "tests/test_handoff_gap_to_topic_design_helper.py",
    "tests/test_source_audit_profile.py",
    "tests/test_research_workflow_orchestrator.py",
    "tests/test_workspace_abstract_resource_bytes.py",
    "tests/test_stage1_native_handoff_guidance.py",
    "tests/test_fulltext_summary_guidance.py",
    "tests/test_summarize_prompt_only.py",
    "tests/test_selected_hub_handoff_contract.py",
    "tests/test_research_process_receipts.py",
    "tests/test_source_claim_guidance.py",
    "tests/test_stage1_budget_guidance.py",
    "tests/test_stage1_eval_contract.py",
    "tests/test_native_skill_schema_resource.py",
    "tests/test_native_reader.py",
})
SKILLS_PREFIXES = ("skills/", "src/research_hub/skills_data/")

INFRA_EXACT = frozenset({
    "pyproject.toml",
    "constraints.txt",
    ".github/workflows/ci.yml",
    "scripts/check_ci_checkout.py",
    "scripts/classify_ci_changes.py",
    "tests/test_ci_routing.py",
})

WORKSPACE_UI_EXACT = frozenset({
    "src/research_hub/__init__.py",
    "src/research_hub/__main__.py",
    "src/research_hub/cli.py",
    "src/research_hub/mcp_server.py",
})
WORKSPACE_UI_PREFIXES = (
    "web/",
    "src/research_hub/workspace/",
    "src/research_hub/workspace_static/",
    "scripts/workspace_",
    "tests/test_workspace_",
)
PYTHON_CODE_PREFIXES = ("src/", "tests/", "scripts/")


def _outputs(
    scope: str,
    *,
    docs_skills_linux: bool,
    docs_skills_windows: bool,
    workspace: bool,
    python_tests: bool,
    full_os_matrix: bool,
    stress: bool,
    audit: bool,
    reason: str = "",
) -> dict[str, str]:
    result = {
        "scope": scope,
        "run_docs_skills_linux": "true" if docs_skills_linux else "false",
        "run_docs_skills_windows": "true" if docs_skills_windows else "false",
        "run_workspace": "true" if workspace else "false",
        "run_python_tests": "true" if python_tests else "false",
        "run_full_os_matrix": "true" if full_os_matrix else "false",
        "run_stress": "true" if stress else "false",
        "run_audit": "true" if audit else "false",
    }
    if reason:
        result["reason"] = reason
    return result


def full_outputs(reason: str) -> dict[str, str]:
    return _outputs(
        "full",
        docs_skills_linux=False,
        docs_skills_windows=False,
        workspace=True,
        python_tests=True,
        full_os_matrix=True,
        stress=True,
        audit=True,
        reason=reason,
    )


def _valid_relpath(raw: str) -> str | None:
    if not raw or "\\" in raw or raw.startswith("/"):
        return None
    normalized = PurePosixPath(raw).as_posix()
    if normalized in {"", "."} or ".." in PurePosixPath(normalized).parts:
        return None
    return normalized


def _is_docs(path: str) -> bool:
    return path in DOCS_EXACT or path.startswith(DOCS_PREFIXES)


def _is_skills(path: str) -> bool:
    return path in SKILLS_EXACT or path.startswith(SKILLS_PREFIXES)


def _is_workspace_ui(path: str) -> bool:
    if _is_docs(path) or _is_skills(path):
        return False
    return path in WORKSPACE_UI_EXACT or path.startswith(WORKSPACE_UI_PREFIXES)


def _is_known_code(path: str) -> bool:
    return path.startswith(PYTHON_CODE_PREFIXES) or path.startswith("web/")


def classify_paths(
    paths: list[str] | tuple[str, ...],
    *,
    event_name: str,
    github_ref: str,
) -> dict[str, str]:
    """Classify changed repository paths into a fail-closed CI routing scope."""
    if event_name == "push" and github_ref.startswith("refs/heads/verify/"):
        return full_outputs("verify/** push always runs full CI")
    if not paths:
        return full_outputs("empty diff fails closed to full CI")

    clean: list[str] = []
    for raw in paths:
        norm = _valid_relpath(raw)
        if norm is None:
            return full_outputs(f"invalid path {raw!r} fails closed to full CI")
        clean.append(norm)

    if any(path in INFRA_EXACT for path in clean):
        return full_outputs("CI/packaging infrastructure changed")

    if all(_is_docs(path) for path in clean):
        return _outputs(
            "docs",
            docs_skills_linux=True,
            docs_skills_windows=False,
            workspace=False,
            python_tests=False,
            full_os_matrix=False,
            stress=False,
            audit=False,
            reason="documentation-only change",
        )

    if all(_is_docs(path) or _is_skills(path) for path in clean):
        return _outputs(
            "skills",
            docs_skills_linux=True,
            docs_skills_windows=True,
            workspace=False,
            python_tests=False,
            full_os_matrix=False,
            stress=False,
            audit=False,
            reason="skills/plugin contract change",
        )

    if any(not (_is_docs(path) or _is_skills(path) or _is_known_code(path)) for path in clean):
        return full_outputs("unrecognized root or config path fails closed to full CI")

    needs_workspace = any(_is_workspace_ui(path) for path in clean)
    return _outputs(
        "code",
        docs_skills_linux=False,
        docs_skills_windows=False,
        workspace=needs_workspace,
        python_tests=True,
        full_os_matrix=False,
        stress=True,
        audit=False,
        reason="source/test change (workspace UI)" if needs_workspace else "source/test change",
    )


def _nonzero_oid(value: object) -> str | None:
    if not isinstance(value, str) or not OID_RE.fullmatch(value) or value == "0" * 40:
        return None
    return value


def _git(*args: str, cwd: Path | None) -> bytes:
    proc = subprocess.run(
        ["git", "--no-replace-objects", *args],
        cwd=cwd,
        capture_output=True,
        check=True,
        timeout=15,
    )
    return proc.stdout


def changed_paths_from_event(
    event_name: str,
    event: object,
    github_ref: str,
    *,
    cwd: Path | None = None,
) -> list[str]:
    """Resolve the git changed file list for PR or master push events."""
    if not isinstance(event, dict):
        raise ValueError("event payload must be a JSON object")

    if event_name == "pull_request":
        pr = event.get("pull_request")
        if not isinstance(pr, dict):
            raise ValueError("missing pull_request payload")
        base = _nonzero_oid((pr.get("base") or {}).get("sha") if isinstance(pr.get("base"), dict) else None)
        head = _nonzero_oid((pr.get("head") or {}).get("sha") if isinstance(pr.get("head"), dict) else None)
        if not base or not head:
            raise ValueError("invalid PR base/head SHA")
        merge_base = _git("merge-base", base, head, cwd=cwd).decode("utf-8").strip()
        raw = _git("diff", "--name-only", "-z", merge_base, head, cwd=cwd)
    elif event_name == "push":
        if github_ref.startswith("refs/heads/verify/"):
            return []
        before = _nonzero_oid(event.get("before"))
        after = _nonzero_oid(event.get("after"))
        if not before or not after:
            raise ValueError("missing or zero before/after SHA")
        _git("cat-file", "-e", f"{before}^{{commit}}", cwd=cwd)
        raw = _git("diff", "--name-only", "-z", before, after, cwd=cwd)
    else:
        raise ValueError(f"unsupported event: {event_name!r}")

    return [item.decode("utf-8", errors="surrogateescape") for item in raw.split(b"\x00") if item]


def classify_event(
    event_name: str,
    event: object,
    github_ref: str,
    *,
    cwd: Path | None = None,
) -> dict[str, str]:
    """Compute CI routing outputs from an Actions event payload, failing closed."""
    if event_name == "push" and github_ref.startswith("refs/heads/verify/"):
        return full_outputs("verify/** push always runs full CI")
    try:
        paths = changed_paths_from_event(event_name, event, github_ref, cwd=cwd)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        return full_outputs(f"diff resolution failed ({type(exc).__name__}: {exc})")
    return classify_paths(paths, event_name=event_name, github_ref=github_ref)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify changed paths for CI routing.")
    parser.add_argument("--github-output", type=Path, default=None)
    args = parser.parse_args(argv)

    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    github_ref = os.environ.get("GITHUB_REF", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")

    if event_path and Path(event_path).is_file():
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            result = full_outputs(f"event JSON unreadable ({type(exc).__name__})")
        else:
            result = classify_event(event_name, event, github_ref)
    else:
        result = full_outputs("GITHUB_EVENT_PATH missing")

    if args.github_output is not None:
        lines = [f"{k}={v}" for k, v in result.items() if k != "reason"]
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
