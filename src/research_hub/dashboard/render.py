"""Compose the dashboard template + sections + inline assets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research_hub.dashboard.context import DashboardContext, collect_dashboard_context
from research_hub.dashboard.data import collect_dashboard_data
from research_hub.dashboard.sections import (
    DEFAULT_SECTIONS,
    DashboardSection,
    html_escape,
)
from research_hub.dashboard.types import DashboardData

_PACKAGE_DIR = Path(__file__).parent
_TEMPLATE_PATH = _PACKAGE_DIR / "template.html"
_STYLE_PATH = _PACKAGE_DIR / "style.css"
_SCRIPT_PATH = _PACKAGE_DIR / "script.js"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _persona_label(persona: str) -> str:
    return "Analyst persona" if persona == "analyst" else "Researcher persona"


def _attr(obj: Any, name: str, default: Any = "") -> Any:
    return getattr(obj, name, default)


def _vault_data(ctx: Any) -> dict:
    """Minimal JSON payload for client-side scripts.

    Polymorphic: accepts either the new ``DashboardData`` (clusters
    contain nested ``papers``) or the legacy ``DashboardContext``
    (papers live at the top level).
    """
    clusters = list(_attr(ctx, "clusters", []) or [])
    nested_papers = []
    for c in clusters:
        for p in _attr(c, "papers", []) or []:
            nested_papers.append(
                {
                    "slug": _attr(p, "slug", ""),
                    "title": _attr(p, "title", ""),
                    "cluster_slug": _attr(c, "slug", ""),
                    "year": _attr(p, "year", ""),
                    "status": _attr(p, "status", ""),
                }
            )
    top_level_papers = list(_attr(ctx, "papers", []) or [])
    if top_level_papers:
        papers = [
            {
                "slug": _attr(p, "slug", ""),
                "title": _attr(p, "title", ""),
                "cluster_slug": _attr(p, "cluster_slug", ""),
                "year": _attr(p, "year", ""),
                "status": _attr(p, "status", ""),
            }
            for p in top_level_papers
        ]
    else:
        papers = nested_papers

    return {
        "vault_root": _attr(ctx, "vault_root", ""),
        "generated_at": _attr(ctx, "generated_at", ""),
        "persona": _attr(ctx, "persona", "researcher"),
        "totals": {
            "papers": int(_attr(ctx, "total_papers", 0) or 0),
            "clusters": int(_attr(ctx, "total_clusters", 0) or 0),
            "unread": int(_attr(ctx, "total_unread", 0) or 0),
            "this_week": int(_attr(ctx, "papers_this_week", 0) or 0),
        },
        "papers": papers,
        "clusters": [
            {
                "slug": _attr(c, "slug", ""),
                "name": _attr(c, "name", ""),
                "paper_count": int(_attr(c, "paper_count", 0) or 0),
                "unread_count": int(_attr(c, "unread_count", 0) or 0),
            }
            for c in clusters
        ],
    }


def render_dashboard(
    ctx: Any,
    sections: list[DashboardSection] | None = None,
    *,
    refresh_seconds: int = 0,
    csrf_token: str = "",
) -> str:
    """Render the full dashboard HTML for an in-memory snapshot.

    ``ctx`` may be either a ``DashboardData`` (the v0.10 path used by
    ``render_dashboard_from_config``) or a legacy ``DashboardContext``
    (used by the backwards-compat ``render_dashboard_html`` shim).
    The new section classes use defensive attribute access so the
    same render function handles both.

    ``refresh_seconds`` injects a ``<meta http-equiv="refresh">`` so
    the open browser tab auto-reloads at that cadence. Used by the
    ``research-hub dashboard --watch`` mode. ``0`` (default) emits no
    refresh meta — the file stays static.
    """
    section_list = sorted(
        sections if sections is not None else DEFAULT_SECTIONS,
        key=lambda s: s.order,
    )
    body = "".join(section.render(ctx) for section in section_list)
    template = _load_text(_TEMPLATE_PATH)
    style = _load_text(_STYLE_PATH)
    script = _load_text(_SCRIPT_PATH)
    vault_json = json.dumps(_vault_data(ctx), ensure_ascii=False)
    # Escape closing script tag to prevent injection from titles.
    vault_json_safe = vault_json.replace("</", "<\\/")
    refresh_meta = (
        f'<meta http-equiv="refresh" content="{int(refresh_seconds)}">'
        if refresh_seconds and refresh_seconds > 0
        else ""
    )
    csrf_meta = f'<meta name="csrf-token" content="{html_escape(csrf_token)}">'
    return (
        template.replace("{{ STYLE }}", style)
        .replace("{{ SCRIPT }}", script)
        .replace("{{ BODY }}", body)
        .replace("{{ AUTO_REFRESH_META }}", refresh_meta)
        .replace("{{ CSRF_META }}", csrf_meta)
        .replace("{{ VAULT_ROOT }}", html_escape(_attr(ctx, "vault_root", "")))
        .replace("{{ GENERATED_AT }}", html_escape(_attr(ctx, "generated_at", "")))
        .replace(
            "{{ PERSONA_LABEL }}",
            html_escape(_persona_label(str(_attr(ctx, "persona", "researcher")))),
        )
        .replace("{{ VAULT_DATA_JSON }}", vault_json_safe)
    )


def render_dashboard_from_config(
    cfg,
    zot=None,
    *,
    refresh_seconds: int = 0,
    csrf_token: str = "",
) -> str:
    """Collect the v0.10 DashboardData and render in one call.

    Falls back to the legacy DashboardContext + render path if the new
    data layer raises (paranoia: dashboard must always render).
    """
    try:
        data = collect_dashboard_data(cfg, zot=zot)
        return render_dashboard(data, refresh_seconds=refresh_seconds, csrf_token=csrf_token)
    except Exception:
        ctx = collect_dashboard_context(cfg)
        return render_dashboard(ctx, refresh_seconds=refresh_seconds, csrf_token=csrf_token)
