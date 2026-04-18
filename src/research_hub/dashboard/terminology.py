"""Per-persona display labels + tab/section visibility for the dashboard."""

from __future__ import annotations

from typing import Literal

Persona = Literal["researcher", "analyst", "humanities", "internal"]
ALL_PERSONAS: tuple[Persona, ...] = ("researcher", "analyst", "humanities", "internal")


_LABELS: dict[str, dict[Persona, str]] = {
    "cluster": {"researcher": "Cluster", "analyst": "Topic", "humanities": "Theme", "internal": "Project area"},
    "clusters": {"researcher": "Clusters", "analyst": "Topics", "humanities": "Themes", "internal": "Project areas"},
    "subtopic": {"researcher": "Sub-topic", "analyst": "Sub-topic", "humanities": "Sub-theme", "internal": "Sub-area"},
    "subtopics": {"researcher": "Sub-topics", "analyst": "Sub-topics", "humanities": "Sub-themes", "internal": "Sub-areas"},
    "crystal": {"researcher": "Crystal", "analyst": "AI Brief", "humanities": "Synthesis", "internal": "AI Brief"},
    "crystals": {"researcher": "Crystals", "analyst": "AI Briefs", "humanities": "Syntheses", "internal": "AI Briefs"},
    "paper": {"researcher": "Paper", "analyst": "Document", "humanities": "Source", "internal": "Document"},
    "papers": {"researcher": "Papers", "analyst": "Documents", "humanities": "Sources", "internal": "Documents"},
    "label_seed": {"researcher": "Seed", "analyst": "Anchor", "humanities": "Foundational", "internal": "Origin"},
    "label_core": {"researcher": "Core", "analyst": "Core", "humanities": "Central", "internal": "Primary"},
    "label_method": {"researcher": "Method", "analyst": "How-to", "humanities": "Methodological", "internal": "Procedure"},
    "label_benchmark": {"researcher": "Benchmark", "analyst": "Reference", "humanities": "Comparative", "internal": "Specification"},
    "label_survey": {"researcher": "Survey", "analyst": "Overview", "humanities": "Historiographic", "internal": "Overview"},
    "label_application": {"researcher": "Application", "analyst": "Case study", "humanities": "Case", "internal": "Implementation"},
    "label_tangential": {"researcher": "Tangential", "analyst": "Adjacent", "humanities": "Peripheral", "internal": "Related"},
    "label_deprecated": {"researcher": "Deprecated", "analyst": "Deprecated", "humanities": "Superseded", "internal": "Deprecated"},
    "label_archived": {"researcher": "Archived", "analyst": "Archived", "humanities": "Archived", "internal": "Archived"},
    "citation_graph": {"researcher": "Citation graph", "analyst": "Reference graph", "humanities": "Citation network", "internal": "Reference network"},
    "doi": {"researcher": "DOI", "analyst": "DOI", "humanities": "DOI/URN", "internal": "Identifier"},
    "zotero_collection": {"researcher": "Zotero collection", "analyst": "Source collection", "humanities": "Zotero collection", "internal": "Library folder"},
    "vault": {"researcher": "Vault", "analyst": "Workspace", "humanities": "Archive", "internal": "Knowledge base"},
}


_VISIBLE_TABS: dict[Persona, set[str]] = {
    "researcher": {"overview", "library", "briefings", "writing", "diagnostics", "manage"},
    "humanities": {"overview", "library", "briefings", "writing", "diagnostics", "manage"},
    "analyst": {"overview", "library", "briefings", "writing", "manage"},
    "internal": {"overview", "library", "briefings", "writing", "manage"},
}


_SECTION_GATES: dict[str, dict[Persona, bool]] = {
    "manage_bind_zotero": {"researcher": True, "analyst": False, "humanities": True, "internal": False},
    "writing_compose_draft": {"researcher": True, "analyst": False, "humanities": True, "internal": False},
    "library_zotero_column": {"researcher": True, "analyst": False, "humanities": True, "internal": False},
    "library_citation_graph": {"researcher": True, "analyst": False, "humanities": True, "internal": False},
    "library_rich_bibtex": {"researcher": True, "analyst": False, "humanities": True, "internal": False},
}


def _persona(persona: str) -> Persona:
    return persona if persona in ALL_PERSONAS else "researcher"


def get_label(key: str, persona: str = "researcher") -> str:
    p = _persona(persona)
    by_persona = _LABELS.get(key, {})
    return by_persona.get(p, by_persona.get("researcher", key))


def visible_tabs(persona: str) -> set[str]:
    return set(_VISIBLE_TABS[_persona(persona)])


def is_section_visible(section: str, persona: str) -> bool:
    return _SECTION_GATES.get(section, {}).get(_persona(persona), True)


def label_capitalize(key: str, persona: str = "researcher") -> str:
    label = get_label(key, persona)
    return label[:1].upper() + label[1:] if label else label
