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
    DROP_ZONE_ICON_BUTTON_CSS,
    DROP_ZONE_LINK_ICON_NAME,
    GENERATE_AUDIO_BUTTON_TEXTS,
    GENERATE_BRIEFING_BUTTON_TEXTS,
    GENERATE_MIND_MAP_BUTTON_TEXTS,
    GENERATE_VIDEO_BUTTON_TEXTS,
    GENERATION_ARTIFACT_LINK_CSS,
    GENERATION_TIMEOUT_MS,
    NOTEBOOK_LIST_URL,
    NOTEBOOK_TILE_LINK_CSS,
    NOTEBOOK_TITLE_EDITABLE_CSS,
    NOTEBOOK_TITLE_INPUT_CSS,
    NOTEBOOK_TITLE_SPAN_CSS,
    SOURCE_PANEL_CSS,
    SOURCE_UPLOAD_FILE_INPUT_CSS,
    SOURCE_WEBSITE_INSERT_BUTTON_TEXTS,
    SOURCE_WEBSITE_TAB_TEXTS,
    SOURCE_WEBSITE_URL_INPUT_PLACEHOLDERS,
    URL_DIALOG_SUBMIT_BUTTON_CSS,
    URL_INPUT_TEXTAREA_CSS,
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
        # Angular SPA: networkidle is unreliable because the app keeps
        # polling. Wait for the add-source button directly — it is the
        # element we need next, and it only appears after the notebook
        # view has fully mounted.
        try:
            self.page.locator(ADD_SOURCE_BUTTON_CSS).first.wait_for(
                state="attached", timeout=20_000
            )
        except Exception:
            pass
        return NotebookHandle(name=name, url=self.page.url, notebook_id=_parse_notebook_id(self.page.url))

    def create_notebook(self, name: str) -> NotebookHandle:
        """Create a fresh notebook and rename it via the title input.

        NotebookLM commits a new notebook as soon as you click the
        create grid card. It lands on
        `/notebook/<uuid>?addSource=true` with the upload dialog open.
        The rename element is `<input class="title-input">` inside
        `<editable-project-title>`; fill it directly and press Enter.
        """
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

        # Wait for the notebook to actually commit (URL leaves
        # /notebook/creating once Angular assigns a real UUID).
        for _ in range(20):
            if "/notebook/creating" not in (self.page.url or ""):
                break
            self.page.wait_for_timeout(500)

        try:
            title_input = self.page.locator(NOTEBOOK_TITLE_INPUT_CSS).first
            title_input.wait_for(state="attached", timeout=10_000)
            title_input.fill(name)
            title_input.press("Enter")
            self.page.wait_for_timeout(500)
        except Exception:
            pass
        return NotebookHandle(
            name=name,
            url=self.page.url,
            notebook_id=_parse_notebook_id(self.page.url),
        )

    def open_or_create_notebook(self, name: str) -> NotebookHandle:
        try:
            return self.open_notebook_by_name(name)
        except NotebookLMError:
            return self.create_notebook(name)

    def _click_add_source(self) -> None:
        """Click the Add-source button inside the Source panel.

        Waits up to 15s because NotebookLM is an Angular SPA that loads
        the notebook view asynchronously after tile click, so the button
        may not exist at the moment we enter this method. If the primary
        CSS selector does not resolve, fall back to a localized aria-
        label regex before raising NotebookLMError.
        """
        button = self.page.locator(ADD_SOURCE_BUTTON_CSS).first
        try:
            button.wait_for(state="visible", timeout=15_000)
        except Exception:
            label_regex = re.compile("|".join(re.escape(t) for t in ADD_SOURCE_BUTTON_TEXTS))
            button = self.page.get_by_role("button", name=label_regex).first
            try:
                button.wait_for(state="visible", timeout=5_000)
            except Exception as exc:
                raise NotebookLMError(
                    f"Add-source button not found: {exc}",
                    selector=ADD_SOURCE_BUTTON_CSS,
                    page_url=self.page.url,
                )
        button.click()

    def upload_pdf(self, pdf_path: Path) -> UploadResult:
        """Attach a PDF via NotebookLM's source upload flow.

        NotebookLM does not expose a visible `<input type="file">`; the
        Upload drop-zone button spawns a native OS file chooser. Use
        Playwright's `expect_file_chooser` to intercept the chooser
        and drive it programmatically with `set_files`.

        The Add-source button is only clicked if the upload dialog is
        not already open (for example, the staging view after
        `create_notebook` lands on `?addSource=true` with the dialog
        pre-opened).
        """
        try:
            drop_zone = self.page.locator(DROP_ZONE_ICON_BUTTON_CSS).first
            dialog_open = False
            try:
                drop_zone.wait_for(state="visible", timeout=2_000)
                dialog_open = True
            except Exception:
                pass
            if not dialog_open:
                self._click_add_source()
                drop_zone.wait_for(state="visible", timeout=10_000)

            upload_button = (
                self.page.locator(DROP_ZONE_ICON_BUTTON_CSS)
                .filter(has=self.page.locator("mat-icon", has_text="upload"))
                .first
            )
            try:
                upload_button.wait_for(state="visible", timeout=5_000)
            except Exception:
                upload_button = self.page.locator(SOURCE_UPLOAD_FILE_INPUT_CSS).first
                upload_button.set_input_files(str(pdf_path))
                self.page.wait_for_timeout(BETWEEN_UPLOADS_MS)
                return UploadResult(source_kind="pdf", path_or_url=str(pdf_path), success=True)

            with self.page.expect_file_chooser() as fc_info:
                upload_button.click()
            chooser = fc_info.value
            chooser.set_files(str(pdf_path))

            # Wait for the drop-zone button to disappear, signalling
            # the dialog closed and the source landed.
            try:
                self.page.locator(DROP_ZONE_ICON_BUTTON_CSS).first.wait_for(
                    state="detached", timeout=30_000
                )
            except Exception:
                pass

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
        """Insert a website source through the Add-source dialog.

        Flow (verified against 2026-04-11 zh-TW DOM):
          1. Click the Add-source button (left source panel)
          2. Click the drop-zone icon button whose mat-icon is "link"
          3. Fill the urls textarea via formcontrolname selector
          4. Click the primary submit button (labeled 插入/Insert)
          5. Wait for the dialog to close, indicating the source landed

        Falls back to aria-label / tab-role heuristics if the primary
        CSS selectors do not resolve, so locale variations still work.
        """
        try:
            drop_zone = self.page.locator(DROP_ZONE_ICON_BUTTON_CSS).first
            dialog_open = False
            try:
                drop_zone.wait_for(state="visible", timeout=2_000)
                dialog_open = True
            except Exception:
                pass
            if not dialog_open:
                self._click_add_source()

            link_button = (
                self.page.locator(DROP_ZONE_ICON_BUTTON_CSS)
                .filter(has=self.page.locator("mat-icon", has_text=DROP_ZONE_LINK_ICON_NAME))
                .first
            )
            try:
                link_button.wait_for(state="visible", timeout=10_000)
                link_button.click()
            except Exception:
                tab_regex = re.compile("|".join(re.escape(t) for t in SOURCE_WEBSITE_TAB_TEXTS))
                self.page.get_by_role("tab", name=tab_regex).first.click()

            url_input = self.page.locator(URL_INPUT_TEXTAREA_CSS).first
            try:
                url_input.wait_for(state="visible", timeout=10_000)
            except Exception:
                placeholder_regex = re.compile(
                    "|".join(re.escape(t) for t in SOURCE_WEBSITE_URL_INPUT_PLACEHOLDERS)
                )
                url_input = self.page.get_by_placeholder(placeholder_regex).first
            url_input.fill(url)

            submit_button = self.page.locator(URL_DIALOG_SUBMIT_BUTTON_CSS).first
            try:
                submit_button.wait_for(state="visible", timeout=5_000)
                submit_button.click()
            except Exception:
                insert_regex = re.compile(
                    "|".join(re.escape(t) for t in SOURCE_WEBSITE_INSERT_BUTTON_TEXTS)
                )
                self.page.get_by_role("button", name=insert_regex).first.click()

            # Wait for the dialog to close so the next source upload
            # does not race against the overlay.
            try:
                self.page.locator(URL_INPUT_TEXTAREA_CSS).first.wait_for(
                    state="detached", timeout=15_000
                )
            except Exception:
                pass

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
