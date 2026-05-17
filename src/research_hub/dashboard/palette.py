"""Command-palette manifest (Phase B / v1.1).

Single source of truth for the dashboard ⌘K palette: the UNION of
the dashboard's whitelisted interactive actions
(``executor.ALLOWED_ACTIONS``) and the CLI subcommand list
(``research_hub.describe.build_manifest``). No parallel command
list — adding a CLI subcommand or an ALLOWED_ACTION automatically
surfaces in the palette, and ``tests/test_v110_ui_palette.py``
locks that contract so the two can never silently desync.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_palette_manifest() -> dict[str, Any]:
    """Return ``{"actions": [...], "subcommands": [...]}``.

    - ``actions``: sorted ``executor.ALLOWED_ACTIONS`` — the
      dashboard-exec surface (run live via ``/api/exec`` or
      copy the equivalent CLI command).
    - ``subcommands``: ``describe`` subcommand entries
      (``name`` / ``summary`` / ``supports_json``) — the full
      CLI surface, copy-to-clipboard.
    """
    from research_hub.dashboard.executor import ALLOWED_ACTIONS

    actions = [
        {"id": name, "label": name, "kind": "action"}
        for name in sorted(ALLOWED_ACTIONS)
    ]

    subcommands: list[dict[str, Any]] = []
    try:
        from research_hub.describe import build_manifest

        for entry in build_manifest().get("subcommands", []):
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            subcommands.append(
                {
                    "id": f"cli:{name}",
                    "label": name,
                    "kind": "cli",
                    "hint": str(entry.get("summary", "") or ""),
                    "supports_json": bool(entry.get("supports_json", False)),
                }
            )
    except Exception as exc:
        # describe is best-effort for the palette; the action set is
        # always available even if argparse introspection fails. Not
        # a W1-class swallow (UI affordance, contract-test-guarded on
        # a healthy tree), but leave a server-log breadcrumb per the
        # v0.90.0 breadcrumb philosophy rather than degrading silently.
        logger.warning(
            "palette: describe.build_manifest failed (%s: %s); "
            "palette will show actions only",
            type(exc).__name__,
            exc,
        )
        subcommands = []

    return {"actions": actions, "subcommands": subcommands}
