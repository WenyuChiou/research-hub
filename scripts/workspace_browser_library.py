"""Candidate-specific literature UI acceptance against the real temporary service.

Synthetic metadata only; saved setup passes are historical fixture declarations,
never provider checks. The browser does not save records or settings here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from types import SimpleNamespace
from urllib.parse import urlsplit

from research_hub.setup_snapshot import save_setup_snapshot


def prepare_library_fixture(workspace):
    if os.environ.get("RESEARCH_HUB_WRITING_ADAPTER", "").strip():
        raise RuntimeError("Library browser fixtures require no external writing adapter")
    project = "library-organization-fixture"
    workspace.create_project(id=project, title="Synthetic library organization",
                             archetype="review", goal="UI acceptance with synthetic metadata only.")
    data = [
        {"title": "Synthetic unclassified record", "category": "  ", "summary": "  ",
         "relevance": "A relevance note must not become a summary.", "reading_level": "abstract"},
        {"title": "Synthetic human record", "category": "human", "summary": "  ",
         "abstract": "An existing synthetic saved abstract.", "reading_level": "abstract"},
        {"title": "Synthetic methods record", "category": "methods",
         "summary": "An existing synthetic saved summary.", "reading_level": "metadata"},
        {"title": "Synthetic model record", "category": "llm", "summary": 0,
         "reading_level": "abstract-snippet"},
    ]
    sources = [workspace.add_record(project, kind="source", data={
        **item, "locator": f"https://example.invalid/library-fixture/{index}",
        "year": 2000 + index, "human_acceptance": "pending",
    }) for index, item in enumerate(data, 1)]
    screening = workspace.add_record(project, kind="screening", data={
        "source_id": sources[1]["id"], "decision": "include",
        "rationale": "Synthetic saved screening only; not reading or identity verification.",
    })
    observed = datetime.now(timezone.utc)
    save_setup_snapshot(workspace.root, SimpleNamespace(components={
        name: {"status": "passed"} for name in ("vault", "zotero", "notebooklm_auth")
    }), observed_at=observed)
    return {"project_id": project, "sources": sources, "screening": screening,
            "observed_at": observed.isoformat().replace("+00:00", "Z")}


def check_library_journey(screen, workspace, checks, output):
    from playwright.sync_api import expect

    fixture = prepare_library_fixture(workspace)
    before = json.dumps(workspace.records(fixture["project_id"]), sort_keys=True)
    page = screen.page
    mutations, external = [], []

    def observe(request):
        if request.url.startswith(screen.base + "/api/") and request.method != "GET":
            mutations.append({"method": request.method, "path": urlsplit(request.url).path})
        if request.url.startswith(("http://", "https://")) and urlsplit(request.url).netloc != urlsplit(screen.base).netloc:
            external.append(request.url)

    page.on("request", observe)
    try:
        page.set_viewport_size({"width": 1440, "height": 1000})
        # A real navigation reloads App's cached project list and setup snapshot.
        screen.open()
        expect(page.locator("html")).to_have_attribute("lang", "en")
        screen.choose(fixture["project_id"])
        screen.navigate("Literature")
        catalog = page.locator(".literature-library")
        expect(catalog).to_have_count(1)
        filters = catalog.get_by_role("group", name="Organize saved material", exact=True)
        rows = catalog.locator("tbody tr")
        labels = (("All saved material", 4), ("Unclassified", 1),
                  ("Missing summary", 2), ("Awaiting screening", 3))
        for label, count in labels:
            button = filters.get_by_role("button", name=f"{label} ({count})", exact=True)
            expect(button).to_be_visible()
            button.click()
            expect(button).to_have_attribute("aria-pressed", "true")
            expect(rows).to_have_count(count)
        expect(rows.get_by_role("button", name="Synthetic human record", exact=True)).to_have_count(0)
        checks.append({"check": "Real library organization counts and views: all4/unclassified1/missing2/awaiting3", "status": "PASS"})

        filters.get_by_role("button", name="Missing summary (2)", exact=True).click()
        category = catalog.get_by_label("Category", exact=True)
        search = catalog.get_by_role("searchbox", name="Search this collection", exact=True)
        category.select_option("llm")
        search.fill("model")
        expect(rows).to_have_count(1)
        expect(rows.get_by_role("button", name="Synthetic model record", exact=True)).to_be_visible()
        search.fill("no synthetic match")
        expect(rows).to_have_count(0)
        expect(catalog.get_by_text("No literature matches these filters.", exact=True)).to_be_visible()
        catalog.get_by_role("button", name="Clear filters", exact=True).click()
        expect(rows).to_have_count(4)
        expect(search).to_have_value("")
        expect(category).to_have_value("")
        expect(filters.get_by_role("button", name="All saved material (4)", exact=True)).to_have_attribute("aria-pressed", "true")
        checks.append({"check": "Real library crossed organization/category/search filters clear together", "status": "PASS"})

        model = rows.get_by_role("button", name="Synthetic model record", exact=True)
        model.click()
        detail = catalog.locator(".catalog-detail")
        expect(detail.get_by_role("heading", name="Synthetic model record", exact=True)).to_be_focused()
        expect(detail.get_by_text("Abstract / source snippets", exact=True)).to_be_visible()
        expect(detail.get_by_text("No summary saved. Preliminary relevance below is not a full-paper summary.", exact=True)).to_be_visible()
        expect(detail.get_by_role("link", name="Open original source", exact=True)).to_have_attribute("href", fixture["sources"][3]["data"]["locator"])
        detail.get_by_role("button", name="Back to selected item in list", exact=True).click()
        expect(model).to_be_focused()
        rows.get_by_role("button", name="Synthetic human record", exact=True).click()
        expect(detail.get_by_text("An existing synthetic saved abstract.", exact=True)).to_be_visible()
        checks.append({"check": "Real detail preserves saved abstract, missing-summary/snippet/source labels and returns focus to the selected row", "status": "PASS"})

        page.set_viewport_size({"width": 1440, "height": 500})
        trigger = page.get_by_role("button", name="Integrations & setup", exact=True)
        bounds = trigger.bounding_box()
        assert bounds and bounds["x"] >= 0 and bounds["y"] >= 0
        assert bounds["x"] + bounds["width"] <= 1441 and bounds["y"] + bounds["height"] <= 501, bounds
        trigger.focus()
        page.keyboard.press("Enter")
        setup = page.get_by_role("dialog", name="Integrations & setup", exact=True)
        expect(setup.get_by_role("heading", name="Integrations & setup", exact=True)).to_be_focused()
        expect(setup.locator("time")).to_have_attribute("datetime", fixture["observed_at"])
        expect(setup.get_by_text("Within the saved-observation display window; historical only", exact=True)).to_be_visible()
        for name in ("Zotero", "Obsidian", "NotebookLM"):
            tool = setup.locator("li.integration-tool").filter(has=page.get_by_role("heading", name=name, exact=True))
            expect(tool.get_by_text("Reported pass (historical)", exact=True)).to_be_visible()
            expect(tool.get_by_text("Not checked", exact=True)).to_be_visible()
        checks.append({"check": "1440x500 setup trigger is fully in view; saved observation time/pass never claims current connection", "status": "PASS", "native_zoom": "not_verified"})

        form = setup.get_by_role("form", name="Zotero library draft", exact=True)
        library_id = form.get_by_role("textbox", name="Numeric library ID", exact=True)
        library_type = form.get_by_role("combobox", name="Library type", exact=True)
        library_id.fill("000123")
        library_type.select_option("user")
        form.get_by_role("button", name="Check format", exact=True).click()
        expect(form.get_by_text("Numeric format is valid. Draft only; not saved and connection not checked.", exact=True)).to_be_visible()
        expect(form.get_by_role("definition").filter(has_text="123")).to_have_count(1)
        form.get_by_role("button", name="Cancel", exact=True).click()
        expect(library_id).to_have_value("")
        expect(library_type).to_have_value("")
        library_id.fill("456")
        library_type.select_option("group")
        setup.get_by_role("button", name="Close setup guidance", exact=True).click()
        expect(trigger).to_be_focused()
        trigger.click()
        expect(library_id).to_have_value("")
        expect(library_type).to_have_value("")
        setup.get_by_role("button", name="Close setup guidance", exact=True).click()
        checks.append({"check": "Real Zotero draft validates locally and Cancel/close/reopen clear ID and type without saving", "status": "PASS"})

        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        trigger.click()
        geometry = setup.bounding_box()
        assert geometry and geometry["x"] >= 0 and geometry["y"] >= 0
        assert geometry["x"] + geometry["width"] <= 391 and geometry["y"] + geometry["height"] <= 845
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(output / "library-organization-390px.png"), full_page=True)
        page.keyboard.press("Escape")
        expect(setup).to_have_count(0)
        expect(trigger).to_be_focused()
        checks.append({"check": "New library and settings have no horizontal overflow at390px and Escape restores trigger focus", "status": "PASS", "native_zoom": "not_verified"})
        assert not mutations, mutations
        assert not external, external
        assert json.dumps(workspace.records(fixture["project_id"]), sort_keys=True) == before
        checks.append({"check": "Organization/detail/setup interactions preserve exact stored source/screening metadata with zero mutation or external requests", "status": "PASS"})
    finally:
        page.remove_listener("request", observe)
