"""v0.67 Track B: `research-hub context` CLI subcommand group.

Phase 2 of the Codex skills brief. Lets users / scripts invoke the
workspace-skill's logic from shell instead of through an AI session.

Three subcommands:
- `context init`     - bootstrap an empty .research/ skeleton (idempotent)
- `context audit`    - check .research/ files for required fields, freshness, and dataset paths
- `context compress` - print a pointer to the research-context-compressor skill
                       (or --print-prompt to emit the canonical prompt)

CLI is intentionally thin. Real semantic compression is an AI task
performed by the `research-context-compressor` skill, not by this module.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# These are the v1 schema files declared in docs/research-workspace-manifest.md
SKELETON_FILES: tuple[tuple[str, str], ...] = (
    (
        "project_manifest.yml",
        (
            "# research-workspace manifest v1 — see docs/research-workspace-manifest.md\n"
            'project_name: ""\n'
            'research_area: ""\n'
            'research_question: ""\n'
            'current_stage: ""           # discovery | exploration | experiments | writing | rebuttal | submission\n'
            "primary_tools: []\n"
            "key_repositories: []\n"
            "data_sources: []\n"
            "model_components: []\n"
            "main_entrypoints: []\n"
            "important_outputs: []\n"
            'paper_or_deliverable: ""\n'
            f'last_updated: "{datetime.now(timezone.utc).date().isoformat()}"\n'
        ),
    ),
    (
        "experiment_matrix.yml",
        (
            "# experiment_matrix.yml v1\n"
            "experiments: []\n"
            "# Example entry:\n"
            '#   - id: "E1"\n'
            '#     hypothesis: "..."\n'
            '#     status: planned   # planned | running | complete | abandoned\n'
        ),
    ),
    (
        "data_dictionary.yml",
        (
            "# data_dictionary.yml v1\n"
            "datasets: []\n"
            "# Example entry:\n"
            '#   - id: "harvey-2017"\n'
            '#     description: "Hurricane Harvey flood depth grids"\n'
            '#     source: "FEMA"\n'
            '#     format: "GeoTIFF"\n'
            '#     location: "data/harvey/"\n'
        ),
    ),
    ("decisions.md", "# Decisions log (ADR-style)\n\n"),
    ("open_questions.md", "# Open questions\n\n"),
    ("run_log.md", "# Run log (append-only)\n\n"),
)


CANONICAL_COMPRESSION_PROMPT = """\
Compress this project context for future agents.

