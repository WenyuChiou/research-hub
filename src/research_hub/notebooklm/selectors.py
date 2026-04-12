"""NotebookLM UI selectors — one place for every DOM target.

NotebookLM is an Angular + Material Design SPA. The ``_ngcontent-ng-*``
attributes are regenerated on every build and are NOT stable — do not
target them. Stable targets (in descending order of durability):

  1. Custom element tag names (``project-button``, ``welcome-page``,
     ``page-header``, ``project-grid``, ``mat-card``, ``mat-icon``)
  2. Semantic CSS classes scoped to the app
     (``create-new-button``, ``create-new-action-button``,
     ``project-button-title``, ``project-button-card``,
     ``create-new-label``, ``extendable-label``)
  3. ``aria-label`` text — localised but stable within a locale
  4. Href patterns — ``a[href*='/notebook/']`` identifies every
     notebook tile regardless of layout
  5. Material data-attributes (``data-mat-icon-type``) — only if the
     icon name is distinctive

When Google ships a UI update:

  1. Run ``research-hub notebooklm login --cdp --keep-open``.
  2. F12 → Elements → pick the target control.
  3. Update the constant in this file, not the calling code.
  4. Re-run the relevant command with ``--dry-run`` to verify.

The selectors below were verified against the 2026-04-11 NotebookLM
UI with a Traditional-Chinese locale. For other locales, set the
alternate-locale strings via environment variables (see
``_localized_text`` below).
"""

from __future__ import annotations

import os


# --- URLs ---------------------------------------------------------------
NOTEBOOKLM_HOME = "https://notebooklm.google.com/"
NOTEBOOK_LIST_URL = "https://notebooklm.google.com/"
NOTEBOOK_URL_TEMPLATE = "https://notebooklm.google.com/notebook/{notebook_id}"
NOTEBOOK_URL_PATTERN = "/notebook/"


# --- Localized strings --------------------------------------------------
# The app language follows the user's Google account settings. Override
# via env var if the auto-detected locale is wrong.
_LOCALE = os.environ.get("RESEARCH_HUB_NLM_LOCALE", "zh-TW")


def _localized_text(key: str) -> tuple[str, ...]:
    """Return all known localized strings for ``key``.

    Playwright's ``get_by_role(name=)`` can accept a regex that matches
    any of the strings, which makes the client robust to language
    fallbacks. Add new locale variants here as users report them.
    """
    table: dict[str, dict[str, tuple[str, ...]]] = {
        "create_new_notebook": {
            "zh-TW": ("建立新的筆記本", "新建"),
            "zh-CN": ("创建新的记事本", "新建"),
            "en": ("Create new notebook", "New notebook", "+ New"),
            "ja": ("新しいノートブックを作成", "新規"),
        },
        "add_source": {
            "zh-TW": ("新增來源",),
            "zh-CN": ("添加来源",),
            "en": ("Add source",),
            "ja": ("ソースを追加",),
        },
        "website_tab": {
            "zh-TW": ("網站", "網址"),
            "zh-CN": ("网站", "网址"),
            "en": ("Website", "URL", "Link"),
            "ja": ("ウェブサイト",),
        },
        "url_input_placeholder": {
            "zh-TW": ("貼上網址", "輸入網址"),
            "zh-CN": ("粘贴网址",),
            "en": ("Paste URL", "Enter URL"),
            "ja": ("URLを貼り付け",),
        },
        "insert_source_button": {
            "zh-TW": ("插入", "新增"),
            "zh-CN": ("插入",),
            "en": ("Insert", "Add"),
            "ja": ("挿入",),
        },
        "studio_panel": {
            "zh-TW": ("Studio", "工作室"),
            "zh-CN": ("Studio", "工作室"),
            "en": ("Studio",),
            "ja": ("Studio",),
        },
        "briefing_button": {
            "zh-TW": ("簡報文件", "大綱"),
            "zh-CN": ("摘要文档",),
            "en": ("Briefing doc", "Briefing document"),
            "ja": ("概要ドキュメント",),
        },
        "audio_button": {
            "zh-TW": ("音訊總覽", "音訊摘要"),
            "zh-CN": ("音频概览",),
            "en": ("Audio Overview", "Audio overview"),
            "ja": ("音声概要",),
        },
        "mind_map_button": {
            "zh-TW": ("心智圖",),
            "zh-CN": ("思维导图",),
            "en": ("Mind map", "Mind Map"),
            "ja": ("マインドマップ",),
        },
        "video_button": {
            "zh-TW": ("影片總覽", "影片摘要"),
            "zh-CN": ("视频概览",),
            "en": ("Video Overview", "Video overview"),
            "ja": ("動画概要",),
        },
    }
    primary = table.get(key, {}).get(_LOCALE, ())
    english = table.get(key, {}).get("en", ())
    seen: set[str] = set()
    out: list[str] = []
    for text in (*primary, *english):
        if text not in seen:
            seen.add(text)
            out.append(text)
    return tuple(out)


