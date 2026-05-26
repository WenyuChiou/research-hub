"""End-to-end pipeline: topic string ??cluster ??search ??ingest ??NotebookLM.

v0.46 "lazy mode": one command does everything.
v0.49: optional auto-crystal step via detected LLM CLI + Next Steps banner.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from research_hub.clusters import ClusterRegistry, slugify
from research_hub.config import get_config
from research_hub.discover import _to_papers_input
from research_hub.llm_cli import (
    _extract_first_json,
    detect_llm_cli,
    invoke_llm_cli,
)
from research_hub.pipeline import run_pipeline


# LLM CLI detection/invocation moved to llm_cli.py (Wave 1 refactor).


def _invoke_llm_cli(cli_name: str, prompt: str, timeout_sec: float = 180.0, **kwargs) -> str:
    """Back-compat wrapper — delegates to llm_cli.invoke_llm_cli (Wave 1 refactor)."""
    return invoke_llm_cli(cli_name, prompt, timeout_sec=timeout_sec, **kwargs)


_invoke_llm_cli._llm_cli_backcompat_wrapper = True  # type: ignore[attr-defined]




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
    nlm_deferred: bool = False
    nlm_error: str = ""
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
    do_cluster_overview: bool = True,
    cluster_overview_threshold: int = 0,
    do_fit_check: bool = True,
    fit_check_threshold: int = 3,
    no_llm_fit_check: bool = False,
    llm_cli: Optional[str] = None,
    dry_run: bool = False,
    print_progress: bool = True,
    zotero_batch_size: int = 50,
    # NOTE: intentionally False at the Python-API layer while the CLI
    # default is True. Programmatic callers (tests, library users) stay
    # opt-in so the PDF-attach network round-trips do not fire unless
    # the caller explicitly asks for them; CLI users get the default-on
    # behaviour via the argparse BooleanOptionalAction in cli.py.
    with_pdfs: bool = False,
    with_summary: bool = False,
    peer_reviewed: bool = False,
    include_suspect_urls: bool = False,
    # Year filter for the search step (parsed upstream from `--year RANGE`).
    # None on either side = unbounded in that direction.
    year_from: int | None = None,
    year_to: int | None = None,
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

    Search and ingest failures stop the run. NotebookLM failures are deferred
    because papers have already landed in the vault.
    """
    cfg = get_config()
    user_adapters = getattr(cfg, "llm_cli_adapters", {}) or {}
    if not isinstance(user_adapters, dict):
        user_adapters = {}
    if llm_cli is None:
        try:
            effective_cli = detect_llm_cli(user_adapters=user_adapters)
        except TypeError:
            # Preserve older tests/callers that monkeypatch detect_llm_cli
            # with a zero-argument function.
            effective_cli = detect_llm_cli()
    else:
        effective_cli = llm_cli
    if print_progress:
        cli_info = effective_cli or "none (term-overlap fallback)"
        print(f"[fit-check] LLM CLI: {cli_info}")
    del cluster_overview_threshold


    started = time.time()
    report = AutoReport(cluster_slug="", cluster_created=False)

    # 1. Slugify + 2. cluster create-or-get
    explicit_cluster_slug = cluster_slug is not None
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
            try:
                from research_hub.vault.graph_config import refresh_graph_from_vault
                refresh_graph_from_vault(cfg)
            except Exception as exc:
                _step_log(report, "graph.refresh", False, 0.0, str(exc), print_progress)
            # v0.49.4: also auto-create + bind a Zotero collection so ingest
            # has somewhere to put papers without manual `clusters bind`.
            _ensure_zotero_collection(registry, cluster, slug, report, print_progress)
    else:
        _step_log(report, "cluster", True, 0.0, f"existing: {slug}", print_progress)
        if getattr(cluster, "status", "active") == "archived" and not explicit_cluster_slug:
            _step_log(
                report,
                "archive",
                True,
                _elapsed(started, report),
                f"skipped archived cluster: {slug}",
                print_progress,
            )
            return report
        # NOTE: clusters with a recorded zotero_collection_key are trusted
        # without round-tripping to Zotero. If the user manually deleted
        # that collection in the Zotero UI, the next ingest will 404 on
        # write. Validating-and-rebinding stale keys is a separate concern
        # (see follow-up: probe-then-rebind on stale keys).
        if not dry_run and not getattr(cluster, "zotero_collection_key", None):
            _ensure_zotero_collection(registry, cluster, slug, report, print_progress)

    # Print plan if dry_run; do NOT execute remaining steps
    if dry_run:
        backends, exclude_types, min_confidence = _resolve_search_options(
            field=field,
            peer_reviewed=peer_reviewed,
        )
        filter_note = ""
        if peer_reviewed:
            filter_note = (
                f", exclude_types={','.join(exclude_types)}, "
                f"min_confidence={min_confidence:g}"
            )
        if year_from is not None or year_to is not None:
            year_note = (
                f"{year_from if year_from is not None else ''}-"
                f"{year_to if year_to is not None else ''}"
            )
            filter_note += f", year={year_note}"
        plan_lines = [
            f"  search {topic!r} (max_papers={max_papers}, "
            f"backends={'+'.join(backends)}{filter_note})",
        ]
        if do_fit_check:
            if no_llm_fit_check:
                plan_lines.append(
                    f"  fit-check via term-overlap rule (threshold={fit_check_threshold})"
                )
            else:
                cli_for_plan = effective_cli or "(none on PATH - will skip)"
                plan_lines.append(
                    f"  fit-check via LLM judge ({cli_for_plan}, threshold={fit_check_threshold})"
                )
        plan_lines.append(f"  ingest into cluster {slug}")
        if with_pdfs:
            plan_lines.append("  attach open-access PDFs from arXiv/OpenAlex/Unpaywall/Crossref")
        if with_summary:
            cli = effective_cli or "(none on PATH -> will skip)"
            plan_lines.append(f"  summarize per-paper notes via LLM CLI ({cli})")
        if do_cluster_overview:
            cli = effective_cli or "(none on PATH -> save prompt only)"
            plan_lines.append(f"  cluster overview auto-fill via LLM CLI ({cli})")
        if do_nlm:
            plan_lines.extend([
                f"  notebooklm bundle --cluster {slug}",
                f"  notebooklm upload --cluster {slug}",
                f"  notebooklm generate --cluster {slug} --type brief",
                f"  notebooklm download --cluster {slug} --type brief",
            ])
        if do_crystals:
            cli = effective_cli or "(none on PATH)"
            plan_lines.append(f"  crystal emit + apply via LLM CLI: {cli}")
        if print_progress:
            print("Dry-run plan:")
            for line in plan_lines:
                print(line)
        report.total_duration_sec = time.time() - started
        return report

    # Phase C: fail-closed first-run guard — surface a missing LLM judge
    # BEFORE the slow multi-backend search instead of after an empty
    # vault. Does NOT weaken the gate: the only opt-out is the explicit,
    # pre-existing --no-fit-check (do_fit_check=False), which still runs
    # L0/L1/L3 authenticity, just no relevance filter.
    if do_fit_check and not no_llm_fit_check and not effective_cli:
        if print_progress:
            print(
                "No relevance judge LLM CLI on PATH.\n"
                "  Relevance checking is fail-closed: every paper would be\n"
                "  quarantined (NOT written to the vault). Choose one:\n"
                "    - install / log in a judge CLI, then re-run, OR\n"
                "    - re-run with --no-fit-check (papers still pass\n"
                "      L0/L1/L3 authenticity; NOT relevance-filtered), OR\n"
                "    - re-run with --no-llm-fit-check to use rule-based\n"
                "      term-overlap relevance filtering, OR\n"
                "    - run 'research-hub doctor' to check setup."
            )
        report.ok = False
        report.error = (
            "no relevance judge on PATH (fail-closed); re-run with "
            "--no-fit-check, --no-llm-fit-check, or install a supported LLM CLI"
        )
        report.total_duration_sec = time.time() - started
        return report

    # 3 + 4. Search — print active backends before starting so user knows what's running.
    # NOTE: This reflects the FIELD_PRESETS definition, which is the source of truth
    # for backend selection in _run_search. If user-configured backends are added
    # via HubConfig.search_backends in the future, this print should be updated to
    # reflect the actual resolved list.
    if print_progress:
        from research_hub.search.fallback import FIELD_PRESETS, DEFAULT_BACKENDS
        active_backends = FIELD_PRESETS.get(field, DEFAULT_BACKENDS) if field else DEFAULT_BACKENDS
        print(f"[search] backends: {', '.join(active_backends)}")
    try:
        search_kwargs = {
            "max_papers": max_papers,
            "cluster_slug": slug,
        }
        if peer_reviewed:
            search_kwargs["peer_reviewed"] = True
        if field is not None:
            search_kwargs["field"] = field
        if year_from is not None:
            search_kwargs["year_from"] = year_from
        if year_to is not None:
            search_kwargs["year_to"] = year_to
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

    # LLM-judge fit-check between search and ingest. Phase A makes this
    # fail-closed: unjudged or low-score papers go to quarantine before
    # Zotero/Obsidian writes.
    if do_fit_check:
        papers = _run_fit_check_step(
            cfg, papers, topic, slug, effective_cli,
            fit_check_threshold, report, started, print_progress,
            no_llm_fit_check=no_llm_fit_check,
            user_adapters=user_adapters,
        )
        report.papers_ingested = len(papers)

    # Write papers_input.json to cfg.root (the default location pipeline reads from)
    papers_input_path = cfg.root / "papers_input.json"
    papers_input_path.write_text(
        json.dumps({"papers": papers}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 5. Ingest
    try:

        run_kwargs = {
            "dry_run": False,
            "cluster_slug": slug,
            "query": topic,
            "verify": False,
            "zotero_batch_size": zotero_batch_size,
            "allow_archived_cluster": explicit_cluster_slug,
        }
        if with_pdfs:
            run_kwargs["with_pdfs"] = True
        rc = run_pipeline(**run_kwargs)
        if rc != 0:
            raise RuntimeError("pipeline returned exit code " + str(rc))        
        # F6: the count must be authoritative. Previously, when EVERY
        # candidate was quarantined the raw dir was never created, the
        # `exists()` guard was skipped, and the tentative `len(papers)`
        # survived -> `[OK] ingest N papers` printed despite 0 written.
        raw_dir = cfg.raw / slug
        attempted = report.papers_ingested  # tentative len(papers)
        written = len(list(raw_dir.glob("*.md"))) if raw_dir.exists() else 0
        report.papers_ingested = written
        # PR-E: after a successful ingest, refresh the vault-level
        # navigation artifacts (`_HOME.md` + `hub/_moc/*.md` populated
        # bodies + every cluster's `00_overview.md`). Pre-fix these
        # were silently stale after every `auto` -- `populate_all_overviews`
        # was wired into `vault rebuild-overviews` only, never into the
        # primary ingest flow. Non-fatal (the ingest itself succeeded);
        # log + continue on any failure so a per-cluster overview / MOC
        # / home-render error doesn't sink the whole auto pipeline.
        if written > 0:
            try:
                from research_hub.vault.hub_overview import populate_all_overviews
                populate_all_overviews(cfg)
            except Exception as exc:  # noqa: BLE001 - best-effort post-ingest refresh
                print(
                    f"  [WARN] populate_all_overviews failed; _HOME.md / "
                    f"MOCs / overviews may be stale: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
        try:
            from research_hub.authenticity import DEFERRED_LAYER, list_quarantine
            q_rows = list_quarantine(cfg, cluster=slug)
            deferred = sum(1 for r in q_rows if r.get("layer") == DEFERRED_LAYER)
            quarantined = len(q_rows) - deferred
        except Exception:
            deferred = 0
            quarantined = 0
        detail = (
            f"{written} written, {quarantined} quarantined, "
            f"{deferred} deferred (of {attempted} candidate(s)) in raw/{slug}/"
        )
        # F6: candidates existed but the vault got nothing (all rejected
        # by fit-check / the fail-closed authenticity gate). Render the
        # ingest step as [FAIL] with an honest count + actionable hint so
        # it can never read as `[OK] ingest N papers` again. We do NOT
        # flip report.ok / abort: quarantine-of-all is the safety gate
        # working as designed, not an orchestration crash, and the
        # end-of-run quarantine summary (more actionable) still prints.
        ingest_ok = not (written == 0 and attempted > 0)
        if ingest_ok:
            _step_log(report, "ingest", True, _elapsed(started, report),
                      detail, print_progress)
        else:
            _step_log(report, "ingest", False, _elapsed(started, report),
                      detail + " -- nothing reached the vault", print_progress)
            if deferred and not quarantined:
                # Pure transient failure (doi.org / Crossref rate-limit):
                # the papers are NOT rejected — retry once the resolver
                # is reachable (re-run, or `quarantine restore`).
                report.error = (
                    f"ingest wrote 0 papers; {deferred} deferred "
                    f"(transient resolver failure -- not rejected; retry: "
                    f"re-run, or research-hub quarantine restore "
                    f"<paper-slug> --cluster {slug})"
                )
            else:
                report.error = (
                    f"ingest wrote 0 papers ({quarantined} quarantined, "
                    f"{deferred} deferred of {attempted}); inspect: "
                    f"research-hub quarantine list --cluster {slug}"
                )
    except Exception as exc:
        _step_log(report, "ingest", False, _elapsed(started, report), str(exc), print_progress)
        report.ok = False
        report.error = "ingest failed: " + str(exc)
        return report

    if with_summary:
        _run_summary_step(cfg, slug, effective_cli, report, started, print_progress)

    if do_cluster_overview:
        _run_cluster_overview_step(cfg, slug, effective_cli, report, started, print_progress)

    if with_pdfs:
        # Attach open-access PDFs to Zotero items after ingest.
        # Refresh cluster from registry so we have the latest collection key.
        from research_hub.clusters import ClusterRegistry as _CR
        _clust = _CR(cfg.clusters_file).get(slug)
        if _clust:
            _run_pdf_attach_step(cfg, slug, _clust, report, started, print_progress)

    if not do_nlm:
        if do_crystals:
            _run_crystal_step(cfg, slug, effective_cli, report, started, print_progress)
        report.total_duration_sec = time.time() - started
        if print_progress:
            _print_next_steps(report, slug, cfg, do_crystals=do_crystals)
        return report

    # 6, 7, 8, 9 — NotebookLM
    cluster = registry.get(slug)  # refresh

    # Pre-flight: check NLM session health before attempting any browser work.
    # A stale / missing state.json produces an opaque browser error deep inside
    # upload_cluster; catching it here lets us print a clear HINT and skip
    # gracefully instead.
    try:
        from research_hub.notebooklm.auth import check_session_health, default_state_file
        _state_file = default_state_file(cfg.research_hub_dir)
        _health = check_session_health(_state_file)
        if not _health.get("ok"):
            from research_hub._invocation import recommended_cli_invocation
            _inv = recommended_cli_invocation()
            _reason = _health.get("reason", "unknown")
            report.nlm_deferred = True
            report.ok = True
            report.nlm_error = f"nlm.preflight: session not valid ({_reason})"
            _step_log(report, "nlm.preflight", False, _elapsed(started, report),
                      f"session not valid — run: {_inv} notebooklm login --auto-detect", print_progress)
            if print_progress:
                print(f"  [HINT] NLM session is not valid ({_reason}).")
                print(f"         Run:  {_inv} notebooklm login --auto-detect")
                print(f"         Then re-run auto to upload to NotebookLM.")
            if do_crystals:
                _run_crystal_step(cfg, slug, effective_cli, report, started, print_progress)
            report.total_duration_sec = time.time() - started
            if print_progress:
                _print_next_steps(report, slug, cfg, do_crystals=do_crystals)
            return report
    except ImportError:
        # Auth module not installed; fall through to normal NLM steps.
        pass
    except Exception as exc:
        # Health check failed at runtime (e.g. file lock, event-loop conflict).
        # Log and fall through so the normal NLM path handles it.
        if print_progress:
            print(f"  [NLM] preflight check failed ({type(exc).__name__}); proceeding.")

    nlm_step = "nlm"
    try:
        nlm_step = "nlm.bundle"
        from research_hub.notebooklm.bundle import bundle_cluster
        from research_hub.notebooklm.upload import (
            download_briefing_for_cluster,
            generate_artifact,
            upload_cluster,
        )
        bundle_report = bundle_cluster(cluster, cfg, download_pdfs=True)        
        _step_log(report, "nlm.bundle", True, _elapsed(started, report),        
                  f"{bundle_report.pdf_count} PDFs", print_progress)

        nlm_step = "nlm.upload"
        upload_report = upload_cluster(
            cluster, cfg, headless=False,
            include_suspect_urls=include_suspect_urls,
        )
        report.nlm_uploaded = upload_report.success_count
        report.notebook_url = upload_report.notebook_url
        _step_log(report, "nlm.upload", True, _elapsed(started, report),        
                  f"{upload_report.success_count} succeeded", print_progress)   
        if upload_report.notebook_was_reused and print_progress:
            print(
                "  [NLM] Reusing existing notebook (same cluster name). "
                "To start clean, delete it at https://notebooklm.google.com/ first."
            )

        nlm_step = "nlm.generate"
        generate_artifact(cluster, cfg, kind="brief", headless=False)
        _step_log(report, "nlm.generate", True, _elapsed(started, report),      
                  "brief generation triggered", print_progress)

        nlm_step = "nlm.download"
        download_report = download_briefing_for_cluster(cluster, cfg, headless=False)
        report.brief_path = download_report.artifact_path
        _step_log(report, "nlm.download", True, _elapsed(started, report),
                  f"{download_report.char_count} chars saved", print_progress)
    except Exception as exc:
        report.nlm_deferred = True
        report.nlm_error = f"{nlm_step}: {exc}"
        report.ok = True
        _step_log(report, nlm_step, False, _elapsed(started, report), str(exc), print_progress)

    # 10. (optional) Crystal generation via detected LLM CLI
    if do_crystals:
        _run_crystal_step(cfg, slug, effective_cli, report, started, print_progress)

    report.total_duration_sec = time.time() - started
    if print_progress:
        _print_next_steps(report, slug, cfg, do_crystals=do_crystals)
    return report


def _run_pdf_attach_step(
    cfg,
    slug: str,
    cluster,
    report: AutoReport,
    started: float,
    print_progress: bool,
) -> None:
    """Attach open-access PDFs to Zotero items that were just ingested.

    Uses the same OpenAlex / Unpaywall / arXiv lookup chain as
    ``research-hub paper attach-pdfs``.  Best-effort: any failure is logged
    but does not abort the pipeline.  Items that already have a PDF attachment
    are silently skipped (idempotent).

    Only open-access PDFs are attached — paywalled papers remain as metadata-
    only items (the abstract is still available via the Obsidian note).
    """
    try:
        from research_hub.zotero.client import get_client
        from research_hub.zotero.pdf_attach import attach_pdfs, plan_attach_for_items

        zot = get_client()
        web = getattr(zot, "web", None) or zot
        coll_key = getattr(cluster, "zotero_collection_key", "") or ""
        if not coll_key:
            _step_log(report, "pdf.attach", False, _elapsed(started, report),
                      "no Zotero collection key — skip", print_progress)
            return
        # Fetch items in this collection; exclude attachments (we want parent items only)
        items = web.collection_items(coll_key, itemType="-attachment") or []
        if not items:
            _step_log(report, "pdf.attach", True, _elapsed(started, report),
                      "no items in collection", print_progress)
            return
        plans = plan_attach_for_items(items)
        actionable = [p for p in plans if p.pdf_url]
        if not actionable:
            _step_log(report, "pdf.attach", True, _elapsed(started, report),
                      f"0 OA PDFs found for {len(items)} item(s)", print_progress)
            return
        local_pdfs_dir = getattr(cfg, "root", None)
        if local_pdfs_dir is not None:
            local_pdfs_dir = local_pdfs_dir / "pdfs"
        results = attach_pdfs(web, actionable, rate_limit_rps=1.0,
                               local_pdfs_dir=local_pdfs_dir)
        summary = results.summary
        ok, skip, fail = summary.ok, summary.skip, summary.fail
        _step_log(report, "pdf.attach", True, _elapsed(started, report),
                  f"{ok} attached, {skip} skipped, {fail} failed "
                  f"of {len(actionable)} with OA PDF",
                  print_progress)
    except Exception as exc:
        _step_log(report, "pdf.attach", False, _elapsed(started, report),
                  f"pdf attach error: {exc}", print_progress)


def _run_summary_step(
    cfg,
    slug: str,
    llm_cli: Optional[str],
    report: AutoReport,
    started: float,
    print_progress: bool,
) -> None:
    """Best-effort per-paper summary autofill after ingest.

    v0.88.6: this single step now drives **both** summary layers so
    `auto --with-summary` produces a fully-filled note (1-line
    `## Summary` callout AND structured `## Key Findings` /
    `## Methodology` / `## Relevance` sections). Previously the second
    layer was only filled when the user ran the separate
    `research-hub paper summarize --pending` command afterwards, which
    was an opaque gotcha for new users.

    Failure of either layer is logged but does not block the other —
    each is best-effort and the structured layer can be retried via
    `paper summarize --pending` at any time.
    """
    from research_hub.summarize import summarize_cluster

    cli = llm_cli or detect_llm_cli()
    if not cli:
        _step_log(report, "summary", True, _elapsed(started, report),
                  "skipped (no supported LLM CLI on PATH)", print_progress)
        return

    # --- Layer 1: ## Summary 1-liner callout, via summarize_cluster ---
    summary_count = 0
    summary_errors = 0
    try:
        summary_report = summarize_cluster(cfg, slug, llm_cli=cli, apply=True)
    except Exception as exc:
        _step_log(report, "summary", False, _elapsed(started, report),
                  f"summarize failed: {exc}", print_progress)
    else:
        if not summary_report.ok:
            _step_log(report, "summary", False, _elapsed(started, report),
                      summary_report.error or "summarize failed", print_progress)
        else:
            apply_result = summary_report.apply_result
            if apply_result is not None:
                summary_count = len(apply_result.applied)
                summary_errors = len(apply_result.errors)

    # --- Layer 2: ## Key Findings / Methodology / Relevance, via paper-summarize ---
    # Drives the v0.87.1 §O3 paper_summarize path so KF/Methodology/Relevance
    # placeholders also get filled (and summarize_status flips pending → done).
    paper_done = 0
    paper_failed = 0
    paper_errors = 0
    try:
        from research_hub.paper_summarize import summarize_pending

        results = summarize_pending(
            cfg, cluster_slug_filter=slug, backend=cli, dry_run=False
        )
        # v0.88.8: SummarizeResult exposes its outcome under `.action`,
        # not `.status` — v0.88.6 read the wrong attribute, so the count
        # always logged as "0 done" even when 12+ paper notes had actually
        # been filled. The on-disk work was correct; only the report lied.
        for r in results:
            action = getattr(r, "action", "") or getattr(r, "status", "")
            if action == "done":
                paper_done += 1
            elif action in {"failed_no_abstract", "would_fail_no_abstract"}:
                paper_failed += 1
            elif action == "error":
                paper_errors += 1
    except Exception as exc:
        _step_log(report, "summary", False, _elapsed(started, report),
                  (
                      f"summary layer-1: {summary_count} ok / {summary_errors} err; "
                      f"summary layer-2 (KF/Methodology/Relevance): {exc}"
                  ),
                  print_progress)
        return

    layer2_msg = (
        f"layer-2 (KF/Methodology/Relevance): {paper_done} done"
        + (f" / {paper_failed} failed_no_abstract" if paper_failed else "")
        + (f" / {paper_errors} errors" if paper_errors else "")
    )
    layer1_msg = (
        f"layer-1 (## Summary): {summary_count} ok"
        + (f" / {summary_errors} err" if summary_errors else "")
    )
    ok = (summary_errors == 0 and paper_errors == 0)
    _step_log(
        report, "summary", ok, _elapsed(started, report),
        f"{layer1_msg}; {layer2_msg} via {cli}",
        print_progress,
    )


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
                  f"no LLM CLI on PATH (supported adapters not found); prompt saved to {prompt_path}",
                  print_progress)
        return

    try:
        # v0.88.10: crystals are the longest LLM call in the pipeline (10
        # cards × ~50 papers' worth of context); the default 180 s
        # _invoke_llm_cli timeout was tripping out in real Stage B runs
        # with full-size clusters. Bump to 600 s for this step only.
        raw_response = _invoke_llm_cli(cli_name, prompt, timeout_sec=600.0)
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


def _run_cluster_overview_step(
    cfg,
    slug: str,
    llm_cli: Optional[str],
    report: AutoReport,
    started: float,
    print_progress: bool,
) -> None:
    """Best-effort cluster overview autofill after ingest."""
    from research_hub.cluster_overview import overview_cluster

    try:
        overview_report = overview_cluster(cfg, slug, llm_cli=llm_cli, apply=True)
    except Exception as exc:
        _step_log(report, "cluster_overview", False, _elapsed(started, report),
                  f"overview step failed: {exc}", print_progress)
        return

    if not overview_report.ok:
        _step_log(report, "cluster_overview", False, _elapsed(started, report),
                  overview_report.error or "overview step failed", print_progress)
        return

    apply = overview_report.apply_result
    if apply and apply.written:
        detail = f"wrote 00_overview.md via {overview_report.cli_used or 'saved payload'}"
    elif apply and apply.skipped:
        # v0.88.9: idempotent skip — user's hand-curated TL;DR was
        # preserved. Not a failure, just reuse.
        detail = f"skipped: {apply.skip_reason or 'preserved hand-curated overview'}"
    elif overview_report.prompt_path:
        detail = f"no LLM CLI on PATH; prompt saved to {overview_report.prompt_path}"
    else:
        detail = "overview step completed"
    _step_log(report, "cluster_overview", True, _elapsed(started, report), detail, print_progress)


def _print_next_steps(report: AutoReport, slug: str, cfg, *, do_crystals: bool) -> None:
    """Print copy-paste-ready commands so users know what to do after auto."""
    print()
    print("=" * 60)
    print(f"Done in {report.total_duration_sec:.1f}s. Cluster: {slug}")
    print("=" * 60)
    if report.notebook_url:
        print(f"  NotebookLM: {report.notebook_url}")
    if report.brief_path:
        print(f"  Brief:      {report.brief_path}")
    if report.nlm_deferred:
        from research_hub._invocation import recommended_cli_invocation
        inv = recommended_cli_invocation()
        is_auth_error = (report.nlm_error or "").startswith("nlm.preflight:")
        if is_auth_error:
            print(f"  [NLM] skipped — session expired. Fix:")
            print(f"    {inv} notebooklm login --auto-detect")
        else:
            print(f"  [NLM] skipped (check: {inv} notebooklm login --auto-detect). Resume with:")
        print(f"    {inv} notebooklm bundle   --cluster {slug}")
        print(f"    {inv} notebooklm upload   --cluster {slug}")
        print(f"    {inv} notebooklm generate --cluster {slug} --type brief")
        print(f"    {inv} notebooklm download --cluster {slug} --type brief")
        if report.nlm_error:
            print(f"  Last NLM error: {report.nlm_error}")
    print()
    # Phase C: make the fail-closed gate auditable instead of a silent
    # empty/short vault. Reuse Phase A's list_quarantine (NOT a fresh
    # dir-scan) for the full L0-L4 picture for this cluster.
    try:
        from collections import Counter

        from research_hub.authenticity import DEFERRED_LAYER, list_quarantine

        q_rows = list_quarantine(cfg, cluster=slug)
    except Exception as exc:  # best-effort UX affordance; never fatal
        q_rows = []
        DEFERRED_LAYER = "L1-deferred"
        print(f"  [quarantine] summary unavailable for {slug} ({type(exc).__name__})")
    if q_rows:
        # PR-C: keep this footer consistent with the ingest step — show
        # deferred (transient, retryable) distinctly from quarantined
        # (rejected by the fail-closed gate), not lumped as "quarantined".
        deferred_rows = [r for r in q_rows if r.get("layer") == DEFERRED_LAYER]
        quar_rows = [r for r in q_rows if r.get("layer") != DEFERRED_LAYER]
        print()
        if quar_rows:
            print(
                f"  [quarantine] {len(quar_rows)} paper(s) quarantined for "
                f"cluster {slug} (fail-closed authenticity gate; not in the "
                f"vault):"
            )
            for reason, count in sorted(
                Counter((r.get("reason") or "unknown") for r in quar_rows).items()
            ):
                print(f"    - {reason}: {count}")
        if deferred_rows:
            print(
                f"  [deferred] {len(deferred_rows)} paper(s) NOT rejected -- "
                f"transient resolver failure (rate-limit/unreachable); "
                f"retryable for cluster {slug}:"
            )
            for reason, count in sorted(
                Counter((r.get("reason") or "unknown") for r in deferred_rows).items()
            ):
                print(f"    - {reason}: {count}")
        print("  Review / recover:")
        print(f"    research-hub quarantine list --cluster {slug}")
        print(f"    research-hub quarantine show <paper-slug> --cluster {slug}")
        print(f"    research-hub quarantine restore <paper-slug> --cluster {slug}")
        print()
    # Summarize hint: count papers in the cluster with summarize_status=pending
    # so the user knows to run `paper summarize --pending` after ingesting.
    try:
        import re as _re
        cfg_raw = getattr(cfg, "raw", None)
        if cfg_raw is not None:
            pending_count = 0
            no_abstract_count = 0
            cluster_dir = cfg_raw / slug
            if cluster_dir.is_dir():
                for note in cluster_dir.glob("*.md"):
                    text = note.read_text(encoding="utf-8", errors="ignore")
                    m = _re.search(r"^summarize_status:\s*(\S+)", text, _re.MULTILINE)
                    if m:
                        status_val = m.group(1)
                        if status_val == "pending":
                            pending_count += 1
                        elif status_val == "failed_no_abstract":
                            no_abstract_count += 1
            if pending_count:
                print(f"  [HINT] {pending_count} paper(s) pending summary — run:")
                print(f"  python -m research_hub.cli paper summarize --pending --cluster {slug}")
                print()
            if no_abstract_count:
                print(f"  [HINT] {no_abstract_count} paper(s) have no extractable abstract"
                      f" — add a PDF or check the source URL.")
                print()
    except Exception:
        pass
    print("Next steps (copy-paste any of these):")
    print()
    print("  # See your new cluster in the live dashboard")
    print(f"  research-hub serve --dashboard")
    print()
    if not do_crystals:
        print("  # Generate cached AI answers (~10 Q&As, ~1 KB each)")
        print(f"  research-hub crystal emit  --cluster {slug} > /tmp/cprompt.md")
        print(f"  # paste /tmp/cprompt.md into a supported LLM/chat, save response as crystals.json")
        print(f"  research-hub crystal apply --cluster {slug} --scored crystals.json")
        print()
        print("  # Or auto-pipe through a detected LLM CLI:")
        print(f"  research-hub auto \"{slug}\" --with-crystals  # if a supported LLM CLI is on PATH")
        print()
    print("  # Ad-hoc Q&A against the uploaded notebook")
    print(f"  research-hub ask {slug} \"what are the 3 main research threads?\"")
    print()
    print("  # Talk to Claude Desktop instead (with research-hub MCP installed)")
    print(f"  > \"Claude, what's in my {slug} cluster?\"  # calls read_crystal()")
    print()


def _find_existing_collection_key_by_name(web, name: str) -> str | None:
    """Look up a Zotero collection by case-insensitive name, return key or None.

    v0.68.4: prevent the duplicate-collection accumulation bug. Previously
    `_ensure_zotero_collection` always POSTed a new collection, so any code
    path that called auto_pipeline without a recorded cluster.zotero_collection_key
    (test reset, manual collection delete on Zotero side, fresh cluster
    that happens to share a name) would silently create a duplicate. A real
    incident left 283 empty orphan collections in the maintainer's library
    over months of test runs.

    Name match is case-folded (`.casefold()`) on both sides because the
    Zotero web UI lets users rename to case-only-different forms ("Flood
    Risk" vs "flood risk"), and a case-sensitive match would still leak
    duplicates from that path. casefold() is preferred over lower() for
    Unicode correctness (e.g., German ß).
    """
    target = name.casefold()
    try:
        # Manual pagination: pyzotero's follow() pattern hit a None-path bug
        # on some versions; explicit start= avoids it.
        start = 0
        while True:
            chunk = web.collections(limit=100, start=start)
            if not chunk:
                return None
            for c in chunk:
                if c.get("data", {}).get("name", "").casefold() == target:
                    return c["data"]["key"]
            if len(chunk) < 100:
                return None
            start += 100
    except Exception:
        return None


def _run_fit_check_step(
    cfg,
    papers: list[dict],
    topic: str,
    slug: str,
    llm_cli: Optional[str],
    threshold: int,
    report: AutoReport,
    started: float,
    print_progress: bool,
    no_llm_fit_check: bool = False,
    user_adapters: dict | None = None,
) -> list[dict]:
    """LLM-judge relevance gate between search and ingest.

    Phase A makes this fail-closed: unjudged or low-score candidates are
    quarantined before they can reach Zotero or Obsidian.

    """
    if not papers:
        return papers

    from research_hub.authenticity import quarantine_paper

    if no_llm_fit_check:
        from research_hub.fit_check import (
            _read_definition_from_overview,
            screen_relevance,
        )

        if print_progress:
            print("[fit-check] no-llm mode: BM25 bimodal-gap relevance gate")

        definition = topic
        try:
            existing = _read_definition_from_overview(cfg, slug)
            if existing:
                definition = existing
        except Exception:
            pass

        # BM25 over 1..3-gram topic terms, IDF self-calibrated on this
        # batch; a paper is rejected only when the batch's scores show a
        # clear bimodal split and the paper sits in the low cluster.
        # Replaces the old `term_overlap >= 0.1` gate, which kept any paper
        # sharing one common word and let generic hydrology papers flood
        # an LLM cluster.
        verdicts = screen_relevance(papers, definition)
        kept: list[dict] = []
        for paper, verdict in zip(papers, verdicts):
            if verdict["kept"]:
                provenance = dict(paper.get("provenance") or {})
                provenance["fit_score"] = verdict["score"]
                provenance["fit_check_mode"] = "bm25_relevance"
                provenance["fit_check_tier"] = verdict["tier"]
                if verdict["tier"] == "cold-start":
                    # Kept but unscreened -- mark for later re-screening.
                    provenance["relevance_unverified"] = True
                paper["provenance"] = provenance
                kept.append(paper)
                continue
            quarantine_paper(
                cfg,
                paper,
                cluster_slug=slug,
                layer="L4",
                reason="low_relevance",
                details={
                    "fit_score": verdict["score"],
                    "mode": "bm25_relevance",
                    "detail": verdict["reason"],
                },
            )
        _step_log(report, "fit_check", True, _elapsed(started, report),
                  f"kept {len(kept)}/{len(papers)}; quarantined {len(papers) - len(kept)} "
                  "(mode=bm25_relevance)",
                  print_progress)
        return kept

    cli = llm_cli or detect_llm_cli()
    if not cli:
        for paper in papers:
            quarantine_paper(
                cfg,
                paper,
                cluster_slug=slug,
                layer="L4",
                reason="relevance_unjudged",
                details={"detail": "no LLM CLI on PATH"},
            )
        _step_log(report, "fit_check", True, _elapsed(started, report),
                  f"quarantined all {len(papers)} (no LLM CLI on PATH)", print_progress)
        return []

    try:
        from research_hub.fit_check import emit_prompt, apply_scores
        # If a cluster overview exists, use that. Otherwise fall back to the
        # raw topic — first-time `auto` runs have no overview yet.
        definition = topic
        try:
            from research_hub.fit_check import _read_definition_from_overview
            existing = _read_definition_from_overview(cfg, slug)
            if existing:
                definition = existing
        except Exception:
            pass

        prompt = emit_prompt(slug, papers, definition=definition)
        try:
            raw = _invoke_llm_cli(cli, prompt, user_adapters=user_adapters)
        except TypeError:
            raw = _invoke_llm_cli(cli, prompt)
        payload = _extract_first_json(raw)
        if payload is None:
            for paper in papers:
                quarantine_paper(
                    cfg,
                    paper,
                    cluster_slug=slug,
                    layer="L4",
                    reason="relevance_unjudged",
                    details={"detail": f"LLM ({cli}) returned unparseable JSON"},
                )
            _step_log(report, "fit_check", False, _elapsed(started, report),
                      f"LLM ({cli}) returned unparseable JSON; quarantined all {len(papers)}", print_progress)
            return []

        fit_report = apply_scores(slug, papers, payload, threshold=threshold)
        accepted_dois = {a.doi.lower(): a.score for a in fit_report.accepted if a.doi}
        accepted_titles = {
            a.title.strip().lower(): a.score
            for a in fit_report.accepted
            if a.title
        }
        rejected_dois = {a.doi.lower(): a.score for a in fit_report.rejected if a.doi}
        rejected_titles = {
            a.title.strip().lower(): a.score
            for a in fit_report.rejected
            if a.title
        }
        kept: list[dict] = []
        for paper in papers:
            doi_key = str(paper.get("doi", "") or "").lower()
            title_key = str(paper.get("title", "") or "").strip().lower()
            score = accepted_dois.get(doi_key, accepted_titles.get(title_key))
            if score is not None:
                provenance = dict(paper.get("provenance") or {})
                provenance["fit_score"] = score
                paper["provenance"] = provenance
                kept.append(paper)
                continue
            low_score = rejected_dois.get(doi_key, rejected_titles.get(title_key))
            quarantine_paper(
                cfg,
                paper,
                cluster_slug=slug,
                layer="L4",
                reason="low_relevance",
                details={"fit_score": low_score},
            )
        _step_log(report, "fit_check", True, _elapsed(started, report),
                  f"kept {len(kept)}/{len(papers)}; quarantined {len(papers) - len(kept)} "
                  f"(threshold={threshold}, cli={cli})",
                  print_progress)
        return kept
    except Exception as exc:
        for paper in papers:
            quarantine_paper(
                cfg,
                paper,
                cluster_slug=slug,
                layer="L4",
                reason="relevance_unjudged",
                details={"detail": f"fit_check error: {exc}"},
            )
        _step_log(report, "fit_check", False, _elapsed(started, report),
                  f"fit_check error: {exc}; quarantined all {len(papers)}", print_progress)
        return []


def _maybe_reparent_collection(zot, web, collection_key: str, slug: str, print_progress: bool) -> None:
    """Best-effort: nest a top-level Zotero collection under the configured parent.

    Called after ``_find_existing_collection_key_by_name`` finds an existing
    collection that was created before the parent-collection feature was added.
    Only acts if the collection's ``parentCollection`` is ``False`` (i.e. it is
    currently a top-level collection with no parent).  Never raises — any failure
    is silently ignored so the main ingest flow is not blocked.
    """
    try:
        from research_hub.config import get_config as _get_config
        from research_hub.zotero.client import ZoteroDualClient, ensure_parent_collection
        try:
            _cfg = _get_config()
            _parent_name = getattr(_cfg, "zotero_parent_collection", "research-hub")
        except Exception:
            _parent_name = "research-hub"
        if not _parent_name:
            return
        coll = web.collection(collection_key)
        if not isinstance(coll, dict):
            return
        data = coll.get("data", coll)
        current_parent = data.get("parentCollection")
        if current_parent is not False:
            return  # already nested (or unknown state) — nothing to do
        # Collection is top-level; reparent it under the configured parent.
        # Use the caller's client when it IS a ZoteroDualClient (which has
        # update_collection with parent_key= kwarg); fall back to creating a
        # fresh one for bare pyzotero clients (which also have update_collection
        # but with a different signature — so hasattr alone is ambiguous).
        dual = zot if isinstance(zot, ZoteroDualClient) else ZoteroDualClient()
        parent_key = ensure_parent_collection(dual, _parent_name)
        if parent_key:
            dual.update_collection(collection_key, parent_key=parent_key)
            if print_progress:
                print(
                    f"  [zotero.bind] reparented {collection_key} ({slug}) "
                    f"under '{_parent_name}' ({parent_key})"
                )
    except Exception:
        pass  # best-effort — never blocks ingest


def _ensure_zotero_collection(registry, cluster, slug: str, report: AutoReport, print_progress: bool) -> None:
    """Auto-create + bind a Zotero collection so `ingest` has a target.

    Best-effort: skips silently if Zotero is not configured (analyst persona,
    or RESEARCH_HUB_NO_ZOTERO=1). This keeps the lazy-mode promise that
    `auto "topic"` can run end-to-end without a manual `clusters bind`.

    v0.68.4: probes Zotero for an existing collection with this name before
    creating, to prevent accumulating duplicate empty collections.
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
        existing_key = _find_existing_collection_key_by_name(web, cluster.name)
        if existing_key:
            collision_slug = next(
                (
                    other.slug
                    for other in registry.list()
                    if other.slug != slug
                    and (other.zotero_collection_key or "").strip() == existing_key
                ),
                None,
            )
            if collision_slug:
                if print_progress:
                    print(
                        f"  [WARN] Zotero collection {existing_key} is already bound to "
                        f"{collision_slug}; creating a fresh collection for {slug} instead."
                    )
            else:
                cluster.zotero_collection_key = existing_key
                registry.save()
                # Reparent if this collection was created before the parent-
                # collection feature existed and is currently top-level.
                _maybe_reparent_collection(zot, web, existing_key, slug, print_progress)
                _step_log(report, "zotero.bind", True, 0.0,
                          f"reused existing collection {existing_key} for {slug}", print_progress)
                return
        from research_hub.config import get_config as _get_config
        from research_hub.zotero.client import ensure_parent_collection as _ensure_parent
        try:
            _cfg = _get_config()
            _parent_name = getattr(_cfg, "zotero_parent_collection", "research-hub")
        except Exception:
            _parent_name = "research-hub"
        # Resolve the dual-client instance for caching; web is already unwrapped above
        _dual = getattr(zot, "_dual_ref", None)
        if _dual is None:
            # zot was returned by get_client() which is the dual-client; build a
            # thin wrapper so ensure_parent_collection has a .web attribute
            from types import SimpleNamespace as _SN
            _dual = _SN(web=web)
        _parent_key: str | bool = _ensure_parent(_dual, _parent_name) if _parent_name else False
        result = web.create_collections(
            [{"name": cluster.name, "parentCollection": _parent_key if _parent_key else False}]
        )
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


def _resolve_search_options(
    *,
    field: Optional[str] = None,
    peer_reviewed: bool = False,
) -> tuple[tuple[str, ...], tuple[str, ...], float]:
    from research_hub.search.fallback import FIELD_PRESETS, apply_peer_reviewed
    backends = tuple(
        FIELD_PRESETS[field] if field else ("arxiv", "semantic-scholar", "openalex", "crossref")
    )
    exclude_types: tuple[str, ...] = ()
    min_confidence = 0.0
    if peer_reviewed:
        backends, exclude_types, min_confidence = apply_peer_reviewed(
            backends,
            exclude_types,
            min_confidence,
        )
    return backends, exclude_types, min_confidence


def _run_search(
    topic: str,
    *,
    max_papers: int,
    cluster_slug: str,
    field: Optional[str] = None,
    peer_reviewed: bool = False,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[dict]:
    """Run arxiv + semantic_scholar search, return papers_input dicts."""
    from research_hub.search import search_papers


    # v0.49.4: search arxiv + semantic-scholar + openalex + crossref so the
    # pipeline survives semantic-scholar rate-limiting and one-backend gaps.
    backends, exclude_types, min_confidence = _resolve_search_options(
        field=field,
        peer_reviewed=peer_reviewed,
    )
    results = search_papers(
        topic,
        backends=backends,
        exclude_types=exclude_types,
        min_confidence=min_confidence,
        limit=max_papers,
        year_from=year_from,
        year_to=year_to,
    )
    return _to_papers_input([asdict(r) for r in results], cluster_slug)
