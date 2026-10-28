#!/usr/bin/env python3
"""Optional offline presentation of native observations; Python standard library only."""
import sys

sys.dont_write_bytecode = True

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
from urllib.parse import quote, urlsplit

LIMIT = 4 * 1024 * 1024
LEVELS = {"unavailable": -1, "metadata": 0, "abstract": 1, "excerpt": 2, "full-text": 3}
SOURCE_FIELDS = "id work_id title locator access need_ids relevance version reading_level reading_ref material attempt_ids".split()
LABELS = {
    "en": ("Stage 1 source reader", "Sources", "Recorded needs", "Completion", "Bibliography", "Provided category", "Provided summary", "Provided claims", "Limitations", "Not supplied", "Unknown version (null)"),
    "zh-TW": ("Stage 1 來源閱讀頁", "來源", "已記錄的研究需求", "完成狀態", "參考書目", "提供的分類", "提供的摘要", "提供的主張", "限制", "未提供", "版本未知（null）"),
}
NOTICE = {
    "en": "Caller-provided observations and presentation only. Reading, source support, bibliography verification and translation parity are not attested. No inclusion or Stage 2 decision is made.",
    "zh-TW": "本頁僅呈現呼叫者提供的觀察與內容，不認證實際閱讀、來源支持、書目查核或翻譯對等性，也不作納入文獻或 Stage 2 決定。",
}


class ReaderError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReaderError(message)


def obj(value, required, optional=()):
    require(isinstance(value, dict), "expected an object")
    require(set(required) <= set(value) <= set(required) | set(optional), "missing or unexpected fields")
    return value


def text(value, nullable=False):
    if nullable and value is None:
        return value
    require(isinstance(value, str) and bool(value.strip()), "expected nonempty text")
    require(len(value) <= 20000, "text exceeds presentation bound")
    require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value), "control character in text")
    value.encode("utf-8", errors="strict")
    return value


def rows(value):
    require(isinstance(value, list) and len(value) <= 10000, "expected a bounded array")
    return value


def strings(value):
    for item in rows(value):
        text(item)
    require(len(value) == len(set(value)), "duplicate reference")
    return value


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(source):
    return [source["id"], source["work_id"], source["version"]]


def token(value):
    return sha(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def source_anchor(source):
    return "source-" + token(identity(source))


def bib_key(source):
    return "ref_" + token(identity(source))


def url(value):
    text(value)
    require(not any(c.isspace() or ord(c) < 32 for c in value), "unsafe URL whitespace")
    parsed = urlsplit(value)
    require(parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname), "unsafe URL scheme or host")
    require(parsed.username is None and parsed.password is None, "URL credentials are not supported")
    parsed.port  # Reject malformed ports before rendering.
    return value


def locator_link(value):
    """Citation strings stay text; only explicit HTTP(S) locators become links."""
    text(value)
    scheme = urlsplit(value).scheme.lower()
    if scheme in {"http", "https"}:
        return url(value)
    require(scheme not in {"javascript", "vbscript", "data", "file", "blob"} and "://" not in value,
            "unsafe bibliography locator scheme")
    return None


def material(value):
    if value is None:
        return
    obj(value, ["path", "sha256"])
    name = text(value["path"])
    parts = PurePosixPath(name.replace("\\", "/")).parts
    require(not PureWindowsPath(name).drive and not name.startswith(("/", "\\"))
            and ".." not in parts and not any(p.casefold() in {".git", ".research"} for p in parts), "unsafe material reference")
    require(isinstance(value["sha256"], str) and re.fullmatch("[0-9a-f]{64}", value["sha256"]), "invalid material hash")


def indexed(items, field):
    found = {}
    for item in rows(items):
        require(isinstance(item, dict) and field in item, "missing identity")
        key = text(item[field])
        require(key not in found, "duplicate identity: " + key)
        found[key] = item
    return found


