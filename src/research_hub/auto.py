"""End-to-end pipeline: topic string ??cluster ??search ??ingest ??NotebookLM.

v0.46 "lazy mode": one command does everything.
"""
from __future__ import annotations

import json
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
    do_nlm: bool = True,
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
            cluster = registry.create(slug=slug, name=display, first_query=topic)
            report.cluster_created = True
            _step_log(report, "cluster", True, 0.0, f"created: {slug}", print_progress)
    else:
        _step_log(report, "cluster", True, 0.0, f"existing: {slug}", print_progress)

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
        if print_progress:
            print("Dry-run plan:")
            for line in plan_lines:
                print(line)
        report.total_duration_sec = time.time() - started
        return report

    # 3 + 4. Search ??papers_input.json
    try:
        papers = _run_search(topic, max_papers=max_papers, cluster_slug=slug)   
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
        report.total_duration_sec = time.time() - started
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

    report.total_duration_sec = time.time() - started
    return report


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
        symbol = "✅" if ok else "❌"
        print(f"{symbol} {name:<14} {detail}")


def _elapsed(started: float, report: AutoReport) -> float:
    return time.time() - started


def _run_search(topic: str, *, max_papers: int, cluster_slug: str) -> list[dict]:
    """Run arxiv + semantic_scholar search, return papers_input dicts."""       


    results = search_papers(
        topic,
        backends="arxiv,semantic_scholar",
        limit=max_papers,
    )
    return _to_papers_input([asdict(r) for r in results], cluster_slug)
