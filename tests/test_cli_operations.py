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
