"""NotebookLM UI selectors: one place for every DOM target.

NotebookLM is a Google product with no stable DOM API. Every selector
here can break when Google changes the UI. When that happens:

1. Run `research-hub notebooklm login` and sign in.
2. Open the notebook list manually and inspect the target control.
3. Update the constant in this file, not in the calling code.
4. Re-run `research-hub notebooklm upload --cluster <slug> --dry-run`
   to verify the new selector works.

Selectors are layered:
- URLs: stable-ish base URLs for navigation
- Roles: prefer ARIA roles over class names
- Test IDs: use if Google adds them
- Fallback CSS/XPath: last resort and most fragile
"""

from __future__ import annotations

# --- URLs ---------------------------------------------------------------
NOTEBOOKLM_HOME = "https://notebooklm.google.com/"
NOTEBOOK_LIST_URL = "https://notebooklm.google.com/"
NOTEBOOK_URL_TEMPLATE = "https://notebooklm.google.com/notebook/{notebook_id}"

# --- Notebook list page -------------------------------------------------
NOTEBOOK_TILE_BY_NAME_XPATH = "//h2[contains(., {name!r})]/ancestor::*[@role='button'][1]"
CREATE_NEW_NOTEBOOK_BUTTON_ROLE = ("button", "Create new notebook")
NOTEBOOK_TITLE_TEXTBOX_ROLE = ("textbox", "title")
NOTEBOOK_TITLE_EDITABLE_CSS = "[contenteditable='true']"

# --- Inside a notebook --------------------------------------------------
ADD_SOURCE_BUTTON_ROLE = ("button", "Add source")
SOURCE_UPLOAD_FILE_INPUT = "input[type='file']"
SOURCE_WEBSITE_TAB_ROLE = ("tab", "Website")
SOURCE_WEBSITE_URL_INPUT_PLACEHOLDER = "Paste URL"
SOURCE_WEBSITE_INSERT_BUTTON_ROLE = ("button", "Insert")
SOURCE_LIST_ITEM_ROLE = ("listitem", None)

# --- Studio panel (generation triggers) --------------------------------
STUDIO_PANEL_ROLE = ("region", "Studio")
GENERATE_BRIEFING_BUTTON_ROLE = ("button", "Briefing doc")
GENERATE_AUDIO_BUTTON_ROLE = ("button", "Audio Overview")
GENERATE_MIND_MAP_BUTTON_ROLE = ("button", "Mind map")
GENERATE_VIDEO_BUTTON_ROLE = ("button", "Video Overview")

# Status indicators for generation. Google shows a progress chip while
# the AI is thinking. When that chip disappears and an artifact card
# appears in the Studio panel, generation is done.
GENERATION_PROGRESS_CHIP_TEXT = "Generating"
GENERATION_COMPLETE_LINK_CSS = "a[href*='/notebook/']"

# --- Timeouts (ms) ------------------------------------------------------
NAV_TIMEOUT_MS = 30_000
UPLOAD_TIMEOUT_MS = 120_000
GENERATION_TIMEOUT_MS = 300_000
BETWEEN_UPLOADS_MS = 2_000