def observations_view(value):
    """Check presentation fields/references, not native execution or source binding."""
    obj(value, "format run_id project_id brief capabilities needs attempts sources completion".split())
    require(value["format"] == "research-discovery-observations/1.0", "unsupported observations format")
    for key in ("run_id", "project_id", "brief"):
        text(value[key])
    for capability in rows(value["capabilities"]):
        obj(capability, ["name", "kind", "availability", "observation"])
        text(capability["name"])
        text(capability["observation"])
        require(capability["kind"] in {"search", "deep-research", "read", "citation", "skill"}, "invalid capability kind")
        require(capability["availability"] in {"available", "unavailable", "unknown"}, "invalid capability availability")
    needs = indexed(value["needs"], "id")
    for need in needs.values():
        obj(need, ["id", "text", "families", "status"])
        text(need["text"])
        strings(need["families"])
        require(need["status"] in {"covered", "unresolved", "not-assessed"}, "invalid need status")
    attempts = indexed(value["attempts"], "id")
    for attempt in attempts.values():
        obj(attempt, "id need_ids kind tool input status outcome result_count receipt".split())
        require(set(strings(attempt["need_ids"])) <= set(needs), "unknown attempt need")
        text(attempt["tool"], True)
        text(attempt["input"])
        require(attempt["kind"] in {"search", "read"}, "invalid attempt kind")
        require(attempt["status"] in {"planned", "declared", "observed", "unavailable"}, "invalid attempt status")
        require(attempt["outcome"] in {"success", "empty", "partial", "timeout", "denied", "error", "unknown"}, "invalid attempt outcome")
        count = attempt["result_count"]
        require(count is None or type(count) is int and count >= 0, "invalid result count")
        if attempt["receipt"] is not None:
            receipt = obj(attempt["receipt"], ["reference", "material"])
            text(receipt["reference"], True)
            material(receipt["material"])
    sources = indexed(value["sources"], "id")
    for source in sources.values():
        obj(source, SOURCE_FIELDS)
        for key in ("work_id", "title", "locator", "relevance"):
            text(source[key])
        text(source["version"], True)
        text(source["reading_ref"], True)
        require(source["reading_level"] in LEVELS, "invalid reading level")
        if LEVELS[source["reading_level"]] > 0:
            require(source["reading_ref"] is not None, "assessed reading requires its recorded reference")
        require(source["access"] in {"public", "restricted", "unavailable", "unknown"}, "invalid access state")
        require(set(strings(source["need_ids"])) <= set(needs), "unknown source need")
        require(set(strings(source["attempt_ids"])) <= set(attempts), "unknown source attempt")
        material(source["material"])
        locator_link(source["locator"])
    completion = obj(value["completion"], ["status", "reason", "residual_need_ids"])
    text(completion["reason"])
    require(completion["status"] in {"continue", "partial", "bounded-complete"}, "invalid completion state")
    require(set(strings(completion["residual_need_ids"])) <= set(needs), "unknown residual need")
    return sources


def joined(record, sources):
    source = sources.get(text(record["source_id"]))
    require(source is not None, "unknown source identity")
    text(record["work_id"])
    text(record["version"], True)
    require([record["source_id"], record["work_id"], record["version"]] == identity(source), "source/work/version mismatch")
    return source


def observation_translations_view(value, observations, observations_sha256, sources):
    """Bind caller-supplied presentation text to one exact observation snapshot."""
    obj(value, ["observations_sha256", "run_id", "project_id"], ["brief", "completion_reason", "needs", "sources"])
    require(value["observations_sha256"] == observations_sha256, "translation observation hash mismatch")
    require(value["run_id"] == observations["run_id"] and value["project_id"] == observations["project_id"], "translation run/project mismatch")
    for field in ("brief", "completion_reason"):
        if field in value:
            text(value[field])
    needs = indexed(value.get("needs", []), "id")
    original_needs = {item["id"] for item in observations["needs"]}
    for item in needs.values():
        obj(item, ["id", "text"])
        require(item["id"] in original_needs, "unknown translated need")
        text(item["text"])
    translated_sources = {}
    for item in rows(value.get("sources", [])):
        obj(item, ["source_id", "work_id", "version"], ["title", "relevance"])
        source = joined(item, sources)
        require(source["id"] not in translated_sources, "duplicate translated source")
        require("title" in item or "relevance" in item, "translated source has no text")
        for field in ("title", "relevance"):
            if field in item:
                text(item[field])
        translated_sources[source["id"]] = item
    return {"brief": value.get("brief"), "completion_reason": value.get("completion_reason"), "needs": needs, "sources": translated_sources}


