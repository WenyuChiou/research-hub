"""Compose the dashboard template + sections + inline assets."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from research_hub.dashboard.context import DashboardContext, collect_dashboard_context
from research_hub.dashboard.sections import (
    DEFAULT_SECTIONS,
    DashboardSection,
    html_escape,
)

_PACKAGE_DIR = Path(__file__).parent
_TEMPLATE_PATH = _PACKAGE_DIR / "template.html"
_STYLE_PATH = _PACKAGE_DIR / "style.css"
_SCRIPT_PATH = _PACKAGE_DIR / "script.js"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _persona_label(persona: str) -> str:
    return "Analyst persona" if persona == "analyst" else "Researcher persona"


def _vault_data(ctx: DashboardContext) -> dict:
    """Minimal JSON payload for client-side scripts (no PII beyond filenames)."""
    return {
        "vault_root": ctx.vault_root,
        "generated_at": ctx.generated_at,
        "persona": ctx.persona,
        "totals": {
            "papers": ctx.total_papers,
            "clusters": ctx.total_clusters,
            "unread": ctx.total_unread,
            "this_week": ctx.papers_this_week,
        },
        "papers": [
            {
                "slug": p.slug,
                "title": p.title,
                "cluster_slug": p.cluster_slug,
                "year": p.year,
                "status": p.status,
            }
            for p in ctx.papers
        ],
        "clusters": [
            {
                "slug": c.slug,
                "name": c.name,
                "paper_count": c.paper_count,
                "unread_count": c.unread_count,
            }
            for c in ctx.clusters
        ],
    }


def render_dashboard(
    ctx: DashboardContext,
    sections: list[DashboardSection] | None = None,
) -> str:
    """Render the full dashboard HTML for an in-memory context."""
    section_list = sorted(
        sections if sections is not None else DEFAULT_SECTIONS,
        key=lambda s: s.order,
    )
    body = "".join(section.render(ctx) for section in section_list)
    template = _load_text(_TEMPLATE_PATH)
    style = _load_text(_STYLE_PATH)
    script = _load_text(_SCRIPT_PATH)
    vault_json = json.dumps(_vault_data(ctx), ensure_ascii=False)
    # Escape closing script tag to prevent script injection from titles.
    vault_json_safe = vault_json.replace("</", "<\\/")
    return (
        template.replace("{{ STYLE }}", style)
        .replace("{{ SCRIPT }}", script)
        .replace("{{ BODY }}", body)
        .replace("{{ VAULT_ROOT }}", html_escape(ctx.vault_root))
        .replace("{{ GENERATED_AT }}", html_escape(ctx.generated_at))
        .replace("{{ PERSONA_LABEL }}", html_escape(_persona_label(ctx.persona)))
        .replace("{{ VAULT_DATA_JSON }}", vault_json_safe)
    )


def render_dashboard_from_config(cfg) -> str:
    """Convenience: collect context + render in one call."""
    ctx = collect_dashboard_context(cfg)
    return render_dashboard(ctx)
