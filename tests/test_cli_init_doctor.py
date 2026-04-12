"""Tests for init and doctor CLI wiring."""

from __future__ import annotations


def test_build_parser_accepts_init_flags():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(
        [
            "init",
            "--vault",
            "kb",
            "--zotero-key",
            "secret",
            "--zotero-library-id",
            "123",
            "--non-interactive",
        ]
    )
    assert args.command == "init"
    assert args.vault == "kb"
    assert args.zotero_key == "secret"
    assert args.zotero_library_id == "123"
    assert args.non_interactive is True


def test_build_parser_accepts_doctor_command():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["doctor"])
    assert args.command == "doctor"


def test_main_routes_init_and_doctor(monkeypatch):
    from research_hub import cli

    calls: list[tuple[str, tuple, dict]] = []

    def fake_run_init(*, vault_root=None, zotero_key=None, zotero_library_id=None, non_interactive=False):
        calls.append(
            (
                "init",
                tuple(),
                {
                    "vault_root": vault_root,
                    "zotero_key": zotero_key,
                    "zotero_library_id": zotero_library_id,
                    "non_interactive": non_interactive,
                },
            )
        )
        return 0

    def fake_run_doctor():
        calls.append(("doctor.run", tuple(), {}))
        return ["result"]

    def fake_print_doctor_report(results):
        calls.append(("doctor.print", (results,), {}))
        return 0

    monkeypatch.setattr("research_hub.init_wizard.run_init", fake_run_init)
    monkeypatch.setattr("research_hub.doctor.run_doctor", fake_run_doctor)
    monkeypatch.setattr("research_hub.doctor.print_doctor_report", fake_print_doctor_report)

    assert (
        cli.main(
            [
                "init",
                "--vault",
                "kb",
                "--zotero-key",
                "secret",
                "--zotero-library-id",
                "123",
                "--non-interactive",
            ]
        )
        == 0
    )
    assert cli.main(["doctor"]) == 0
    assert calls == [
        (
            "init",
            tuple(),
            {
                "vault_root": "kb",
                "zotero_key": "secret",
                "zotero_library_id": "123",
                "non_interactive": True,
            },
        ),
        ("doctor.run", tuple(), {}),
        ("doctor.print", (["result"],), {}),
    ]