def content_view(value, language, sources, shared_claims, observations, observations_sha256):
    version = value.get("format") if isinstance(value, dict) else None
    optional = ["delivery_notes"]
    if version == "native-reader-content/1.1":
        optional.append("observation_translations")
    obj(value, ["format", "language", "records"], optional)
    require(isinstance(version, str) and version in {"native-reader-content/1.0", "native-reader-content/1.1"} and value["language"] == language, "requested language content is missing or mismatched")
    translations = None
    if "observation_translations" in value:
        translations = observation_translations_view(value["observation_translations"], observations, observations_sha256, sources)
    for note in rows(value.get("delivery_notes", [])):
        text(note)
    found, claim_ids = {}, set()
    for record in rows(value["records"]):
        obj(record, "source_id work_id version reading_level reading_ref".split(), ["category", "summary", "limitations", "claims"])
        source = joined(record, sources)
        require(source["id"] not in found, "duplicate source presentation")
        require(record["reading_level"] == source["reading_level"] and record["reading_ref"] == source["reading_ref"], "presentation changes recorded reading scope/reference")
        if record.get("category") is not None:
            category = obj(record["category"], ["label", "reason"])
            text(category["label"])
            text(category["reason"])
        text(record.get("summary"), True)
        for item in rows(record.get("limitations", [])):
            text(item)
        for claim in rows(record.get("claims", [])):
            obj(claim, ["id", "text", "reading_level", "reading_ref", "locator"])
            key = text(claim["id"])
            require(key not in claim_ids, "duplicate claim identity")
            claim_ids.add(key)
            text(claim["text"])
            require(claim["reading_level"] in LEVELS and LEVELS[claim["reading_level"]] <= LEVELS[source["reading_level"]], "claim exceeds recorded reading scope")
            require(claim["reading_ref"] == source["reading_ref"], "claim reading reference differs from source")
            text(claim["locator"], True)
            if LEVELS[claim["reading_level"]] > 0:
                require(claim["locator"] is not None, "assessed claim needs a supplied locator")
            binding = identity(source) + [claim["reading_level"], claim["reading_ref"], claim["locator"]]
            require(key not in shared_claims or shared_claims[key] == binding, "cross-language claim identity/scope mismatch")
            shared_claims[key] = binding
        found[source["id"]] = record
    return found, translations


def bibliography_view(value, sources):
    obj(value, ["format", "records"])
    version = value["format"]
    require(isinstance(version, str) and version in {"native-reader-bibliography/1.0", "native-reader-bibliography/1.1"}, "unsupported bibliography format")
    found = {}
    for record in rows(value["records"]):
        optional = ["authors", "year", "venue", "doi", "url"]
        if version == "native-reader-bibliography/1.1":
            optional.append("author_kinds")
        obj(record, ["source_id", "work_id", "version", "title", "verification_ref"], optional)
        source = joined(record, sources)
        require(source["id"] not in found, "duplicate bibliography source")
        require(record["title"] == source["title"], "bibliography changes original title")
        require(text(record["verification_ref"]) in {source["locator"], source["reading_ref"]}, "bibliography verification pointer is not a recorded source reference")
        if record.get("authors") is not None:
            # Display names are ordered metadata, not unique reference IDs.
            for name in rows(record["authors"]):
                text(name)
        if "author_kinds" in record:
            kinds = rows(record["author_kinds"])
            require(isinstance(record.get("authors"), list) and len(kinds) == len(record["authors"]), "author kinds require a matching authors list")
            for name, kind in zip(record["authors"], kinds):
                require(isinstance(kind, str) and kind in {"person", "literal"}, "invalid author kind")
                if kind == "person":
                    require(re.search(r"(?<!\S)and(?!\S)", name, flags=re.IGNORECASE) is None, "person author contains ambiguous BibTeX and delimiter")
                    require("{" not in name and "}" not in name, "person author contains BibTeX grouping braces")
                    parts = name.split(",")
                    require(len(parts) <= 3 and all(any(not c.isspace() and c != "-" for c in part) for part in parts), "person author must have at most two commas and name components containing non-separator text")
        if record.get("year") is not None:
            require(type(record["year"]) is int and 0 < record["year"] < 10000, "invalid supplied year")
        text(record.get("venue"), True)
        if record.get("url") is not None:
            url(record["url"])
        if record.get("doi") is not None:
            doi = text(record["doi"])
            require(not any(127 <= ord(c) <= 159 for c in doi), "control character in DOI")
            require(re.fullmatch(r"10\.\d{4,9}/[^\s]+", doi), "invalid supplied DOI")
        found[source["id"]] = record
    return found


def tex(value):
    escapes = {"\\": r"\textbackslash{}", "{": r"\textbraceleft{}", "}": r"\textbraceright{}", "$": r"\$", "&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\n": " ", "\r": " ", "\t": " "}
    return "".join(escapes.get(c, c) for c in value)


