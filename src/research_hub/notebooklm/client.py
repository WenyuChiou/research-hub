"""NotebookLMClient: targeted Playwright flows against the live UI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from research_hub.notebooklm.selectors import (
    ADD_SOURCE_BUTTON_CSS,
    ADD_SOURCE_BUTTON_TEXTS,
    ARTIFACT_BUTTON_CONTAINER_CSS,
    ARTIFACT_BUTTON_CREATING_CSS,
    ARTIFACT_BUTTON_CSS,
    BETWEEN_UPLOADS_MS,
    CREATE_NEW_BUTTON_TEXTS,
    CREATE_NEW_GRID_CARD_CSS,
    CREATE_NEW_TOOLBAR_BUTTON_CSS,
    GENERATE_AUDIO_BUTTON_TEXTS,
    GENERATE_BRIEFING_BUTTON_TEXTS,
    GENERATE_MIND_MAP_BUTTON_TEXTS,
    GENERATE_VIDEO_BUTTON_TEXTS,
    GENERATION_ARTIFACT_LINK_CSS,
    GENERATION_TIMEOUT_MS,
    NOTEBOOK_LIST_URL,
    NOTEBOOK_TILE_LINK_CSS,
    NOTEBOOK_TITLE_EDITABLE_CSS,
    NOTEBOOK_TITLE_SPAN_CSS,
    SOURCE_UPLOAD_FILE_INPUT_CSS,
    SOURCE_WEBSITE_INSERT_BUTTON_TEXTS,
    SOURCE_WEBSITE_TAB_TEXTS,
    SOURCE_WEBSITE_URL_INPUT_PLACEHOLDERS,
    notebook_tile_xpath_by_name,
)


class NotebookLMError(Exception):
    """Base error carrying selector and page context for diagnosis."""

    def __init__(
        self,
        message: str,
        *,
        selector: str | None = None,
        page_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.selector = selector
        self.page_url = page_url


@dataclass
class UploadResult:
    source_kind: str
    path_or_url: str
    success: bool
    error: str = ""


@dataclass
class NotebookHandle:
    name: str
    url: str
    notebook_id: str = ""


class NotebookLMClient:
    """NotebookLM flows that operate on an explicit Playwright page."""

    def __init__(self, page) -> None:
        self.page = page

    def goto_notebook_list(self) -> None:
        self.page.goto(NOTEBOOK_LIST_URL)
        self.page.wait_for_load_state("networkidle")

    def list_notebooks(self) -> list[str]:
        """Return visible notebook names from the notebook list page."""
        self.goto_notebook_list()
        return [
            span.inner_text().strip()
            for span in self.page.locator(NOTEBOOK_TITLE_SPAN_CSS).all()
            if span.inner_text().strip()
        ]

    def open_notebook_by_name(self, name: str) -> NotebookHandle:
        """Open an existing notebook by its visible title."""
        self.goto_notebook_list()
        xpath = notebook_tile_xpath_by_name(name)
        locator = self.page.locator(f"xpath={xpath}").first
        if locator.count() == 0:
            raise NotebookLMError(
                f"Notebook not found: {name}",
                selector=xpath,
                page_url=self.page.url,
            )
        locator.click()
        self.page.wait_for_load_state("networkidle")
        return NotebookHandle(name=name, url=self.page.url, notebook_id=_parse_notebook_id(self.page.url))

    def create_notebook(self, name: str) -> NotebookHandle:
        """Create a notebook. Prefer the grid card, fall back to toolbar button."""
        self.goto_notebook_list()
        grid_card = self.page.locator(CREATE_NEW_GRID_CARD_CSS).first
        if grid_card.count() > 0:
            grid_card.click()
        else:
            toolbar = self.page.locator(CREATE_NEW_TOOLBAR_BUTTON_CSS).first
            if toolbar.count() > 0:
                toolbar.click()
            else:
                label_regex = re.compile("|".join(re.escape(t) for t in CREATE_NEW_BUTTON_TEXTS))
                self.page.get_by_role("button", name=label_regex).first.click()
        self.page.wait_for_load_state("networkidle")
        try:
            editable = self.page.locator(NOTEBOOK_TITLE_EDITABLE_CSS).first
            if editable.count() > 0:
                editable.fill(name)
                editable.press("Enter")
        except Exception:
            pass
        return NotebookHandle(name=name, url=self.page.url, notebook_id=_parse_notebook_id(self.page.url))

    def open_or_create_notebook(self, name: str) -> NotebookHandle:
        try:
            return self.open_notebook_by_name(name)
        except NotebookLMError:
            return self.create_notebook(name)

    def _click_add_source(self) -> None:
        """Click the Add-source stretched button inside the Source panel."""
        button = self.page.locator(ADD_SOURCE_BUTTON_CSS).first
        if button.count() == 0:
            label_regex = re.compile("|".join(re.escape(t) for t in ADD_SOURCE_BUTTON_TEXTS))
            button = self.page.get_by_role("button", name=label_regex).first
        if button.count() == 0:
            raise NotebookLMError(
                "Add-source button not found",
                selector=ADD_SOURCE_BUTTON_CSS,
                page_url=self.page.url,
            )
        button.click()

    def upload_pdf(self, pdf_path: Path) -> UploadResult:
        """Attach a PDF via NotebookLM's source upload flow."""
        try:
            self._click_add_source()
            self.page.locator(SOURCE_UPLOAD_FILE_INPUT_CSS).first.set_input_files(str(pdf_path))
            self.page.wait_for_timeout(BETWEEN_UPLOADS_MS)
            return UploadResult(source_kind="pdf", path_or_url=str(pdf_path), success=True)
        except Exception as exc:
            return UploadResult(
                source_kind="pdf",
                path_or_url=str(pdf_path),
                success=False,
                error=str(exc),
            )

    def upload_url(self, url: str) -> UploadResult:
        """Insert a website source using the Website tab."""
        try:
            self._click_add_source()
            tab_regex = re.compile("|".join(re.escape(t) for t in SOURCE_WEBSITE_TAB_TEXTS))
            self.page.get_by_role("tab", name=tab_regex).first.click()
            placeholder_regex = re.compile(
                "|".join(re.escape(t) for t in SOURCE_WEBSITE_URL_INPUT_PLACEHOLDERS)
            )
            self.page.get_by_placeholder(placeholder_regex).first.fill(url)
            insert_regex = re.compile("|".join(re.escape(t) for t in SOURCE_WEBSITE_INSERT_BUTTON_TEXTS))
            self.page.get_by_role("button", name=insert_regex).first.click()
            self.page.wait_for_timeout(BETWEEN_UPLOADS_MS)
            return UploadResult(source_kind="url", path_or_url=url, success=True)
        except Exception as exc:
            return UploadResult(source_kind="url", path_or_url=url, success=False, error=str(exc))

    def _find_artifact_container(self, label_texts: tuple[str, ...]):
        """Find the `.create-artifact-button-container` whose inner button matches any label."""
        label_regex = re.compile("|".join(re.escape(t) for t in label_texts))
        button = self.page.get_by_role("button", name=label_regex).first
        if button.count() == 0:
            return None
        container = button.locator(f"xpath=ancestor::*[contains(concat(' ', @class, ' '), ' create-artifact-button-container ')][1]")
        if container.count() == 0:
            return None
        return {"button": button, "container": container}

    def _trigger_and_wait(self, label_texts: tuple[str, ...], kind_label: str) -> str:
        """Click an artifact-create button and wait for the creating class to clear."""
        found = self._find_artifact_container(label_texts)
        if found is None:
            raise NotebookLMError(
                f"Generation button not found: {kind_label}",
                selector=f"aria-label~={label_texts}",
                page_url=self.page.url,
            )
        found["button"].click()
        try:
            self.page.wait_for_function(
                f"""() => !document.querySelector({ARTIFACT_BUTTON_CREATING_CSS!r})""",
                timeout=GENERATION_TIMEOUT_MS,
            )
        except Exception:
            pass
        links = self.page.locator(GENERATION_ARTIFACT_LINK_CSS).all()
        if not links:
            return self.page.url
        return links[-1].get_attribute("href") or self.page.url

    def trigger_briefing(self) -> str:
        return self._trigger_and_wait(GENERATE_BRIEFING_BUTTON_TEXTS, "briefing")

    def trigger_audio_overview(self) -> str:
        return self._trigger_and_wait(GENERATE_AUDIO_BUTTON_TEXTS, "audio")

    def trigger_mind_map(self) -> str:
        return self._trigger_and_wait(GENERATE_MIND_MAP_BUTTON_TEXTS, "mind_map")

    def trigger_video_overview(self) -> str:
        return self._trigger_and_wait(GENERATE_VIDEO_BUTTON_TEXTS, "video")


def _parse_notebook_id(url: str) -> str:
    """Extract the notebook identifier from a NotebookLM URL."""
    match = re.search(r"/notebook/([^/?#]+)", url)
    return match.group(1) if match else ""
