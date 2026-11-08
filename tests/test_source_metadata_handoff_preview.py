"""Synthetic Stage1 source proposals through the official no-write CLI branch."""

import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from unittest.mock import patch

import pytest

from research_hub.workspace.cli import add_workspace_parsers, dispatch_workspace
from research_hub.workspace.core import WorkspaceError
from research_hub.workspace.source_handoff import (
    MAX_PREVIEW_BYTES, parse_preview_data, preview_source_record, source_record_arguments,
)


def synthetic_batch():
    return [{
        "id": f"synthetic-{i:02d}", "title": f"Synthetic paper {i}",
        "year": 2000 + i, "url": f"https://example.org/source/{i}",
        "relevance": "Caller relevance annotation, not summary prose.",
        "reading_level": "abstract-snippet" if i == 20 else "abstract",
        "reading_level_note": "Only the declared abstract or snippet was inspected.",
        "category": "human" if i <= 11 else "human-review" if i == 12 else "llm",
    } for i in range(1, 21)]


def cli_preview(root, arguments):
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args([
        "project", "record", "--root", str(root), "--project", "synthetic-project",
        "--kind", arguments["kind"], "--data", json.dumps(arguments["data"]), "--dry-run", "--json",
    ])
    output = io.StringIO()
    with redirect_stdout(output):
        status = dispatch_workspace(args)
    return status, json.loads(output.getvalue())


def test_twenty_source_proposals_via_official_cli_have_no_io(tmp_path):
    batch = synthetic_batch()
    before = deepcopy(batch)
    root = tmp_path / "does-not-exist"
    with (
        patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("Service forbidden")),
        patch("research_hub.workspace.cli.WorkspaceService", side_effect=AssertionError("Workspace forbidden")),
        patch("research_hub.workspace.core.sqlite3.connect", side_effect=AssertionError("DB forbidden")),
        patch("research_hub.config.get_config", side_effect=AssertionError("Config forbidden")),
        patch("socket.create_connection", side_effect=AssertionError("Network forbidden")),
        patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")),
    ):
        proposals = []
        for index, paper in enumerate(batch):
            prior = [{"batch_id": "synthetic-old", "candidate_id": f"old-{index}",
                      "source_url": "https://example.org/prior", "version": "unknown"}] if index < 7 else []
            arguments = source_record_arguments(paper, batch_id="synthetic-new", prior_batch_matches=prior)
            status, result = cli_preview(root, arguments)
            assert status == 0
            preview = result["preview"]
            data = preview["data"]
            assert {key: data[key] for key in paper} == paper
            assert data["id"] == paper["id"] and preview["record_id"] is None
            assert data["batch_id"] == "synthetic-new" and data["prior_batch_matches"] == prior
            assert data["locator"] == paper["url"]
            assert data["reading_scope"] == data["reading_level"] == paper["reading_level"]
            assert data["identity_status"] == "unverified" and data["human_acceptance"] == "pending"
            assert not any(k in data for k in ("summary", "abstract", "full_text", "recorded_at"))
            assert preview["missing_fields"] == ["authors", "abstract", "summary"]
            assert not preview["project_verified"] and not preview["persisted"] and not preview["execution_authorized"]
            proposals.append(preview)
    assert len(proposals) == 20 and sum(p["data"]["reading_scope"] == "abstract-snippet" for p in proposals) == 1
    assert batch == before and not root.exists()


def test_main_cli_dispatches_dry_run_without_configuration(tmp_path):
    from research_hub import cli
    arguments = source_record_arguments(synthetic_batch()[-1], batch_id="synthetic-new")
    output = io.StringIO()
    with (
        patch.object(cli, "get_config", side_effect=AssertionError("Config forbidden")),
        patch.object(cli, "require_config", side_effect=AssertionError("Config forbidden")),
        patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("Service forbidden")),
        redirect_stdout(output),
    ):
        code = cli.main(["project", "record", "--root", str(tmp_path / "unused"), "--project", "synthetic-project",
                         "--kind", "source", "--data", json.dumps(arguments["data"]), "--dry-run", "--json"])
    assert code == 0
    assert json.loads(output.getvalue())["preview"]["data"]["reading_scope"] == "abstract-snippet"


@pytest.mark.parametrize("raw", ['[]', '{"id":"private","id":"repeated"}', '{"value":NaN}', '{"secret":"PRIVATE"'])
def test_invalid_preview_json_diagnostics_do_not_echo_values(raw):
    with pytest.raises(WorkspaceError) as error:
        parse_preview_data(raw)
    assert "PRIVATE" not in str(error.value) and "private" not in str(error.value)


