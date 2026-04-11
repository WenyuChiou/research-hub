"""Tests for CLI status and migrate-yaml wiring."""

from __future__ import annotations


def test_build_parser_accepts_status_flags():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["status", "--cluster", "alpha"])
    assert args.command == "status"
    assert args.cluster == "alpha"


def test_build_parser_accepts_migrate_yaml_flags():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(
        ["migrate-yaml", "--assign-cluster", "alpha", "--folder", "survey", "--force", "--dry-run"]
    )
    assert args.command == "migrate-yaml"
    assert args.assign_cluster == "alpha"
    assert args.folder == "survey"
    assert args.force is True
    assert args.dry_run is True


def test_main_routes_status_and_migrate(monkeypatch):
    from research_hub import cli

    calls: list[tuple[str, tuple, dict]] = []

    def fake_status(*, cluster=None):
        calls.append(("status", tuple(), {"cluster": cluster}))
        return 0

    def fake_migrate(*, assign_cluster=None, folder=None, force=False, dry_run=False):
        calls.append(
            (
                "migrate-yaml",
                tuple(),
                {
                    "assign_cluster": assign_cluster,
                    "folder": folder,
                    "force": force,
                    "dry_run": dry_run,
                },
            )
        )
        return 0

    monkeypatch.setattr(cli, "_status", fake_status)
    monkeypatch.setattr(cli, "_migrate_yaml", fake_migrate)

    assert cli.main(["status", "--cluster", "alpha"]) == 0
    assert cli.main(["migrate-yaml", "--assign-cluster", "alpha", "--folder", "survey", "--force"]) == 0
    assert calls == [
        ("status", tuple(), {"cluster": "alpha"}),
        (
            "migrate-yaml",
            tuple(),
            {
                "assign_cluster": "alpha",
                "folder": "survey",
                "force": True,
                "dry_run": False,
            },
        ),
    ]
