"""Chromium/HTTP/SQLite smoke; fixture decisions are not human acceptance.

Delivery fixtures simulate decision transport only, never a person's scientific
approval. The missing-assessment compatibility case is an explicitly labelled
HTTP response fixture; stale/missing files use actual backend assessments.

Install the optional test runner with pip install playwright==1.58.0 and
python -m playwright install chromium. This is not a runtime dependency.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import tempfile
import threading
import time

from playwright.sync_api import expect, sync_playwright

from research_hub.workspace.demo import create_demo
from research_hub.workspace.core import Workspace, digest, file_hash
from research_hub.workspace.server import WorkspaceServer
from research_hub.workspace.tasks import TaskService, _LOCAL_HUMAN


def prepare_revision_fixtures(workspace):
    """Seed only the run's temporary project; no executor or provider calls."""
    if os.environ.get("RESEARCH_HUB_WRITING_ADAPTER", "").strip():
        raise RuntimeError("Browser revision fixtures require no external writing adapter")
    project_id = "delivery-revision-fixture"
    workspace.create_project(id=project_id, title="Synthetic delivery revision fixtures",
                             archetype="review", goal="UI transport only; no scientific or human acceptance.")
    candidates = workspace.root / "candidates"
    candidates.mkdir(exist_ok=True)
    service = TaskService(workspace)
    fixtures = {"project_id": project_id, "tasks": {}}
    for name in ("changed", "missing_file", "missing_assessment", "current"):
        path = candidates / f"browser-revision-{name}.md"
        path.write_text(f"Synthetic {name} candidate; not research evidence.\n", encoding="utf-8")
        task = service.create(project_id, operation="draft", mode="handoff")
        task = service.import_result(
            task["id"], prose="Synthetic decision-transport fixture; no real scientific acceptance.",
            input_hash=digest(task["request"]),
            artifacts=[{"path": path.relative_to(workspace.root).as_posix(), "sha256": file_hash(path)}])
        service.decide(task["id"], outcome="accept", actor="synthetic-browser-fixture",
                       rationale="Exercise decision plumbing only, not human scientific approval",
                       action_hash=task["action_hash"], proof=_LOCAL_HUMAN)
        assert service.get(task["id"])["freshness"]["status"] == "current"
        fixtures["tasks"][name] = {"id": task["id"], "path": path}
    return fixtures


class WorkspacePage:
    def __init__(self, page, base):
        self.page, self.base = page, base

    def open(self):
        self.page.goto(self.base + "/app/")
        expect(self.page.get_by_role("combobox", name="Choose a project")).to_be_visible()

    def navigate(self, label):
        self.page.get_by_role("navigation").get_by_role("link", name=label, exact=True).click()
        expect(self.page.get_by_role("heading", name=label, level=1, exact=True)).to_be_visible()
        expect(self.page.get_by_role("heading", level=1)).to_have_text(label)

    def choose(self, project):
        self.page.get_by_role("combobox", name="Choose a project").select_option(project)
        expect(self.page.get_by_role("main")).to_contain_text(project)


