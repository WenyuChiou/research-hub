"""Hosted browser acceptance for session-only drafts; never dispatches a model.

Requires the existing temporary WorkspaceServer harness. Real preview/Prepare
HTTP is used; legacy capability omission and lost reply are explicit fixtures.
Not executable in a VM where browser/socket launch was denied.
"""
from __future__ import annotations

import json
import time
import uuid

from playwright.sync_api import expect
from workspace_browser_fixtures import ABSTRACT, SOURCE


def check_composer_sessions(screen, service, fixtures, checks, output):
    page = screen.page
    page.set_default_timeout(10_000)
    page.set_viewport_size({"width": 1440, "height": 1000})
    project = fixtures["project_id"]
    tasks_url = screen.base + "/api/v1/projects/" + project + "/tasks"
    workspace_url = screen.base + "/api/v1/workspace"
    run_url = screen.base + "/api/v1/tasks/*/run"
    writes, reads, held, created = [], [], [], []
    runs = {"count": 0}

    def observe(request):
        if request.url.startswith(screen.base + "/api/v1/"):
            (reads if request.method == "GET" else writes).append(request.url)

    def reject_run(route):
        runs["count"] += 1
        route.fulfill(status=503, content_type="application/json",
                      body=json.dumps({"ok": False, "error": "Synthetic guard: no runner dispatch"}))

    def held_prepare(route):
        request = route.request.post_data_json
        identity = request["prepare_request"]
        assert identity["version"] == 1
        assert uuid.UUID(identity["key"]).version == 4
        assert identity["workspace_instance_id"] == service.workspace.preparation_namespace()
        assert request["source_selection"] == fixtures["selection"]
        response = route.fetch(timeout=10_000)
        assert response.status == 200
        value = response.json()
        assert value["ok"] is True
        assert value["preparation"]["version"] == 1
        assert value["preparation"]["key"] == identity["key"]
        assert value["preparation"]["disposition"] == "created"
        created.append(value["task"]["id"])
        held.append((route, value))

    def legacy_capabilities(route):
        response = route.fetch(timeout=10_000)
        value = response.json()
        value["capabilities"].pop("prepare_reconciliation", None)
        value["capabilities"].pop("text_intake", None)
        route.fulfill(status=response.status, content_type="application/json", body=json.dumps(value))

    def lose_keyless_reply(route):
        payload = route.request.post_data_json
        assert "prepare_request" not in payload
        response = route.fetch(timeout=10_000)  # Actual local save, not a fabricated task.
        assert response.status == 200
        value = response.json()
        assert value["ok"] is True
        created.append(value["task"]["id"])
        route.fulfill(status=503, content_type="application/json",
                      body=json.dumps({"ok": False, "error": "Synthetic reply lost after local save"}))

    def card(source):
        return page.locator("#record-" + source["id"])

    def open_source(source):
        card(source).get_by_role("button", name="Draft from an existing abstract", exact=True).click()

    def assert_draft(purpose, locked=False):
        expect(page.get_by_label("Purpose or question (optional)", exact=True)).to_have_value(purpose)
        expect(page.get_by_label("Registered source text (read only)", exact=True)).to_have_value(SOURCE.replace("\r\n", "\n"))
        expect(card(fixtures["source"]).locator("p.preserve-lines")).to_have_text(ABSTRACT)
        button = page.get_by_role("button", name="Prepare from this abstract", exact=True)
        if locked:
            expect(button).to_be_disabled()
            expect(page.get_by_label("Choose existing evidence text", exact=True)).to_be_disabled()
        else:
            expect(button).to_be_enabled()

    def select_draft(purpose):
        open_source(fixtures["source"])
        page.get_by_label("Choose existing evidence text", exact=True).select_option(fixtures["artifact"]["id"])
        page.get_by_role("button", name="Read selected saved text", exact=True).click()
        textarea = page.get_by_label("Registered source text (read only)", exact=True)
        expect(textarea).to_have_value(SOURCE.replace("\r\n", "\n"))
        selection = textarea.evaluate("""(element, text) => {
            const start = element.value.indexOf(text);
            if (start < 0) throw new Error('Synthetic selected passage absent');
            element.focus(); element.setSelectionRange(start, start + text.length);
            return element.value.slice(element.selectionStart, element.selectionEnd);
        }""", ABSTRACT.replace("\r\n", "\n"))
        assert selection == ABSTRACT.replace("\r\n", "\n")
        textarea.press("Shift")  # Native-like event after scripted range, not keyboard-only acceptance.
        page.get_by_label("Purpose or question (optional)", exact=True).fill(purpose)
        assert_draft(purpose)

    def source_roundtrip(purpose, locked=False):
        open_source(fixtures["other_source"])
        expect(page.get_by_label("Purpose or question (optional)", exact=True)).to_have_count(0)
        open_source(fixtures["source"])
        assert_draft(purpose, locked)

    def project_roundtrip(purpose, locked=False):
        screen.choose(fixtures["other_project"])
        expect(page.get_by_label("Purpose or question (optional)", exact=True)).to_have_count(0)
        screen.choose(project)
        open_source(fixtures["source"])
        assert_draft(purpose, locked)

    before = {task["id"] for task in service.list(project)}
    page.on("request", observe)
    page.route(run_url, reject_run)
    try:
        screen.open()
        screen.choose(project)
        screen.navigate("Literature")
        purpose = "Synthetic retained purpose A; no scientific claim"
        select_draft(purpose)
        preview_reads = sum(url.endswith("/text") for url in reads)
        assert preview_reads == 1
        source_roundtrip(purpose)
        project_roundtrip(purpose)
        assert sum(url.endswith("/text") for url in reads) == preview_reads
        assert not writes and runs["count"] == 0
        page.screenshot(path=str(output / "composer-unsent-roundtrip.png"), full_page=True)
        checks.append({"check": "Browser unsent source/project roundtrips preserve exact passage, range and purpose without reread or mutation",
                       "status": "PASS", "boundary": "Synthetic local source; scripted range plus browser key event"})

        page.route(tasks_url, held_prepare)
        with page.expect_request(lambda request: request.url == tasks_url and request.method == "POST"):
            page.get_by_role("button", name="Prepare from this abstract", exact=True).click()
        expect(page.get_by_role("button", name="Preparing…", exact=True)).to_be_disabled()
        expect(card(fixtures["source"]).get_by_text(
            "Preparation is in flight. Leaving this source does not cancel the save; "
            "inspect the original project's tasks before submitting again.", exact=True,
        )).to_be_visible()
        deadline = time.monotonic() + 10
        while not held and time.monotonic() < deadline:
            page.wait_for_timeout(25)  # Pump route callbacks; bounded by real-save completion.
        assert len(held) == 1, "Actual Prepare response must be captured before newer navigation"
        decision = page.locator("#record-" + fixtures["screening"]["id"])
        expect(decision.get_by_role("heading", name="Synthetic shared title", exact=True)).to_be_visible()
        decision.get_by_role("button", name="Return to this source", exact=True).click()
        expect(card(fixtures["other_source"])).to_be_focused()
        route, value = held.pop()
        # Known-task UI appears before onSaved's refresh completes. Wait through
        # that continuation before asserting navigation, or the oracle can pass
        # early and miss a delayed Review hijack.
        with page.expect_response(lambda response: response.url == workspace_url and response.request.method == "GET"), \
             page.expect_response(lambda response: response.url == tasks_url.removesuffix("/tasks") and response.request.method == "GET"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(value))
        page.wait_for_load_state("networkidle", timeout=10_000)
        page.unroute(tasks_url, held_prepare)
        expect(page.get_by_role("button", name="Open prepared task", exact=True)).to_be_visible()
        expect(page.get_by_role("heading", level=1)).to_have_text("Literature")
        expect(card(fixtures["other_source"])).to_be_focused()
        assert_draft(purpose, locked=True)
        assert writes == [tasks_url] and runs["count"] == 0
        assert len(created) == 1
        assert {task["id"] for task in service.list(project)} == before | set(created)
        page.screenshot(path=str(output / "composer-held-same-page-return.png"), full_page=True)
        checks.append({"check": "Browser held actual Prepare cannot override newer same-page screening-source focus",
                       "status": "PASS", "boundary": "Real local save; response timing controlled, no model"})

        # New App session, explicit new test intent. No previous unknown is cleared.
        legacy_read_start = len(reads)
        page.route(workspace_url, legacy_capabilities)
        screen.open()
        screen.choose(project)
        screen.navigate("Literature")
        legacy_purpose = "Synthetic keyless lost-response draft"
        select_draft(legacy_purpose)
        page.route(tasks_url, lose_keyless_reply)
        page.get_by_role("button", name="Prepare from this abstract", exact=True).click()
        expect(page.get_by_text("The preparation response did not establish whether a task was saved.", exact=False)).to_be_visible()
        source_roundtrip(legacy_purpose, locked=True)
        project_roundtrip(legacy_purpose, locked=True)
        with page.expect_response(lambda response: response.url == tasks_url.removesuffix("/tasks") and response.request.method == "GET"):
            page.get_by_role("button", name="Refresh", exact=True).click()
        page.wait_for_load_state("networkidle", timeout=10_000)
        assert_draft(legacy_purpose, locked=True)
        assert writes == [tasks_url, tasks_url] and runs["count"] == 0
        assert not any("/preparations/" in url for url in reads[legacy_read_start:]), "No keyed lookup invented for legacy reply"
        assert {task["id"] for task in service.list(project)} == before | set(created)
        assert len(created) == 2 and not service.workspace.snapshot(project)["actions"]
        for identity in created:
            pack = service.get(identity)["request"]["research_draft"]["source_pack"]
            assert pack["source_record_id"] == fixtures["source"]["id"]
            assert pack["artifact_id"] == fixtures["artifact"]["id"]
            assert pack["text"] == ABSTRACT
            assert (pack["start"], pack["end"]) == (fixtures["selection"]["start"], fixtures["selection"]["end"])
        assert fixtures["source_path"].read_bytes() == SOURCE.encode("utf-8")
        page.screenshot(path=str(output / "composer-keyless-unknown-roundtrip.png"), full_page=True)
        checks.append({"check": "Browser keyless lost response remains locked across source/project roundtrips and Refresh; no replay",
                       "status": "PASS", "prepare_posts": 2, "run_dispatches": 0,
                       "boundary": "Legacy capability response fixture; actual local save followed by synthetic503, not native provider uncertainty"})
    finally:
        for route, _ in held:
            route.abort()
        page.unroute(tasks_url, held_prepare)
        page.unroute(tasks_url, lose_keyless_reply)
        page.unroute(workspace_url, legacy_capabilities)
        page.unroute(run_url, reject_run)
        page.remove_listener("request", observe)