def test_processing_limit_is_not_a_paper_quota():
    with pytest.raises(WorkspaceError):
        parse_preview_data('"' + 'x' * MAX_PREVIEW_BYTES + '"')


def test_snippet_cannot_be_promoted_and_data_is_not_mutated():
    arguments = source_record_arguments(synthetic_batch()[-1], batch_id="synthetic-new")
    original = deepcopy(arguments)
    preview_source_record("synthetic-project", **arguments)
    assert arguments == original
    arguments["data"]["reading_scope"] = "abstract"
    with pytest.raises(WorkspaceError, match="without promotion"):
        preview_source_record("synthetic-project", **arguments)


def test_other_record_kinds_do_not_fall_through_to_write(tmp_path):
    with patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("Write forbidden")):
        status, result = cli_preview(tmp_path / "unused", {"kind": "question", "data": {"text": "Synthetic"}})
    assert status == 1 and not result["ok"] and not (tmp_path / "unused").exists()


def test_blank_prose_stays_a_missing_body():
    arguments = source_record_arguments(synthetic_batch()[0], batch_id="synthetic-new")
    arguments["data"].update(summary=" \n", abstract="\t")
    result = preview_source_record("synthetic-project", **arguments)
    assert result["preview"]["missing_fields"] == ["authors", "abstract", "summary"]


def test_ordinary_record_route_is_unchanged(tmp_path):
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    data = {"title": "Synthetic", "locator": "https://example.org/source"}
    args = parser.parse_args(["project", "record", "--root", str(tmp_path), "--project", "synthetic-project",
                              "--kind", "source", "--data", json.dumps(data), "--json"])
    with patch("research_hub.workspace.cli.call_workspace", return_value={"ok": True}) as dispatch:
        assert dispatch_workspace(args) == 0
    dispatch.assert_called_once_with(str(tmp_path), "project", "record",
                                     {"project_id": "synthetic-project", "kind": "source", "data": data}, proof=None)


@pytest.mark.parametrize(("project", "raw_data"), [("", '{"private":"PRIVATE"}'), ("synthetic-project", "")])
def test_empty_preview_arguments_return_json_without_writes(tmp_path, project, raw_data):
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest="command", required=True))
    root = tmp_path / "unused"
    args = parser.parse_args(["project", "record", "--root", str(root), "--project", project,
                              "--kind", "source", "--data", raw_data, "--dry-run", "--json"])
    output = io.StringIO()
    with (
        patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("Service forbidden")),
        patch("research_hub.workspace.core.sqlite3.connect", side_effect=AssertionError("DB forbidden")),
        redirect_stdout(output),
    ):
        code = dispatch_workspace(args)
    result = json.loads(output.getvalue())
    assert code == 1 and result["code"] == "invalid_request"
    assert "PRIVATE" not in output.getvalue() and not root.exists()


def generated_observation():
    return {
        "observation_id": "generated-summary:synthetic", "source_id": "synthetic-20",
        "work_id": "local:synthetic", "version_id": None, "version_review_ref": None,
        "acquisition_ref": "Synthetic generated report; not publisher acquisition",
        "status": "available", "evidence_level": "generated-summary",
        "source_fetch_result": None, "raw_path": None, "raw_sha256": None,
        "text_path": "generated/not-opened.md", "text_sha256": "1" * 64,
        "source_version": None,
    }


def test_legacy_record_rejection_does_not_drop_valid_observation_preview(tmp_path):
    from pathlib import Path
    import jsonschema  # Load its packaged meta-schemas before the caller-file tripwire.
    arguments = source_record_arguments(synthetic_batch()[-1], batch_id="synthetic-new")
    arguments["data"].update(reading_scope="abstract", source_records=[generated_observation()])
    before = deepcopy(arguments)
    original_read = Path.read_text
    schema = Path(__file__).resolve().parents[1] / "src/research_hub/schemas/research-source-audit-1.0.json"

    def bundled_schema_only(path, *args, **kwargs):
        assert path == schema, "Caller text paths must never be opened"
        return original_read(path, *args, **kwargs)

    with (
        patch("research_hub.workspace.cli.call_workspace", side_effect=AssertionError("Service forbidden")),
        patch("research_hub.workspace.cli.WorkspaceService", side_effect=AssertionError("Workspace forbidden")),
        patch("research_hub.workspace.core.sqlite3.connect", side_effect=AssertionError("DB forbidden")),
        patch("research_hub.config.get_config", side_effect=AssertionError("Config forbidden")),
        patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")),
        patch.object(Path, "read_text", bundled_schema_only),
        patch.object(Path, "read_bytes", side_effect=AssertionError("Caller bytes forbidden")),
    ):
        status, result = cli_preview(tmp_path / "unused", arguments)
    assert status == 1 and result["ok"] is False
    assert "without promotion" in result["error"]
    assert result["record_preview_status"] == "rejected"
    assert result["record_preview_contract"] == "local-quick-list-metadata-policy"
    assert result["core_record_validity"] == "not-assessed"
    observation = result["source_audit_item_preview"]
    assert observation["status"] == "valid" and observation["item_count"] == 1
    assert observation["findings"] == []
    assert observation["packet_binding"] == observation["artifact_binding"] == "not-performed"
    assert observation["persisted"] is False and observation["execution_authorized"] is False
    assert arguments == before and not (tmp_path / "unused").exists()


