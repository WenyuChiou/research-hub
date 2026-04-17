"""Tests for NotebookLM CLI parser and dispatch."""

from __future__ import annotations


def test_build_parser_accepts_notebooklm_upload_and_generate_flags():
    from research_hub.cli import build_parser

    upload_args = build_parser().parse_args(["notebooklm", "upload", "--cluster", "alpha", "--dry-run", "--visible"])
    assert upload_args.command == "notebooklm"
    assert upload_args.notebooklm_command == "upload"
    assert upload_args.cluster == "alpha"
    assert upload_args.dry_run is True
    assert upload_args.headless is False

    generate_args = build_parser().parse_args(["notebooklm", "generate", "--cluster", "alpha", "--type", "all", "--visible"])
    assert generate_args.notebooklm_command == "generate"
    assert generate_args.type == "all"
    assert generate_args.headless is False


def test_main_routes_notebooklm_upload_and_generate(monkeypatch, mock_require_config):
    from research_hub import cli

    calls = []

    monkeypatch.setattr(cli, "_nlm_upload", lambda cluster, dry_run, headless, create_if_missing: calls.append(("upload", cluster, dry_run, headless, create_if_missing)) or 0)
    monkeypatch.setattr(cli, "_nlm_generate", lambda cluster, artifact_type, headless: calls.append(("generate", cluster, artifact_type, headless)) or 0)

    assert cli.main(["notebooklm", "upload", "--cluster", "alpha", "--dry-run"]) == 0
    assert cli.main(["notebooklm", "generate", "--cluster", "alpha", "--type", "mind-map"]) == 0
    assert calls == [
        ("upload", "alpha", True, False, True),
        ("generate", "alpha", "mind-map", False),
    ]