def bibtex(sources, bibliography):
    entries = []
    for key in sorted(bibliography):
        record = bibliography[key]
        fields = {"title": tex(record["title"])}
        if record.get("authors"):
            kinds = record.get("author_kinds", ["literal"] * len(record["authors"]))
            fields["author"] = " and ".join(tex(name) if kind == "person" else "{" + tex(name) + "}"
                                           for name, kind in zip(record["authors"], kinds))
        for source_key, target_key in [("year", "year"), ("venue", "journal")]:
            if record.get(source_key) is not None:
                fields[target_key] = tex(str(record[source_key]))
        for name in ("doi", "url"):
            if record.get(name) is not None:
                fields[name] = quote(record[name], safe=":/?#[]@!$&'()*+,;=%-._~")
        entries.append("@misc{" + bib_key(sources[key]) + ",\n" + ",\n".join("  " + k + " = {" + v + "}" for k, v in fields.items()) + "\n}")
    return ("% Supplied verified bibliography only; verification is caller-recorded.\n" + "\n\n".join(entries) + "\n").encode("utf-8")


def esc(value):
    return html.escape(str(value), quote=True)


def paragraph(label, value):
    return "<p><strong>" + esc(label) + ":</strong> " + esc(value) + "</p>"


def reader_html(language, observations, sources, content, bibliography, languages, input_hashes, delivery_notes=(), attachments=(), translations=None):
    title, source_label, needs_label, completion_label, bib_label, category_label, summary_label, claims_label, limits_label, missing, unknown = LABELS[language]
    zh = language == "zh-TW"
    def ui(en, tw):
        return tw if zh else en
    status_zh = {"continue": "繼續", "partial": "部分完成", "bounded-complete": "範圍內完成",
                 "covered": "已涵蓋", "unresolved": "未解決", "not-assessed": "未評估",
                 "unavailable": "無法取得", "metadata": "僅書目資料", "abstract": "摘要", "excerpt": "摘錄", "full-text": "全文",
                 "public": "公開", "restricted": "受限", "unknown": "未知"}
    def status(value):
        return status_zh[value] + " (" + value + ")" if zh else value
    has_translations = translations is not None
    def original_value(value):
        # The observations schema does not identify the language of free text.
        return '<span lang="">' + esc(value) + '</span>' if has_translations else esc(value)
    def original_paragraph(label, value):
        if not has_translations:
            return paragraph(label, value)
        return '<p><strong>' + esc(label) + ':</strong> ' + original_value(value) + '</p>'
    def original_title(value):
        return ui('Original title: ', '原始標題：') + original_value(value)
    def supplied_translation(value, label=None):
        if value is None:
            return ""
        return paragraph(label or ui('Supplied translation (not verified)', '提供的翻譯（未經驗證）'), value)
    translations = translations or {"brief": None, "completion_reason": None, "needs": {}, "sources": {}}
    def index_title(source):
        translated = translations['sources'].get(source['id'], {}).get('title')
        extra = (' — ' + ui('Supplied title translation (not verified): ', '提供的標題翻譯（未經驗證）：') + esc(translated)) if translated is not None else ''
        return original_title(source['title']) + extra
    def back():
        return '<p><a href="#contents">' + ui('Back to contents', '返回目錄') + '</a></p>'
    ordered = sorted(sources.values(), key=lambda source: identity(source)[0])
    works = {}
    categories = {}
    for source in ordered:
        works.setdefault(source["work_id"], []).append(source)
        category = content.get(source["id"], {}).get("category")
        if category:
            categories.setdefault(category["label"], []).append(source)
    def work_anchor(work_id):
        return "work-" + token(work_id)
    out = ["<!doctype html><html lang=\"" + language + "\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
           "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">",
           "<title>" + esc(title) + "</title><style>body{max-width:76ch;margin:auto;padding:1.5rem;font:1rem/1.65 system-ui;color:#202b36;background:#faf9f6}a{color:#005c78}article,section,details{margin:1.5rem 0;padding:1rem;border:1px solid #bbc6cc;border-radius:.4rem}p,li,pre{white-space:pre-wrap;overflow-wrap:anywhere}code{overflow-wrap:anywhere}:target{outline:3px solid #b48b35}nav a{margin-right:1rem}.scope{background:#eef2f3;padding:.5rem}dt{font-weight:600}dd{margin:0 0 .5rem}</style></head><body id=\"top\"><a href=\"#main\">" + ui("Skip to content", "跳至主要內容") + "</a><header><h1>" + esc(title) + "</h1>",
           "<p>" + esc(NOTICE[language]) + "</p><nav aria-label=\"" + ui("Exports", "匯出及語言") + "\"><a href=\"native-reader.json\">JSON</a><a href=\"references.bib\">BibTeX</a>"]
    language_names = {"en": "English", "zh-TW": "繁體中文"}
    for lang in languages:
        out.append('<a href="reader.' + lang + '.html" lang="' + lang + '" hreflang="' + lang + '">' + language_names[lang] + '</a>')
    for name in attachments:
        label = ui("Supplied PDF attachment (language/content not verified): ", "提供的 PDF 附件（語言及內容未經驗證）：") if name.lower().endswith(".pdf") else ""
        out.append('<a download href="' + esc(name) + '">' + esc(label + name) + '</a>')
    out.extend(["</nav>", paragraph(ui("Languages supplied", "已提供的語言"), ", ".join(languages) or missing), paragraph(ui("Languages not supplied", "未提供的語言"), ", ".join(sorted(set(LABELS) - set(languages))) or "—"), "</header><main id=\"main\">",
                '<section id="brief"><h2>' + ui('Research brief', '研究簡述') + '</h2>', supplied_translation(translations['brief']) + original_paragraph(ui('Original brief', '原始研究簡述'), observations['brief']),
                paragraph(ui('Run / project', '執行 / 專案'), observations['run_id'] + ' / ' + observations['project_id']),
                paragraph(ui('Distinct work IDs / source-version observations', '不同作品 ID / 來源版本紀錄'), str(len(works)) + ' / ' + str(len(ordered))), '</section>',
                '<section id="completion"><h2>' + esc(completion_label) + '</h2>'])
    completion = observations['completion']
    out.extend([paragraph(ui('Recorded status', '紀錄狀態'), status(completion['status'])), supplied_translation(translations['completion_reason']) + original_paragraph(ui('Original recorded reason', '原始紀錄原因'), completion['reason']),
                paragraph(ui('Residual need IDs', '剩餘需求 ID'), ', '.join(completion['residual_need_ids']) or '—'), '</section>',
                '<section id="needs"><h2>' + esc(needs_label) + '</h2>'])
    for need in observations['needs']:
        translated_need = translations['needs'].get(need['id'])
        out.append(supplied_translation(translated_need['text'] if translated_need else None, need['id'] + ' / ' + ui('Supplied translation (not verified)', '提供的翻譯（未經驗證）')) + original_paragraph(need['id'] + ' / ' + status(need['status']) + ' / ' + ui('original', '原文'), need['text']))
    out.extend(['</section><nav id="contents" aria-label="' + ui('Contents', '目錄') + '"><h2>' + ui('Contents', '目錄') + '</h2>',
                '<a href="#categories">' + ui('Provided categories', '提供的分類') + '</a><a href="#literature">' + ui('Works and versions', '作品與版本') + '</a><a href="#bibliography">' + esc(bib_label) + '</a><a href="#delivery-notes">' + ui('Appendix', '附錄') + '</a></nav>',
                '<section id="categories"><h2>' + ui('Provided categories', '提供的分類') + '</h2><p>' + ui('Labels are supplied presentation labels, not scientific classifications or inclusion decisions.', '分類名稱僅為提供的呈現標籤，不代表科學分類或納入決定。') + '</p>'])
    if not categories:
        out.append('<p>' + esc(missing) + '</p>')
    for label, category_sources in sorted(categories.items()):
        out.append('<h3>' + esc(label) + '</h3><ul>')
        for source in category_sources:
            out.append('<li><a href="#' + source_anchor(source) + '">' + index_title(source) + " — " + esc(source["work_id"]) + " / " + esc(source["id"]) + " / " + esc(source["version"] if source["version"] is not None else unknown) + '</a></li>')
        out.append('</ul>')
    out.extend([back(), '</section><section id="literature"><h2>' + ui('Works and versions', '作品與版本') + '</h2><ul>'])
    for work_id, versions in sorted(works.items()):
        out.append('<li><a href="#' + work_anchor(work_id) + '">' + original_title(versions[0]['title']) + ' — ' + esc(work_id) + '</a><ul>')
        for source in versions:
            out.append('<li><a href="#' + source_anchor(source) + '">' + index_title(source) + ' — ' + esc(source['id']) + ' / ' + esc(source['version'] if source['version'] is not None else unknown) + '</a></li>')
        out.append('</ul></li>')
    out.append('</ul></section>')
    for work_id, versions in sorted(works.items()):
        out.append('<section id="' + work_anchor(work_id) + '"><h2>' + ui('Work', '作品') + ': ' + esc(work_id) + '</h2>')
        for source in versions:
            record = content.get(source['id'], {})
            translated_source = translations['sources'].get(source['id'], {})
            out.extend(['<article id="' + source_anchor(source) + '"><h3>' + original_title(source['title']) + '</h3>' + supplied_translation(translated_source.get('title'), ui('Supplied title translation (not verified)', '提供的標題翻譯（未經驗證）')), paragraph(ui('Source / work', '來源 / 作品'), source['id'] + ' / ' + source['work_id']), paragraph(ui('Version', '版本'), source['version'] if source['version'] is not None else unknown),
                        '<div class="scope">' + paragraph(ui('Recorded reading level / access', '紀錄的閱讀層級 / 取得狀態'), status(source['reading_level']) + ' / ' + status(source['access'])) + paragraph(ui('Original recorded reading reference', '原始紀錄閱讀參照'), source['reading_ref'] or missing) + '</div>', supplied_translation(translated_source.get('relevance'), ui('Supplied relevance translation (not verified)', '提供的相關性翻譯（未經驗證）')) + original_paragraph(ui('Original relevance', '原始相關性說明'), source['relevance']), paragraph(ui('Recorded need IDs / attempt IDs', '紀錄的需求 ID / 嘗試 ID'), ', '.join(source['need_ids']) + ' / ' + ', '.join(source['attempt_ids']))])
            link = locator_link(source['locator'])
            out.append('<p><strong>' + ui('Original locator', '原始定位資訊') + ':</strong> ' + ('<a href="' + esc(link) + '" rel="noreferrer">' + esc(source['locator']) + '</a>' if link else esc(source['locator'])) + '</p>')
            if source['material'] is not None:
                out.append(paragraph(ui('Recorded material reference (not opened or rebound)', '紀錄的材料參照（未開啟或重新綁定）'), source['material']['path'] + ' / ' + source['material']['sha256']))
            category = record.get('category')
            out.extend([paragraph(category_label, (category['label'] + ' — ' + category['reason']) if category else missing), paragraph(summary_label, record.get('summary') or missing), '<h4>' + esc(claims_label) + '</h4>'])
            if not record.get('claims'):
                out.append('<p>' + esc(missing) + '</p>')
            for claim in record.get('claims', []):
                out.extend(['<section id="claim-' + token([source['id'], claim['id']]) + '"><h5>' + esc(claim['id']) + '</h5><p>' + esc(claim['text']) + '</p>', paragraph(ui('Provided scope', '提供的範圍'), status(claim['reading_level'])), paragraph(ui('Recorded reference / supplied locator', '紀錄參照 / 提供的定位資訊'), (claim['reading_ref'] or missing) + ' / ' + (claim['locator'] or missing)), '</section>'])
            out.append('<h4>' + esc(limits_label) + '</h4><ul>' + ''.join('<li>' + esc(v) + '</li>' for v in record.get('limitations', [])) + '</ul>')
            if source['id'] in bibliography:
                out.append('<p><a href="#bib-' + bib_key(source) + '">' + esc(bib_label) + '</a></p>')
            out.append(back() + '</article>')
        out.append('</section>')
    out.extend(['<section id="bibliography"><h2>' + esc(bib_label) + '</h2><p>' + ui('BibTeX exports supplied version records; fields may be unknown or missing, so these are not necessarily complete citations. Check version records and author formatting on import.', 'BibTeX 匯出的是提供的版本紀錄；欄位可能未知或缺漏，因此不一定是完整引文。匯入時請檢查版本紀錄與作者格式。') + '</p>'])
    for key in sorted(bibliography):
        record = bibliography[key]
        source = sources[key]
        out.extend(['<section id="bib-' + bib_key(source) + '"><h3>' + original_title(record['title']) + '</h3>',
                    paragraph(ui('Source / work / version', '來源 / 作品 / 版本'), source['id'] + ' / ' + source['work_id'] + ' / ' + (source['version'] if source['version'] is not None else unknown)),
                    '<p><strong>' + ui('Authors (supplied display names)', '作者（提供的顯示名稱）') + ':</strong></p>' + ('<ul>' + ''.join('<li>' + esc(name) + '</li>' for name in record['authors']) + '</ul>' if record.get('authors') else '<p>' + esc(missing) + '</p>'),
                    paragraph(ui('Year', '年份'), record.get('year') if record.get('year') is not None else missing),
                    paragraph(ui('Venue', '出版處'), record.get('venue') if record.get('venue') is not None else missing),
                    paragraph('DOI', record.get('doi') if record.get('doi') is not None else missing),
                    paragraph('URL', record.get('url') if record.get('url') is not None else missing),
                    paragraph(ui('BibTeX key', 'BibTeX 鍵值'), bib_key(source)),
                    paragraph(ui('Caller-recorded verification reference', '呼叫者紀錄的驗證參照'), record['verification_ref']), '</section>'])
    out.extend([back(), '</section><details id="delivery-notes"><summary>' + ui('Appendix: supplied delivery notes and tool audit', '附錄：提供的交付說明與工具稽核') + '</summary>'])
    if delivery_notes:
        out.append('<h2>' + ui('Supplied delivery notes', '提供的交付說明') + '</h2>' + ''.join('<p>' + esc(note) + '</p>' for note in delivery_notes))
    out.extend(['<h2>' + ui('Original capability and attempt records', '原始能力與嘗試紀錄') + '</h2><pre>' + esc(json.dumps({'capabilities': observations['capabilities'], 'attempts': observations['attempts']}, ensure_ascii=False, sort_keys=True, indent=2)) + '</pre>', back(), '</details></main><footer>' + paragraph(ui('Input SHA256', '輸入 SHA256'), json.dumps(input_hashes, ensure_ascii=False, sort_keys=True)) + back() + '</footer></body></html>'])
    return "\n".join(out).encode("utf-8")