def test_bad_observation_keeps_record_rejection_and_non_content_diagnostics(tmp_path):
    arguments = source_record_arguments(synthetic_batch()[-1], batch_id="synthetic-new")
    observation = generated_observation()
    observation.update(acquisition_ref=None, unexpected="PRIVATE")
    arguments["data"].update(reading_scope="abstract", source_records=[observation])
    status, result = cli_preview(tmp_path / "unused", arguments)
    assert status == 1 and not result["ok"] and result["record_preview_status"] == "rejected"
    report = result["source_audit_item_preview"]
    assert report["status"] == "rejected" and report["findings"]
    assert "PRIVATE" not in json.dumps(result)
    assert arguments["data"]["reading_scope"] == "abstract"


def test_observation_compatibility_does_not_redefine_generic_source_records(tmp_path):
    arguments = source_record_arguments(synthetic_batch()[0], batch_id="synthetic-new")
    arguments["data"]["source_records"] = [{"backend": "synthetic metadata"}]
    status, result = cli_preview(tmp_path / "unused", arguments)
    assert status == 0 and result["ok"] and result["record_preview_status"] == "metadata-valid"
    assert result["source_audit_item_preview"]["status"] == "rejected"
    assert result["preview"]["data"]["source_records"] == arguments["data"]["source_records"]
    assert not (tmp_path / "unused").exists()


def test_duplicate_observation_ids_are_not_reported_as_valid_items(tmp_path):
    arguments = source_record_arguments(synthetic_batch()[0], batch_id="synthetic-new")
    item = generated_observation()
    arguments["data"]["source_records"] = [item, deepcopy(item)]
    status, result = cli_preview(tmp_path / "unused", arguments)
    assert status == 0 and result["record_preview_status"] == "metadata-valid"
    report = result["source_audit_item_preview"]
    assert report["status"] == "rejected"
    assert any(f["code"] == "duplicate-observation-id" for f in report["findings"])


def test_metadata_and_observation_results_both_valid_without_claiming_binding(tmp_path):
    arguments = source_record_arguments(synthetic_batch()[-1], batch_id="synthetic-new")
    arguments["data"]["source_records"] = [generated_observation()]
    status, result = cli_preview(tmp_path / "unused", arguments)
    assert status == 0 and result["record_preview_status"] == "metadata-valid"
    report = result["source_audit_item_preview"]
    assert report["status"] == "valid" and report["item_count"] == 1
    assert report["version_identity_scientific_checks"] == "not-performed"
    assert result["preview"]["data"]["reading_scope"] == "abstract-snippet"
    assert not result["preview"]["persisted"] and not (tmp_path / "unused").exists()


@pytest.mark.parametrize(("records", "status"), [([], "not-supplied"), (None, "rejected")])
def test_empty_or_wrong_type_observations_are_not_a_passed_audit(tmp_path, records, status):
    arguments = source_record_arguments(synthetic_batch()[0], batch_id="synthetic-new")
    arguments["data"]["source_records"] = records
    exit_code, result = cli_preview(tmp_path / "unused", arguments)
    assert exit_code == 0 and result["record_preview_status"] == "metadata-valid"
    report = result["source_audit_item_preview"]
    assert report["status"] == status and report["packet_binding"] == "not-performed"


def test_observation_findings_are_bounded_without_echoing_private_content(tmp_path):
    arguments = source_record_arguments(synthetic_batch()[-1], batch_id="synthetic-new")
    arguments["data"].update(reading_scope="abstract", source_records=[{"PRIVATE": "PRIVATE"}] * 101)
    status, result = cli_preview(tmp_path / "unused", arguments)
    report = result["source_audit_item_preview"]
    assert status == 1 and not result["ok"] and report["status"] == "rejected"
    assert report["findings_truncated"] and len(report["findings"]) == 100
    assert "PRIVATE" not in json.dumps(result)
