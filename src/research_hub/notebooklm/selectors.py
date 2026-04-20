"""NotebookLM UI selectors: one place for every DOM target."""

from __future__ import annotations

import os


NOTEBOOKLM_HOME = "https://notebooklm.google.com/"
NOTEBOOK_LIST_URL = "https://notebooklm.google.com/"
NOTEBOOK_URL_TEMPLATE = "https://notebooklm.google.com/notebook/{notebook_id}"
NOTEBOOK_URL_PATTERN = "/notebook/"

_LOCALE = os.environ.get("RESEARCH_HUB_NLM_LOCALE", "zh-TW")


def _localized_text(key: str) -> tuple[str, ...]:
    """Return all known localized strings for ``key``."""
    table: dict[str, dict[str, tuple[str, ...]]] = {
        "create_new_notebook": {
            "zh-TW": ("建立新的記事本", "建立", "新建記事本"),
            "zh-CN": ("新建笔记本", "新建", "创建"),
            "en": ("Create new notebook", "New notebook", "+ New"),
            "ja": ("新しいノートブックを作成", "新規"),
            "ko": ("새 노트북 만들기", "새 노트북"),
            "es": ("Crear cuaderno", "Nuevo cuaderno"),
            "fr": ("Creer un notebook", "Nouveau notebook"),
            "de": ("Neues Notebook erstellen", "Neues Notebook"),
        },
        "add_source": {
            "zh-TW": ("新增來源", "新增資料來源", "新增資料"),
            "zh-CN": ("添加来源", "添加资料来源", "添加资料"),
            "en": ("Add source",),
            "ja": ("ソースを追加",),
            "ko": ("소스 추가",),
            "es": ("Anadir fuente",),
            "fr": ("Ajouter une source",),
            "de": ("Quelle hinzufugen",),
        },
        "website_tab": {
            "zh-TW": ("網站", "網址"),
            "zh-CN": ("网站", "网址"),
            "en": ("Website", "URL", "Link"),
            "ja": ("ウェブサイト", "URL", "リンク"),
            "ko": ("웹사이트", "URL", "링크"),
            "es": ("Sitio web", "URL", "Enlace"),
            "fr": ("Site Web", "URL", "Lien"),
            "de": ("Webseite", "URL", "Link"),
        },
        "url_input_placeholder": {
            "zh-TW": ("貼上網址", "輸入網址"),
            "zh-CN": ("粘贴网址", "输入网址"),
            "en": ("Paste URL", "Enter URL"),
            "ja": ("URLを貼り付け", "URLを入力"),
            "ko": ("URL 붙여넣기", "URL 입력"),
            "es": ("Pega la URL", "Introduce la URL"),
            "fr": ("Coller l'URL", "Saisir l'URL"),
            "de": ("URL einfugen", "URL eingeben"),
        },
        "insert_source_button": {
            "zh-TW": ("插入", "新增"),
            "zh-CN": ("插入", "添加"),
            "en": ("Insert", "Add"),
            "ja": ("挿入", "追加"),
            "ko": ("삽입", "추가"),
            "es": ("Insertar", "Agregar"),
            "fr": ("Inserer", "Ajouter"),
            "de": ("Einfugen", "Hinzufugen"),
        },
        "studio_panel": {
            "zh-TW": ("Studio", "工作室", "已生成的內容"),
            "zh-CN": ("Studio", "工作室", "已生成的内容"),
            "en": ("Studio",),
            "ja": ("Studio",),
            "ko": ("Studio", "스튜디오"),
            "es": ("Studio", "Estudio"),
            "fr": ("Studio",),
            "de": ("Studio",),
        },
        "briefing_button": {
            "zh-TW": ("報告", "簡介文件", "簡報文件", "Briefing doc"),
            "zh-CN": ("报告", "简报文档", "简介文档", "Briefing doc"),
            "en": ("Report", "Briefing doc", "Briefing document"),
            "ja": ("レポート", "ブリーフィング ドキュメント"),
            "ko": ("보고서", "브리핑 문서"),
            "es": ("Informe", "Documento informativo"),
            "fr": ("Rapport", "Document de synthese"),
            "de": ("Bericht", "Briefing-Dokument"),
        },
        "audio_button": {
            "zh-TW": ("語音摘要", "語音概覽", "語音", "Audio Overview"),
            "zh-CN": ("语音概览", "音频概览", "语音", "Audio Overview"),
            "en": ("Audio Overview", "Audio overview"),
            "ja": ("音声概要",),
            "ko": ("오디오 개요",),
            "es": ("Resumen de audio",),
            "fr": ("Vue d'ensemble audio",),
            "de": ("Audio-Uberblick",),
        },
        "mind_map_button": {
            "zh-TW": ("心智圖", "Mind map"),
            "zh-CN": ("思维导图", "Mind map"),
            "en": ("Mind map", "Mind Map"),
            "ja": ("マインドマップ",),
            "ko": ("마인드맵",),
            "es": ("Mapa mental",),
            "fr": ("Carte mentale",),
            "de": ("Mindmap",),
        },
        "video_button": {
            "zh-TW": ("影片摘要", "影片概覽", "影片", "Video Overview"),
            "zh-CN": ("视频概览", "视频", "Video Overview"),
            "en": ("Video Overview", "Video overview"),
            "ja": ("動画概要",),
            "ko": ("비디오 개요",),
            "es": ("Resumen en video",),
            "fr": ("Vue d'ensemble video",),
            "de": ("Video-Uberblick",),
        },
        "slides_button": {
            "zh-TW": ("蝪∪",),
            "zh-CN": ("幻灯片", "撟餌??"),
            "en": ("Slides",),
            "ja": ("スライド",),
            "ko": ("슬라이드",),
            "es": ("Diapositivas",),
            "fr": ("Diapositives",),
            "de": ("Folien",),
        },
        "quiz_button": {
            "zh-TW": ("皜祇?",),
            "zh-CN": ("测验", "瘚?"),
            "en": ("Quiz",),
            "ja": ("クイズ",),
            "ko": ("퀴즈",),
            "es": ("Cuestionario",),
            "fr": ("Quiz",),
            "de": ("Quiz",),
        },
        "flashcards_button": {
            "zh-TW": ("摮貊???",),
            "zh-CN": ("抽认卡", "摮虫???"),
            "en": ("Flashcards",),
            "ja": ("フラッシュカード",),
            "ko": ("플래시카드",),
            "es": ("Tarjetas",),
            "fr": ("Fiches memoire",),
            "de": ("Karteikarten",),
        },
        "data_table_button": {
            "zh-TW": ("鞈?銵?",),
            "zh-CN": ("数据表", "?唳銵?"),
            "en": ("Data Table", "Data table"),
            "ja": ("データテーブル",),
            "ko": ("데이터 표",),
            "es": ("Tabla de datos",),
            "fr": ("Tableau de donnees",),
            "de": ("Datentabelle",),
        },
        "infographic_button": {
            "zh-TW": ("鞈??”",),
            "zh-CN": ("信息图", "靽⊥??"),
            "en": ("Infographic",),
            "ja": ("インフォグラフィック",),
            "ko": ("인포그래픽",),
            "es": ("Infografia",),
            "fr": ("Infographie",),
            "de": ("Infografik",),
        },
        "briefing_preset": {
            "zh-TW": ("簡介文件", "研讀指南", "網誌文章"),
            "zh-CN": ("简介文档", "学习指南", "博客文章"),
            "en": ("Brief", "Study guide", "Blog post"),
            "ja": ("概要", "学習ガイド", "ブログ記事"),
            "ko": ("요약", "학습 가이드", "블로그 게시물"),
            "es": ("Resumen", "Guia de estudio", "Entrada de blog"),
            "fr": ("Bref", "Guide d'etude", "Article de blog"),
            "de": ("Kurzfassung", "Lernhilfe", "Blogbeitrag"),
        },
        "audio_preset": {
            "zh-TW": ("語音", "語音概覽"),
            "zh-CN": ("语音", "语音概览"),
            "en": ("Audio Overview",),
            "ja": ("音声概要",),
            "ko": ("오디오 개요",),
            "es": ("Resumen de audio",),
            "fr": ("Vue d'ensemble audio",),
            "de": ("Audio-Uberblick",),
        },
        "mind_map_preset": {
            "zh-TW": ("心智圖"),
            "zh-CN": ("思维导图"),
            "en": ("Mind map",),
            "ja": ("マインドマップ",),
            "ko": ("마인드맵",),
            "es": ("Mapa mental",),
            "fr": ("Carte mentale",),
            "de": ("Mindmap",),
        },
        "video_preset": {
            "zh-TW": ("影片摘要", "影片概覽"),
            "zh-CN": ("视频概览", "视频"),
            "en": ("Video Overview",),
            "ja": ("動画概要",),
            "ko": ("비디오 개요",),
            "es": ("Resumen en video",),
            "fr": ("Vue d'ensemble video",),
            "de": ("Video-Uberblick",),
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


NOTEBOOK_TILE_LINK_CSS = "project-button a[href*='/notebook/']"
NOTEBOOK_TILE_CARD_CSS = "project-button mat-card.project-button-card"
NOTEBOOK_TITLE_SPAN_CSS = "span.project-button-title"


def notebook_tile_xpath_by_name(name: str) -> str:
    """Build an XPath that matches a notebook tile with exact visible name."""
    escaped = _xpath_literal(name)
    return (
        "//span[contains(@class, 'project-button-title') and normalize-space(string()) = {0}]"
        "/ancestor::project-button//a[contains(@href, '/notebook/')]"
    ).format(escaped)


def _xpath_literal(text: str) -> str:
    """Safely embed arbitrary text as an XPath string literal."""
    if "'" not in text:
        return "'{0}'".format(text)
    if '"' not in text:
        return '"{0}"'.format(text)
    parts = text.split("'")
    return "concat(" + ', "\'", '.join("'{0}'".format(part) for part in parts) + ")"


CREATE_NEW_GRID_CARD_CSS = "mat-card.create-new-action-button"
CREATE_NEW_TOOLBAR_BUTTON_CSS = "button.create-new-button"
CREATE_NEW_BUTTON_TEXTS = _localized_text("create_new_notebook")

NOTEBOOK_TITLE_INPUT_CSS = "input.title-input"
NOTEBOOK_TITLE_EDITABLE_CSS = "input.title-input"
NOTEBOOK_TITLE_TEXTBOX_ROLE = ("textbox", None)

SOURCE_PANEL_CSS = "source-picker"
SOURCE_PANEL_CONTENT_CSS = "source-picker .contents"
ADD_SOURCE_BUTTON_CSS = "button.add-source-button"
ADD_SOURCE_BUTTON_TEXTS = _localized_text("add_source")
SOURCE_UPLOAD_FILE_INPUT_CSS = "input[type='file']"
DROP_ZONE_ICON_BUTTON_CSS = "button.drop-zone-icon-button"
DROP_ZONE_LINK_ICON_NAME = "link"
URL_INPUT_TEXTAREA_CSS = 'textarea[formcontrolname="urls"]'
URL_DIALOG_SUBMIT_BUTTON_CSS = "button[mat-flat-button][color='primary']"
SOURCE_WEBSITE_TAB_TEXTS = _localized_text("website_tab")
SOURCE_WEBSITE_URL_INPUT_PLACEHOLDERS = _localized_text("url_input_placeholder")
SOURCE_WEBSITE_INSERT_BUTTON_TEXTS = _localized_text("insert_source_button")

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

GENERATION_PROGRESS_CHIP_TEXTS = ("?Ｙ?銝?", "Generating", "??銝?", "??")
GENERATION_ARTIFACT_LINK_CSS = "a[href*='/notebook/']"
ARTIFACT_LIBRARY_EMPTY_STATE_CSS = ".artifact-library-empty-state"

NOTEBOOK_SUMMARY_CSS = "span.notebook-summary"
NOTEBOOK_SUMMARY_CONTENT_CSS = "span.notebook-summary .summary-content"
NOTEBOOK_TITLE_H1_CSS = "h1.notebook-title"
COPY_SUMMARY_BUTTON_CSS = "button.xap-copy-to-clipboard"

ARTIFACT_LIBRARY_ITEM_CSS = "artifact-library-item"
ARTIFACT_STRETCHED_BUTTON_CSS = "button.artifact-stretched-button"
ARTIFACT_TITLE_SPAN_CSS = "span.artifact-title"
ARTIFACT_MORE_BUTTON_CSS = "button.artifact-more-button"

BRIEFING_PRESETS = _localized_text("briefing_preset")
AUDIO_PRESETS = _localized_text("audio_preset")
MIND_MAP_PRESETS = _localized_text("mind_map_preset")
VIDEO_PRESETS = _localized_text("video_preset")

NAV_TIMEOUT_MS = 30_000
UPLOAD_TIMEOUT_MS = 120_000
GENERATION_TIMEOUT_MS = 300_000
BETWEEN_UPLOADS_MS = 2_000

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