class Navigation(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.links = set(), []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            require(attrs["id"] not in self.ids, "duplicate generated navigation ID")
            self.ids.add(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))


def verify_links(files, required_exports=()):
    pages = {}
    for name, data in files.items():
        if name.endswith(".html"):
            page = Navigation()
            page.feed(data.decode("utf-8"))
            page.close()
            pages[name] = page
    for name, page in pages.items():
        require(set(required_exports) <= set(page.links), "required export is not discoverable in " + name)
        for href in page.links:
            parsed = urlsplit(href)
            if parsed.scheme:
                url(href)
                continue
            require(not parsed.netloc and not parsed.query and parsed.path in {"", *files}, "unresolved local export link")
            target = parsed.path or name
            if parsed.fragment:
                require(target in pages and parsed.fragment in pages[target].ids, "unresolved local navigation fragment")


def safe_path(value, must_exist=True):
    path = Path(value)
    require(".." not in path.parts, "path traversal is not supported")
    path = Path(os.path.abspath(path))
    for part in reversed([path, *path.parents]):
        try:
            info = part.lstat()
        except FileNotFoundError:
            require(not must_exist and part == path, "input or output parent is missing")
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024), "linked paths are not supported")
    return path


def read_file(value):
    path = safe_path(value)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "input must be a single-link regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    # A FIFO substituted after the pathname check must not block before fstat.
    if os.name == "posix":
        flags |= os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        require(stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1, "input must be a single-link regular file")
        require((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino), "input identity changed")
        data = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
    require(len(data) <= LIMIT, "input exceeds 4 MiB")
    require((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "input changed during read")
    return path, data


def read_input(value):
    path, data = read_file(value)
    def pairs(items):
        result = {}
        for key, item in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = item
        return result
    def constant(value):
        raise ReaderError("nonfinite JSON value: " + value)
    payload = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=constant)
    return path, data, payload


