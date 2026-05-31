"""Shared CLI helpers for Research Hub."""

from __future__ import annotations

import argparse
from contextlib import nullcontext, redirect_stdout
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import re
import sys

from research_hub._deprecation import warn_deprecated


_CLI_DEPRECATED_ALIASES: dict[tuple[str, ...], tuple[str, str]] = {
    ("ask",): ("research-hub ask", "research-hub notebooklm ask"),
    ("summarize",): ("research-hub summarize", "research-hub paper summarize"),
    ("cleanup",): ("research-hub cleanup", "research-hub tidy"),
    ("label-bulk",): ("research-hub label-bulk", "research-hub paper bulk-relabel"),
}


def _cli_deprecated_alias(argv: list[str] | tuple[str, ...]) -> tuple[str, str] | None:
    if not argv:
        return None
    command = argv[0]
    for alias, deprecation in _CLI_DEPRECATED_ALIASES.items():
        if (command,) == alias:
            return deprecation
    return None


def _warn_cli_deprecated_alias_from_argv(argv: list[str] | tuple[str, ...]) -> None:
    deprecation = _cli_deprecated_alias(argv)
    if deprecation is None:
        return
    what, replacement = deprecation
    warn_deprecated(
        what,
        replacement=replacement,
        removed_in="v2.0.0",
        stacklevel=3,
    )


def _warn_cli_deprecated_alias_from_args(args: argparse.Namespace) -> None:
    _warn_cli_deprecated_alias_from_argv([str(args.command or "")])


def _json_safe(value):
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        return _json_safe(value.to_dict())
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _emit_cli_json(command: str, rc: int, report) -> None:
    """Emit a structured JSON envelope for any CLI subcommand under --json.

    Envelope shape (v0.91.0 W5 contract, schema_version 1.0):

        {
          "schema_version": "1.0",
          "ok": bool,                 # rc == 0
          "command": str,             # subcommand name, e.g. "auto"
          "version": str,             # research_hub.__version__
          "report": <_json_safe(report)>,   # per-command shape
        }

    The ENVELOPE is versioned and stable. The `report` payload shape
    is per-command — agents reasoning against `_emit_cli_json` output
    should branch on `command` to know what to expect inside `report`.
    Per-Report schema_version is tracked for v0.92 (G2 audit #8 follow-up).

    Forward-compat: pre-v0.91 envelopes lack `schema_version` entirely.
    A reader that sees the key MISSING should treat the envelope as
    schema 0 (legacy) and continue — the {ok, command, version, report}
    keys are present in every version since v0.89.0.

    v0.89.1: default=str catches the edge cases _json_safe returns
    verbatim (datetime, bytes, Exception instances, custom objects)
    — the v0.89.0 code-review skill flagged these would crash
    json.dumps. Cheap belt-and-suspenders.
    """
    from research_hub import __version__

    payload = {
        "schema_version": "1.0",
        "ok": rc == 0,
        "command": command,
        "version": __version__,
        "report": _json_safe(report),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _stdout_to_stderr(enabled: bool):
    return redirect_stdout(sys.stderr) if enabled else nullcontext()


def _read_zotero_key_from_frontmatter(md_path: Path) -> str | None:
    """Pull the `zotero-key: XXXX` line out of an Obsidian raw note."""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    frontmatter = text[3:end]
    import re as _re
    match = _re.search(r"^zotero-key:\s*([A-Z0-9]+)", frontmatter, _re.MULTILINE)
    return match.group(1) if match else None


def _parse_year_range(spec: str | None) -> tuple[int | None, int | None]:
    if spec is None:
        return (None, None)
    text = spec.strip()
    if not text:
        raise SystemExit(f"invalid --year spec: {spec}")
    if re.fullmatch(r"\d{4}", text):
        year = int(text)
        return (year, year)
    if re.fullmatch(r"\d{4}-", text):
        return (int(text[:4]), None)
    if re.fullmatch(r"-\d{4}", text):
        return (None, int(text[1:]))
    if re.fullmatch(r"\d{4}-\d{4}", text):
        start, end = text.split("-", 1)
        return (int(start), int(end))
    raise SystemExit(f"invalid --year spec: {spec}")


def _parse_csv_terms(spec: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in spec.split(",") if item.strip())


def _parse_negative_terms(spec: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in re.split(r"[\s,]+", spec) if item.strip())


def _parse_seed_dois(seed_dois: str, seed_dois_file: str | None) -> tuple[str, ...]:
    values: list[str] = []
    if seed_dois:
        values.extend(item.strip() for item in seed_dois.split(",") if item.strip())
    if seed_dois_file:
        for line in Path(seed_dois_file).read_text(encoding="utf-8").splitlines():
            doi = line.strip()
            if doi and not doi.startswith("#"):
                values.append(doi)
    return tuple(values)