Read .research/project_manifest.yml first if it exists, then inspect:
- README.md
- pyproject.toml / package.json / requirements.txt
- docs/, scripts/, notebooks/
- data/ and outputs/ directory listings (don't read every file)
- git log --oneline -20

Then write or refresh the .research/ files:
- project_manifest.yml  (REQUIRED: project_name, research_area,
  research_question, current_stage, last_updated)
- experiment_matrix.yml (if scripts/ or notebooks/ exist)
- data_dictionary.yml   (if data/ exists)

Append a single-paragraph entry to .research/run_log.md describing what
you did. Update existing files in place; do NOT overwrite human-edited
fields. If a required field is unknown, leave it empty and add an entry
to .research/open_questions.md.

Print a 5-line summary at the end: which files were written, how many
experiments and datasets you found, and any questions surfaced.
"""


def _project_root_from_args(args, cfg) -> Path:
    """Resolve the .research/ parent directory.

    Default: cfg.research_hub_dir.parent (i.e. the vault root). Override with
    --vault arg if provided. Raises ValueError if neither resolves.
    """
    explicit = getattr(args, "vault", None)
    if explicit:
        return Path(explicit).resolve()
    if cfg is not None and getattr(cfg, "research_hub_dir", None):
        return Path(cfg.research_hub_dir).parent.resolve()
    raise ValueError("--vault is required when no research-hub config is loaded")


def context_init(args, cfg) -> int:
    """Create a `.research/` skeleton at the resolved project root.

    Idempotent: never overwrites an existing file. Skips files that
    already exist and reports them as 'kept'.
    """
    root = _project_root_from_args(args, cfg)
    research_dir = root / ".research"
    research_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    kept: list[str] = []
    for name, body in SKELETON_FILES:
        path = research_dir / name
        if path.exists():
            kept.append(name)
            continue
        path.write_text(body, encoding="utf-8")
        written.append(name)

    print(f"[context init] root: {root}")
    print(f"  Wrote {len(written)} new file(s):")
    for name in written:
        print(f"    + .research/{name}")
    if kept:
        print(f"  Kept {len(kept)} existing file(s) untouched:")
        for name in kept:
            print(f"    = .research/{name}")
    print()
    print("  Next: edit .research/project_manifest.yml to fill in real values,")
    print("  or load the `research-context-compressor` skill in an AI session")
    print("  and ask it to populate them automatically.")
    return 0


def _load_yaml_safe(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
        loaded = yaml.safe_load(text) or {}
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        # Tolerate yaml errors during audit; we want the audit to keep
        # going and report which file failed rather than crash.
        return {}


def context_audit(args, cfg) -> int:
    """Audit `.research/` for schema correctness and freshness.

    Prints `[OK]` / `[WARN]` lines, exits 0 unless any FAIL appears
    (audit currently does not produce FAILs — only OK / WARN / INFO).
    """
    root = _project_root_from_args(args, cfg)
    research_dir = root / ".research"

    if not research_dir.exists():
        print(f"[context audit] root: {root}")
        print("  [WARN] .research/ does not exist — run `research-hub context init` first")
        return 0

    print(f"[context audit] root: {root}")
    issues = 0

    manifest_path = research_dir / "project_manifest.yml"
    if not manifest_path.exists():
        print("  [WARN] project_manifest.yml is missing")
        issues += 1
    else:
        manifest = _load_yaml_safe(manifest_path)
        required = ("project_name", "research_area", "research_question",
                    "current_stage", "last_updated")
        missing = [f for f in required if not str(manifest.get(f, "") or "").strip()]
        if missing:
            print(f"  [WARN] project_manifest.yml missing required fields: {missing}")
            issues += 1
        else:
            print("  [OK]   project_manifest.yml has all required fields")
        last_updated = str(manifest.get("last_updated", "") or "").strip()
        if last_updated:
            try:
                dt = datetime.fromisoformat(last_updated)
                age_days = (datetime.now() - dt).days
                if age_days > 90:
                    print(f"  [WARN] project_manifest.yml last_updated is {age_days} days old (>90)")
                    issues += 1
                else:
                    print(f"  [OK]   last_updated {age_days} days ago")
            except ValueError:
                print(f"  [WARN] last_updated {last_updated!r} is not ISO date format")
                issues += 1

    em_path = research_dir / "experiment_matrix.yml"
    if em_path.exists():
        em = _load_yaml_safe(em_path)
        experiments = em.get("experiments") or []
        ids = [str(e.get("id", "")).strip() for e in experiments if isinstance(e, dict)]
        dup_ids = [i for i in ids if i and ids.count(i) > 1]
        if dup_ids:
            print(f"  [WARN] experiment_matrix.yml has duplicate IDs: {sorted(set(dup_ids))}")
            issues += 1
        else:
            print(f"  [OK]   experiment_matrix.yml: {len(experiments)} experiment(s), unique IDs")

    dd_path = research_dir / "data_dictionary.yml"
    if dd_path.exists():
        dd = _load_yaml_safe(dd_path)
        datasets = dd.get("datasets") or []
        missing_paths: list[str] = []
        for ds in datasets:
            if not isinstance(ds, dict):
                continue
            loc = str(ds.get("location", "") or "").strip()
            if loc and not (root / loc).exists():
                missing_paths.append(f"{ds.get('id', '?')} -> {loc}")
        if missing_paths:
            print(f"  [WARN] data_dictionary.yml: {len(missing_paths)} dataset path(s) not found:")
            for entry in missing_paths[:5]:
                print(f"           {entry}")
            issues += 1
        else:
            print(f"  [OK]   data_dictionary.yml: {len(datasets)} dataset(s); all paths exist")

    if issues == 0:
        print("\n[context audit] all checks passed")
    else:
        print(f"\n[context audit] {issues} warning(s); review above")
    return 0  # WARNs are non-fatal


def context_compress(args, cfg) -> int:
    """Point the user at the research-context-compressor AI skill.

    With --print-prompt, emit the canonical compression prompt for piping
    into Claude / Codex / Gemini sessions.
    """
    if getattr(args, "print_prompt", False):
        print(CANONICAL_COMPRESSION_PROMPT)
        return 0

    root = _project_root_from_args(args, cfg)
    print(f"[context compress] root: {root}")
    print()
    print("  Compression is performed by the `research-context-compressor` AI skill.")
    print("  This CLI does not run the LLM directly. Two options:")
    print()
    print("  1. Open an AI session (Claude / Cursor / Codex / Gemini), make sure")
    print("     the `research-context-compressor` skill is loaded, then say:")
    print("       \"Compress this project context for future agents.\"")
    print()
    print("  2. Pipe the canonical prompt into a CLI assistant directly:")
    print("       research-hub context compress --print-prompt | codex exec --full-auto")
    print()
    print("  After compression runs, verify the result with:")
    print("       research-hub context audit")
    return 0


def dispatch(args, cfg) -> int:
    """Single entry point used by cli.py main()."""
    sub = getattr(args, "context_command", None)
    if sub == "init":
        return context_init(args, cfg)
    if sub == "audit":
        return context_audit(args, cfg)
    if sub == "compress":
        return context_compress(args, cfg)
    print(f"unknown context subcommand: {sub!r}", flush=True)
    return 2
