"""Summarization and memory CLI handlers for Research Hub."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from research_hub.config import get_config
from research_hub.cli_common import _emit_cli_json


def _cmd_crystal(args, cfg, *, emit_json: bool = False) -> int:
    from research_hub import crystal

    if args.crystal_command == "emit":
        question_slugs = [item.strip() for item in args.questions.split(",") if item.strip()] if args.questions else None
        prompt = crystal.emit_crystal_prompt(cfg, args.cluster, question_slugs=question_slugs)
        if args.out:
            Path(args.out).write_text(prompt, encoding="utf-8")
            if emit_json:
                _emit_cli_json(
                    "crystal emit",
                    0,
                    {
                        "cluster_slug": args.cluster,
                        "question_slugs": question_slugs or [],
                        "out_path": args.out,
                        "prompt_chars": len(prompt),
                    },
                )
                return 0
            print(f"wrote {args.out}")
        else:
            if emit_json:
                _emit_cli_json(
                    "crystal emit",
                    0,
                    {
                        "cluster_slug": args.cluster,
                        "question_slugs": question_slugs or [],
                        "out_path": None,
                        "prompt": prompt,
                        "prompt_chars": len(prompt),
                    },
                )
                return 0
            print(prompt)
        return 0
    if args.crystal_command == "apply":
        scored = json.loads(Path(args.scored).read_text(encoding="utf-8"))
        result = crystal.apply_crystals(cfg, args.cluster, scored)
        rc = 0 if not result.errors else 1
        if emit_json:
            _emit_cli_json("crystal apply", rc, result)
            return rc
        print(f"written: {len(result.written)}, replaced: {len(result.replaced)}, skipped: {len(result.skipped)}")
        if result.errors:
            for error in result.errors:
                print(f"  ERROR: {error}", file=sys.stderr)
            return 1
        return 0
    if args.crystal_command == "list":
        crystals = crystal.list_crystals(cfg, args.cluster)
        if not crystals:
            print("(no crystals yet; generate via `research-hub crystal emit`)")
            return 0
        for item in crystals:
            print(f"{item.question_slug:25s}  {item.tldr[:80]}")
        return 0
    if args.crystal_command == "read":
        item = crystal.read_crystal(cfg, args.cluster, args.slug)
        if item is None:
            print(f"crystal not found: {args.slug}", file=sys.stderr)
            return 1
        print(item.tldr if args.level == "tldr" else item.full if args.level == "full" else item.gist)
        return 0
    if args.crystal_command == "check":
        staleness = crystal.check_staleness(cfg, args.cluster)
        if not staleness:
            print("(no crystals to check)")
            return 0
        for slug, item in staleness.items():
            marker = "STALE" if item.stale else "fresh"
            print(f"{slug:25s}  {marker}  delta={item.delta_ratio:.0%}  +{len(item.added_papers)}/-{len(item.removed_papers)}")
        return 0
    raise ValueError(f"unknown crystal command: {args.crystal_command}")

def _cmd_summarize(args, cfg, *, emit_json: bool = False) -> int:
    from research_hub import summarize as summarize_mod

    report = summarize_mod.summarize_cluster(
        cfg,
        args.cluster,
        llm_cli=args.llm_cli,
        apply=args.apply,
        write_zotero=not args.no_zotero,
        write_obsidian=not args.no_obsidian,
    )
    if not report.ok:
        if emit_json:
            _emit_cli_json("summarize", 1, report)
            return 1
        print(f"summarize failed: {report.error}", file=sys.stderr)
        return 1
    if report.prompt_path:
        if emit_json:
            _emit_cli_json("summarize", 0, report)
            return 0
        print(f"no LLM CLI on PATH; prompt saved to {report.prompt_path}")
        print("pipe it through your LLM CLI and re-run with --apply")
        return 0
    if not args.apply:
        if emit_json:
            _emit_cli_json("summarize", 0, report)
            return 0
        print(f"cli used: {report.cli_used}")
        print("(dry-run; pass --apply to write to Obsidian + Zotero)")
        return 0
    apply_result = report.apply_result
    if apply_result is None:
        if emit_json:
            _emit_cli_json("summarize", 1, report)
            return 1
        print("no apply result returned")
        return 1
    rc = 0 if not apply_result.errors else 1
    if emit_json:
        _emit_cli_json("summarize", rc, report)
        return rc
    print(f"cli used: {report.cli_used}")
    print(
        f"applied: {len(apply_result.applied)}  "
        f"skipped: {len(apply_result.skipped)}  "
        f"errors: {len(apply_result.errors)}"
    )
    print(f"obsidian writes: {apply_result.obsidian_writes}, zotero writes: {apply_result.zotero_writes}")
    for skip in apply_result.skipped:
        print(f"  SKIP {skip}")
    for err in apply_result.errors:
        print(f"  ERROR {err}", file=sys.stderr)
    return rc

def _vault_summarize_status_migrate(
    cluster_slug: str | None,
    dry_run: bool,
    *,
    emit_json: bool = False,
) -> int:
    from collections import Counter

    from research_hub.vault.summarize_migrate import migrate_existing_to_pending_status

    cfg = get_config()
    results = migrate_existing_to_pending_status(
        cfg.root,
        cluster_slug_filter=cluster_slug,
        dry_run=dry_run,
    )
    counts = Counter(action for _path, action in results)
    if emit_json:
        _emit_cli_json(
            "vault summarize-status-migrate",
            0,
            {
                "cluster_filter": cluster_slug,
                "dry_run": dry_run,
                "counts": dict(counts),
                "results": [{"path": path, "action": action} for path, action in results],
            },
        )
        return 0
    mode = "would flip" if dry_run else "flipped"
    print(f"{counts.get('pending', 0):4d} notes {mode} pending")
    print(f"{counts.get('done', 0):4d} notes {mode} done")
    print(f"{counts.get('failed_no_abstract', 0):4d} notes {mode} failed_no_abstract")
    print(f"{counts.get('already_set', 0):4d} already_set")
    skipped = sum(count for action, count in counts.items() if action.startswith("skipped_"))
    if skipped:
        print(f"{skipped:4d} skipped")
    if dry_run:
        print("")
        print("Preview only. Re-run with --apply to write summarize_status.")
    return 0

def _paper_summarize_pending(args) -> int:
    from collections import Counter

    from research_hub.paper_summarize import summarize_pending

    if not args.pending:
        print("Specify --pending to run the summarize queue.", file=sys.stderr)
        return 2
    cfg = get_config()
    try:
        results = summarize_pending(
            cfg,
            cluster_slug_filter=args.cluster,
            backend=args.cli,
            max_papers=args.max_papers,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"paper summarize failed: {exc}", file=sys.stderr)
        return 1

    counts = Counter(result.action for result in results)
    print(
        f"processed: {len(results)}  "
        f"done: {counts.get('done', 0)}  "
        f"failed_no_abstract: {counts.get('failed_no_abstract', 0)}  "
        f"errors: {counts.get('error', 0)}"
    )
    if args.dry_run:
        print(
            f"dry-run: would_summarize={counts.get('would_summarize', 0)}  "
            f"would_fail_no_abstract={counts.get('would_fail_no_abstract', 0)}"
        )
    for result in results:
        if result.error:
            print(f"  ERROR {result.path}: {result.error}", file=sys.stderr)
    return 0 if not counts.get("error", 0) else 1

def _cmd_memory(args, cfg) -> int:
    from research_hub.memory import (
        apply_memory,
        emit_memory_prompt,
        list_claims,
        list_entities,
        list_methods,
        read_memory,
    )

    if args.memory_command == "emit":
        print(emit_memory_prompt(cfg, args.cluster))
        return 0
    if args.memory_command == "apply":
        scored = json.loads(Path(args.scored).read_text(encoding="utf-8"))
        result = apply_memory(cfg, args.cluster, scored)
        print(f"entities={result.entity_count} claims={result.claim_count} methods={result.method_count}")
        print(f"written: {result.written_path}")
        for error in result.errors:
            print(f"  ! {error}", file=sys.stderr)
        return 0
    if args.memory_command == "list":
        entities = list_entities(cfg, args.cluster)
        claims = list_claims(cfg, args.cluster)
        methods = list_methods(cfg, args.cluster)
        if args.kind == "entities":
            for item in entities:
                print(f"{item.slug}\t{item.type}\t{item.name}")
            return 0
        if args.kind == "claims":
            for item in claims:
                print(f"[{item.confidence}] {item.slug}: {item.text[:80]}")
            return 0
        if args.kind == "methods":
            for item in methods:
                print(f"{item.slug}\t{item.family}\t{item.name}")
            return 0
        print("[entities]")
        for item in entities:
            print(f"{item.slug}\t{item.type}\t{item.name}")
        print()
        print("[claims]")
        for item in claims:
            print(f"[{item.confidence}] {item.slug}: {item.text[:80]}")
        print()
        print("[methods]")
        for item in methods:
            print(f"{item.slug}\t{item.family}\t{item.name}")
        return 0
    if args.memory_command == "read":
        memory = read_memory(cfg, args.cluster)
        if memory is None:
            print(f"No memory found for cluster: {args.cluster}", file=sys.stderr)
            return 1
        print(json.dumps(memory.to_dict(), indent=2, ensure_ascii=False))
        return 0
    raise ValueError(f"unknown memory command: {args.memory_command}")
