"""Shared dataclasses for the dashboard data layer.

This file is the contract between `dashboard/data.py` (backend, walks
the vault and returns a populated DashboardData) and `dashboard/sections.py`
(frontend, renders sections from a DashboardData snapshot). Both layers
import only from here so they can be developed in parallel.

Conventions:
- Every dataclass uses `from __future__ import annotations` for clean
  forward refs.
- Boolean cross-system flags (in_zotero / in_obsidian / in_nlm) are
  computed once in the data layer and never recomputed in sections.
- Strings default to "" not None so templates can render unconditionally.
- Lists default via field(default_factory=list) so each instance is
  independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Persona = Literal["researcher", "analyst"]
ReadingStatus = Literal["unread", "reading", "deep-read", "cited"]
HealthStatus = Literal["OK", "WARN", "FAIL"]
DriftKind = Literal[
    "folder_mismatch",
    "duplicate_doi",
    "orphan_note",
    "stale_nlm",
    "crystal_stale",
]


@dataclass
class PaperRow:
    """One paper, fully populated for the cluster paper list."""

    slug: str
    title: str
    authors: str            # already formatted "Last, F.; Last2, F2."
    year: str
    abstract: str           # from Obsidian frontmatter `abstract` field
    doi: str
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    status: ReadingStatus = "unread"
    ingested_at: str = ""
    obsidian_path: str = ""
    zotero_key: str = ""
    in_zotero: bool = False
    in_obsidian: bool = False
    in_nlm: bool = False
    bibtex: str = ""        # pre-rendered for the [Cite] button


@dataclass
class BriefingPreview:
    """One downloaded NotebookLM briefing for the AI Briefings section."""

    cluster_slug: str
    cluster_name: str
    notebook_url: str
    preview_text: str       # first ~500 chars (markdown stripped)
    full_text: str          # complete brief for "Copy full text"
    char_count: int = 0
    downloaded_at: str = ""
    titles: list[str] = field(default_factory=list)


@dataclass
class ClusterCard:
    """One cluster, populated with its papers and per-system status."""

    slug: str
    name: str
    papers: list[PaperRow] = field(default_factory=list)
    zotero_count: int = 0
    obsidian_count: int = 0
    nlm_count: int = 0
    last_activity: str = ""
    notebooklm_notebook: str = ""
    notebooklm_notebook_url: str = ""
    zotero_collection_key: str = ""
    has_overview: bool = False
    subtopic_count: int = 0
    cluster_bibtex: str = ""  # pre-rendered .bib for the cluster batch download
    briefing: BriefingPreview | None = None
    label_counts: dict[str, int] = field(default_factory=dict)
    archived_count: int = 0
    archived_papers: list[dict[str, object]] = field(default_factory=list)

    @property
    def paper_count(self) -> int:
        return len(self.papers)

    @property
    def new_this_week(self) -> int:
        return sum(1 for p in self.papers if p.ingested_at and _is_this_week(p.ingested_at))


@dataclass
class HealthBadge:
    """One subsystem's rolled-up doctor result for the diagnostics footer."""

    subsystem: Literal["zotero", "obsidian", "notebooklm"]
    status: HealthStatus
    summary: str = ""
    items: list[dict] = field(default_factory=list)  # raw CheckResult dicts for the drawer


@dataclass
class DriftAlert:
    """One drift / inconsistency finding for the diagnostics footer."""

    kind: DriftKind
    severity: HealthStatus
    title: str
    description: str
    sample_paths: list[str] = field(default_factory=list)
    fix_command: str = ""


@dataclass
class Quote:
    slug: str
    doi: str
    title: str
    authors: str
    year: str
    cluster_slug: str = ""
    cluster_name: str = ""
    page: str = ""
    text: str = ""
    captured_at: str = ""
    context_note: str = ""
    paper_labels: list[str] = field(default_factory=list)


@dataclass
class CrystalSummary:
    cluster_slug: str
    total_canonical: int
    generated_count: int
    stale_count: int
    last_generated: str = ""
    crystals: list[dict] = field(default_factory=list)

    @property
    def completion_ratio(self) -> float:
        return self.generated_count / self.total_canonical if self.total_canonical else 0.0


@dataclass
class DashboardData:
    """Top-level snapshot — every section reads only from this."""

    vault_root: str
    generated_at: str
    persona: Persona
    total_papers: int
    total_clusters: int
    papers_this_week: int
    clusters: list[ClusterCard] = field(default_factory=list)
    briefings: list[BriefingPreview] = field(default_factory=list)
    quotes: list[Quote] = field(default_factory=list)
    crystal_summary_by_cluster: dict[str, CrystalSummary] = field(default_factory=dict)
    labels_across_clusters: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    health_badges: list[HealthBadge] = field(default_factory=list)
    drift_alerts: list[DriftAlert] = field(default_factory=list)

    @property
    def show_zotero_column(self) -> bool:
        return self.persona != "analyst"

    @property
    def show_cite_buttons(self) -> bool:
        return self.persona != "analyst"


def _is_this_week(iso_timestamp: str) -> bool:
    """True if `iso_timestamp` is within the last 7 days."""
    from datetime import datetime, timedelta, timezone

    if not iso_timestamp:
        return False
    try:
        ts = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts) <= timedelta(days=7)
