"""v0.67 Track B: research-hub context init/audit/compress CLI subcommand."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


def _args(**kw):
    """Build an argparse.Namespace-like object for context_cli dispatch."""
    return SimpleNamespace(**kw)


def test_context_init_creates_skeleton_files(tmp_path):
    from research_hub.context_cli import context_init

    rc = context_init(_args(vault=str(tmp_path)), cfg=None)

    assert rc == 0
    research = tmp_path / ".research"
    for name in ("project_manifest.yml", "experiment_matrix.yml",
                 "data_dictionary.yml", "decisions.md", "open_questions.md",
                 "run_log.md"):
        assert (research / name).exists(), f"missing {name}"


def test_context_init_idempotent(tmp_path):
    from research_hub.context_cli import context_init

    context_init(_args(vault=str(tmp_path)), cfg=None)
    target = tmp_path / ".research" / "project_manifest.yml"
    first_mtime = target.stat().st_mtime
    first_text = target.read_text(encoding="utf-8")

    # Second call: must not modify
    context_init(_args(vault=str(tmp_path)), cfg=None)

    assert target.stat().st_mtime == first_mtime
    assert target.read_text(encoding="utf-8") == first_text


def test_context_init_skips_existing_files(tmp_path):
    """Pre-create one file with custom content; init must NOT overwrite."""
    from research_hub.context_cli import context_init

    research = tmp_path / ".research"
    research.mkdir()
    custom = research / "decisions.md"
    custom.write_text("# DO NOT OVERWRITE\nMy custom decision log\n", encoding="utf-8")

    context_init(_args(vault=str(tmp_path)), cfg=None)

    assert "DO NOT OVERWRITE" in custom.read_text(encoding="utf-8")


def test_context_audit_passes_clean_project(tmp_path, capsys):
    """Fully populated .research/ should yield 0 warnings."""
    from research_hub.context_cli import context_init, context_audit

    context_init(_args(vault=str(tmp_path)), cfg=None)
    # Fill in required fields
    manifest = tmp_path / ".research" / "project_manifest.yml"
    manifest.write_text(
        'project_name: "Test"\n'
        'research_area: "civil eng"\n'
        'research_question: "Does X?"\n'
        'current_stage: "exploration"\n'
        f'last_updated: "{datetime.now().date().isoformat()}"\n',
        encoding="utf-8",
    )
    capsys.readouterr()  # clear init output

    rc = context_audit(_args(vault=str(tmp_path)), cfg=None)
    out = capsys.readouterr().out

    assert rc == 0
    assert "all checks passed" in out
    assert "[WARN]" not in out


def test_context_audit_flags_missing_required_fields(tmp_path, capsys):
    from research_hub.context_cli import context_init, context_audit

    context_init(_args(vault=str(tmp_path)), cfg=None)
    capsys.readouterr()

    context_audit(_args(vault=str(tmp_path)), cfg=None)
    out = capsys.readouterr().out

    assert "[WARN]" in out
    assert "missing required fields" in out


def test_context_audit_flags_stale_last_updated(tmp_path, capsys):
    from research_hub.context_cli import context_init, context_audit

    context_init(_args(vault=str(tmp_path)), cfg=None)
    manifest = tmp_path / ".research" / "project_manifest.yml"
    stale_date = (datetime.now() - timedelta(days=120)).date().isoformat()
    manifest.write_text(
        'project_name: "Test"\nresearch_area: "x"\nresearch_question: "?"\n'
        f'current_stage: "x"\nlast_updated: "{stale_date}"\n',
        encoding="utf-8",
    )
    capsys.readouterr()

    context_audit(_args(vault=str(tmp_path)), cfg=None)
    out = capsys.readouterr().out

    assert "120 days old" in out or "days old" in out
    assert "[WARN]" in out


def test_context_audit_flags_dataset_path_not_found(tmp_path, capsys):
    from research_hub.context_cli import context_init, context_audit

    context_init(_args(vault=str(tmp_path)), cfg=None)
    dd = tmp_path / ".research" / "data_dictionary.yml"
    dd.write_text(
        'datasets:\n  - id: "ghost"\n    description: "missing"\n    location: "data/ghost/"\n',
        encoding="utf-8",
    )
    capsys.readouterr()

    context_audit(_args(vault=str(tmp_path)), cfg=None)
    out = capsys.readouterr().out

    assert "dataset path(s) not found" in out
    assert "ghost" in out


def test_context_audit_returns_zero_on_warn_only(tmp_path):
    """WARNs are non-fatal; only FAIL would return non-zero."""
    from research_hub.context_cli import context_init, context_audit

    context_init(_args(vault=str(tmp_path)), cfg=None)
    rc = context_audit(_args(vault=str(tmp_path)), cfg=None)
    assert rc == 0


def test_context_compress_prints_canonical_prompt(capsys):
    from research_hub.context_cli import context_compress

    rc = context_compress(_args(vault=".", print_prompt=True), cfg=None)
    out = capsys.readouterr().out

    assert rc == 0
    assert ".research/project_manifest.yml" in out
    assert "experiment_matrix.yml" in out
    assert "data_dictionary.yml" in out


def test_context_compress_default_points_at_skill(tmp_path, capsys):
    from research_hub.context_cli import context_compress

    rc = context_compress(_args(vault=str(tmp_path), print_prompt=False), cfg=None)
    out = capsys.readouterr().out

    assert rc == 0
    assert "research-context-compressor" in out
    assert "AI skill" in out
