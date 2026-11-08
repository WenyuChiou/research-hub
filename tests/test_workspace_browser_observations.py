"""Offline fixture fidelity only; real Chromium acceptance is a separate run."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workspace_browser_observations.py"


def load_script():
    spec = importlib.util.spec_from_file_location("workspace_observation_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_data_needs_no_process_network_database_or_playwright(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Offline fixture must not create processes, sockets or databases")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    fixture = load_script()
    records, context = fixture.fixture_data()
    assert len(records) == 6
    assert len({record["id"] for record in records}) == 6
    assert all(record["id"] != record["data"]["id"] for record in records)
    assert all(record["data"]["identity_status"] == "unverified" and
               record["data"]["human_acceptance"] == "pending" for record in records)
    assert records[0]["data"]["summary"] == "Human preserved wording."
    assert "summary" not in records[1]["data"]
    assert context["projectId"] == "synthetic-project"


def test_report_previews_have_actual_hash_and_exact_outer_source_binding():
    records, context = load_script().fixture_data()
    artifacts = {item["id"]: item for item in context["artifacts"]}
    previews = {item["artifact_id"]: item for item in context["previews"]}
    for record in records:
        for obs in record["data"]["source_records"]:
            assert obs["source_id"] == record["data"]["id"]
            assert obs["raw_path"] is None and obs["raw_sha256"] is None
            if not obs["text_sha256"]:
                continue
            matches = [a for a in artifacts.values() if a["path"] == obs["text_path"]]
            assert len(matches) == 1
            artifact = matches[0]
            preview = previews[artifact["id"]]
            assert artifact["project_id"] == context["projectId"]
            assert artifact["source_record_id"] == record["id"]
            assert artifact["sha256"] == obs["text_sha256"] == hashlib.sha256(preview["text"].encode()).hexdigest()
            assert preview["bytes_read"] == len(preview["text"].encode())
            assert preview["codepoint_length"] == len(preview["text"])


def test_existing_output_is_rejected_before_reading_or_overwriting_unrelated_files(tmp_path, monkeypatch):
    fixture = load_script()
    selected = tmp_path / "existing"
    selected.mkdir()
    unrelated = selected / "unrelated-synthetic.txt"
    unrelated.write_text("Synthetic preexisting content", encoding="utf-8")
    monkeypatch.setattr(Path, "read_bytes", lambda *_args: pytest.fail("No existing output or source reads"))
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("No build process"))
    with pytest.raises(RuntimeError, match="Choose a new scratch directory"):
        fixture.build_fixture(selected)
    assert unrelated.read_text(encoding="utf-8") == "Synthetic preexisting content"
    assert sorted(path.name for path in selected.iterdir()) == [unrelated.name]


def test_historical_and_incomplete_cases_do_not_promote_saved_metadata():
    records, context = load_script().fixture_data()
    manual, generated, unbound, versions, legacy, bad_time = records
    assert manual["data"]["reading_level"] == "abstract-snippet"
    assert manual["data"]["reading_scope"] == "abstract"
    assert [o["evidence_level"] for o in manual["data"]["source_records"]] == ["metadata", "generated-summary"]
    assert "summary" not in generated["data"]
    assert unbound["data"]["source_records"][0]["text_sha256"] is None
    assert [o["version_id"] for o in versions["data"]["source_records"]] == ["2023", "2026"]
    assert all(o["version_review_ref"] is None for o in versions["data"]["source_records"])
    assert legacy["data"]["abstract"] == "Original saved abstract."
    assert legacy["data"]["source_records"] == []
    assert any("Reported observation time: not-a-date" in p["text"] for p in context["previews"])
    assert all("category" not in r["data"] for r in records)


def test_full_smoke_calls_component_after_original_try_and_persists_its_failure():
    source = (SCRIPT.parent / "workspace_browser_smoke.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    run = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run")
    component_try = next(node for node in run.body if isinstance(node, ast.Try) and any(
        isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "run_observation_component"
        for call in ast.walk(node)))
    assert component_try.handlers and component_try.finalbody
    assert any(isinstance(node, ast.Raise) for node in ast.walk(component_try.handlers[0]))
    assert '"source-observations"' in ast.get_source_segment(source, component_try)
    assert '"component-browser-fixture"' in ast.get_source_segment(source, component_try)
