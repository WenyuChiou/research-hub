from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re


def _readme_text() -> str:
    return (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_readme_env_var_table_is_machine_parseable_and_version_drift_free():
    text = _readme_text()
    start_marker = "<!-- env-vars-table-start -->"
    end_marker = "<!-- env-vars-table-end -->"

    assert start_marker in text
    assert end_marker in text

    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker)
    table_lines = [line.strip() for line in text[start:end].splitlines() if line.strip()]

    assert table_lines[0] == "| Name | Required | Purpose |"
    assert table_lines[1] == "|---|---|---|"

    rows = [line for line in table_lines[2:] if line.startswith("|")]
    assert len(rows) >= 5
    assert any("`ZOTERO_API_KEY`" in row for row in rows)

    assert "v0.81.0" not in text
    assert "v0.68.3" not in text


def test_researcher_first_visuals_and_preview_install_are_bilingual():
    root = Path(__file__).resolve().parents[1]
    for readme, locale in (("README.md", "en"), ("README.zh-TW.md", "zh-TW")):
        text = (root / readme).read_text(encoding="utf-8")
        lifecycle = f"docs/images/workspace-lifecycle.{locale}.png"
        screenshot = f"docs/images/workspace-ui.{locale}.png"
        writing = f"docs/images/workspace-writing.{locale}.png"
        assert lifecycle in text[:2500]
        assert text.index(lifecycle) < text.index(screenshot) < text.index(writing)
        # README uses a newer source snapshot; the producer manifest retains
        # its historical preview pin and must not be silently rewritten.
        assert "git checkout --detach 1f0726a7e92a1231e633963f17236a2f5c1eab8f" in text
        for executable in ("./.venv/bin/python", r".\.venv\Scripts\python.exe"):
            assert f"{executable} -m research_hub project demo --root ./workspace-demo --json" in text
        assert "docs/workspace-architecture.md" in text
        for relative in (lifecycle, screenshot, writing):
            assert (root / relative).is_file()


def test_legacy_cover_remains_available_and_unchanged():
    root = Path(__file__).resolve().parents[1]
    asset = root / "docs/images/research-hub-cover.png"
    assert asset.stat().st_size > 1_000_000
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == (
        "f77e8c9b933007132747f8a85c58d8fc7feeeddce30a9453541a3f92326abe91"
    )


def test_dated_capability_baseline_does_not_inherit_later_timeout_or_setup_evidence():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs/capability-baseline.md").read_text(encoding="utf-8")
    pin = json.loads((root / "docs/workspace-writing-source.json").read_text(encoding="utf-8"))
    assert pin["hub_preview_commit"] == "6381dfa7d474dd27cd4adb33f0f59ea8ec395150"
    assert "does **not** include" in text
    assert "https://github.com/WenyuChiou/research-hub/pull/175" in text
    assert "030bbd451022a9bdf8ab91cc12af5bed0b5cf857" in text
    assert "separate source, wheel and" in text
    assert "not live connector verification" in text
    assert "not a recommendation to deploy an unmerged validation branch" in text


def test_readme_command_blocks_and_compatibility_anchors_match():
    root = Path(__file__).resolve().parents[1]
    english = (root / "README.md").read_text(encoding="utf-8")
    chinese = (root / "README.zh-TW.md").read_text(encoding="utf-8")
    blocks = lambda text: re.findall(r"```(?:sh|powershell)\n(.*?)```", text, re.S)
    assert blocks(english) == blocks(chinese)
    for name in ("start-here", "first-run-checklist", "workspace-preview",
                 "credential-reference", "connect-your-ai-host", "published-dashboard"):
        marker = f'<a id="{name}"></a>'
        assert english.count(marker) == chinese.count(marker) == 1


def test_readme_source_pin_matches_fetch_checkout_and_verification_history():
    root = Path(__file__).resolve().parents[1]
    revision = "1f0726a7e92a1231e633963f17236a2f5c1eab8f"
    history = (root / "docs/readme-verification-history.md").read_text(encoding="utf-8")
    assert revision in history
    for filename in ("README.md", "README.zh-TW.md"):
        text = (root / filename).read_text(encoding="utf-8")
        assert re.findall(r"^git fetch origin ([0-9a-f]{40})$", text, re.M) == [revision]
        assert re.findall(r"^git checkout --detach ([0-9a-f]{40})$", text, re.M) == [revision]
        assert "docs/readme-verification-history.md#source-demo-first-task-2026-11-07" in text


def test_readme_first_task_matches_populated_demo_and_visible_limits(tmp_path):
    from research_hub.workspace.core import Workspace
    from research_hub.workspace.demo import create_demo

    root = Path(__file__).resolve().parents[1]
    demo = tmp_path / "demo"
    result = create_demo(demo)
    project = next(item for item in result["projects"] if item["id"] == "review-demo")
    workspace = Workspace(demo)
    sources = [item["data"] for item in workspace.records(project["id"]) if item["kind"] == "source"]
    assert len(sources) == 2
    source = next(item for item in sources if item["doi"] == "10.1145/103162.103163")
    assert source["identity_status"] == "unverified"
    assert not source.get("summary") and not source.get("abstract")
    assert not [item for item in workspace.records("summation-demo") if item["kind"] == "source"]
    labels = (root / "web/src/i18n.ts").read_text(encoding="utf-8")
    for filename, visible in (
        ("README.md", ("Unverified", "Coverage unknown", "No summary saved")),
        ("README.zh-TW.md", ("尚未驗證", "範圍未知", "尚未保存摘要")),
    ):
        text = (root / filename).read_text(encoding="utf-8")
        first_task = re.findall(r"^1\. (.+)\n2\. (.+)\n3\. (.+)$", text, re.M)
        assert len(first_task) == 1, "Keep one explicit three-step first task in each README"
        choose, inspect, expect = first_task[0]
        assert project["title"] in choose and "`review-demo`" in choose
        assert "summation-demo" not in choose
        assert source["title"] in inspect
        assert source["doi"] in expect
        for label in visible:
            assert label in labels and label in expect
        assert "serve --workspace --root ./workspace-demo" in text
