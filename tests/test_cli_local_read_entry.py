"""Local readers retain dispatch/audit semantics without importing providers."""

from contextlib import contextmanager
import builtins
from pathlib import Path
import sys
import re
from types import ModuleType, SimpleNamespace

import pytest

from research_hub import cli_entry


@pytest.mark.parametrize("operation", ["show", "list"])
def test_local_read_reuses_workspace_parser_dispatch_and_audit(monkeypatch, operation):
    from research_hub.workspace import cli as workspace_cli
    from research_hub import audit

    calls, context = [], SimpleNamespace(exit_code=None)
    original_import = builtins.__import__

    def restricted_import(name, *args, **kwargs):
        assert name != "research_hub.cli", "Local read imported provider CLI"
        return original_import(name, *args, **kwargs)

    @contextmanager
    def observed_audit(directory, argv):
        calls.append((directory, list(argv)))
        yield context

    def dispatch(args):
        assert args.command == "project" and args.workspace_operation == operation
        assert args.root == "synthetic-unused" and args.json
        return 0

    monkeypatch.setattr(builtins, "__import__", restricted_import)
    monkeypatch.setattr(workspace_cli, "dispatch_workspace", dispatch)
    monkeypatch.setattr(audit, "audit_command", observed_audit)
    argv = ["project", operation, "--root", "synthetic-unused", "--json"]
    if operation == "show":
        argv.extend(["--project", "synthetic-study"])
    assert cli_entry.main(argv) == 0
    assert calls == [(None, argv)] and context.exit_code == 0


@pytest.mark.parametrize("argv", [[], ["--help"], ["--version"], ["search", "--help"],
                                  ["task", "decide"], ["action", "execute"],
                                  ["project", "record"], ["project", "search"]])
def test_every_other_path_preserves_legacy_dispatch(monkeypatch, argv):
    calls = []
    legacy = ModuleType("research_hub.cli")
    legacy.main = lambda value: calls.append(value) or 7
    monkeypatch.setitem(sys.modules, "research_hub.cli", legacy)
    assert cli_entry.main(argv) == 7
    assert calls == [argv]


def test_local_read_keeps_parser_required_argument_errors():
    with pytest.raises(SystemExit) as error:
        cli_entry.main(["project", "show"])
    assert error.value.code == 2


def test_module_and_console_share_entrypoint():
    root = Path(__file__).resolve().parents[1]
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    scripts = text.split("[project.scripts]\n", 1)[1].split("\n[", 1)[0]
    assert re.search(r'^research-hub\s*=\s*"research_hub\.cli_entry:main"\s*$', scripts, re.MULTILINE)
    assert "from research_hub.cli_entry import main" in (root / "src/research_hub/__main__.py").read_text(encoding="utf-8")
