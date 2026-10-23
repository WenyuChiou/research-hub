"""Bilingual, progressively disclosed native-source evidence for the dashboard."""
from __future__ import annotations

from html import escape

from research_hub.dashboard.source_evidence import SourceEvidence


_REASONS = {
    "not_observed": ("尚無可用的快取觀察。", "No cache observation is available."),
    "cache_missing": ("找不到本機 NotebookLM 快取檔。", "The local NotebookLM cache file is missing."),
    "cache_unreadable": ("無法讀取本機 NotebookLM 快取檔。", "The local NotebookLM cache file could not be read."),
    "cache_invalid": ("本機快取格式無效，無法判定這篇來源的狀態。", "The local cache format is invalid; this source's state is unknown."),
    "identity_not_linked": ("未找到完全相符的主要快取識別；不代表遠端沒有這篇來源。", "No exact primary-cache identity match; this does not establish remote absence."),
    "identity_ambiguous": ("找到多個快取識別，無法唯一對應上傳版本。", "Multiple cached identities match; an uploaded version cannot be uniquely bound."),
    "version_unknown": ("快取有來源識別，但沒有可用的上傳內容指紋。", "A source identity is cached, but its uploaded payload fingerprint is unavailable."),
    "historical_version": ("僅有歷史上傳內容指紋；尚未比較目前內容或查核遠端。", "Only a historical uploaded-payload fingerprint is recorded; current content and remote state were not checked."),
}


def _bilingual(zh: str, en: str) -> str:
    return f'<span lang="zh-Hant">{escape(zh)}</span> <span lang="en">{escape(en)}</span>'


def render_source_evidence(cluster_slug: str, paper) -> str:
    evidence = getattr(paper, "nlm_source_evidence", None)
    if not isinstance(evidence, SourceEvidence):
        evidence = SourceEvidence()
    reason = _REASONS.get(evidence.reason, _REASONS["not_observed"])
    if evidence.reason in {"cache_missing", "cache_unreadable", "cache_invalid"}:
        next_step = ("先檢查本機快取檔是否存在、可讀且格式正確，再重新產生畫面；不要清空快取或直接重傳。",
                     "Inspect the local cache file and its format, then regenerate the dashboard; do not clear the cache or blindly re-upload.")
    else:
        next_step = ("人工核對來源、bundle manifest 與目標筆記本；先確認版本，再決定是否保留或替換。",
                     "Manually compare the source, bundle manifest and intended notebook; establish the version before choosing whether to keep or replace it.")

    def item(zh: str, en: str, value: object) -> str:
        text = str(value or "").strip()
        rendered = f'<code>{escape(text)}</code>' if text else _bilingual("未知", "Unknown")
        return f'<div><dt>{_bilingual(zh, en)}</dt><dd>{rendered}</dd></div>'

    identities = "".join([
        item("來源 DOI", "Source DOI", getattr(paper, "doi", "")),
        item("筆記記錄的 Zotero key", "Zotero key recorded in note", getattr(paper, "zotero_key", "")),
        item("Obsidian 筆記路徑", "Obsidian note path", getattr(paper, "obsidian_path", "")),
        item("主題群組", "Cluster", cluster_slug),
    ])
    version = _bilingual("未知", "Unknown")
    technical = ""
    if evidence.source_key:
        technical_items = item("主要快取識別", "Primary cache identity", evidence.source_key)
        if evidence.payload_sha256:
            version = _bilingual("已記錄歷史指紋；不是目前版本驗證", "Historical fingerprint recorded; not current-version verification")
            technical_items += item("上傳內容類型", "Payload kind", evidence.payload_kind)
            technical_items += item("歷史內容 SHA-256", "Historical payload SHA-256", evidence.payload_sha256)
        technical = f'<details class="source-evidence-technical"><summary>{_bilingual("技術識別", "Technical identifiers")}</summary><dl>{technical_items}</dl></details>'

    return f"""
      <details class="source-evidence">
        <summary>{_bilingual("來源與同步證據", "Source & sync evidence")}
          <span class="source-evidence-status">{_bilingual("遠端同步：未知", "Remote sync: unknown")}</span>
        </summary>
        <div class="source-evidence-body">
          <p>{_bilingual("僅顯示本機筆記與快取記錄，不是 Zotero 或 NotebookLM 即時查核。", "Local note and cache records only, not a live Zotero or NotebookLM check.")}</p>
          <dl>{identities}<div><dt>{_bilingual("NotebookLM 快取內容版本", "NotebookLM cached payload version")}</dt><dd>{version}</dd></div></dl>
          <p><strong>{_bilingual("原因／限制：", "Reason / limit:")}</strong> {_bilingual(*reason)}</p>
          <p><strong>{_bilingual("下一步：", "Next step:")}</strong> {_bilingual(*next_step)}</p>
          {technical}
          <p>{_bilingual("此檢視不會自動上傳、替換或刪除來源。", "No automatic upload, replacement or deletion from this view.")}</p>
        </div>
      </details>
    """
