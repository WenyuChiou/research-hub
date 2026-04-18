"""Cluster memory: structured entities, claims, and methods extracted per cluster."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_hub.crystal import (
    _parse_frontmatter,
    _read_cluster_definition,
    _read_cluster_papers,
    _strip_frontmatter,
)
from research_hub.security import atomic_write_text, safe_join

logger = logging.getLogger(__name__)

ENTITY_TYPES = ("org", "dataset", "model", "benchmark", "method", "person", "concept", "venue")
METHOD_FAMILIES = (
    "supervised",
    "self-supervised",
    "rl",
    "finetune",
    "prompt",
    "search",
    "graph",
    "statistical",
    "geometric",
    "symbolic",
    "hybrid",
    "other",
)
CONFIDENCE_LEVELS = ("high", "medium", "low")
_MEMORY_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass
class MemoryEntity:
    slug: str
    name: str
    type: str
    papers: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "type": self.type,
            "papers": list(self.papers),
            "aliases": list(self.aliases),
            "notes": self.notes,
        }


@dataclass
class MemoryClaim:
    slug: str
    text: str
    confidence: str
    papers: list[str] = field(default_factory=list)
    related_entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "text": self.text,
            "confidence": self.confidence,
            "papers": list(self.papers),
            "related_entities": list(self.related_entities),
        }


@dataclass
class MemoryMethod:
    slug: str
    name: str
    family: str
    papers: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "family": self.family,
            "papers": list(self.papers),
            "description": self.description,
        }


@dataclass
class ClusterMemory:
    cluster_slug: str
    entities: list[MemoryEntity] = field(default_factory=list)
    claims: list[MemoryClaim] = field(default_factory=list)
    methods: list[MemoryMethod] = field(default_factory=list)
    based_on_papers: list[str] = field(default_factory=list)
    based_on_paper_count: int = 0
    last_generated: str = ""
    generator: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_slug": self.cluster_slug,
            "entities": [entity.to_dict() for entity in self.entities],
            "claims": [claim.to_dict() for claim in self.claims],
            "methods": [method.to_dict() for method in self.methods],
            "based_on_papers": list(self.based_on_papers),
            "based_on_paper_count": self.based_on_paper_count,
            "last_generated": self.last_generated,
            "generator": self.generator,
        }


@dataclass
class MemoryApplyResult:
    cluster_slug: str
    entity_count: int = 0
    claim_count: int = 0
    method_count: int = 0
    written_path: str = ""
    errors: list[str] = field(default_factory=list)


def memory_path(cfg, cluster_slug: str) -> Path:
    return safe_join(cfg.hub, cluster_slug, "memory.json")


def emit_memory_prompt(cfg, cluster_slug: str) -> str:
    """Build a prompt asking the AI to extract entities, claims, and methods."""
    from research_hub.clusters import ClusterRegistry

    cluster = ClusterRegistry(cfg.clusters_file).get(cluster_slug)
    if cluster is None:
        raise ValueError(f"unknown cluster: {cluster_slug}")

    papers = _read_cluster_papers(cfg, cluster_slug)
    definition = _read_cluster_definition(cfg, cluster_slug) or f"(no definition in hub/{cluster_slug}/00_overview.md)"

    lines = [
        f'# Cluster memory extraction: "{cluster_slug}" ({cluster.name})',
        "",
        "Extract structured entities, claims, and methods from the papers in this cluster.",
        "",
        "## Cluster definition",
        "",
        definition,
        "",
        f"## Papers in cluster ({len(papers)} total)",
        "",
    ]
    for index, paper in enumerate(papers, start=1):
        lines.extend([
            f"### {index}. {paper['title']}",
            f"- slug: `{paper['slug']}`",
            f"- year: {paper['year'] or '????'}",
            f"- doi: {paper['doi'] or '(none)'}",
            f"- one_liner: {paper['one_liner'] or '(no summary)'}",
            "",
        ])
    lines.extend([
        "## Instructions",
        "",
        "- Return ONE JSON object, nothing else.",
        f"- `entities`: orgs, datasets, models, benchmarks, key concepts. Suggested types: {', '.join(ENTITY_TYPES)}.",
        "- `claims`: 5-15 important findings as concrete statements. Each MUST cite >=1 paper slug.",
        f"- `methods`: technique families used. Suggested families: {', '.join(METHOD_FAMILIES)}.",
        "- All slugs must be lowercase kebab-case (a-z, 0-9, hyphens only).",
        "- Prefer fewer high-quality records over many low-quality records.",
        "- `confidence` in {high, medium, low}.",
        "",
        "## Output JSON schema",
        "",
        "```json",
        json.dumps(
            {
                "generator": "your-model-name",
                "entities": [
                    {
                        "slug": "openai",
                        "name": "OpenAI",
                        "type": "org",
                        "papers": ["paper-slug-1"],
                        "aliases": [],
                        "notes": "",
                    }
                ],
                "claims": [
                    {
                        "slug": "rlhf-improves-instruction-following",
                        "text": "RLHF improves instruction-following over SFT alone.",
                        "confidence": "high",
                        "papers": ["paper-slug-1"],
                        "related_entities": ["openai"],
                    }
                ],
                "methods": [
                    {
                        "slug": "rlhf",
                        "name": "Reinforcement Learning from Human Feedback",
                        "family": "rl",
                        "papers": ["paper-slug-1"],
                        "description": "Train reward model on preferences, then PPO.",
                    }
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        "```",
    ])
    return "\n".join(lines)


def apply_memory(cfg, cluster_slug: str, scored: dict[str, Any] | list[Any]) -> MemoryApplyResult:
    """Validate an AI response, build cluster memory, and write memory.json."""
    if isinstance(scored, list):
        scored = {"entities": [], "claims": [], "methods": [], "items": scored}

    result = MemoryApplyResult(cluster_slug=cluster_slug)
    paper_slugs = [paper["slug"] for paper in _read_cluster_papers(cfg, cluster_slug)]
    paper_set = set(paper_slugs)
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    generator = str(scored.get("generator", "unknown") or "unknown")

    def _slug_ok(value: str) -> bool:
        return bool(value) and bool(_MEMORY_SLUG_RE.fullmatch(value))

    def _filter_papers(items: list[Any]) -> list[str]:
        return [paper for paper in items if isinstance(paper, str) and paper in paper_set]

    entities: list[MemoryEntity] = []
    seen_entities: set[str] = set()
    for raw in scored.get("entities", []) or []:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug", "") or "").strip().lower()
        if not _slug_ok(slug) or slug in seen_entities:
            result.errors.append(f"entity slug invalid or dup: {slug!r}")
            continue
        seen_entities.add(slug)
        entities.append(
            MemoryEntity(
                slug=slug,
                name=str(raw.get("name", "") or slug),
                type=str(raw.get("type", "") or "concept"),
                papers=_filter_papers(raw.get("papers") or []),
                aliases=[str(alias) for alias in (raw.get("aliases") or []) if isinstance(alias, str)],
                notes=str(raw.get("notes", "") or ""),
            )
        )

    claims: list[MemoryClaim] = []
    seen_claims: set[str] = set()
    for raw in scored.get("claims", []) or []:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug", "") or "").strip().lower()
        text = str(raw.get("text", "") or "").strip()
        if not _slug_ok(slug) or slug in seen_claims or not text:
            result.errors.append(f"claim slug/text invalid or dup: {slug!r}")
            continue
        papers = _filter_papers(raw.get("papers") or [])
        if not papers:
            result.errors.append(f"claim {slug!r} has no valid supporting papers, skipping")
            continue
        seen_claims.add(slug)
        confidence = str(raw.get("confidence", "medium") or "medium").strip().lower()
        if confidence not in CONFIDENCE_LEVELS:
            confidence = "medium"
        claims.append(
            MemoryClaim(
                slug=slug,
                text=text,
                confidence=confidence,
                papers=papers,
                related_entities=[
                    str(entity_slug)
                    for entity_slug in (raw.get("related_entities") or [])
                    if str(entity_slug) in seen_entities
                ],
            )
        )

    methods: list[MemoryMethod] = []
    seen_methods: set[str] = set()
    for raw in scored.get("methods", []) or []:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug", "") or "").strip().lower()
        if not _slug_ok(slug) or slug in seen_methods:
            result.errors.append(f"method slug invalid or dup: {slug!r}")
            continue
        seen_methods.add(slug)
        methods.append(
            MemoryMethod(
                slug=slug,
                name=str(raw.get("name", "") or slug),
                family=str(raw.get("family", "") or "other"),
                papers=_filter_papers(raw.get("papers") or []),
                description=str(raw.get("description", "") or ""),
            )
        )

    memory = ClusterMemory(
        cluster_slug=cluster_slug,
        entities=entities,
        claims=claims,
        methods=methods,
        based_on_papers=paper_slugs,
        based_on_paper_count=len(paper_slugs),
        last_generated=timestamp,
        generator=generator,
    )

    target = memory_path(cfg, cluster_slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, json.dumps(memory.to_dict(), indent=2, ensure_ascii=False) + "\n")

    result.entity_count = len(entities)
    result.claim_count = len(claims)
    result.method_count = len(methods)
    result.written_path = str(target)
    return result


def read_memory(cfg, cluster_slug: str) -> ClusterMemory | None:
    path = memory_path(cfg, cluster_slug)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return ClusterMemory(
        cluster_slug=str(data.get("cluster_slug", cluster_slug)),
        entities=[MemoryEntity(**item) for item in data.get("entities", [])],
        claims=[MemoryClaim(**item) for item in data.get("claims", [])],
        methods=[MemoryMethod(**item) for item in data.get("methods", [])],
        based_on_papers=list(data.get("based_on_papers", [])),
        based_on_paper_count=int(data.get("based_on_paper_count", 0)),
        last_generated=str(data.get("last_generated", "")),
        generator=str(data.get("generator", "unknown")),
    )


def list_entities(cfg, cluster_slug: str) -> list[MemoryEntity]:
    memory = read_memory(cfg, cluster_slug)
    return list(memory.entities) if memory else []


def list_claims(cfg, cluster_slug: str) -> list[MemoryClaim]:
    memory = read_memory(cfg, cluster_slug)
    return list(memory.claims) if memory else []


def list_methods(cfg, cluster_slug: str) -> list[MemoryMethod]:
    memory = read_memory(cfg, cluster_slug)
    return list(memory.methods) if memory else []


__all__ = [
    "ENTITY_TYPES",
    "METHOD_FAMILIES",
    "CONFIDENCE_LEVELS",
    "MemoryEntity",
    "MemoryClaim",
    "MemoryMethod",
    "ClusterMemory",
    "MemoryApplyResult",
    "memory_path",
    "emit_memory_prompt",
    "apply_memory",
    "read_memory",
    "list_entities",
    "list_claims",
    "list_methods",
]
