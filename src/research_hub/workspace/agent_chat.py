"""Interactive bilingual AI Agent bridge for Research Hub workspaces."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from typing import Any

from .core import Workspace, WorkspaceError, digest

_ALLOWED_ENGINES = ("auto", "fast", "claude", "codex", "gemini")
_MAX_ACTION_BATCH = 50
_ALLOWED_ACTION_TYPES = frozenset({
    "archive_source",
    "restore_source",
    "add_tags",
    "remove_tags",
    "set_category",
    "screen_source",
    "add_source",
    "sync_zotero",
    "bundle_notebooklm",
    "upload_notebooklm",
    "pack_obsidian",
})

_DELETE_VERBS_RE = re.compile(
    r"(?:刪除|移除|移出|刪掉|封存|歸檔|\b(?:delete|remove|archive|drop)\b)", re.IGNORECASE
)
_RESTORE_VERBS_RE = re.compile(
    r"(?:復原|還原|取消封存|取消刪除|\b(?:restore|unarchive|recover)\b)", re.IGNORECASE
)
_INCLUDE_VERBS_RE = re.compile(r"(?:納入|保留|收錄|\binclude\b)", re.IGNORECASE)
_EXCLUDE_VERBS_RE = re.compile(r"(?:排除|剔除|\bexclude\b)", re.IGNORECASE)
_ADD_SOURCE_RE = re.compile(
    r"(?:新增文獻|加入文獻|添加文獻|add source|add paper)\s*[:：]?\s*(.+)", re.IGNORECASE
)
_TAG_ADD_RE = re.compile(r"(?:加|加上|新增|貼上|標記|add)\s*(?:標籤|tag)?", re.IGNORECASE)
_TAG_REMOVE_RE = re.compile(r"(?:移除|刪除|拔掉|remove|drop)\s*(?:標籤|tag)", re.IGNORECASE)
_CATEGORY_SET_RE = re.compile(
    r"(?:分類改為|設為分類|改分類為|category\s*(?:to|=|:))\s*[:：]?\s*([^\s,，;；\n]{1,64})",
    re.IGNORECASE,
)
_HASHTAG_RE = re.compile(r"#([A-Za-z0-9_\-\u4e00-\u9fff]{1,64})")
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _clean_text(value: object, *, limit: int = 4000) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _normalize_tag(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.strip().lstrip("#").strip()[:80]


def _format_scoped_titles(scoped: list[dict[str, Any]]) -> str:
    names = "、".join(f"「{s['title'][:45]}」" for s in scoped[:3])
    return f"{names} 等 {len(scoped)} 篇" if len(scoped) > 3 else f"{names}（共 {len(scoped)} 篇）"


def _match_sources(message: str, catalog: list[dict[str, Any]], *, include_archived: bool = False) -> list[dict[str, Any]]:
    """Find sources referenced in natural language by ID, DOI, year, or title fragments."""
    candidates = [s for s in catalog if include_archived or not s["archived"]]
    msg_no_tags = _HASHTAG_RE.sub(" ", message)
    msg_lower = msg_no_tags.casefold()
    matched: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(item: dict[str, Any]) -> None:
        if item["id"] not in seen:
            seen.add(item["id"])
            matched.append(item)

    if any(tok in msg_lower for tok in ("全部文獻", "所有文獻", "all papers", "all sources")):
        return candidates

    for s in candidates:
        if s["id"].casefold() in msg_lower or s["id"][:8].casefold() in msg_lower:
            _add(s)
        elif s["doi"] and s["doi"].casefold() in msg_lower:
            _add(s)

    if matched:
        return matched

    # Quoted title fragments: "..." or 「...」 or 『...』 — fail closed if any explicit quote misses.
    quoted = re.findall(r"[\"“「『]([^\"”」』]{2,160})[\"”」』]", msg_no_tags)
    if quoted:
        for q in quoted:
            ql = q.strip().casefold()
            q_hits = [s for s in candidates if ql and ql in s["title"].casefold()]
            if not q_hits:
                return []
            for s in q_hits:
                _add(s)
        return matched

    # Direct longest title-word overlap (>= 4 chars substring or >= 2 meaningful tokens)
    stop_tokens = {
        "幫我", "請", "刪除", "移除", "復原", "還原", "文獻", "論文", "這篇", "那篇",
        "加上", "標籤", "分類", "納入", "排除", "同步", "上傳", "產生", "匯出", "寫入",
        "正式", "筆記", "雲端", "限定", "delete", "remove", "restore", "paper", "papers",
        "source", "sources", "items", "year", "years", "for", "from", "with", "the", "and",
        "into", "all", "only", "upload", "bundle", "sync", "pack", "add", "archive",
        "include", "exclude", "tag", "tags", "confirm", "notebooklm", "zotero", "obsidian", "nlm",
    }
    scored: list[tuple[int, dict[str, Any]]] = []
    msg_tokens = {
        tok for tok in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{3,}", msg_lower)
        if tok not in stop_tokens
    }
    for s in candidates:
        title_l = s["title"].casefold()
        if len(title_l) >= 6 and title_l in msg_lower:
            scored.append((1000 + len(title_l), s))
            continue
        title_tokens = [
            tok for tok in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{3,}", title_l)
            if tok not in stop_tokens
        ]
        overlap = sum(len(tok) for tok in title_tokens if tok in msg_tokens)
        if overlap >= 5:
            scored.append((overlap, s))

    if scored:
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top_score = scored[0][0]
        for score, s in scored:
            if score == top_score or score >= max(8, int(top_score * 0.7)):
                _add(s)
        return matched

    # Explicit scope with non-stop title tokens that matched nothing should not widen to a bare year filter.
    if re.search(r"(?:只|僅|限定|\bonly\b)", msg_no_tags, re.IGNORECASE):
        unmatched_alpha = {t for t in re.findall(r"[a-z]{3,}", msg_lower) if t not in stop_tokens}
        if unmatched_alpha:
            return []

    # Year filter if user specifically mentions a year alongside batch tag/archive
    years = _YEAR_RE.findall(msg_no_tags)
    if years:
        for s in candidates:
            if s["year"] in years:
                _add(s)
    return matched


class WorkspaceAgentBridge:
    """Two-step AI Assistant for interactive Research Hub workspace curation & sync."""

    def __init__(self, workspace: Workspace, *, sync_hooks: Any = None) -> None:
        self.workspace = workspace
        self.sync_hooks = sync_hooks

    def status(self) -> dict[str, Any]:
        cli_presence = {name: bool(shutil.which(name)) for name in ("claude", "codex", "gemini")}
        engines: list[dict[str, Any]] = [
            {"id": "auto", "label": "Auto (Fast + CLI)", "available": True},
            {"id": "fast", "label": "Workspace Fast Commander", "available": True},
        ]
        for name in ("claude", "codex", "gemini"):
            engines.append({
                "id": name,
                "label": name.capitalize(),
                "available": cli_presence[name],
            })
        detected_cli = next((name for name in ("claude", "codex", "gemini") if cli_presence[name]), None)
        return {
            "ok": True,
            "available_engines": engines,
            "default_engine": "auto",
            "detected_cli": detected_cli,
        }

    def _source_catalog(self, project_id: str) -> list[dict[str, Any]]:
        records = self.workspace.records(project_id)
        curations: dict[str, dict[str, Any]] = {}
        screenings: dict[str, str] = {}
        sources: list[dict[str, Any]] = []
        for rec in records:
            kind = rec.get("kind")
            data = rec.get("data") or {}
            if kind == "source_curation" and isinstance(data.get("source_id"), str):
                curations.setdefault(data["source_id"], {}).update(data)
            elif kind == "screening" and isinstance(data.get("source_id"), str):
                dec = str(data.get("decision") or "").strip()
                if dec in {"include", "exclude"}:
                    screenings[data["source_id"]] = dec
            elif kind == "source":
                sources.append(rec)

        catalog: list[dict[str, Any]] = []
        for rec in sources:
            sid = rec["id"]
            raw_data = dict(rec.get("data") or {})
            overlay = curations.get(sid, {})
            base = {**raw_data, **overlay}
            if "tags" in overlay:
                effective_tags = [str(t) for t in (overlay.get("tags") or []) if isinstance(t, str)]
            else:
                merged_raw: list[str] = []
                seen_raw: set[str] = set()
                for t in list(raw_data.get("tags") or []) + list(raw_data.get("labels") or []):
                    if not isinstance(t, str):
                        continue
                    cleaned = _normalize_tag(t)
                    if cleaned and cleaned.casefold() not in seen_raw:
                        seen_raw.add(cleaned.casefold())
                        merged_raw.append(cleaned)
                effective_tags = merged_raw
            catalog.append({
                "id": sid,
                "title": str(base.get("title") or "Untitled source"),
                "doi": str(base.get("doi") or ""),
                "year": str(base.get("year") or ""),
                "category": str(base.get("category") or ""),
                "tags": effective_tags,
                "archived": bool(base.get("archived", False)),
                "screening": screenings.get(sid, "unscreened"),
            })
        return catalog

    def _plan_fast(self, project_id: str, message: str, catalog: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], bool]:
        """Deterministic bilingual command planner. Returns (reply, actions, matched_intent)."""
        msg = message.strip()
        msg_l = msg.casefold()
        actions: list[dict[str, Any]] = []

        # 1. Explicit sync hooks (honoring optional single/multi-paper scoping)
        explicitly_scoped = bool(
            re.search(r"[\"“「『]|(?:只|僅|限定|\bonly\b)", msg, re.IGNORECASE)
        )
        if any(k in msg_l for k in ("上傳 notebooklm", "上傳至 notebooklm", "upload notebooklm", "upload to notebooklm")):
            scoped = _match_sources(msg, catalog, include_archived=False)
            if explicitly_scoped and not scoped:
                return "找不到符合指定條件的文獻，無法建立 scoped 上傳提案；請確認文獻標題或 DOI。", [], True
            act: dict[str, Any] = {"type": "upload_notebooklm", "summary": "產生並上傳專案文獻包至 NotebookLM 雲端筆記本"}
            if scoped:
                scoped_label = _format_scoped_titles(scoped)
                act["selected_source_ids"] = [s["id"] for s in scoped]
                act["summary"] = f"產生並上傳已選文獻 {scoped_label} 至 NotebookLM 雲端筆記本"
                reply_msg = f"已規劃將指定文獻 {scoped_label} 打包並上傳至 NotebookLM，請確認執行。"
            else:
                reply_msg = "已規劃將目前入選文獻打包並上傳至 NotebookLM 雲端筆記本，請確認執行。"
            actions.append(act)
            return reply_msg, actions, True
        if any(k in msg_l for k in ("notebooklm", "nlm")) and any(k in msg_l for k in ("匯出", "產生", "打包", "bundle", "pack")):
            scoped = _match_sources(msg, catalog, include_archived=False)
            if explicitly_scoped and not scoped:
                return "找不到符合指定條件的文獻，無法建立 scoped 匯出提案。", [], True
            act = {"type": "bundle_notebooklm", "summary": "更新 NotebookLM Markdown 匯出包"}
            if scoped:
                scoped_label = _format_scoped_titles(scoped)
                act["selected_source_ids"] = [s["id"] for s in scoped]
                act["summary"] = f"更新已選 {scoped_label} 的 NotebookLM Markdown 匯出包"
                reply_msg = f"已規劃重新產生 {scoped_label} 的 NotebookLM 來源包，請確認執行。"
            else:
                reply_msg = "已規劃重新產生 NotebookLM 來源包，請確認執行。"
            actions.append(act)
            return reply_msg, actions, True
        if "zotero" in msg_l and any(k in msg_l for k in ("寫入", "同步", "push", "sync")):
            dry_run = "寫入" not in msg_l and "confirm" not in msg_l and "正式" not in msg_l
            scoped = _match_sources(msg, catalog, include_archived=False)
            if explicitly_scoped and not scoped:
                return "找不到符合指定條件的文獻，無法建立 scoped Zotero 同步提案。", [], True
            act = {
                "type": "sync_zotero",
                "dry_run": dry_run,
                "summary": "Zotero Dry-run 預覽比對" if dry_run else "正式同步專案文獻與 Collection 至 Zotero 雲端書目庫",
            }
            if scoped:
                scoped_label = _format_scoped_titles(scoped)
                act["selected_source_ids"] = [s["id"] for s in scoped]
                act["summary"] = (
                    f"Zotero Dry-run 預覽（已選 {scoped_label}）"
                    if dry_run
                    else f"正式同步已選 {scoped_label} 與 Collection 至 Zotero"
                )
                reply_msg = (
                    f"已規劃將 {scoped_label} 正式同步至 Zotero（含建立 `[Research Hub]` Collection），請確認執行。"
                    if not dry_run
                    else f"已規劃對 {scoped_label} 執行 Zotero Dry-run 預覽檢查，請確認執行。"
                )
            else:
                reply_msg = (
                    "已規劃 Zotero 同步作業（含建立 `[Research Hub]` Collection），請確認執行。"
                    if not dry_run
                    else "已規劃 Zotero Dry-run 預覽檢查，請確認執行。"
                )
            actions.append(act)
            return reply_msg, actions, True
        if "obsidian" in msg_l and any(k in msg_l for k in ("產生", "匯出", "打包", "pack")):
            scoped = _match_sources(msg, catalog, include_archived=False)
            if explicitly_scoped and not scoped:
                return "找不到符合指定條件的文獻，無法建立 scoped Obsidian 匯出提案。", [], True
            act = {"type": "pack_obsidian", "summary": "產生 Obsidian 筆記與 .base 索引檢視"}
            if scoped:
                scoped_label = _format_scoped_titles(scoped)
                act["selected_source_ids"] = [s["id"] for s in scoped]
                act["summary"] = f"產生已選 {scoped_label} 的 Obsidian 筆記與 .base 索引檢視"
                reply_msg = f"已規劃產生 {scoped_label} 的 Obsidian 筆記與 `.base` 資料庫檢視，請確認執行。"
            else:
                reply_msg = "已規劃產生 Obsidian 筆記與 `.base` 資料庫檢視，請確認執行。"
            actions.append(act)
            return reply_msg, actions, True

        # 2. Add source
        add_match = _ADD_SOURCE_RE.match(msg)
        if add_match:
            tail = add_match.group(1).strip()
            url_match = re.search(r"https?://\S+", tail)
            locator = url_match.group(0) if url_match else "https://example.org/manual-entry"
            title = re.sub(r"https?://\S+", "", tail).strip(" ,，;；") or "Untitled manual source"
            actions.append({
                "type": "add_source",
                "title": title,
                "locator": locator,
                "summary": f"新增文獻「{title}」",
            })
            return f"已規劃新增文獻 **{title}**，請確認執行。", actions, True

        # 3. Restore archived source
        if _RESTORE_VERBS_RE.search(msg):
            archived_hits = [s for s in _match_sources(msg, catalog, include_archived=True) if s["archived"]]
            if archived_hits:
                for s in archived_hits:
                    actions.append({
                        "type": "restore_source",
                        "source_id": s["id"],
                        "title": s["title"],
                        "summary": f"復原文獻「{s['title']}」",
                    })
                return f"已找到 {len(archived_hits)} 篇已封存／刪除文獻，準備復原至作用中書目庫，請確認執行。", actions, True

        # 4. Tags add / remove (before archive_source so "Remove #tag from all papers" updates tags instead of archiving)
        tags = [_normalize_tag(t) for t in _HASHTAG_RE.findall(msg)]
        tags = [t for t in tags if t]
        archive_by_tag_re = re.compile(
            r"(?:封存|歸檔|\barchive\b|(?:delete|remove)\s+(?:all\s+)?(?:papers?|sources?)\s+(?:with|tagged)|(?:刪除|移除)(?:所有)?(?:含有?|帶有?)\s*#)",
            re.IGNORECASE,
        )
        if tags and not archive_by_tag_re.search(msg):
            hits = _match_sources(msg, catalog, include_archived=False)
            if hits:
                is_remove = bool(_TAG_REMOVE_RE.search(msg) or _DELETE_VERBS_RE.search(msg))
                action_type = "remove_tags" if is_remove else "add_tags"
                verb = "移除標籤" if action_type == "remove_tags" else "加上標籤"
                for s in hits:
                    actions.append({
                        "type": action_type,
                        "source_id": s["id"],
                        "title": s["title"],
                        "tags": tags,
                        "summary": f"為「{s['title']}」{verb} {', '.join('#' + t for t in tags)}",
                    })
                return f"已為 {len(hits)} 篇文獻規劃{verb}（{', '.join('#' + t for t in tags)}），請確認執行。", actions, True
            return "找不到符合條件的未封存文獻可更新標籤，請確認文獻標題或 DOI。", [], True

        # 5. Archive / delete source
        if _DELETE_VERBS_RE.search(msg) and not _TAG_REMOVE_RE.search(msg):
            hits = _match_sources(msg, catalog, include_archived=False)
            if hits:
                for s in hits:
                    actions.append({
                        "type": "archive_source",
                        "source_id": s["id"],
                        "title": s["title"],
                        "summary": f"移出／刪除文獻「{s['title']}」",
                    })
                names = "、".join(f"「{h['title'][:45]}」" for h in hits[:3])
                return f"已比對到 {len(hits)} 篇文獻（{names}），將從作用中書目庫封存移除，請確認執行。", actions, True
            return "找不到符合的未刪除文獻可移出，請提供更精確的標題關鍵字或 DOI。", [], True

        # 6. Category update
        cat_match = _CATEGORY_SET_RE.search(msg)
        if cat_match:
            category = cat_match.group(1).strip()
            hits = _match_sources(msg, catalog, include_archived=False)
            if hits:
                for s in hits:
                    actions.append({
                        "type": "set_category",
                        "source_id": s["id"],
                        "title": s["title"],
                        "category": category,
                        "summary": f"將「{s['title']}」分類改為 {category}",
                    })
                return f"已規劃將 {len(hits)} 篇文獻分類改為 `{category}`，請確認執行。", actions, True

        # 7. Include / exclude screening
        if _EXCLUDE_VERBS_RE.search(msg):
            hits = _match_sources(msg, catalog, include_archived=False)
            if hits:
                for s in hits:
                    actions.append({
                        "type": "screen_source",
                        "source_id": s["id"],
                        "title": s["title"],
                        "decision": "exclude",
                        "rationale": f"AI Agent console instruction: {msg[:240]}",
                        "summary": f"將「{s['title']}」標記為排除 (exclude)",
                    })
                return f"已規劃將 {len(hits)} 篇文獻標記為 **排除**，請確認執行。", actions, True
        if _INCLUDE_VERBS_RE.search(msg):
            hits = _match_sources(msg, catalog, include_archived=False)
            if hits:
                for s in hits:
                    actions.append({
                        "type": "screen_source",
                        "source_id": s["id"],
                        "title": s["title"],
                        "decision": "include",
                        "rationale": f"AI Agent console instruction: {msg[:240]}",
                        "summary": f"將「{s['title']}」標記為納入 (include)",
                    })
                return f"已規劃將 {len(hits)} 篇文獻標記為 **納入**，請確認執行。", actions, True

        # 8. Inventory / summary query (read-only reply)
        if any(k in msg_l for k in ("幾篇", "清單", "列出", "狀態", "count", "list", "status", "summary")):
            active = [s for s in catalog if not s["archived"]]
            archived_count = len(catalog) - len(active)
            included = sum(1 for s in active if s["screening"] == "include")
            sample_titles = "\n".join(
                f"- **{s['title']}** ({s['year'] or 'n.d.'}, `{s['screening']}`)"
                for s in active[:8]
            )
            reply = (
                f"目前專案共有 **{len(active)} 篇作用中文獻**（納入 {included} 篇，已封存/刪除 {archived_count} 篇）。\n\n"
                f"{sample_titles}"
            )
            return reply, [], True

        return "", [], False

    def _plan_via_cli(
        self, cli_name: str, project_id: str, message: str, catalog: list[dict[str, Any]]
    ) -> tuple[str, list[dict[str, Any]]]:
        from research_hub.llm_cli import _extract_first_json

        executable = shutil.which(cli_name)
        if not executable:
            raise WorkspaceError(f"Requested CLI engine '{cli_name}' is not installed on PATH", "cli_unavailable")

        compact_catalog = [
            {
                "id": s["id"],
                "title": s["title"],
                "year": s["year"],
                "doi": s["doi"],
                "category": s["category"],
                "tags": s["tags"],
                "archived": s["archived"],
                "screening": s["screening"],
            }
            for s in catalog[:60]
        ]
        prompt = (
            "You are the Research Hub AI Assistant for project "
            f"'{project_id}'. Respond ONLY with one JSON object of the form:\n"
            '{"reply": "<concise answer in the user language>", "actions": [...]}\n\n'
            "Allowed action objects:\n"
            '- {"type": "archive_source", "source_id": "<id>", "summary": "..."}\n'
            '- {"type": "restore_source", "source_id": "<id>", "summary": "..."}\n'
            '- {"type": "add_tags", "source_id": "<id>", "tags": ["tag1"], "summary": "..."}\n'
            '- {"type": "remove_tags", "source_id": "<id>", "tags": ["tag1"], "summary": "..."}\n'
            '- {"type": "set_category", "source_id": "<id>", "category": "<slug>", "summary": "..."}\n'
            '- {"type": "screen_source", "source_id": "<id>", "decision": "include|exclude", "rationale": "...", "summary": "..."}\n'
            '- {"type": "sync_zotero", "dry_run": true, "summary": "..."}\n'
            '- {"type": "bundle_notebooklm", "summary": "..."}\n'
            '- {"type": "upload_notebooklm", "summary": "..."}\n'
            '- {"type": "pack_obsidian", "summary": "..."}\n\n'
            f"Current project sources:\n{json.dumps(compact_catalog, ensure_ascii=False)}\n\n"
            f"User request:\n{message}\n"
        )
        # Read-only isolated execution: run CLI inside a blank temp directory without auto-approve flags.
        cmd_map = {
            "claude": [executable, "-p"],
            "codex": [executable, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "-"],
            "gemini": [executable, "-p", ""],
        }
        cmd = cmd_map[cli_name]
        with tempfile.TemporaryDirectory(prefix="rh-agent-ro-") as tmpdir:
            proc = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=60.0,
                cwd=tmpdir,
                check=False,
            )
        if proc.returncode != 0:
            raise RuntimeError(f"CLI exited with code {proc.returncode}")
        raw = proc.stdout or ""
        parsed = _extract_first_json(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("reply"), str):
            validated = self._sanitize_proposed_actions(parsed.get("actions"), catalog)
            return parsed["reply"].strip(), validated
        return raw.strip()[:2000], []

    def _sanitize_proposed_actions(
        self, raw_actions: object, catalog: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_actions, list):
            return []
        catalog_map = {s["id"]: s for s in catalog}
        clean: list[dict[str, Any]] = []
        for entry in raw_actions[:500]:
            if not isinstance(entry, dict):
                continue
            atype = entry.get("type")
            if atype not in _ALLOWED_ACTION_TYPES:
                continue
            item: dict[str, Any] = {"type": atype}
            if atype in {"archive_source", "restore_source", "add_tags", "remove_tags", "set_category", "screen_source"}:
                sid = _clean_text(entry.get("source_id"), limit=128)
                if sid not in catalog_map:
                    continue
                item["source_id"] = sid
                item["title"] = catalog_map[sid]["title"]
            if atype in {"add_tags", "remove_tags"}:
                raw_tags = entry.get("tags")
                if not isinstance(raw_tags, list):
                    continue
                tags = [_normalize_tag(t) for t in raw_tags if isinstance(t, str)]
                tags = [t for t in tags if t]
                if not tags:
                    continue
                item["tags"] = tags
            if atype == "set_category":
                cat = _clean_text(entry.get("category"), limit=120)
                if not cat:
                    continue
                item["category"] = cat
            if atype == "screen_source":
                dec = entry.get("decision")
                if dec not in {"include", "exclude"}:
                    continue
                item["decision"] = dec
                item["rationale"] = _clean_text(entry.get("rationale"), limit=500) or "AI Agent review"
            if atype == "add_source":
                title = _clean_text(entry.get("title"), limit=500)
                locator = _clean_text(entry.get("locator"), limit=1000)
                if not title or not locator.lower().startswith(("http://", "https://")):
                    continue
                item["title"] = title
                item["locator"] = locator
            if atype in {"bundle_notebooklm", "upload_notebooklm", "sync_zotero", "pack_obsidian"}:
                raw_sel = entry.get("selected_source_ids")
                if isinstance(raw_sel, list):
                    valid_ids = [
                        _clean_text(s, limit=128)
                        for s in raw_sel
                        if isinstance(s, str) and _clean_text(s, limit=128) in catalog_map
                    ]
                    if not valid_ids:
                        continue
                    item["selected_source_ids"] = valid_ids
            if atype == "sync_zotero":
                item["dry_run"] = bool(entry.get("dry_run", True))
                if not item["dry_run"]:
                    if isinstance(entry.get("expected_library"), str) and entry["expected_library"].strip():
                        item["expected_library"] = entry["expected_library"].strip()
                    if isinstance(entry.get("expected_plan_digest"), str) and entry["expected_plan_digest"].strip():
                        item["expected_plan_digest"] = entry["expected_plan_digest"].strip()
                    if isinstance(entry.get("expected_revisions"), dict):
                        item["expected_revisions"] = {
                            str(k): str(v) for k, v in entry["expected_revisions"].items()
                            if isinstance(k, str) and isinstance(v, str)
                        }
            item["summary"] = _clean_text(entry.get("summary"), limit=300) or atype
            clean.append(item)
        return clean

    def _enforce_batch_limit(
        self, reply: str, actions: list[dict[str, Any]]
    ) -> tuple[str, list[dict[str, Any]]]:
        if len(actions) > _MAX_ACTION_BATCH:
            return (
                f"本次指令共比對到 {len(actions)} 項操作，超過單次安全上限（{_MAX_ACTION_BATCH} 項）。"
                f"為避免部分文獻被靜默略過，已拒絕建立超額批次提案；請改以年份（如 2024）、#標籤或關鍵字分批執行。"
                f" (Matched {len(actions)} actions > {_MAX_ACTION_BATCH} batch limit; narrow your filter to run in batches.)",
                [],
            )
        return reply, actions

    def _bind_preview_targets(self, project_id: str, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Bind live sync_zotero proposals to read-only dry-run digests before user confirmation."""
        if self.sync_hooks is None:
            return actions
        bound: list[dict[str, Any]] = []
        for action in actions:
            entry = dict(action)
            if entry.get("type") == "sync_zotero" and entry.get("dry_run") is False:
                try:
                    preview_req: dict[str, Any] = {"dry_run": True}
                    if entry.get("selected_source_ids"):
                        preview_req["selected_source_ids"] = entry["selected_source_ids"]
                    preview = self.sync_hooks.sync_zotero(project_id, preview_req)
                    if isinstance(preview.get("destination_library"), str) and preview["destination_library"]:
                        entry["expected_library"] = preview["destination_library"]
                    if isinstance(preview.get("plan_digest"), str) and preview["plan_digest"]:
                        entry["expected_plan_digest"] = preview["plan_digest"]
                    if isinstance(preview.get("source_revisions"), dict):
                        entry["expected_revisions"] = preview["source_revisions"]
                except Exception:
                    pass
            bound.append(entry)
        return bound

    def chat(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Strictly read-only chat turn: analyzes project catalog and proposes actions."""
        if not isinstance(payload, dict):
            raise WorkspaceError("Chat payload must be an object", "invalid_request")
        extra = set(payload) - {"message", "engine", "history"}
        if extra:
            raise WorkspaceError(f"Unsupported chat fields: {', '.join(sorted(extra))}", "invalid_request")

        message = _clean_text(payload.get("message"), limit=4000)
        if not message:
            raise WorkspaceError("message must be non-empty", "invalid_request")
        engine = _clean_text(payload.get("engine") or "auto", limit=32).lower() or "auto"
        if engine not in _ALLOWED_ENGINES:
            raise WorkspaceError(f"Unsupported engine: {engine}", "invalid_request")

        catalog = self._source_catalog(project_id)
        engine_used = "fast"
        reply = ""
        actions: list[dict[str, Any]] = []

        if engine in {"fast", "auto"}:
            reply, actions, matched = self._plan_fast(project_id, message, catalog)
            if matched:
                actions = self._sanitize_proposed_actions(actions, catalog)
                reply, actions = self._enforce_batch_limit(reply, actions)
                actions = self._bind_preview_targets(project_id, actions)
                plan_digest = digest({"project_id": project_id, "actions": actions})
                return {
                    "ok": True,
                    "engine_used": "fast",
                    "reply": reply,
                    "proposed_actions": actions,
                    "plan_digest": plan_digest,
                    "requires_confirmation": bool(actions),
                }

        cli_choice = None
        if engine in {"claude", "codex", "gemini"}:
            if shutil.which(engine):
                cli_choice = engine
            else:
                raise WorkspaceError(f"Requested CLI engine '{engine}' is not installed on PATH", "cli_unavailable")
        elif engine == "auto":
            cli_choice = next((name for name in ("claude", "codex", "gemini") if shutil.which(name)), None)

        if cli_choice is not None:
            try:
                reply, actions = self._plan_via_cli(cli_choice, project_id, message, catalog)
                engine_used = cli_choice
            except Exception:
                reply, actions, _ = self._plan_fast(project_id, message, catalog)

        if not reply:
            reply = (
                "目前可用自然語言指令操作書目與整合，例如：\n"
                "- 「幫我刪除 <論文標題關鍵字> 這篇文獻」\n"
                "- 「復原 <論文標題關鍵字>」\n"
                "- 「為 <關鍵字> 加上標籤 #review」\n"
                "- 「列出目前文獻狀態」\n"
                "- 「上傳至 NotebookLM」或「寫入同步 Zotero」"
            )

        actions = self._sanitize_proposed_actions(actions, catalog)
        reply, actions = self._enforce_batch_limit(reply, actions)
        actions = self._bind_preview_targets(project_id, actions)
        plan_digest = digest({"project_id": project_id, "actions": actions})
        return {
            "ok": True,
            "engine_used": engine_used,
            "reply": reply,
            "proposed_actions": actions,
            "plan_digest": plan_digest,
            "requires_confirmation": bool(actions),
        }

    def apply(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute human-confirmed proposed actions after digest verification."""
        if not isinstance(payload, dict):
            raise WorkspaceError("Apply payload must be an object", "invalid_request")
        extra = set(payload) - {"proposed_actions", "expected_plan_digest"}
        if extra:
            raise WorkspaceError(f"Unsupported apply fields: {', '.join(sorted(extra))}", "invalid_request")

        raw_actions = payload.get("proposed_actions")
        if not isinstance(raw_actions, list) or not raw_actions or len(raw_actions) > 50:
            raise WorkspaceError("proposed_actions must be a non-empty list", "invalid_request")
        expected_digest = _clean_text(payload.get("expected_plan_digest"), limit=128)
        if not expected_digest:
            raise WorkspaceError("expected_plan_digest is required", "invalid_request")

        catalog = self._source_catalog(project_id)
        sanitized = self._sanitize_proposed_actions(raw_actions, catalog)
        if len(sanitized) != len(raw_actions) or digest({"project_id": project_id, "actions": sanitized}) != expected_digest:
            raise WorkspaceError("Action plan expired or modified; re-submit the chat command.", "stale_preview")

        catalog_map = {s["id"]: s for s in catalog}

        # Pre-validate the entire batch before mutating any workspace record
        sim_tags = {sid: list(info.get("tags") or []) for sid, info in catalog_map.items()}
        for action in sanitized:
            atype = action["type"]
            if atype in {"add_tags", "remove_tags"}:
                sid = action["source_id"]
                existing = sim_tags.get(sid, [])
                if atype == "add_tags":
                    seen = {t.casefold() for t in existing}
                    merged = existing + [t for t in action["tags"] if t.casefold() not in seen]
                else:
                    drop = {t.casefold() for t in action["tags"]}
                    merged = [t for t in existing if t.casefold() not in drop]
                if len(merged) > 30:
                    raise WorkspaceError("tags supports at most 30 entries", "invalid_request")
                sim_tags[sid] = merged
            elif atype in {"bundle_notebooklm", "upload_notebooklm", "sync_zotero", "pack_obsidian"} and self.sync_hooks is None:
                raise WorkspaceError("Sync hooks are unavailable in this server mode", "integrations_unavailable")

        results: list[dict[str, Any]] = []

        for action in sanitized:
            atype = action["type"]
            if atype == "archive_source":
                rec = self.workspace.add_record(
                    project_id,
                    kind="source_curation",
                    data={"source_id": action["source_id"], "archived": True},
                )
                results.append({"type": atype, "source_id": action["source_id"], "record_id": rec["id"], "ok": True})
            elif atype == "restore_source":
                rec = self.workspace.add_record(
                    project_id,
                    kind="source_curation",
                    data={"source_id": action["source_id"], "archived": False},
                )
                results.append({"type": atype, "source_id": action["source_id"], "record_id": rec["id"], "ok": True})
            elif atype in {"add_tags", "remove_tags"}:
                sid = action["source_id"]
                existing = list(catalog_map.get(sid, {}).get("tags") or [])
                if atype == "add_tags":
                    seen = {t.casefold() for t in existing}
                    merged = existing + [t for t in action["tags"] if t.casefold() not in seen]
                else:
                    drop = {t.casefold() for t in action["tags"]}
                    merged = [t for t in existing if t.casefold() not in drop]
                rec = self.workspace.add_record(
                    project_id,
                    kind="source_curation",
                    data={"source_id": sid, "tags": merged},
                )
                catalog_map[sid]["tags"] = merged
                results.append({"type": atype, "source_id": sid, "tags": merged, "record_id": rec["id"], "ok": True})
            elif atype == "set_category":
                rec = self.workspace.add_record(
                    project_id,
                    kind="source_curation",
                    data={"source_id": action["source_id"], "category": action["category"]},
                )
                results.append({"type": atype, "source_id": action["source_id"], "record_id": rec["id"], "ok": True})
            elif atype == "screen_source":
                rec = self.workspace.add_record(
                    project_id,
                    kind="screening",
                    data={
                        "source_id": action["source_id"],
                        "decision": action["decision"],
                        "rationale": action["rationale"],
                    },
                )
                results.append({"type": atype, "source_id": action["source_id"], "record_id": rec["id"], "ok": True})
            elif atype == "add_source":
                rec = self.workspace.add_record(
                    project_id,
                    kind="source",
                    data={"title": action["title"], "locator": action["locator"]},
                )
                results.append({"type": atype, "record_id": rec["id"], "ok": True})
            elif atype in {"bundle_notebooklm", "upload_notebooklm", "sync_zotero", "pack_obsidian"}:
                if self.sync_hooks is None:
                    raise WorkspaceError("Sync hooks are unavailable in this server mode", "integrations_unavailable")
                if atype == "bundle_notebooklm":
                    hook_payload: dict[str, Any] = {}
                    if action.get("selected_source_ids"):
                        hook_payload["selected_source_ids"] = action["selected_source_ids"]
                    hook_res = self.sync_hooks.bundle_notebooklm(project_id, hook_payload)
                elif atype == "upload_notebooklm":
                    hook_payload = {}
                    if action.get("selected_source_ids"):
                        hook_payload["selected_source_ids"] = action["selected_source_ids"]
                    hook_res = self.sync_hooks.upload_notebooklm(project_id, hook_payload)
                elif atype == "sync_zotero":
                    zot_payload: dict[str, Any] = {"dry_run": bool(action.get("dry_run", True))}
                    if action.get("selected_source_ids"):
                        zot_payload["selected_source_ids"] = action["selected_source_ids"]
                    if not zot_payload["dry_run"]:
                        if action.get("expected_library"):
                            zot_payload["expected_library"] = action["expected_library"]
                        if action.get("expected_revisions"):
                            zot_payload["expected_revisions"] = action["expected_revisions"]
                        if action.get("expected_plan_digest"):
                            zot_payload["expected_plan_digest"] = action["expected_plan_digest"]
                    hook_res = self.sync_hooks.sync_zotero(project_id, zot_payload)
                else:
                    hook_payload = {}
                    if action.get("selected_source_ids"):
                        hook_payload["selected_source_ids"] = action["selected_source_ids"]
                    hook_res = self.sync_hooks.pack_obsidian(project_id, hook_payload)
                results.append({"type": atype, "ok": True, "detail": hook_res})

        return {"ok": True, "applied_count": len(results), "results": results}
