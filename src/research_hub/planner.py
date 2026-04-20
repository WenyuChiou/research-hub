"""Intent planner — convert freeform user intent into an executable auto plan.

When a user (or AI agent) says vague things like:
  "I want to learn about harness engineering"
  "find recent papers on RAG for agriculture"
  "research ABM for my dissertation"
  "ingest these papers into Zotero only, skip NotebookLM"

an LLM agent shouldn't immediately call `auto_research_topic` — too many
implicit choices (cluster slug, max_papers, NLM yes/no, crystals yes/no,
collision with existing clusters).

This module returns a structured plan + clarifying questions so the agent
can confirm with the user before acting. Pure heuristics, no LLM call.

Used by:
  - MCP tool `plan_research_workflow`
  - CLI `research-hub plan "intent"`
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional


_INTENT_PREFIXES = (
    "i want to ", "i'd like to ", "i need to ", "please ",
    "help me ", "can you ", "could you ",
    "find ", "search for ", "search ", "research ", "look for ",
    "look up ", "study ", "learn about ", "learn ",
    "understand ", "explore ", "investigate ", "deep dive into ",
    "deep dive on ", "dive into ", "ingest ", "import ",
    "read about ", "read ",
    # zh-TW
    "我想 ", "我想要 ", "我要 ", "幫我 ",
    "找 ", "搜尋 ", "研究 ", "學習 ", "了解 ",
)

_DEPTH_KEYWORDS = {
    "thesis": 25, "dissertation": 25, "phd": 20, "deep dive": 20,
    "comprehensive": 20, "full review": 25, "literature review": 25,
    "survey": 20,
    "論文": 20, "畢業": 25, "博士": 20, "回顧": 20, "綜述": 20,
}

_LEARNING_KEYWORDS = (
    "learn", "study", "understand", "what is", "explain",
    "introduction", "tutorial",
    "學習", "了解", "什麼是", "入門",
)

_NO_ZOTERO_HINTS = (
    "no zotero", "without zotero", "skip zotero", "obsidian only",
    "不用 zotero", "不要 zotero", "略過 zotero",
)

_NO_NLM_HINTS = (
    "no notebooklm", "no nlm", "skip nlm", "skip notebooklm",
    "without notebooklm",
    "不用 notebooklm", "不要 notebooklm", "略過 notebooklm",
)


@dataclass
class WorkflowPlan:
    """Structured plan returned to the caller (AI agent or human)."""
    intent_summary: str
    suggested_topic: str
    suggested_cluster_slug: str
    suggested_max_papers: int = 8
    suggested_do_nlm: bool = True
    suggested_do_crystals: bool = False  # opt-in: requires LLM CLI on PATH
    suggested_persona: str = "researcher"
    estimated_duration_sec: int = 90
    existing_cluster_match: Optional[str] = None
    existing_cluster_paper_count: int = 0
    clarifying_questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_call: dict = field(default_factory=dict)
    raw_intent: str = ""


def plan_workflow(
    user_intent: str,
    *,
    cfg=None,
    detect_llm_cli_fn=None,
) -> WorkflowPlan:
    """Heuristic intent → executable plan.

    cfg: HubConfig (optional). If passed, the planner checks for existing
    cluster collisions so the agent can warn before creating a duplicate.

    detect_llm_cli_fn: callable returning the detected LLM CLI name or None.
    Defaults to research_hub.auto.detect_llm_cli. Used to decide whether
    to recommend `do_crystals=True` (only if a CLI is on PATH).
    """
    raw = (user_intent or "").strip()
    if not raw:
        return WorkflowPlan(
            intent_summary="(empty intent)",
            suggested_topic="",
            suggested_cluster_slug="",
            warnings=["No intent provided. Tell me what you want to research."],
            raw_intent=raw,
        )

    topic = _strip_intent_prefixes(raw)
    summary = _summarize(raw, topic)

    # Slugify
    from research_hub.clusters import slugify
    slug = slugify(topic)

    # Collision check against existing clusters
    existing_match: Optional[str] = None
    existing_papers = 0
    warnings: list[str] = []
    if cfg is not None:
        existing_match, existing_papers = _find_similar_cluster(cfg, slug, topic)
        if existing_match:
            warnings.append(
                f"Cluster '{existing_match}' already exists ({existing_papers} papers). "
                f"Consider --cluster {existing_match} instead of creating a new one."
            )

    # Depth heuristic
    max_papers = 8
    intent_lower = raw.lower()
    for kw, n in _DEPTH_KEYWORDS.items():
        if kw in intent_lower:
            max_papers = n
            break

    # NLM / Zotero opt-out hints
    do_nlm = not any(h in intent_lower for h in _NO_NLM_HINTS)
    no_zotero = any(h in intent_lower for h in _NO_ZOTERO_HINTS)
    persona = "analyst" if no_zotero else "researcher"

    # Crystal recommendation: only if LLM CLI present + intent reads as "learning"
    if detect_llm_cli_fn is None:
        from research_hub.auto import detect_llm_cli as _detect
        detect_llm_cli_fn = _detect
    cli_name = detect_llm_cli_fn()
    is_learning = any(kw in intent_lower for kw in _LEARNING_KEYWORDS)
    do_crystals = bool(cli_name) and is_learning

    # Build clarifying questions for the agent to ask the user
    questions = _clarifying_questions(
        topic=topic,
        slug=slug,
        max_papers=max_papers,
        do_nlm=do_nlm,
        do_crystals=do_crystals,
        cli_name=cli_name,
        existing_match=existing_match,
    )

    # Estimated duration (rough)
    duration = 30  # cluster + search + ingest baseline
    if do_nlm:
        duration += 60  # bundle + upload + generate + download
    if do_crystals:
        duration += 90  # LLM CLI roundtrip
    duration += max_papers * 2  # per-paper Zotero/Obsidian write

    next_call = {
        "tool": "auto_research_topic",
        "args": {
            "topic": topic,
            "cluster_slug": existing_match or "",
            "max_papers": max_papers,
            "do_nlm": do_nlm,
            "do_crystals": do_crystals,
        },
    }

    return WorkflowPlan(
        intent_summary=summary,
        suggested_topic=topic,
        suggested_cluster_slug=existing_match or slug,
        suggested_max_papers=max_papers,
        suggested_do_nlm=do_nlm,
        suggested_do_crystals=do_crystals,
        suggested_persona=persona,
        estimated_duration_sec=duration,
        existing_cluster_match=existing_match,
        existing_cluster_paper_count=existing_papers,
        clarifying_questions=questions,
        warnings=warnings,
        next_call=next_call,
        raw_intent=raw,
    )


def _strip_intent_prefixes(text: str) -> str:
    """Remove common 'I want to find papers on X' prefix → 'X'.

    Loops until stable so chained prefixes like 'I want to learn about X'
    and 'please find papers on X' both reduce to just 'X'.
    """
    cur = text.strip(" .?!,:;-")
    for _ in range(5):  # safety cap on the loop
        lowered = cur.lower()
        matched = None
        for prefix in _INTENT_PREFIXES:
            if lowered.startswith(prefix):
                matched = prefix
                break
        if matched is None:
            break
        cur = cur[len(matched):].strip(" .?!,:;-")
    return cur


def _summarize(raw: str, topic: str) -> str:
    """One-line restatement so the user can confirm we understood."""
    if topic == raw.strip(" .?!,:;-"):
        return f'You want to research: "{topic}"'
    return f'You want to research "{topic}" (parsed from: "{raw[:80]}{"..." if len(raw) > 80 else ""}")'


def _find_similar_cluster(cfg, slug: str, topic: str) -> tuple[Optional[str], int]:
    """Look for an existing cluster slug that overlaps with the proposed one.

    Returns (matching_slug, paper_count) or (None, 0).
    """
    try:
        from research_hub.clusters import ClusterRegistry
        reg = ClusterRegistry(cfg.clusters_file)
        existing = list(reg.list())
    except Exception:
        return None, 0

    # Exact slug match
    for c in existing:
        if c.slug == slug:
            n = _paper_count(cfg, c.slug)
            return c.slug, n

    # Token-overlap heuristic: ≥ 60% of slug tokens present in candidate
    slug_tokens = set(re.split(r"[-_]+", slug.lower())) - {""}
    if not slug_tokens:
        return None, 0
    best: tuple[Optional[str], float, int] = (None, 0.0, 0)
    for c in existing:
        c_tokens = set(re.split(r"[-_]+", c.slug.lower())) - {""}
        if not c_tokens:
            continue
        overlap = len(slug_tokens & c_tokens) / max(len(slug_tokens), 1)
        if overlap >= 0.6 and overlap > best[1]:
            best = (c.slug, overlap, _paper_count(cfg, c.slug))
    return (best[0], best[2]) if best[0] else (None, 0)


def _paper_count(cfg, slug: str) -> int:
    raw_dir = cfg.raw / slug
    if not raw_dir.exists():
        return 0
    return len(list(raw_dir.glob("*.md")))


def _clarifying_questions(
    *,
    topic: str,
    slug: str,
    max_papers: int,
    do_nlm: bool,
    do_crystals: bool,
    cli_name: Optional[str],
    existing_match: Optional[str],
) -> list[str]:
    qs: list[str] = []
    if existing_match:
        qs.append(
            f"Cluster '{existing_match}' already exists. Add to it, or create a new cluster with slug '{slug}'?"
        )
    qs.append(
        f"Search depth: {max_papers} papers OK, or do you want more / fewer? "
        "(thesis-level work usually wants 20-25; quick scan 3-5)"
    )
    if do_nlm:
        qs.append(
            "Generate NotebookLM brief? Adds ~60s but gives you an AI summary of all papers. "
            "Say 'no NLM' to skip."
        )
    if cli_name:
        if do_crystals:
            qs.append(
                f"I'll auto-generate cached AI answers (crystals) using '{cli_name}' CLI on your PATH. "
                "Adds ~90s. Say 'no crystals' to skip."
            )
        else:
            qs.append(
                f"Optional: generate cached AI answers (crystals) using '{cli_name}' CLI? "
                "Recommended for learning topics. Say 'with crystals' to enable."
            )
    else:
        qs.append(
            "(No claude/codex/gemini CLI on your PATH — crystals will be skipped. "
            "Install one of those CLIs to enable fully automated crystal generation.)"
        )
    return qs


def plan_to_dict(plan: WorkflowPlan) -> dict:
    """Serialize plan for MCP / JSON callers."""
    return asdict(plan)
