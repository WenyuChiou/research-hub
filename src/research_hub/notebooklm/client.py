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
    ARTIFACT_LIBRARY_EMPTY_STATE_CSS,
    ARTIFACT_LIBRARY_ITEM_CSS,
    ARTIFACT_STRETCHED_BUTTON_CSS,
    ARTIFACT_TITLE_SPAN_CSS,
    AUDIO_PRESETS,
    BETWEEN_UPLOADS_MS,
    BRIEFING_PRESETS,
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
    MIND_MAP_PRESETS,
    NOTEBOOK_LIST_URL,
    NOTEBOOK_SUMMARY_CONTENT_CSS,
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
    VIDEO_PRESETS,
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


@dataclass
class BriefingArtifact:
    """Plain-text briefing extracted from a notebook's summary panel."""

    notebook_name: str
    notebook_url: str
    notebook_id: str
    text: str
    titles: list[str]  # titles of saved briefings in the studio panel
    source_count: int = 0


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
        """Find the artifact tile whose aria-label matches any localized name.

        Studio-panel artifact tiles are `<div role="button">` elements
        with class `create-artifact-button-container` and an
        `aria-label` containing the localized artifact name (e.g.
        "報告" for Briefing doc, "語音摘要" for Audio Overview).
        Playwright's `get_by_role` accessible-name computation does
        not always align with the raw aria-label, so we target the
        attribute directly via CSS.
        """
        for text in label_texts:
            selector = f'.create-artifact-button-container[aria-label="{text}"]'
            container = self.page.locator(selector).first
            try:
                container.wait_for(state="attached", timeout=5_000)
                return container
            except Exception:
                continue
        return None

    def _click_preset_if_present(self, preset_texts: tuple[str, ...]) -> bool:
        """After clicking an artifact tile, try to click the default preset.

        Some artifact types (Report, Audio) open a sub-dialog with
        preset options (e.g., 簡介文件 / 研讀指南 / 網誌文章 for
        Report). Click the first one found. Returns True if a preset
        was clicked, False if the sub-dialog was not detected (meaning
        generation started directly).
        """
        for text in preset_texts:
            try:
                preset = self.page.locator(f'[aria-label="{text}"]').first
                preset.wait_for(state="visible", timeout=3_000)
                preset.click()
                return True
            except Exception:
                continue
        return False

    def _wait_for_generation(self, timeout_ms: int = 45_000) -> None:
        """Wait for the artifact library to gain content.

        If the library shows the empty-state placeholder, wait for it
        to detach. Otherwise, wait for the child count of
        `<artifact-library>` to increase (handles notebooks that
        already have generated artifacts). Falls back to a fixed sleep
        when detection fails.
        """
        empty = self.page.locator(ARTIFACT_LIBRARY_EMPTY_STATE_CSS).first
        try:
            empty.wait_for(state="attached", timeout=2_000)
            empty.wait_for(state="detached", timeout=timeout_ms)
            return
        except Exception:
            pass
        try:
            baseline = self.page.evaluate(
                "() => document.querySelector('artifact-library')?.children.length ?? 0"
            )
            self.page.wait_for_function(
                f"() => (document.querySelector('artifact-library')?.children.length ?? 0) > {baseline}",
                timeout=timeout_ms,
            )
        except Exception:
            self.page.wait_for_timeout(5_000)

    def _trigger_and_wait(
        self,
        label_texts: tuple[str, ...],
        kind_label: str,
        preset_texts: tuple[str, ...] = (),
    ) -> str:
        """Click an artifact tile, optionally pick a preset, and wait for completion."""
        container = self._find_artifact_container(label_texts)
        if container is None:
            raise NotebookLMError(
                f"Generation button not found: {kind_label}",
                selector=f"aria-label in {label_texts}",
                page_url=self.page.url,
            )
        container.click()
        if preset_texts:
            self._click_preset_if_present(preset_texts)
        self._wait_for_generation(timeout_ms=30_000)
        return self.page.url

    def trigger_briefing(self) -> str:
        return self._trigger_and_wait(GENERATE_BRIEFING_BUTTON_TEXTS, "briefing", BRIEFING_PRESETS)

    def download_briefing(self, handle: NotebookHandle) -> BriefingArtifact:
        """Read the latest briefing summary text from an open notebook.

        NotebookLM auto-renders the most recent briefing into the chat
        panel empty state at `span.notebook-summary .summary-content`.
        We read it directly from the DOM (no clipboard juggling, no
        locale dependence). The studio-panel artifact tile titles are
        also collected so the caller can show what was generated.

        Raises NotebookLMError if no summary content is found, which
        means the notebook has no generated briefings yet.

        Caller contract: the notebook page must already be open. Use
        ``open_notebook_by_name`` (which waits for the notebook view to
        mount) before calling this method.
        """
        summary = self.page.locator(NOTEBOOK_SUMMARY_CONTENT_CSS).first
        try:
            summary.wait_for(state="attached", timeout=15_000)
        except Exception as exc:
            raise NotebookLMError(
                "No briefing summary found on notebook page. "
                "Generate one first via `notebooklm generate --type brief`.",
                selector=NOTEBOOK_SUMMARY_CONTENT_CSS,
                page_url=self.page.url,
            ) from exc

        try:
            text = summary.inner_text().strip()
        except Exception as exc:
            raise NotebookLMError(
                f"Briefing summary element present but unreadable: {exc}",
                selector=NOTEBOOK_SUMMARY_CONTENT_CSS,
                page_url=self.page.url,
            ) from exc

        if not text:
            raise NotebookLMError(
                "Briefing summary element is empty.",
                selector=NOTEBOOK_SUMMARY_CONTENT_CSS,
                page_url=self.page.url,
            )

        titles: list[str] = []
        try:
            for title_el in self.page.locator(ARTIFACT_TITLE_SPAN_CSS).all():
                try:
                    value = title_el.inner_text().strip()
                except Exception:
                    continue
                if value and value not in titles:
                    titles.append(value)
        except Exception:
            pass

        source_count = 0
        try:
            source_count = self.page.evaluate(
                "() => document.querySelectorAll('source-list-item, "
                "[role=\"listitem\"][data-source-id]').length"
            )
        except Exception:
            pass

        return BriefingArtifact(
            notebook_name=handle.name,
            notebook_url=handle.url,
            notebook_id=handle.notebook_id,
            text=text,
            titles=titles,
            source_count=int(source_count or 0),
        )

    def trigger_audio_overview(self) -> str:
        return self._trigger_and_wait(GENERATE_AUDIO_BUTTON_TEXTS, "audio", AUDIO_PRESETS)

    def trigger_mind_map(self) -> str:
        return self._trigger_and_wait(GENERATE_MIND_MAP_BUTTON_TEXTS, "mind_map", MIND_MAP_PRESETS)

    def trigger_video_overview(self) -> str:
        return self._trigger_and_wait(GENERATE_VIDEO_BUTTON_TEXTS, "video", VIDEO_PRESETS)


def _parse_notebook_id(url: str) -> str:
    """Extract the notebook identifier from a NotebookLM URL."""
    match = re.search(r"/notebook/([^/?#]+)", url)
    return match.group(1) if match else ""
