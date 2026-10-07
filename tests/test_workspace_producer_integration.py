"""Pinned public producer integration; opt-in source checkout, never live models."""

import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import zipfile

import pytest

from research_hub.workspace.writing import WritingAdapter

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / "docs/workspace-writing-source.json").read_text(encoding="utf-8"))


def test_bilingual_installation_uses_immutable_sources():
    assert PIN["source_status"] == "merged-main"
    assert PIN["runtime_dependency"] is False
    for name in ("README.md", "README.zh-TW.md", "docs/workspace-guide.md", "docs/workspace-guide.zh-TW.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert f"git checkout --detach {PIN['hub_preview_commit']}" in text
        assert "git clone -b codex/" not in text
        assert "-b codex/writing-workspace-adapter" not in text
        assert PIN["commit"] in text
    for name in ("docs/workspace-guide.md", "docs/workspace-guide.zh-TW.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert PIN["adapter_manifest_sha256"] in text
        assert PIN["bundle_sha256"] in text


def test_ci_verifies_the_same_immutable_producer():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert f"repository: {PIN['repository']}" in workflow
    assert f"ref: {PIN['commit']}" in workflow
    assert "test_workspace_producer_integration.py" in workflow
    assert "RESEARCH_HUB_TEST_WRITING_ADAPTER" in workflow


def test_pinned_bundle_closure_audits_and_offline_handoff(tmp_path, monkeypatch):
    configured = os.environ.get("RESEARCH_HUB_TEST_WRITING_ADAPTER")
    if not configured:
        pytest.skip("Explicit pinned producer checkout required; workspace CI supplies it")
    producer = Path(configured).resolve()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=producer,
                              capture_output=True, text=True, check=True, timeout=10)
    assert revision.stdout.strip() == PIN["commit"]
    manifest = producer / "adapter.json"
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == PIN["adapter_manifest_sha256"]
    builder = producer / "scripts/build_adapter_bundle.py"
    checked = subprocess.run([sys.executable, str(builder), "--root", str(producer), "--check"],
                             capture_output=True, text=True, check=True, timeout=30)
    assert json.loads(checked.stdout)["status"] == "PASS"
    bundle = tmp_path / "adapter.zip"
    subprocess.run([sys.executable, str(builder), "--root", str(producer), "--output", str(bundle)],
                   capture_output=True, text=True, check=True, timeout=30)
    assert hashlib.sha256(bundle.read_bytes()).hexdigest() == PIN["bundle_sha256"]
    extracted = tmp_path / "adapter"
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(extracted)
    adapter = WritingAdapter(extracted)
    assert adapter.sha256 == PIN["adapter_manifest_sha256"]
    assert adapter.instructions("academic-writing-skills")
    assert adapter.instructions("paper-review")
    monkeypatch.setenv("RESEARCH_HUB_WRITING_ADAPTER", str(extracted))
    monkeypatch.delenv("RESEARCH_HUB_AGENT_POLICY", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_AGENT_CHECKPOINT", raising=False)
    report = runpy.run_path(str(ROOT / "scripts/workspace_dogfood.py"))["run"](tmp_path / "demo", live=False)
    assert report["adapter_sha256"] == PIN["adapter_manifest_sha256"]
    assert report["human_acceptance"] == "not_performed"
    assert report["publication"] == "not_authorized"
    assert {lane["project_id"] for lane in report["lanes"]} == {"summation-demo", "review-demo"}
    for lane in report["lanes"]:
        assert lane["status"] == "HANDOFF_ONLY", lane.get("error")
        assert lane["execution"]["status"] == "awaiting_agent"
        assert set(lane["checks"]) == {"state", "consistency", "prose", "regression"}
        for checked in lane["checks"].values():
            assert checked["ok"], checked
            assert checked["adapter_sha256"] == PIN["adapter_manifest_sha256"]
            assert checked["semantic_acceptance"] == "not_performed"