def prepare(observations, content_en=None, content_zh_tw=None, bibliography=None, attachments=()):
    inputs = {"observations": read_input(observations)}
    profile = inputs["observations"][2]
    sources = observations_view(profile)
    content, presentation, shared_claims, translations = {}, {}, {}, {}
    for language, path in [("en", content_en), ("zh-TW", content_zh_tw)]:
        if path is not None:
            inputs[language] = read_input(path)
            presentation[language] = inputs[language][2]
            content[language], translations[language] = content_view(presentation[language], language, sources, shared_claims, profile, sha(inputs["observations"][1]))
    bibliography_payload = None
    bibliography_records = {}
    if bibliography is not None:
        inputs["bibliography"] = read_input(bibliography)
        bibliography_payload = inputs["bibliography"][2]
        bibliography_records = bibliography_view(bibliography_payload, sources)
    require(isinstance(attachments, (list, tuple)) and len(attachments) <= 8, "at most 8 attachments are supported")
    supporting_files, folded_names = {}, set()
    for value in attachments:
        path, data = read_file(value)
        name = path.name
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.(?:json|md|txt|pdf)", name, flags=re.IGNORECASE), "unsafe attachment name or type")
        require(name.casefold() not in {"native-reader.json", "manifest.json"}, "attachment collides with a generated export")
        require(name.casefold() not in folded_names, "duplicate attachment name")
        if path.suffix.lower() != ".pdf":
            require("\x00" not in data.decode("utf-8-sig"), "attachment must be UTF-8 text without NUL")
        folded_names.add(name.casefold())
        supporting_files[name] = data
        inputs["attachment:" + name] = path, data, None
    attachment_names = sorted(supporting_files)
    input_hashes = {key: sha(item[1]) for key, item in inputs.items()}
    languages = sorted(content)
    exported = {"format": "native-reader-presentation/1.0", "observations": profile, "content": presentation, "bibliography": bibliography_payload,
                "languages_supplied": languages, "languages_not_supplied": sorted(set(LABELS) - set(languages)),
                "bib_keys": {key: bib_key(sources[key]) for key in sorted(bibliography_records)},
                "validation_scope": "presentation fields, exact references and generated links only; native evidence checker and semantic verification not performed"}
    if attachment_names:
        exported["attachments"] = [{"name": name, "bytes": len(supporting_files[name]), "sha256": sha(supporting_files[name])} for name in attachment_names]
    files = {"native-reader.json": canonical(exported), "references.bib": bibtex(sources, bibliography_records)}
    files.update(supporting_files)
    for language in languages:
        files["reader." + language + ".html"] = reader_html(language, profile, sources, content[language], bibliography_records, languages, input_hashes,
            presentation[language].get("delivery_notes", []), attachment_names, translations[language])
    verify_links(files, required_exports=["native-reader.json", "references.bib", *attachment_names])
    manifest = {"format": "native-reader-output/1.0", "status": "complete", "inputs": {key: {"name": item[0].name, "bytes": len(item[1]), "sha256": sha(item[1])} for key, item in inputs.items()},
                "outputs": {name: {"bytes": len(data), "sha256": sha(data)} for name, data in sorted(files.items())},
                "languages": languages, "source_records": len(sources), "distinct_work_ids": len({s["work_id"] for s in sources.values()}),
                "unknown_version_records": sum(s["version"] is None for s in sources.values()), "bibliography_records": len(bibliography_records)}
    return inputs, files, manifest


