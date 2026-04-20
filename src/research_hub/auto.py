"""End-to-end pipeline: topic string ??cluster ??search ??ingest ??NotebookLM.

v0.46 "lazy mode": one command does everything.
v0.49: optional auto-crystal step via detected LLM CLI + Next Steps banner.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from research_hub.clusters import ClusterRegistry, slugify
from research_hub.config import get_config
from research_hub.discover import _to_papers_input
from research_hub.notebooklm.bundle import bundle_cluster
from research_hub.notebooklm.upload import (
    download_briefing_for_cluster,
    generate_artifact,
    upload_cluster,
)
from research_hub.pipeline import run_pipeline
from research_hub.search import search_papers
from research_hub.search.fallback import FIELD_PRESETS


_LLM_CLI_CANDIDATES = ("claude", "codex", "gemini")


def detect_llm_cli() -> Optional[str]:
    """Return the first LLM CLI on PATH, or None.

    Order of preference: claude -> codex -> gemini.
    Used by the optional crystal step in auto_pipeline so the user does not
    have to manually pipe the emit prompt through their LLM of choice.
    """
    for name in _LLM_CLI_CANDIDATES:
        if shutil.which(name):
            return name
    return None


def _invoke_llm_cli(cli_name: str, prompt: str, timeout_sec: float = 180.0) -> str:
    """Pipe `prompt` through the detected LLM CLI, capture stdout.

    Each CLI has a slightly different non-interactive invocation:
    - claude:  `claude -p` (prompt via stdin)
    - codex:   `codex exec --full-auto <prompt>` (prompt as positional arg)
    - gemini:  `gemini --approval-mode yolo` (prompt via stdin)

    v0.50.1: resolve the full executable path via shutil.which() so the
    Windows npm `.cmd` shims for codex/gemini are found correctly.
    Without this, subprocess.run("codex", ...) hits FileNotFoundError on
    Windows because Python doesn't auto-append PATHEXT.
    """
    resolved = shutil.which(cli_name)
    if not resolved:
        raise RuntimeError(f"{cli_name} not on PATH")
    if cli_name == "claude":
        cmd = [resolved, "-p"]
        stdin_input = prompt
    elif cli_name == "codex":
        # codex takes the prompt as a positional argument, not stdin
        cmd = [resolved, "exec", "--full-auto", prompt]
        stdin_input = None
    elif cli_name == "gemini":
        cmd = [resolved, "--approval-mode", "yolo"]
        stdin_input = prompt
    else:
        raise ValueError(f"unsupported LLM CLI: {cli_name}")
    proc = subprocess.run(
        cmd,
        input=stdin_input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{cli_name} exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    return proc.stdout


def _extract_first_json(text: str) -> Optional[dict]:
    """Find the first valid JSON object in `text`, ignoring code fences and prose."""
    if not text:
        return None
    fence_starts = [i for i in range(len(text)) if text.startswith("```", i)]
    candidates: list[str] = []
    for i in range(0, len(fence_starts) - 1, 2):
        start = fence_starts[i]
        end = fence_starts[i + 1]
        block = text[start + 3 : end]
        if block.lstrip().lower().startswith("json"):
            block = block.split("\n", 1)[1] if "\n" in block else ""
        candidates.append(block)
    candidates.append(text)
    for c in candidates:
        c = c.strip()
        first_brace = c.find("{")
        last_brace = c.rfind("}")
        if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
            continue
        try:
            return json.loads(c[first_brace : last_brace + 1])
        except json.JSONDecodeError:
            continue
    return None




@dataclass
class AutoStepResult:
    name: str
    ok: bool
    duration_sec: float = 0.0
    detail: str = ""


@dataclass
class AutoReport:
    cluster_slug: str
    cluster_created: bool
    steps: list[AutoStepResult] = field(default_factory=list)
    papers_ingested: int = 0
    nlm_uploaded: int = 0
    brief_path: Optional[Path] = None
    notebook_url: Optional[str] = None
    total_duration_sec: float = 0.0
    ok: bool = True
    error: str = ""


def auto_pipeline(
    topic: str,
    *,
    cluster_slug: Optional[str] = None,
    cluster_name: Optional[str] = None,
    max_papers: int = 8,
    field: Optional[str] = None,
    do_nlm: bool = True,
    do_crystals: bool = False,
    llm_cli: Optional[str] = None,
    dry_run: bool = False,
    print_progress: bool = True,
) -> AutoReport:
    """End-to-end ingest + optional NotebookLM publish.

    Steps:
      1. Slugify topic ??cluster slug (if not provided)
      2. Create cluster if missing
      3. Search arxiv + semantic_scholar (limit=max_papers)
      4. Write papers_input.json
      5. Run pipeline (ingest)
      6. (if do_nlm) Bundle PDFs
      7. (if do_nlm) Upload to NotebookLM
      8. (if do_nlm) Generate brief artifact
      9. (if do_nlm) Download brief to artifacts/

    On dry_run=True: print plan + return early with AutoReport(ok=True).        

    On any step failure: stop, log, return AutoReport with ok=False + error.    
    """
    cfg = get_config()


    started = time.time()
    report = AutoReport(cluster_slug="", cluster_created=False)

    # 1. Slugify + 2. cluster create-or-get
    slug = cluster_slug or slugify(topic)
    if not slug:
        report.ok = False
        report.error = "Could not derive cluster slug from topic"
        return report
    report.cluster_slug = slug

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(slug)
    if cluster is None:
        if dry_run:
            _step_log(report, "cluster", True, 0.0, f"would create: {slug}", print_progress)
        else:
            display = cluster_name or topic.title()
            cluster = registry.create(query=topic, slug=slug, name=display)
            report.cluster_created = True
            _step_log(report, "cluster", True, 0.0, f"created: {slug}", print_progress)
            # v0.49.4: also auto-create + bind a Zotero collection so ingest
            # has somewhere to put papers without manual `clusters bind`.
            _ensure_zotero_collection(registry, cluster, slug, report, print_progress)
    else:
        _step_log(report, "cluster", True, 0.0, f"existing: {slug}", print_progress)
        if not dry_run and not getattr(cluster, "zotero_collection_key", None):
            _ensure_zotero_collection(registry, cluster, slug, report, print_progress)

    # Print plan if dry_run; do NOT execute remaining steps
    if dry_run:
        plan_lines = [
            f"  search {topic!r} (max_papers={max_papers}, backends=arxiv+semantic_scholar)",
            f"  fit-check filter (heuristic)",
            f"  ingest into cluster {slug}",
        ]
        if do_nlm:
            plan_lines.extend([
                f"  notebooklm bundle --cluster {slug}",
                f"  notebooklm upload --cluster {slug}",
                f"  notebooklm generate --cluster {slug} --type brief",
                f"  notebooklm download --cluster {slug} --type brief",
            ])
        if do_crystals:
            cli = llm_cli or detect_llm_cli() or "(none on PATH)"
            plan_lines.append(f"  crystal emit + apply via LLM CLI: {cli}")
        if print_progress:
            print("Dry-run plan:")
            for line in plan_lines:
                print(line)
        report.total_duration_sec = time.time() - started
        return report

    # 3 + 4. Search ??papers_input.json
    try:
        search_kwargs = {"max_papers": max_papers, "cluster_slug": slug}
        if field is not None:
            search_kwargs["field"] = field
        papers = _run_search(topic, **search_kwargs)
        report.papers_ingested = len(papers)  # tentative
        _step_log(report, "search", True, _elapsed(started, report), f"{len(papers)} results", print_progress)
    except Exception as exc:
        _step_log(report, "search", False, _elapsed(started, report), str(exc), print_progress)
        report.ok = False
        report.error = "search failed: " + str(exc)
        return report

    if not papers:
        report.ok = False
        report.error = "Search returned 0 papers ??try a different topic or backend"
        return report

    # Write papers_input.json to cfg.root (the default location pipeline reads from)
    papers_input_path = cfg.root / "papers_input.json"
    papers_input_path.write_text(
        json.dumps({"papers": papers}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 5. Ingest
    try:

        rc = run_pipeline(
            dry_run=False,
            cluster_slug=slug,
            query=topic,
            verify=False,
        )
        if rc != 0:
            raise RuntimeError("pipeline returned exit code " + str(rc))        
        # Count actual ingested files (anything in raw/<slug>/ now)
        raw_dir = cfg.raw / slug
        if raw_dir.exists():
            report.papers_ingested = len(list(raw_dir.glob("*.md")))
        _step_log(report, "ingest", True, _elapsed(started, report),
                  f"{report.papers_ingested} papers in raw/{slug}/", print_progress)
    except Exception as exc:
        _step_log(report, "ingest", False, _elapsed(started, report), str(exc), print_progress)
        report.ok = False
        report.error = "ingest failed: " + str(exc)
        return report

    if not do_nlm:
        if do_crystals:
            _run_crystal_step(cfg, slug, llm_cli, report, started, print_progress)
        report.total_duration_sec = time.time() - started
        if print_progress:
            _print_next_steps(report, slug, do_crystals=do_crystals)
        return report

    # 6, 7, 8, 9 ??NotebookLM
    cluster = registry.get(slug)  # refresh
    try:


        bundle_report = bundle_cluster(cluster, cfg, download_pdfs=True)        
        _step_log(report, "nlm.bundle", True, _elapsed(started, report),        
                  f"{bundle_report.pdf_count} PDFs", print_progress)

        upload_report = upload_cluster(cluster, cfg, headless=False)
        report.nlm_uploaded = upload_report.success_count
        report.notebook_url = upload_report.notebook_url
        _step_log(report, "nlm.upload", True, _elapsed(started, report),        
                  f"{upload_report.success_count} succeeded", print_progress)   

        generate_artifact(cluster, cfg, kind="brief", headless=False)
        _step_log(report, "nlm.generate", True, _elapsed(started, report),      
                  "brief generation triggered", print_progress)

        download_report = download_briefing_for_cluster(cluster, cfg, headless=False)
        report.brief_path = download_report.artifact_path
        _step_log(report, "nlm.download", True, _elapsed(started, report),
                  f"{download_report.char_count} chars saved", print_progress)
    except Exception as exc:
        _step_log(report, "nlm", False, _elapsed(started, report), str(exc), print_progress)
        report.ok = False
        report.error = "NotebookLM step failed: " + str(exc)
        return report

    # 10. (optional) Crystal generation via detected LLM CLI
    if do_crystals:
        _run_crystal_step(cfg, slug, llm_cli, report, started, print_progress)

    report.total_duration_sec = time.time() - started
    if print_progress:
        _print_next_steps(report, slug, do_crystals=do_crystals)
    return report


def _run_crystal_step(
    cfg,
    slug: str,
    llm_cli: Optional[str],
    report: AutoReport,
    started: float,
    print_progress: bool,
) -> None:
    """Emit crystal prompt, pipe through LLM CLI, apply response. Best-effort.

    On any failure (no CLI on PATH, LLM error, malformed JSON), saves the
    raw prompt to artifacts/<slug>/crystal-prompt.md so the user can run it
    manually. Never raises — auto_pipeline already succeeded if we got here.
    """
    from research_hub.crystal import apply_crystals, emit_crystal_prompt

    try:
        prompt = emit_crystal_prompt(cfg, slug)
    except Exception as exc:
        _step_log(report, "crystals", False, _elapsed(started, report),
                  f"emit failed: {exc}", print_progress)
        return

    artifacts_dir = cfg.research_hub_dir / "artifacts" / slug
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = artifacts_dir / "crystal-prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    cli_name = llm_cli or detect_llm_cli()
    if cli_name is None:
        _step_log(report, "crystals", False, _elapsed(started, report),
                  f"no LLM CLI on PATH (claude/codex/gemini); prompt saved to {prompt_path}",
                  print_progress)
        return

    try:
        raw_response = _invoke_llm_cli(cli_name, prompt)
    except Exception as exc:
        _step_log(report, "crystals", False, _elapsed(started, report),
                  f"{cli_name} failed: {exc}; prompt saved to {prompt_path}",
                  print_progress)
        return

    response_path = artifacts_dir / "crystal-response.json"
    response_path.write_text(raw_response, encoding="utf-8")

    parsed = _extract_first_json(raw_response)
    if parsed is None:
        _step_log(report, "crystals", False, _elapsed(started, report),
                  f"could not parse JSON from {cli_name} output; saved to {response_path}",
                  print_progress)
        return

    try:
        apply_result = apply_crystals(cfg, slug, parsed)
    except Exception as exc:
        _step_log(report, "crystals", False, _elapsed(started, report),
                  f"apply failed: {exc}", print_progress)
        return

    written = getattr(apply_result, "written_count", None) or len(getattr(apply_result, "written", []) or [])
    _step_log(report, "crystals", True, _elapsed(started, report),
              f"{written} crystals via {cli_name}", print_progress)


def _print_next_steps(report: AutoReport, slug: str, *, do_crystals: bool) -> None:
    """Print copy-paste-ready commands so users know what to do after auto."""
    print()
    print("=" * 60)
    print(f"Done in {report.total_duration_sec:.1f}s. Cluster: {slug}")
    print("=" * 60)
    if report.notebook_url:
        print(f"  NotebookLM: {report.notebook_url}")
    if report.brief_path:
        print(f"  Brief:      {report.brief_path}")
    print()
    print("Next steps (copy-paste any of these):")
    print()
    print("  # See your new cluster in the live dashboard")
    print(f"  research-hub serve --dashboard")
    print()
    if not do_crystals:
        print("  # Generate cached AI answers (~10 Q&As, ~1 KB each)")
        print(f"  research-hub crystal emit  --cluster {slug} > /tmp/cprompt.md")
        print(f"  # paste /tmp/cprompt.md into Claude/GPT/Gemini, save response as crystals.json")
        print(f"  research-hub crystal apply --cluster {slug} --scored crystals.json")
        print()
        print("  # Or auto-pipe through a detected LLM CLI:")
        print(f"  research-hub auto \"{slug}\" --with-crystals  # if claude/codex/gemini on PATH")
        print()
    print("  # Ad-hoc Q&A against the uploaded notebook")
    print(f"  research-hub ask {slug} \"what are the 3 main research threads?\"")
    print()
    print("  # Talk to Claude Desktop instead (with research-hub MCP installed)")
    print(f"  > \"Claude, what's in my {slug} cluster?\"  # calls read_crystal()")
    print()


def _ensure_zotero_collection(registry, cluster, slug: str, report: AutoReport, print_progress: bool) -> None:
    """Auto-create + bind a Zotero collection so `ingest` has a target.

    Best-effort: skips silently if Zotero is not configured (analyst persona,
    or RESEARCH_HUB_NO_ZOTERO=1). This keeps the lazy-mode promise that
    `auto "topic"` can run end-to-end without a manual `clusters bind`.
    """
    import os
    if os.environ.get("RESEARCH_HUB_NO_ZOTERO") == "1":
        return
    try:
        from research_hub.zotero.client import get_client
        zot = get_client()
    except Exception as exc:
        _step_log(report, "zotero.bind", False, 0.0,
                  f"could not load Zotero client: {exc}", print_progress)
        return
    try:
        # get_client() returns either the dual-client wrapper or pyzotero
        # Zotero directly. Both expose create_collections() that takes a
        # list[dict]; pass the minimal {"name": ...} payload only.
        web = getattr(zot, "web", None) or zot
        result = web.create_collections([{"name": cluster.name}])
        # pyzotero returns {"successful": {"0": {"key": "ABC123", ...}}, ...}
        successful = (result or {}).get("successful", {}) if isinstance(result, dict) else {}
        first = next(iter(successful.values()), None) if successful else None
        new_key = (first or {}).get("key") or (first or {}).get("data", {}).get("key")
        if not new_key:
            _step_log(report, "zotero.bind", False, 0.0,
                      f"Zotero create_collection returned no key: {result}", print_progress)
            return
        cluster.zotero_collection_key = new_key
        registry.save()
        _step_log(report, "zotero.bind", True, 0.0,
                  f"created collection {new_key} for {slug}", print_progress)
    except Exception as exc:
        _step_log(report, "zotero.bind", False, 0.0,
                  f"create_collection failed: {exc}", print_progress)


def _step_log(
    report: AutoReport,
    name: str,
    ok: bool,
    duration_sec: float,
    detail: str,
    print_progress: bool,
) -> None:
    result = AutoStepResult(name=name, ok=ok, duration_sec=duration_sec, detail=detail)
    report.steps.append(result)
    if print_progress:
        symbol = "[OK]" if ok else "[FAIL]"
        print(f"{symbol} {name:<14} {detail}")


def _elapsed(started: float, report: AutoReport) -> float:
    return time.time() - started


def _run_search(topic: str, *, max_papers: int, cluster_slug: str, field: Optional[str] = None) -> list[dict]:
    """Run arxiv + semantic_scholar search, return papers_input dicts."""       


    # v0.49.4: search arxiv + semantic-scholar + openalex + crossref so the
    # pipeline survives semantic-scholar rate-limiting and one-backend gaps.
    backends = list(FIELD_PRESETS[field]) if field else ["arxiv", "semantic-scholar", "openalex", "crossref"]
    results = search_papers(
        topic,
        backends=backends,
        limit=max_papers,
    )
    return _to_papers_input([asdict(r) for r in results], cluster_slug)
