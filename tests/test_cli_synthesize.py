"""Tests for CLI synthesize command wiring."""

from __future__ import annotations

from pathlib import Path


def test_build_parser_accepts_synthesize_flags():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["synthesize", "--cluster", "alpha", "--graph-colors"])
    assert args.command == "synthesize"
    assert args.cluster == "alpha"
    assert args.graph_colors is True


def test_main_routes_synthesize_command(monkeypatch, tmp_path: Path):
    from research_hub import cli

    calls: list[tuple[str | None, bool]] = []

    def fake_synthesize(cluster: str | None, graph_colors: bool) -> int:
        calls.append((cluster, graph_colors))
        return 0

    monkeypatch.setattr(cli, "_synthesize", fake_synthesize)
    result = cli.main(["synthesize", "--cluster", "alpha", "--graph-colors"])
    assert result == 0
    assert calls == [("alpha", True)]