def check_revision_delivery(screen, service, fixtures, checks, output):
    """No UI approval or delivery mutation; Refresh may make read requests."""
    page = screen.page
    page.set_default_timeout(10_000)
    page.set_default_navigation_timeout(15_000)
    items = fixtures["tasks"]
    mutations = []
    def observe(request):
        if request.url.startswith(screen.base + "/api/v1/") and request.method != "GET":
            mutations.append(request.method)
    page.on("request", observe)
    project_url = screen.base + "/api/v1/projects/" + fixtures["project_id"]
    def omit_assessment(route):
        response = route.fetch(timeout=10_000)
        payload = response.json()
        assert payload["ok"] is True
        target = next(task for task in payload["tasks"] if task["id"] == items["missing_assessment"]["id"])
        assert target["freshness"]["status"] == "current"
        del target["freshness"]
        route.fulfill(status=response.status, content_type="application/json", body=json.dumps(payload))
    def checkbox(name):
        return page.locator(f'input[name="task_ids"][value="{items[name]["id"]}"]')
    def card(name):
        return page.get_by_role("article").filter(has_text=items[name]["id"])
    try:
        page.set_viewport_size({"width": 1440, "height": 1000})
        screen.choose(fixtures["project_id"])
        screen.navigate("Review & delivery")
        assert not page.locator('meta[name="research-hub-human-token"]').count()
        for name in items:
            expect(card(name).get_by_text("Matches prepared revisions", exact=True)).to_be_visible()
            checkbox(name).check()
        expect(page.get_by_role("checkbox")).to_have_count(4)
        page.screenshot(path=str(output / "delivery-revisions-current.png"), full_page=True)
        checks.append({"check": "Synthetic accepted/current candidate fixtures are selectable", "status": "PASS"})

        items["changed"]["path"].write_text("Changed synthetic candidate bytes.\n", encoding="utf-8")
        assert service.get(items["changed"]["id"])["freshness"]["status"] == "stale"
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(card("changed").get_by_text("Revision changed", exact=True)).to_be_visible()
        expect(checkbox("changed")).to_have_count(0)
        expect(checkbox("current")).to_be_checked()
        checks.append({"check": "Actual backend changed-file assessment revokes selected candidate after Refresh", "status": "PASS"})

        items["missing_file"]["path"].unlink()
        assert service.get(items["missing_file"]["id"])["freshness"]["status"] == "unknown"
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(card("missing_file").get_by_text("Revision not verified", exact=True)).to_be_visible()
        expect(checkbox("missing_file")).to_have_count(0)
        expect(checkbox("current")).to_be_checked()
        checks.append({"check": "Actual backend missing-file unknown assessment revokes selection after Refresh", "status": "PASS"})

        page.route(project_url, omit_assessment)
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(card("missing_assessment").get_by_text("Revision not verified", exact=True)).to_be_visible()
        expect(checkbox("missing_assessment")).to_have_count(0)
        assert service.get(items["missing_assessment"]["id"])["freshness"]["status"] == "current"
        checks.append({"check": "Legacy HTTP response fixture with omitted freshness revokes selection", "status": "PASS",
                       "boundary": "One response field omitted by test route; not an actual backend file failure"})

        expect(page.get_by_role("checkbox")).to_have_count(1)
        expect(checkbox("current")).to_be_checked()
        for name in items:
            assert service.get(items[name]["id"])["status"] == "completed"
            expect(card(name).get_by_text("Accepted by human", exact=True)).to_be_visible()
        assert not mutations, "Refresh or revoked selections must not submit delivery/approval requests"
        assert not service.workspace.snapshot(fixtures["project_id"])["actions"]
        page.screenshot(path=str(output / "delivery-revisions-revoked.png"), full_page=True)
        checks.append({"check": "Current selection and historical fixture decisions preserved; no mutation request or delivery action", "status": "PASS"})
    finally:
        page.unroute(project_url, omit_assessment)
        page.remove_listener("request", observe)


