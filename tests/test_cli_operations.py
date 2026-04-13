from __future__ import annotations

import pytest

from research_hub.cli import build_parser


@pytest.mark.parametrize(
    "argv",
    [
        ["remove", "--help"],
        ["mark", "--help"],
        ["move", "--help"],
        ["find", "--help"],
        ["dashboard", "--help"],
        ["quote", "--help"],
        ["references", "--help"],
        ["cited-by", "--help"],
        ["clusters", "rename", "--help"],
        ["clusters", "merge", "--help"],
    ],
)
def test_cli_help_commands(argv, capsys):
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(argv)

    assert exc.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_cite_parser_supports_inline_markdown_and_style():
    args = build_parser().parse_args(["cite", "10.1000/example", "--inline", "--style", "chicago"])
    assert args.inline is True
    assert args.markdown is False
    assert args.style == "chicago"


def test_quote_parser_supports_list_and_remove_shapes():
    parser = build_parser()
    list_args = parser.parse_args(["quote", "list", "--cluster", "agents"])
    remove_args = parser.parse_args(["quote", "remove", "paper-one", "--at", "2026-04-12T12:00:00Z"])
    add_args = parser.parse_args(["quote", "paper-one", "--page", "12", "--text", "hello"])
    assert list_args.quote_target == ["list"]
    assert remove_args.quote_target == ["remove", "paper-one"]
    assert add_args.quote_target == ["paper-one"]
