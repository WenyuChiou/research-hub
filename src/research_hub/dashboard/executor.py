"""Whitelisted subprocess executor for dashboard Manage forms."""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

from research_hub.dashboard.manage_commands import (
    build_compose_draft_command,
    build_manage_command,
)

ALLOWED_ACTIONS = frozenset(
    {
        "rename",
        "merge",
        "split",
        "bind-zotero",
        "bind-nlm",
        "delete",
        "move",
        "label",
        "mark",
        "remove",
        "ingest",
        "topic-build",
        "dashboard",
        "pipeline-repair",
        "notebooklm-bundle",
        "notebooklm-upload",
        "notebooklm-generate",
        "notebooklm-download",
        "notebooklm-ask",
        "vault-polish-markdown",
        "bases-emit",
        "discover-new",
        "discover-continue",
        "autofill-apply",
        "compose-draft",
        "clusters-analyze",
    }
)

DEFAULT_TIMEOUT_SECONDS = 300
_ORIGINAL_SUBPROCESS_RUN = subprocess.run


@dataclass
class ExecResult:
    ok: bool
    action: str
    command: list[str]
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _decode_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _tokenize_builder_output(cmd_str: str | None, *, action: str) -> list[str]:
    if not cmd_str:
        raise ValueError(f"missing required fields for action {action!r}")
    tokens = shlex.split(cmd_str)
    if tokens and tokens[0] == "research-hub":
        tokens = tokens[1:]
    return [sys.executable, "-m", "research_hub", *tokens]


def _build_command_args(action: str, slug: str | None, fields: dict[str, Any]) -> list[str]:
    base = [sys.executable, "-m", "research_hub"]

    manage_actions = {
        "rename",
        "merge",
        "split",
        "bind-zotero",
        "bind-nlm",
        "delete",
        "notebooklm-bundle",
        "notebooklm-upload",
        "notebooklm-generate",
        "notebooklm-download",
        "notebooklm-ask",
        "vault-polish-markdown",
        "bases-emit",
    }
    if action in manage_actions:
        effective_slug = slug or str(fields.get("cluster_slug", "") or "")
        builder_fields = dict(fields)
        if "type" in builder_fields and "kind" not in builder_fields:
            builder_fields["kind"] = builder_fields["type"]
        return _tokenize_builder_output(
            build_manage_command(action, effective_slug, **builder_fields),
            action=action,
        )

    if action == "compose-draft":
        args = _tokenize_builder_output(
            build_compose_draft_command(
                cluster_slug=str(fields.get("cluster_slug", "") or ""),
                outline=str(fields.get("outline", "") or ""),
                quote_slugs=list(fields.get("quote_slugs") or []),
                style=str(fields.get("style", "apa") or "apa"),
            ),
            action=action,
        )
        if not fields.get("include_bibliography", True):
            args.append("--no-bibliography")
        return args

    if action == "move":
        return base + ["move", slug or "", "--to", str(fields["target_cluster"])]
    if action == "label":
        return base + ["label", slug or "", "--set", str(fields["label"])]
    if action == "mark":
        return base + ["mark", slug or "", "--status", str(fields["status"])]
    if action == "remove":
        args = base + ["remove", slug or ""]
        if fields.get("dry_run"):
            args.append("--dry-run")
        return args
    if action == "ingest":
        args = base + ["ingest"]
        if fields.get("cluster_slug"):
            args += ["--cluster", str(fields["cluster_slug"])]
        if fields.get("papers_input"):
            args += ["--papers-input", str(fields["papers_input"])]
        return args
    if action == "topic-build":
        return base + ["topic", "build", "--cluster", str(fields["cluster_slug"])]
    if action == "dashboard":
        return base + ["dashboard"]
    if action == "pipeline-repair":
        args = base + ["pipeline", "repair", "--cluster", str(fields["cluster_slug"])]
        args.append("--execute" if fields.get("execute") else "--dry-run")
        return args
    if action == "discover-new":
        args = base + ["discover", "new", "--cluster", str(fields["cluster_slug"])]
        if fields.get("query"):
            args += ["--query", str(fields["query"])]
        return args
    if action == "discover-continue":
        return base + [
            "discover",
            "continue",
            "--cluster",
            str(fields["cluster_slug"]),
            "--scored",
            str(fields["scored"]),
        ]
    if action == "autofill-apply":
        return base + [
            "autofill",
            "apply",
            "--cluster",
            str(fields["cluster_slug"]),
            "--scored",
            str(fields["scored"]),
        ]
    if action == "clusters-analyze":
        return base + [
            "clusters",
            "analyze",
            "--cluster",
            str(fields["cluster_slug"]),
            "--split-suggestion",
        ]

    raise ValueError(f"unknown action: {action!r}")


def execute_action(
    action: str,
    slug: str | None,
    fields: dict[str, Any] | None,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> ExecResult:
    """Validate and run a whitelisted research-hub subcommand."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"action {action!r} not in ALLOWED_ACTIONS")

    payload = dict(fields or {})
    args = _build_command_args(action, slug, payload)

    start = time.monotonic()
    if subprocess.run is not _ORIGINAL_SUBPROCESS_RUN:
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecResult(
                ok=proc.returncode == 0,
                action=action,
                command=args,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                returncode=proc.returncode,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecResult(
                ok=False,
                action=action,
                command=args,
                stdout=_decode_output(exc.stdout),
                stderr=f"timeout after {timeout}s",
                returncode=-1,
                duration_ms=duration_ms,
            )
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        duration_ms = int((time.monotonic() - start) * 1000)
        return ExecResult(
            ok=proc.returncode == 0,
            action=action,
            command=args,
            stdout=stdout or "",
            stderr=stderr or "",
            returncode=proc.returncode,
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        duration_ms = int((time.monotonic() - start) * 1000)
        return ExecResult(
            ok=False,
            action=action,
            command=args,
            stdout=_decode_output(stdout),
            stderr=f"timeout after {timeout}s (process killed)",
            returncode=-1,
            duration_ms=duration_ms,
        )