def write_file(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def generate(output, inputs, files, manifest):
    path = safe_path(output, must_exist=False)
    require(not path.exists(), "output already exists; preserve it and choose a new output set")
    require(path.parent.is_dir(), "output parent is missing")
    for input_path, _, _ in inputs.values():
        require(path != input_path and path not in input_path.parents and input_path not in path.parents, "input/output overlap")
    path.mkdir()  # Exclusive reservation: concurrent runs never share or replace an output set.
    for name, data in sorted(files.items()):
        write_file(path / name, data)
    for input_path, original, _ in inputs.values():
        require(read_file(input_path)[1] == original, "input changed during generation; output remains incomplete")
    write_file(path / "manifest.json", canonical(manifest))  # Completion record is last.
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--content-en", type=Path)
    parser.add_argument("--content-zh-TW", dest="content_zh_tw", type=Path)
    parser.add_argument("--bibliography", type=Path)
    parser.add_argument("--attachment", action="append", type=Path, default=[], help="explicit supporting UTF-8 JSON/Markdown/text or opaque PDF file; repeat up to 8 times")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        require(args.check_only or args.output_dir is not None, "--output-dir is required for generation")
        inputs, files, manifest = prepare(args.observations, args.content_en, args.content_zh_tw, args.bibliography, args.attachment)
        if args.check_only:
            print(json.dumps({"status": "render-inputs-valid", "writes": False, "manifest_preview": manifest}, ensure_ascii=True, sort_keys=True))
        else:
            output = generate(args.output_dir, inputs, files, manifest)
            print(json.dumps({"status": "generated", "output_dir": str(output), "manifest_sha256": sha(canonical(manifest)), "languages": manifest["languages"]}, ensure_ascii=True, sort_keys=True))
    except (ReaderError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
