"""Crystal: pre-computed canonical Q&A answers for research clusters."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_hub.security import safe_join

logger = logging.getLogger(__name__)

CANONICAL_QUESTIONS: list[dict[str, str]] = [
    {"slug": "what-is-this-field", "question": "What is this research area about?"},
    {"slug": "why-now", "question": "Why does this research matter now? What changed?"},
    {"slug": "main-threads", "question": "What are the 3-5 main research threads or schools of thought?"},
    {"slug": "where-experts-disagree", "question": "Where do experts in this field disagree?"},
    {"slug": "sota-and-open-problems", "question": "What is the current state of the art and what remains unsolved?"},
    {"slug": "reading-order", "question": "If I'm new to this field, which 5 papers should I read first and in what order?"},
    {"slug": "key-concepts", "question": "What are the 10-20 key concepts I need to know?"},
    {"slug": "evaluation-standards", "question": "How do people evaluate their work in this field? What benchmarks, metrics, datasets?"},
    {"slug": "common-pitfalls", "question": "What are the common mistakes newcomers make in this field?"},
    {"slug": "adjacent-fields", "question": "What adjacent research areas does this connect to, and how?"},
]
CANONICAL_SLUGS = frozenset(item["slug"] for item in CANONICAL_QUESTIONS)
STALENESS_THRESHOLD = 0.10


def _escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


@dataclass
class CrystalEvidence:
    claim: str
    papers: list[str]


@dataclass
class Crystal:
    cluster_slug: str
    question_slug: str
    question: str
    tldr: str
    gist: str
    full: str
    evidence: list[CrystalEvidence] = field(default_factory=list)
    based_on_papers: list[str] = field(default_factory=list)
    based_on_paper_count: int = 0
    last_generated: str = ""
    generator: str = "unknown"
    confidence: str = "medium"
    see_also: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "---",
            "type: crystal",
            f"cluster: {self.cluster_slug}",
            f"question_slug: {self.question_slug}",
            f'question: "{_escape_yaml(self.question)}"',
            f"based_on_papers: {json.dumps(self.based_on_papers, ensure_ascii=False)}",
            f"based_on_paper_count: {self.based_on_paper_count}",
            f"last_generated: {self.last_generated}",
            f"generator: {self.generator}",
            f"confidence: {self.confidence}",
            "---",
            "",
            f"# {self.question}",
            "",
            "## TL;DR",
            "",
            self.tldr.strip(),
            "",
            "## Gist",
            "",
            self.gist.strip(),
            "",
            "## Full answer",
            "",
            self.full.strip(),
            "",
        ]
        if self.evidence:
            lines.extend(["## Evidence", "", "| Claim | Papers |", "|---|---|"])
            for item in self.evidence:
                lines.append(f"| {item.claim} | {', '.join(f'[[{paper}]]' for paper in item.papers)} |")
            lines.append("")
        if self.see_also:
            lines.extend(["## See also", ""])
            for slug in self.see_also:
                label = next((q["question"] for q in CANONICAL_QUESTIONS if q["slug"] == slug), slug)
                lines.append(f"- [[crystals/{slug}|{label}]]")
            lines.append("")
        return "\n".join(lines)

    @classmethod
    def from_path(cls, path: Path) -> Crystal:
        return cls.from_markdown(path.read_text(encoding="utf-8"))

    @classmethod
    def from_markdown(cls, text: str) -> Crystal:
        if not text.startswith("---\n"):
            raise ValueError("crystal markdown missing frontmatter")
        end = text.index("\n---\n", 4)
        fm = _parse_frontmatter(text[4:end])
        body = text[end + 5 :]
        return cls(
            cluster_slug=str(fm.get("cluster", "") or ""),
            question_slug=str(fm.get("question_slug", "") or ""),
            question=str(fm.get("question", "") or "").replace('\\"', '"').replace("\\\\", "\\"),
            tldr=_extract_section(body, "TL;DR"),
            gist=_extract_section(body, "Gist"),
            full=_extract_section(body, "Full answer"),
            evidence=_extract_evidence(body),
            based_on_papers=list(fm.get("based_on_papers", []) or []),
            based_on_paper_count=int(fm.get("based_on_paper_count", 0) or 0),
            last_generated=str(fm.get("last_generated", "") or ""),
            generator=str(fm.get("generator", "unknown") or "unknown"),
            confidence=str(fm.get("confidence", "medium") or "medium"),
            see_also=[match.group(1) for match in re.finditer(r"\[\[crystals/([^|\]]+)", _extract_section(body, "See also"))],
        )


@dataclass
class CrystalApplyResult:
    cluster_slug: str
    written: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_slug": self.cluster_slug,
            "written": self.written,
            "replaced": self.replaced,
            "skipped": self.skipped,
            "errors": self.errors,
        }


@dataclass
class CrystalStaleness:
    crystal_slug: str
    added_papers: list[str]
    removed_papers: list[str]
    delta_ratio: float
    stale: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "crystal_slug": self.crystal_slug,
            "added_papers": self.added_papers,
            "removed_papers": self.removed_papers,
            "delta_ratio": self.delta_ratio,
            "stale": self.stale,
        }


def crystal_dir(cfg, cluster_slug: str) -> Path:
    return safe_join(cfg.hub, cluster_slug, "crystals")


def emit_crystal_prompt(cfg, cluster_slug: str, *, question_slugs: list[str] | None = None) -> str:
    from research_hub.clusters import ClusterRegistry

    cluster = ClusterRegistry(cfg.clusters_file).get(cluster_slug)
    if cluster is None:
        raise ValueError(f"unknown cluster: {cluster_slug}")
    questions = _select_questions(question_slugs)
    papers = _read_cluster_papers(cfg, cluster_slug)
    definition = _read_cluster_definition(cfg, cluster_slug) or f"(no definition available in hub/{cluster_slug}/00_overview.md)"
    lines = [
        f'# Crystal generation: cluster "{cluster_slug}" ({cluster.name})',
        "",
        "Generate canonical Q&A answers for this research cluster.",
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
            f"- one_liner: {paper['one_liner'] or '(no one-line summary)'}",
            "",
        ])
    lines.extend([f"## Canonical questions to answer ({len(questions)} total)", ""])
    for question in questions:
        lines.append(f"- `{question['slug']}`: {question['question']}")
    lines.extend([
        "",
        "## Instructions",
        "",
        "- Return ONE JSON object, nothing else.",
        "- `tldr`: one sentence.",
        "- `gist`: a short paragraph.",
        "- `full`: a more detailed answer.",
        "- `evidence`: 1-5 claim-to-paper mappings using cluster paper slugs.",
        "- `confidence`: one of `high`, `medium`, `low`.",
        "",
        "## Output JSON schema",
        "",
        "```json",
        json.dumps({
            "generator": "your-model-name",
            "crystals": [{
                "slug": questions[0]["slug"] if questions else "what-is-this-field",
                "question": questions[0]["question"] if questions else "What is this research area about?",
                "tldr": "One-sentence answer.",
                "gist": "Short paragraph.",
                "full": "Longer answer.",
                "evidence": [{"claim": "Concrete claim", "papers": ["paper-slug"]}],
                "confidence": "medium",
            }],
        }, indent=2, ensure_ascii=False),
        "```",
    ])
    return "\n".join(lines)


def apply_crystals(cfg, cluster_slug: str, scored: dict | list) -> CrystalApplyResult:
    payload = scored.get("crystals", []) if isinstance(scored, dict) else scored
    generator = str(scored.get("generator", "unknown") or "unknown") if isinstance(scored, dict) else "unknown"
    payload = payload if isinstance(payload, list) else []
    result = CrystalApplyResult(cluster_slug=cluster_slug)
    target_dir = crystal_dir(cfg, cluster_slug)
    target_dir.mkdir(parents=True, exist_ok=True)
    paper_slugs = [paper["slug"] for paper in _read_cluster_papers(cfg, cluster_slug)]
    sibling_slugs = [str(item.get("slug", "") or "").strip() for item in payload if str(item.get("slug", "") or "").strip() in CANONICAL_SLUGS]
    questions = {item["slug"]: item["question"] for item in CANONICAL_QUESTIONS}
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    for entry in payload:
        slug = str(entry.get("slug", "") or "").strip()
        if not slug:
            result.skipped.append("(no slug)")
            continue
        if slug not in CANONICAL_SLUGS:
            result.skipped.append(f"{slug}: unknown question slug")
            continue
        try:
            crystal = Crystal(
                cluster_slug=cluster_slug,
                question_slug=slug,
                question=str(entry.get("question", "") or questions[slug]),
                tldr=str(entry.get("tldr", "") or "").strip(),
                gist=str(entry.get("gist", "") or "").strip(),
                full=str(entry.get("full", "") or "").strip(),
                evidence=_normalize_evidence(entry.get("evidence")),
                based_on_papers=paper_slugs,
                based_on_paper_count=len(paper_slugs),
                last_generated=timestamp,
                generator=str(entry.get("generator", "") or generator),
                confidence=_normalize_confidence(str(entry.get("confidence", "medium") or "medium")),
                see_also=[item for item in sibling_slugs if item != slug],
            )
        except Exception as exc:
            result.errors.append(f"{slug}: {exc}")
            continue
        path = target_dir / f"{slug}.md"
        if path.exists():
            result.replaced.append(slug)
        else:
            result.written.append(slug)
        path.write_text(crystal.to_markdown(), encoding="utf-8")
    return result


def list_crystals(cfg, cluster_slug: str) -> list[Crystal]:
    base = crystal_dir(cfg, cluster_slug)
    if not base.exists():
        return []
    out: list[Crystal] = []
    for slug in [item["slug"] for item in CANONICAL_QUESTIONS]:
        path = base / f"{slug}.md"
        if path.exists():
            out.append(Crystal.from_path(path))
    return out


def read_crystal(cfg, cluster_slug: str, crystal_slug: str) -> Crystal | None:
    path = crystal_dir(cfg, cluster_slug) / f"{crystal_slug}.md"
    return Crystal.from_path(path) if path.exists() else None


def check_staleness(cfg, cluster_slug: str) -> dict[str, CrystalStaleness]:
    current = {paper["slug"] for paper in _read_cluster_papers(cfg, cluster_slug)}
    out: dict[str, CrystalStaleness] = {}
    for item in list_crystals(cfg, cluster_slug):
        original = set(item.based_on_papers)
        added = sorted(current - original)
        removed = sorted(original - current)
        denom = max(1, item.based_on_paper_count or len(original))
        delta_ratio = (len(added) + len(removed)) / denom
        out[item.question_slug] = CrystalStaleness(
            crystal_slug=item.question_slug,
            added_papers=added,
            removed_papers=removed,
            delta_ratio=delta_ratio,
            stale=delta_ratio > STALENESS_THRESHOLD,
        )
    return out


def _read_cluster_papers(cfg, cluster_slug: str) -> list[dict[str, str]]:
    from research_hub.vault.sync import list_cluster_notes

    papers: list[dict[str, str]] = []
    for note_path in list_cluster_notes(cluster_slug, Path(cfg.raw)):
        if note_path.name in {"00_overview.md", "index.md"} or "topics" in note_path.parts:
            continue
        text = note_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter_for_paper(text)
        papers.append({
            "slug": note_path.stem,
            "title": str(fm.get("title", note_path.stem) or note_path.stem),
            "year": str(fm.get("year", "") or ""),
            "doi": str(fm.get("doi", "") or ""),
            "one_liner": _extract_one_liner(text),
        })
    papers.sort(key=lambda item: item["slug"])
    return papers


def _parse_frontmatter_for_paper(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return {}
    parsed = _parse_frontmatter(text[4:end])
    return {str(key): str(value) for key, value in parsed.items()}


def _extract_one_liner(text: str) -> str:
    body = _strip_frontmatter(text)
    for heading in ("Summary", "Abstract"):
        match = re.search(rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)", body, re.MULTILINE | re.DOTALL)
        if match:
            normalized = re.sub(r"\s+", " ", match.group(1).strip())
            if normalized:
                return re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0][:200]
    return ""


def _read_cluster_definition(cfg, cluster_slug: str) -> str:
    path = safe_join(cfg.hub, cluster_slug, "00_overview.md")
    if not path.exists():
        return ""
    body = _strip_frontmatter(path.read_text(encoding="utf-8"))
    for heading in ("TL;DR", "Definition"):
        match = re.search(rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)", body, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return ""


def _select_questions(question_slugs: list[str] | None) -> list[dict[str, str]]:
    if question_slugs is None:
        return list(CANONICAL_QUESTIONS)
    requested = {slug.strip() for slug in question_slugs if slug.strip()}
    unknown = requested - CANONICAL_SLUGS
    if unknown:
        raise ValueError(f"unknown question slugs: {sorted(unknown)}")
    return [item for item in CANONICAL_QUESTIONS if item["slug"] in requested]


def _normalize_evidence(value: Any) -> list[CrystalEvidence]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("evidence must be a list")
    out: list[CrystalEvidence] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        papers = item.get("papers") or []
        if not isinstance(papers, list):
            papers = [papers]
        claim = str(item.get("claim", "") or "").strip()
        paper_slugs = [str(paper).strip() for paper in papers if str(paper).strip()]
        if claim and paper_slugs:
            out.append(CrystalEvidence(claim=claim, papers=paper_slugs))
    return out


def _normalize_confidence(value: str) -> str:
    return value.strip().lower() if value.strip().lower() in {"high", "medium", "low"} else "medium"


def _parse_frontmatter(frontmatter: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for line in frontmatter.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            out[key] = value[1:-1]
            continue
        if value.startswith("[") and value.endswith("]"):
            try:
                out[key] = json.loads(value)
            except json.JSONDecodeError:
                out[key] = []
            continue
        out[key] = value
    return out


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return text
    return text[end + 5 :]


def _extract_section(body: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)", body, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_evidence(body: str) -> list[CrystalEvidence]:
    block = _extract_section(body, "Evidence")
    evidence: list[CrystalEvidence] = []
    for line in block.splitlines():
        if not line.startswith("|") or "|---" in line or line.strip() == "| Claim | Papers |":
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 2:
            claim = cells[0]
            papers = re.findall(r"\[\[([^|\]]+)(?:\|[^\]]*)?\]\]", cells[1])
            if claim and papers:
                evidence.append(CrystalEvidence(claim=claim, papers=papers))
    return evidence
