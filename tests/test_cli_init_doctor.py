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
            "--persona",
            "analyst",
        ]
    )
    assert args.command == "init"
    assert args.vault == "kb"
    assert args.zotero_key == "secret"
    assert args.zotero_library_id == "123"
    assert args.non_interactive is True
    assert args.persona == "analyst"


def test_build_parser_accepts_field_init_and_examples_commands():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(
        [
            "init",
            "--field",
            "cs",
            "--cluster",
            "llm-agents",
            "--name",
            "LLM Agents",
            "--query",
            "LLM agent benchmark",
            "--definition",
            "Cluster definition",
            "--non-interactive",
        ]
    )
    assert args.field == "cs"
    assert args.cluster == "llm-agents"
    assert args.name == "LLM Agents"
    assert args.query == "LLM agent benchmark"
    assert args.definition == "Cluster definition"

    args = build_parser().parse_args(["examples", "show", "cs_swe"])
    assert args.command == "examples"
    assert args.examples_command == "show"
    assert args.name == "cs_swe"


def test_build_parser_accepts_add_command():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["add", "10.1000/example", "--cluster", "topic", "--no-zotero"])
    assert args.command == "add"
    assert args.identifier == "10.1000/example"
    assert args.cluster == "topic"
    assert args.no_zotero is True


def test_build_parser_accepts_doctor_command():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["doctor"])
    assert args.command == "doctor"


def test_build_parser_accepts_dedup_commands():
    from research_hub.cli import build_parser

    args = build_parser().parse_args(["dedup", "invalidate", "--doi", "10.1/x"])
    assert args.command == "dedup"
    assert args.dedup_command == "invalidate"
    assert args.doi == "10.1/x"

    args = build_parser().parse_args(["dedup", "rebuild", "--obsidian-only"])
    assert args.command == "dedup"
    assert args.dedup_command == "rebuild"
    assert args.obsidian_only is True


def test_main_routes_init_and_doctor(monkeypatch):
    from research_hub import cli

    calls: list[tuple[str, tuple, dict]] = []

    def fake_run_init(
        *,
        vault_root=None,
        zotero_key=None,
        zotero_library_id=None,
        non_interactive=False,
        persona="researcher",
        **_kwargs,  # tolerate future additions like v0.64's no_browser
    ):
        calls.append(
            (
                "init",
                tuple(),
                {
                    "vault_root": vault_root,
                    "zotero_key": zotero_key,
                    "zotero_library_id": zotero_library_id,
                    "non_interactive": non_interactive,
                    "persona": persona,
                },
            )
        )
        return 0

    def fake_run_doctor(*, strict=False, **_kwargs):
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
                "--persona",
                "analyst",
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
                "persona": "analyst",
            },
        ),
        ("doctor.run", tuple(), {}),
        ("doctor.print", (["result"],), {}),
    ]


def test_main_routes_field_init_to_onboarding(monkeypatch):
    from research_hub import cli

    calls = []

    class Result:
        cluster_slug = "field-cluster"
        candidate_count = 6
        next_steps = ["1. step"]

    def fake_wizard(cfg, **kwargs):
        calls.append((cfg, kwargs))
        return Result()

    monkeypatch.setattr("research_hub.cli.get_config", lambda: "cfg")
    monkeypatch.setattr("research_hub.onboarding.run_field_wizard", fake_wizard)

    rc = cli.main(
        [
            "init",
            "--field",
            "bio",
            "--cluster",
            "field-cluster",
            "--name",
            "Field Cluster",
            "--query",
            "protein folding",
            "--definition",
            "desc",
            "--non-interactive",
        ]
    )

    assert rc == 0
    assert calls == [
        (
            "cfg",
            {
                "field": "bio",
                "cluster_slug": "field-cluster",
                "cluster_name": "Field Cluster",
                "query": "protein folding",
                "definition": "desc",
                "non_interactive": True,
            },
        )
    ]