# --- Notebook list page -------------------------------------------------
# Every notebook tile on the home page is a `<a>` inside a
# `<project-button>` custom element, with an `href` of the form
# `/notebook/<uuid>`. The visible title sits in a `<span>` with class
# `project-button-title`. This combination lets us click a tile by
# its human name without depending on Angular-scoped attributes.
NOTEBOOK_TILE_LINK_CSS = "project-button a[href*='/notebook/']"
NOTEBOOK_TILE_CARD_CSS = "project-button mat-card.project-button-card"
NOTEBOOK_TITLE_SPAN_CSS = "span.project-button-title"

# XPath to click a notebook by its visible title. The span holding the
# title is inside the anchor via aria-labelledby, so we walk up to the
# ancestor anchor that has the /notebook/ href.
def notebook_tile_xpath_by_name(name: str) -> str:
    """Build an XPath that matches a notebook tile with exact visible name."""
    escaped = _xpath_literal(name)
    return (
        f"//span[contains(@class, 'project-button-title')"
        f" and normalize-space(string()) = {escaped}]"
        f"/ancestor::project-button//a[contains(@href, '/notebook/')]"
    )


def _xpath_literal(text: str) -> str:
    """Safely embed arbitrary text as an XPath string literal."""
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    parts = text.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


# --- Create-new-notebook targets ----------------------------------------
# Two visual variants ship on the home page:
#   1. Toolbar button: `<button class="create-new-button">` with
#      visible label "新建" / "New" inside a `.create-new-label` span
#      and an `aria-label` matching the full localized string.
#   2. Grid card: `<mat-card class="create-new-action-button">` with
#      role=button and visible text "建立新的筆記本" / "Create new
#      notebook" inside a `.mat-title-large` span.
# Both route to the same create flow. Try the grid card first (more
# visible, fewer overlapping tooltips), fall back to the toolbar.
CREATE_NEW_GRID_CARD_CSS = "mat-card.create-new-action-button"
CREATE_NEW_TOOLBAR_BUTTON_CSS = "button.create-new-button"
CREATE_NEW_BUTTON_TEXTS = _localized_text("create_new_notebook")


# --- Notebook title textbox (shown after creating a new notebook) -----
# On entering a fresh notebook the title row has a contenteditable
# element or a Material textbox. Not observed yet in the live DOM
# snapshot — update after the first `create_notebook` flow runs.
NOTEBOOK_TITLE_TEXTBOX_ROLE = ("textbox", None)
NOTEBOOK_TITLE_EDITABLE_CSS = "[contenteditable='true']"


# --- Inside a notebook: source panel -----------------------------------
# Verified against 2026-04-11 live DOM dump from "Behavioral Science &
# Decision Theory" notebook (zh-TW locale). The add-source control is a
# Material `mat-stroked-button` sitting inside the left source panel:
#   <button mat-stroked-button mattooltip="新增來源" aria-label="新增來源"
#           class="mdc-button ... add-source-button ...">
# The stable anchors are the semantic class `add-source-button` and the
# localized aria-label. `source-stretched-button` was an earlier name
# that no longer exists in the live DOM and is intentionally not listed.
SOURCE_PANEL_CSS = "source-picker"
SOURCE_PANEL_CONTENT_CSS = "source-picker .contents"
ADD_SOURCE_BUTTON_CSS = "button.add-source-button"
ADD_SOURCE_BUTTON_TEXTS = _localized_text("add_source")

# The upload dialog opens a Material dialog with a hidden file input
# and a grid of `drop-zone-icon-button` controls, one per source type.
# The Website / URL one is identified by a child `<mat-icon>link</mat-icon>`
# (the Material icon name, not the visible text). After clicking it the
# dialog transitions to a URL-input view with a textarea whose form
# control name is `urls`, and a primary submit button labeled
# "插入" / "Insert".
SOURCE_UPLOAD_FILE_INPUT_CSS = "input[type='file']"
DROP_ZONE_ICON_BUTTON_CSS = "button.drop-zone-icon-button"
DROP_ZONE_LINK_ICON_NAME = "link"
URL_INPUT_TEXTAREA_CSS = 'textarea[formcontrolname="urls"]'
URL_DIALOG_SUBMIT_BUTTON_CSS = "button[mat-flat-button][color='primary']"
SOURCE_WEBSITE_TAB_TEXTS = _localized_text("website_tab")
SOURCE_WEBSITE_URL_INPUT_PLACEHOLDERS = _localized_text("url_input_placeholder")
SOURCE_WEBSITE_INSERT_BUTTON_TEXTS = _localized_text("insert_source_button")


