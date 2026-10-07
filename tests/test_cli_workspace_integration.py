"""Guard the shared CLI boundary after integrating the workspace and source tools."""

import json

import pytest

from research_hub import cli


@pytest.mark.parametrize("arguments", [
    ["search", "synthetic question"],
    ["enrich", "10.5555/synthetic"],
    ["verify", "--doi", "10.5555/synthetic"],
    ["references", "10.5555/synthetic"],
    ["cited-by", "10.5555/synthetic"],
])
def test_audit_flags_coexist_with_workspace_parser(arguments):
    parser = cli.build_parser()
    audited = parser.parse_args([*arguments, "--audit-output", "audit-evidence"])
    assert audited.audit_output == "audit-evidence"
    workspace = parser.parse_args(["project", "list", "--root", "workspace", "--json"])
    assert workspace.workspace_operation == "list"
    assert not getattr(workspace, "audit_output", None)


def test_workspace_and_source_dispatch_without_account_configuration(tmp_path, monkeypatch, capsys):
    from research_hub import config

    def forbidden(*args, **kwargs):
        raise AssertionError("Explicit local commands must not discover account configuration")

    monkeypatch.setattr(config, "get_config", forbidden)
    monkeypatch.setattr(cli, "get_config", forbidden)
    monkeypatch.setattr(cli, "require_config", forbidden)
    root = tmp_path / "workspace"
    assert cli.main(["project", "demo", "--root", str(root), "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["projects"]) == 2
    assert cli.main(["source", "validate", str(tmp_path / "missing-result.json"), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["valid"] is False
    assert cli.main(["project", "list", "--root", str(root), "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["projects"]) == 2
