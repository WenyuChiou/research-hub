"""NotebookLMClient: targeted Playwright flows against the live UI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from research_hub.notebooklm.selectors import (
    ADD_SOURCE_BUTTON_ROLE,
    BETWEEN_UPLOADS_MS,
    CREATE_NEW_NOTEBOOK_BUTTON_ROLE,
    GENERATE_AUDIO_BUTTON_ROLE,
    GENERATE_BRIEFING_BUTTON_ROLE,
    GENERATE_MIND_MAP_BUTTON_ROLE,
    GENERATE_VIDEO_BUTTON_ROLE,
    GENERATION_COMPLETE_LINK_CSS,
    GENERATION_PROGRESS_CHIP_TEXT,
    GENERATION_TIMEOUT_MS,
    NOTEBOOK_LIST_URL,
    NOTEBOOK_TILE_BY_NAME_XPATH,
    NOTEBOOK_TITLE_EDITABLE_CSS,
    NOTEBOOK_TITLE_TEXTBOX_ROLE,
    SOURCE_UPLOAD_FILE_INPUT,
    SOURCE_WEBSITE_INSERT_BUTTON_ROLE,
    SOURCE_WEBSITE_TAB_ROLE,
    SOURCE_WEBSITE_URL_INPUT_PLACEHOLDER,
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
            heading.inner_text().strip()
            for heading in self.page.locator("h2").all()
            if heading.inner_text().strip()
        ]

    def open_notebook_by_name(self, name: str) -> NotebookHandle:
        """Open an existing notebook by its visible heading text."""
        self.goto_notebook_list()
        xpath = NOTEBOOK_TILE_BY_NAME_XPATH.format(name=name)
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
        """Create a notebook if needed and attempt to rename it."""
        self.goto_notebook_list()
        role, accessible_name = CREATE_NEW_NOTEBOOK_BUTTON_ROLE
        self.page.get_by_role(role, name=accessible_name).click()
        self.page.wait_for_load_state("networkidle")
        try:
            title_role, title_name = NOTEBOOK_TITLE_TEXTBOX_ROLE
            title_input = self.page.get_by_role(title_role, name=re.compile(title_name, re.I)).first
            title_input.fill(name)
            title_input.press("Enter")
        except Exception:
            editable = self.page.locator(NOTEBOOK_TITLE_EDITABLE_CSS).first
            if editable.count() > 0:
                editable.fill(name)
                editable.press("Enter")
        return NotebookHandle(name=name, url=self.page.url, notebook_id=_parse_notebook_id(self.page.url))

    def open_or_create_notebook(self, name: str) -> NotebookHandle:
        try:
            return self.open_notebook_by_name(name)
        except NotebookLMError:
            return self.create_notebook(name)

    def upload_pdf(self, pdf_path: Path) -> UploadResult:
        """Attach a PDF via NotebookLM's source upload flow."""
        try:
            role, name = ADD_SOURCE_BUTTON_ROLE
            self.page.get_by_role(role, name=name).click()
            self.page.locator(SOURCE_UPLOAD_FILE_INPUT).first.set_input_files(str(pdf_path))
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
            role, name = ADD_SOURCE_BUTTON_ROLE
            self.page.get_by_role(role, name=name).click()
            tab_role, tab_name = SOURCE_WEBSITE_TAB_ROLE
            self.page.get_by_role(tab_role, name=tab_name).click()
            self.page.get_by_placeholder(SOURCE_WEBSITE_URL_INPUT_PLACEHOLDER).fill(url)
            insert_role, insert_name = SOURCE_WEBSITE_INSERT_BUTTON_ROLE
            self.page.get_by_role(insert_role, name=insert_name).click()
            self.page.wait_for_timeout(BETWEEN_UPLOADS_MS)
            return UploadResult(source_kind="url", path_or_url=url, success=True)
        except Exception as exc:
            return UploadResult(source_kind="url", path_or_url=url, success=False, error=str(exc))

    def _trigger_and_wait(self, button_role: tuple[str, str], kind_label: str) -> str:
        """Click a generation button and return the resulting artifact link."""
        role, name = button_role
        button = self.page.get_by_role(role, name=name).first
        if button.count() == 0:
            raise NotebookLMError(
                f"Generation button not found: {kind_label}",
                selector=f"role={role}, name={name}",
                page_url=self.page.url,
            )
        button.click()
        try:
            self.page.wait_for_function(
                f"() => !document.body.innerText.includes({GENERATION_PROGRESS_CHIP_TEXT!r})",
                timeout=GENERATION_TIMEOUT_MS,
            )
        except Exception:
            pass
        links = self.page.locator(GENERATION_COMPLETE_LINK_CSS).all()
        if not links:
            raise NotebookLMError(
                f"No artifact link after {kind_label} generation",
                selector=GENERATION_COMPLETE_LINK_CSS,
                page_url=self.page.url,
            )
        return links[-1].get_attribute("href") or self.page.url

    def trigger_briefing(self) -> str:
        return self._trigger_and_wait(GENERATE_BRIEFING_BUTTON_ROLE, "briefing")

    def trigger_audio_overview(self) -> str:
        return self._trigger_and_wait(GENERATE_AUDIO_BUTTON_ROLE, "audio")

    def trigger_mind_map(self) -> str:
        return self._trigger_and_wait(GENERATE_MIND_MAP_BUTTON_ROLE, "mind_map")

    def trigger_video_overview(self) -> str:
        return self._trigger_and_wait(GENERATE_VIDEO_BUTTON_ROLE, "video")


def _parse_notebook_id(url: str) -> str:
    """Extract the notebook identifier from a NotebookLM URL."""
    match = re.search(r"/notebook/([^/?#]+)", url)
    return match.group(1) if match else ""