def run(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    checks, errors = [], []
    report = {"environment": {"python": platform.python_version(), "platform": platform.platform()},
              "checks": checks, "human_acceptance": "not_performed", "live_model": "not_run",
              "synthetic_decision_fixtures": "Four temporary fixture decisions; not real human/scientific acceptance",
              "native_browser_zoom": "not_verified"}
    with tempfile.TemporaryDirectory(prefix="research-hub-browser-") as temporary:
        root = Path(temporary).resolve() / "demo"
        create_demo(root)
        revision_fixtures = prepare_revision_fixtures(Workspace(root))
        server = WorkspaceServer(root, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            screen = WorkspacePage(page, f"http://127.0.0.1:{server.server_port}")
            try:
                screen.open()
                screen.choose("summation-demo")
                for label in ("Overview", "Literature", "Evidence", "Design & results", "Manuscript", "Review & delivery"):
                    screen.navigate(label)
                    checks.append({"check": "EN navigation: " + label, "status": "PASS"})
                page.get_by_role("combobox", name="Operation", exact=True).select_option("outline")
                page.get_by_role("textbox", name="Instructions and acceptance criteria", exact=True).fill("UI transport smoke only: propose a bounded outline; no scientific acceptance.")
                page.get_by_role("button", name="Prepare task", exact=True).click()
                expect(page.get_by_role("button", name="Download handoff packet")).to_be_visible()
                with page.expect_download() as download:
                    page.get_by_role("button", name="Download handoff packet").click()
                packet = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
                tasks = TaskService(server.service.workspace)
                assert tasks.get(packet["task_id"])["status"] == "awaiting_agent"
                checks.append({"check": "Real handoff download remains awaiting_agent", "status": "PASS"})
                page.locator("summary").filter(has_text="Import host output").click()
                page.get_by_role("textbox", name="Input fingerprint from the handoff packet", exact=True).fill(packet["input_hash"])
                page.get_by_role("textbox", name="Agent output", exact=True).fill("Transport fixture: three cases cannot establish universal accuracy. This text is not model output or scientific acceptance.")
                page.get_by_role("button", name="Import for human review", exact=True).click()
                expect(page.get_by_role("article").filter(has_text=packet["task_id"]).get_by_text("Awaiting human review", exact=True)).to_be_visible()
                assert tasks.get(packet["task_id"])["status"] == "awaiting_human"
                assert not page.locator('meta[name="research-hub-human-token"]').count()
                checks.append({"check": "Actual result import requires human acceptance", "status": "PASS"})
                screen.navigate("Overview")
                expect(page.get_by_role("heading", name="Awaiting human review", level=2, exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="Open review & delivery", exact=True)).to_be_visible()
                checks.append({"check": "EN next step prioritizes pending human review", "status": "PASS"})
                expect(page.get_by_role("heading", name="Overview", level=1, exact=True)).to_be_visible()
                page.screenshot(path=str(output / "workspace-ui.en.png"))
                page.get_by_role("button", name="繁體中文", exact=True).click()
                expect(page.locator("html")).to_have_attribute("lang", "zh-TW")
                expect(page.get_by_role("button", name="關閉訊息", exact=True)).to_have_count(0)
                for label in ("研究總覽", "文獻", "證據", "設計與結果", "論文", "審閱與交付"):
                    screen.navigate(label)
                    checks.append({"check": "zh-TW navigation: " + label, "status": "PASS"})
                screen.navigate("研究總覽")
                expect(page.get_by_role("heading", name="等待人工審閱", level=2, exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="開啟審閱與交付", exact=True)).to_be_visible()
                checks.append({"check": "zh-TW next step prioritizes pending human review", "status": "PASS"})
                expect(page.get_by_role("heading", name="研究總覽", level=1, exact=True)).to_be_visible()
                page.screenshot(path=str(output / "workspace-ui.zh-TW.png"))
                checks.append({"check": "Traditional Chinese navigation and real screenshot", "status": "PASS"})
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                checks.append({"check": "390px viewport has no horizontal page overflow", "status": "PASS"})
                page.set_viewport_size({"width": 720, "height": 500})  # 200% of desktop layout width.
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                page.get_by_role("button", name="EN", exact=True).click()
                page.goto(screen.base + "/app/")
                page.keyboard.press("Tab")
                expect(page.get_by_role("link", name="Skip to main content")).to_be_focused()
                page.keyboard.press("Enter")
                expect(page.get_by_role("main")).to_be_focused()
                checks.append({"check": "200% equivalent layout and keyboard skip link", "status": "PASS"})
                check_revision_delivery(screen, tasks, revision_fixtures, checks, output)
                assert not errors, errors
                report["status"] = "PASS"
            except Exception as exc:
                report.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
                page.screenshot(path=str(output / "browser-failure.png"), full_page=True)
                raise
            finally:
                report.update(duration_seconds=round(time.monotonic() - started, 3), page_errors=errors)
                context.tracing.stop(path=str(output / "browser-trace.zip"))
                browser.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                (output / "browser-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Explicit scratch screenshot/trace directory")
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve()), indent=2))