# --- Studio panel (generation triggers) --------------------------------
# Verified against 2026-04-11 live DOM. The right-hand Studio panel is
# a `<studio-panel>` element containing one `<create-artifact-button>`
# per generation type, wrapped in `.create-artifact-button-container`.
# Each container has a distinct color class (blue/green/pink/yellow/
# cyan/orange) but the STABLE identifier is the `aria-label` on the
# inner button matching the localized generation name.
#
# Layout:
#   <studio-panel>
#     <div class="create-artifact-buttons-container">
#       <div class="create-artifact-button-container">
#         <create-artifact-button>
#           <button aria-label="音訊總覽">...</button>
#   ...
#
# While a generation is running, the container gains the class
# `create-artifact-button-creating` — poll its absence to detect
# completion.
STUDIO_PANEL_CSS = "studio-panel"
STUDIO_PANEL_TEXTS = _localized_text("studio_panel")
ARTIFACT_BUTTONS_CONTAINER_CSS = ".create-artifact-buttons-container"
ARTIFACT_BUTTON_CONTAINER_CSS = ".create-artifact-button-container"
ARTIFACT_BUTTON_CREATING_CSS = ".create-artifact-button-creating"
ARTIFACT_BUTTON_CSS = "create-artifact-button button"

GENERATE_BRIEFING_BUTTON_TEXTS = _localized_text("briefing_button")
GENERATE_AUDIO_BUTTON_TEXTS = _localized_text("audio_button")
GENERATE_MIND_MAP_BUTTON_TEXTS = _localized_text("mind_map_button")
GENERATE_VIDEO_BUTTON_TEXTS = _localized_text("video_button")

# Generation progress indicator. Preferred signal is the
# `.create-artifact-button-creating` CSS class on the container;
# the text-based chip is a fallback for locales not yet mapped.
GENERATION_PROGRESS_CHIP_TEXTS = ("產生中", "Generating", "生成中", "生成")
GENERATION_ARTIFACT_LINK_CSS = "a[href*='/notebook/']"


# --- Timeouts (ms) ------------------------------------------------------
NAV_TIMEOUT_MS = 30_000
UPLOAD_TIMEOUT_MS = 120_000
GENERATION_TIMEOUT_MS = 300_000
BETWEEN_UPLOADS_MS = 2_000


# --- Legacy constants kept for backwards compat with pre-v0.4.1 tests --
# Old code imported ``NOTEBOOK_TILE_BY_NAME_XPATH``,
# ``CREATE_NEW_NOTEBOOK_BUTTON_ROLE``, ``ADD_SOURCE_BUTTON_ROLE``,
# ``SOURCE_WEBSITE_TAB_ROLE``, ``SOURCE_WEBSITE_URL_INPUT_PLACEHOLDER``,
# ``SOURCE_WEBSITE_INSERT_BUTTON_ROLE``, ``SOURCE_LIST_ITEM_ROLE``,
# ``STUDIO_PANEL_ROLE``, ``GENERATE_*_BUTTON_ROLE``,
# ``GENERATION_PROGRESS_CHIP_TEXT``, ``GENERATION_COMPLETE_LINK_CSS``.
# Provide compatible aliases so the client layer keeps working while
# it is gradually rewritten to use the new (text-list) constants.
NOTEBOOK_TILE_BY_NAME_XPATH = notebook_tile_xpath_by_name
CREATE_NEW_NOTEBOOK_BUTTON_ROLE = ("button", CREATE_NEW_BUTTON_TEXTS[0])
ADD_SOURCE_BUTTON_ROLE = ("button", ADD_SOURCE_BUTTON_TEXTS[0])
SOURCE_WEBSITE_TAB_ROLE = ("tab", SOURCE_WEBSITE_TAB_TEXTS[0])
SOURCE_WEBSITE_URL_INPUT_PLACEHOLDER = SOURCE_WEBSITE_URL_INPUT_PLACEHOLDERS[0]
SOURCE_WEBSITE_INSERT_BUTTON_ROLE = ("button", SOURCE_WEBSITE_INSERT_BUTTON_TEXTS[0])
SOURCE_LIST_ITEM_ROLE = ("listitem", None)
SOURCE_UPLOAD_FILE_INPUT = SOURCE_UPLOAD_FILE_INPUT_CSS
STUDIO_PANEL_ROLE = ("region", STUDIO_PANEL_TEXTS[0])
GENERATE_BRIEFING_BUTTON_ROLE = ("button", GENERATE_BRIEFING_BUTTON_TEXTS[0])
GENERATE_AUDIO_BUTTON_ROLE = ("button", GENERATE_AUDIO_BUTTON_TEXTS[0])
GENERATE_MIND_MAP_BUTTON_ROLE = ("button", GENERATE_MIND_MAP_BUTTON_TEXTS[0])
GENERATE_VIDEO_BUTTON_ROLE = ("button", GENERATE_VIDEO_BUTTON_TEXTS[0])
GENERATION_PROGRESS_CHIP_TEXT = GENERATION_PROGRESS_CHIP_TEXTS[0]
GENERATION_COMPLETE_LINK_CSS = GENERATION_ARTIFACT_LINK_CSS
