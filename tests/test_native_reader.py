"""Offline synthetic acceptance for the optional standard-library skill renderer."""
import contextlib
import copy
import errno
import hashlib
from html.parser import HTMLParser
import importlib.util
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/research-hub/scripts/render_native_reader.py"
SPEC = importlib.util.spec_from_file_location("native_reader", SCRIPT)
reader = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "dont_write_bytecode", True):
    SPEC.loader.exec_module(reader)


def fixture():
    sources = []
    for index, (work, version, level, access) in enumerate([
        ("work-one", "v1", "full-text", "public"),
        ("work-one", "v2", "abstract", "restricted"),
        ("work-two", None, "metadata", "unknown"),
        ("work-three", "v1", "excerpt", "public"),
        ("work-four", None, "unavailable", "unavailable"),
    ], 1):
        key = "S" + str(index)
        sources.append({"id": key, "work_id": work, "version": version,
                        "title": '<script>alert("title")</script> Same title' if index in (1, 3) else "Synthetic " + key,
                        "locator": "https://example.test/" + key, "access": access,
                        "reading_level": level, "reading_ref": "saved:" + key if level in {"full-text", "abstract", "excerpt"} else None,
                        "material": None, "attempt_ids": ["A1"] if index == 1 else [],
                        "need_ids": ["N1"], "relevance": "Synthetic relevance; not an inclusion decision."})
    observations = {"format": "research-discovery-observations/1.0", "run_id": "synthetic-run", "project_id": "synthetic-project",
                    "brief": "Synthetic reader acceptance, no literature assessment.",
                    "capabilities": [{"name": "fixture", "kind": "read", "availability": "available", "observation": "Authored synthetic input only."}],
                    "needs": [{"id": "N1", "text": "Unresolved synthetic need", "families": ["boundary"], "status": "unresolved"}],
                    "attempts": [{"id": "A1", "need_ids": ["N1"], "kind": "read", "tool": "synthetic fixture", "input": "Authored input",
                                  "status": "observed", "outcome": "success", "result_count": None, "receipt": {"reference": "synthetic-capture", "material": None}}],
                    "sources": sources, "completion": {"status": "partial", "reason": "Synthetic unresolved work remains", "residual_need_ids": ["N1"]}}
    content = {}
    for language in ("en", "zh-TW"):
        content[language] = {"format": "native-reader-content/1.0", "language": language, "records": []}
        for source in sources[:2]:
            content[language]["records"].append({"source_id": source["id"], "work_id": source["work_id"], "version": source["version"],
                "reading_level": source["reading_level"], "reading_ref": source["reading_ref"],
                "category": {"label": "Synthetic category", "reason": "Authored category, not formal inclusion."},
                "summary": "Synthetic supplied English, not model output." if language == "en" else "合成的中文測試內容，並非模型產出。",
                "limitations": ["No scientific acceptance or translation parity is established."],
                "claims": [{"id": "C" + source["id"], "text": '<img src="x" onerror="alert(1)"> Synthetic claim',
                            "reading_level": source["reading_level"], "reading_ref": source["reading_ref"], "locator": "Supplied section 1"}]})
    bibliography = {"format": "native-reader-bibliography/1.0", "records": []}
    for source in sources:
        bibliography["records"].append({"source_id": source["id"], "work_id": source["work_id"], "version": source["version"], "title": source["title"],
            "verification_ref": source["locator"], "authors": [r"Synthetic {Author} \write18 & % #"] if source["id"] == "S1" else None,
            "year": 2020 if source["id"] == "S1" else None, "venue": None, "doi": None, "url": source["locator"]})
    return observations, content, bibliography


class NativeReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-reader-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.observations, self.content, self.bibliography = fixture()
        self.obs = self.root / "observations.json"
        self.en = self.root / "content.en.json"
        self.zh = self.root / "content.zh-TW.json"
        self.bib = self.root / "bibliography.json"
        self.save_inputs()

    def save_inputs(self):
        for path, payload in [(self.obs, self.observations), (self.en, self.content["en"]), (self.zh, self.content["zh-TW"]), (self.bib, self.bibliography)]:
            path.write_bytes(reader.canonical(payload))

    def prepared(self, both=True):
        return reader.prepare(self.obs, self.en, self.zh if both else None, self.bib)

    def snapshot(self, path):
        return {str(p.relative_to(path)): (p.read_bytes(), p.stat().st_mtime_ns) for p in path.rglob("*") if p.is_file()}

    def test_import_writes_no_skill_bytecode_and_restores_host_flag(self):
        clone = self.root / "import-probe"
        test_path = clone / "tests/test_native_reader.py"
        script_path = clone / "skills/research-hub/scripts/render_native_reader.py"
        test_path.parent.mkdir(parents=True)
        script_path.parent.mkdir(parents=True)
        test_path.write_bytes(Path(__file__).read_bytes())
        script_path.write_bytes(SCRIPT.read_bytes())
        code = """import importlib.util, json, sys
from pathlib import Path
root = Path(sys.argv[1])
before = sys.dont_write_bytecode
assert before is False, 'probe requires default bytecode-enabled startup'
spec = importlib.util.spec_from_file_location('native_reader_import_probe', root / 'tests/test_native_reader.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
artifacts = sorted(str(p.relative_to(root)) for p in (root / 'skills').rglob('*.pyc'))
assert artifacts == [], artifacts
assert sys.dont_write_bytecode is before, 'test import changed the host bytecode flag'
print(json.dumps({'skill_bytecode': artifacts, 'host_flag_restored': True}))
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(clone)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"skill_bytecode": [], "host_flag_restored": True})

    def rejected(self):
        self.save_inputs()
        with self.assertRaises((reader.ReaderError, ValueError, TypeError)):
            self.prepared()

    def test_generation_preserves_all_scopes_and_restricted_bibliography(self):
        inputs, files, manifest = self.prepared()
        output = reader.generate(self.root / "reader", inputs, files, manifest)
        self.assertEqual(set(p.name for p in output.iterdir()), {*files, "manifest.json"})
        self.assertEqual((manifest["source_records"], manifest["distinct_work_ids"], manifest["unknown_version_records"]), (5, 4, 2))
        self.assertEqual(manifest["bibliography_records"], 5)
        exported = json.loads(files["native-reader.json"])
        self.assertEqual(exported["observations"], self.observations)
        self.assertEqual(len(set(exported["bib_keys"].values())), 5)
        self.assertNotEqual(exported["bib_keys"]["S1"], exported["bib_keys"]["S2"])
        self.assertNotEqual(exported["bib_keys"]["S1"], exported["bib_keys"]["S3"])
        for level in reader.LEVELS:
            self.assertIn(level, files["reader.en.html"].decode())
        self.assertIn("restricted", files["reader.en.html"].decode())
        self.assertIn("partial", files["reader.en.html"].decode())
        self.assertIn("N1", files["reader.en.html"].decode())
        for name, identity in manifest["outputs"].items():
            self.assertEqual(identity["sha256"], hashlib.sha256((output / name).read_bytes()).hexdigest())
        reader.verify_links(files)

    def test_missing_language_and_missing_bibliography_are_not_invented(self):
        _, files, manifest = reader.prepare(self.obs, self.en)
        self.assertNotIn("reader.zh-TW.html", files)
        self.assertEqual(manifest["languages"], ["en"])
        self.assertNotIn("@misc{", files["references.bib"].decode())
        self.assertIn("zh-TW", json.loads(files["native-reader.json"])["languages_not_supplied"])
        _, files, manifest = reader.prepare(self.obs)
        self.assertEqual(set(files), {"references.bib", "native-reader.json"})
        self.assertEqual(manifest["languages"], [])

    def test_each_bilingual_reader_has_its_notice_once_in_the_header(self):
        expected = {
            "en": "Caller-provided observations and presentation only. Reading, source support, bibliography verification and translation parity are not attested. No inclusion or Stage 2 decision is made.",
            "zh-TW": "本頁僅呈現呼叫者提供的觀察與內容，不認證實際閱讀、來源支持、書目查核或翻譯對等性，也不作納入文獻或 Stage 2 決定。",
        }

        class HeaderText(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.depth = 0
                self.ignored = 0
                self.header_count = 0
                self.parts = []

            def handle_starttag(self, tag, attrs):
                if tag == "header":
                    self.header_count += 1
                    self.depth += 1
                elif self.depth and tag in {"script", "style"}:
                    self.ignored += 1

            def handle_endtag(self, tag):
                if self.depth and tag in {"script", "style"} and self.ignored:
                    self.ignored -= 1
                elif tag == "header" and self.depth:
                    self.depth -= 1

            def handle_data(self, data):
                if self.depth and not self.ignored:
                    self.parts.append(data)

        control = HeaderText()
        control.feed("<header>visible<script>" + expected["en"] + "</script><style>" + expected["zh-TW"] + "</style></header><main>" + expected["en"] + "</main>")
        control.close()
        self.assertEqual("".join(control.parts), "visible")

        inputs, files, manifest = self.prepared()
        output = reader.generate(self.root / "bilingual-notice", inputs, files, manifest)
        for language, notice in expected.items():
            with self.subTest(language=language):
                header = HeaderText()
                header.feed((output / ("reader." + language + ".html")).read_text(encoding="utf-8"))
                header.close()
                self.assertEqual((header.header_count, header.depth, header.ignored), (1, 0, 0))
                header_text = "".join(header.parts)
                self.assertEqual(header_text.count(notice), 1)
                other = "zh-TW" if language == "en" else "en"
                self.assertNotIn(expected[other], header_text)

    def test_missing_bibliography_has_only_the_bibtex_header(self):
        expected = b"% Supplied verified bibliography only; verification is caller-recorded.\n\n"
        for prose in (True, False):
            with self.subTest(bilingual_prose=prose):
                inputs, files, manifest = reader.prepare(self.obs, self.en if prose else None, self.zh if prose else None)
                output = reader.generate(self.root / ("no-bibliography-prose" if prose else "no-bibliography-only"), inputs, files, manifest)
                self.assertEqual((output / "references.bib").read_bytes(), expected)
                delivered_manifest = json.loads((output / "manifest.json").read_bytes())
                self.assertEqual(delivered_manifest["bibliography_records"], 0)
                self.assertEqual(delivered_manifest["languages"], ["en", "zh-TW"] if prose else [])
                exported = json.loads((output / "native-reader.json").read_bytes())
                self.assertIsNone(exported["bibliography"])
                self.assertEqual(exported["bib_keys"], {})

    def test_language_navigation_links_and_missing_language_notice(self):
        class HeaderNavigation(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.in_header = False
                self.in_exports = False
                self.anchor = None
                self.paragraph = None
                self.links = []
                self.paragraphs = []

            def handle_starttag(self, tag, attrs):
                if tag == "header":
                    self.in_header = True
                elif self.in_header and tag == "nav" and dict(attrs).get("aria-label") in {"Exports", "匯出及語言"}:
                    self.in_exports = True
                elif self.in_header and tag == "a" and self.in_exports:
                    self.anchor = [dict(attrs), []]
                elif self.in_header and tag == "p":
                    self.paragraph = []

            def handle_data(self, data):
                if self.anchor is not None:
                    self.anchor[1].append(data)
                if self.paragraph is not None:
                    self.paragraph.append(data)

            def handle_endtag(self, tag):
                if tag == "a" and self.anchor is not None:
                    self.links.append((self.anchor[0], "".join(self.anchor[1])))
                    self.anchor = None
                elif tag == "p" and self.paragraph is not None:
                    self.paragraphs.append("".join(self.paragraph))
                    self.paragraph = None
                elif tag == "nav" and self.in_exports:
                    self.in_exports = False
                elif tag == "header":
                    self.in_header = False

        for both in (True, False):
            with self.subTest(bilingual=both):
                inputs, files, manifest = reader.prepare(self.obs, self.en, self.zh if both else None)
                output = reader.generate(self.root / ("navigation-bilingual" if both else "navigation-en"), inputs, files, manifest)
                expected_languages = ["en", "zh-TW"] if both else ["en"]
                expected_links = [("reader." + lang + ".html", {"en": "English", "zh-TW": "繁體中文"}[lang], lang) for lang in expected_languages]
                for language in expected_languages:
                    with self.subTest(language=language):
                        header = HeaderNavigation()
                        header.feed((output / ("reader." + language + ".html")).read_text(encoding="utf-8"))
                        header.close()
                        language_links = [(attrs.get("href"), label, attrs.get("lang")) for attrs, label in header.links if attrs.get("href", "").startswith("reader.") and attrs.get("href", "").endswith(".html")]
                        self.assertEqual(language_links, expected_links)
                        for attrs, label in header.links:
                            if attrs.get("href", "").startswith("reader."):
                                self.assertEqual(attrs.get("hreflang"), attrs.get("lang"))
                        for href, _, _ in language_links:
                            self.assertTrue((output / href).is_file())
                        if not both:
                            self.assertFalse((output / "reader.zh-TW.html").exists())
                            self.assertIn("Languages not supplied: zh-TW", header.paragraphs)

    def test_reader_first_structure_and_all_version_anchors(self):
        # Synthetic facts intentionally include an unresolved residual and two
        # distinct versions of a work. This tests markup, not usability.
        for language in ("en", "zh-TW"):
            self.content[language]["delivery_notes"] = ["SYNTHETIC DELIVERY APPENDIX"]
        self.save_inputs()
        _, files, manifest = self.prepared()

        class Structure(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.elements, self.links, self.stack, self.text = [], [], [], []
                self.anchor = None
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                self.elements.append((tag, attrs, tuple(self.stack)))
                if tag == "a":
                    self.anchor = [attrs, []]
                if tag not in {"meta", "link", "br", "hr", "img", "input"}:
                    self.stack.append(tag)
            def handle_endtag(self, tag):
                if tag == "a" and self.anchor is not None:
                    self.links.append((self.anchor[0], "".join(self.anchor[1])))
                    self.anchor = None
                if self.stack and self.stack[-1] == tag:
                    self.stack.pop()
            def handle_data(self, value):
                self.text.append(value)
                if self.anchor is not None:
                    self.anchor[1].append(value)

        for language in ("en", "zh-TW"):
            with self.subTest(language=language):
                page = Structure()
                page.feed(files["reader." + language + ".html"].decode())
                page.close()
                ids = {attrs["id"]: (index, tag, attrs, parents)
                       for index, (tag, attrs, parents) in enumerate(page.elements) if "id" in attrs}
                for name in ("main", "contents", "needs", "completion", "literature", "delivery-notes"):
                    self.assertIn(name, ids)
                self.assertEqual(ids["main"][1], "main")
                self.assertLess(ids["needs"][0], ids["contents"][0])
                self.assertLess(ids["completion"][0], ids["contents"][0])
                self.assertLess(ids["contents"][0], ids["literature"][0])
                self.assertLess(ids["literature"][0], ids["delivery-notes"][0])
                self.assertEqual(ids["delivery-notes"][1], "details")
                self.assertNotIn("open", ids["delivery-notes"][2])
                self.assertIn("main", ids["contents"][3])
                self.assertTrue(any(a.get("href") == "#main" and label.strip() for a, label in page.links))
                self.assertTrue(any(a.get("href") == "#contents" and len(label.strip()) > 2 for a, label in page.links))
                visible = " ".join(page.text)
                for expected in (self.observations["brief"], "N1", "partial", "SYNTHETIC DELIVERY APPENDIX"):
                    self.assertIn(expected, visible)
                for source in self.observations["sources"]:
                    anchor = reader.source_anchor(source)
                    self.assertIn(anchor, ids)
                    self.assertTrue(any(a.get("href") == "#" + anchor for a, _ in page.links))
                for work in {source["work_id"] for source in self.observations["sources"]}:
                    self.assertIn("work-" + reader.token(work), ids)
                self.assertEqual(manifest["source_records"], 5)
                self.assertEqual(manifest["distinct_work_ids"], 4)

    def test_categories_are_supplied_per_version_and_works_group_versions(self):
        for language in ("en", "zh-TW"):
            self.content[language]["records"][0]["category"]["label"] = "N1"
            self.content[language]["records"][1]["category"]["label"] = "N2"
        self.save_inputs()
        _, files, _ = self.prepared()
        one, two, three = self.observations["sources"][:3]
        for language in ("en", "zh-TW"):
            with self.subTest(language=language):
                markup = files["reader." + language + ".html"].decode()
                categories = markup.split('<section id="categories">', 1)[1].split('<section id="literature">', 1)[0]
                n1 = categories.split('<h3>N1</h3>', 1)[1].split('</ul>', 1)[0]
                n2 = categories.split('<h3>N2</h3>', 1)[1].split('</ul>', 1)[0]
                self.assertIn('#' + reader.source_anchor(one), n1)
                self.assertNotIn('#' + reader.source_anchor(two), n1)
                self.assertIn('#' + reader.source_anchor(two), n2)
                self.assertNotIn('#' + reader.source_anchor(one), n2)
                self.assertNotIn('#' + reader.source_anchor(three), categories)
                work = markup.split('<section id="work-' + reader.token(one["work_id"]) + '">', 1)[1]
                work = work.split('</section>\n<section id="work-', 1)[0]
                self.assertIn('id="' + reader.source_anchor(one) + '"', work)
                self.assertIn('id="' + reader.source_anchor(two) + '"', work)
                self.assertNotIn('id="' + reader.source_anchor(three) + '"', work)

    def test_untranslated_originals_and_bibliography_limits_are_explicit(self):
        _, files, _ = self.prepared()
        en, zh = (files["reader." + language + ".html"].decode() for language in ("en", "zh-TW"))
        for marker in ("Original brief", "Original recorded reason", "original", "version records", "not necessarily complete citations"):
            self.assertIn(marker, en)
        for marker in ("原始研究簡述", "原始紀錄原因", "原文", "部分完成 (partial)", "未解決 (unresolved)", "版本紀錄", "不一定是完整引文"):
            self.assertIn(marker, zh)
        self.assertIn(self.observations["brief"], zh)
        self.assertIn(self.observations["completion"]["reason"], zh)
        self.assertIn(self.observations["needs"][0]["text"], zh)

    def test_observation_translations_are_bound_labeled_and_additive(self):
        self.observations['needs'].append({'id': 'N2', 'text': 'Original residual need', 'families': [], 'status': 'unresolved'})
        self.observations['completion']['residual_need_ids'] = ['N2']
        self.observations['completion']['status'] = 'partial'
        self.save_inputs()
        original_hash = hashlib.sha256(self.obs.read_bytes()).hexdigest()
        one, two = self.observations['sources'][:2]
        for language in ('en', 'zh-TW'):
            self.content[language]['format'] = 'native-reader-content/1.1'
            self.content[language]['observation_translations'] = {
                'observations_sha256': original_hash,
                'run_id': self.observations['run_id'], 'project_id': self.observations['project_id'],
                'brief': language + ' supplied brief <script>bad</script>',
                'completion_reason': language + ' supplied reason',
                'needs': [{'id': 'N2', 'text': language + ' translated residual need'}],
                'sources': [{'source_id': two['id'], 'work_id': two['work_id'], 'version': two['version'],
                             'title': language + ' translated title', 'relevance': language + ' translated relevance <img src=x>'}],
            }
        self.save_inputs()
        _, files, manifest = self.prepared()
        exported = json.loads(files['native-reader.json'])
        self.assertEqual(exported['observations'], self.observations)
        self.assertEqual(exported['content'], self.content)
        self.assertEqual(exported['observations']['completion']['status'], 'partial')
        self.assertEqual(exported['observations']['completion']['residual_need_ids'], ['N2'])
        self.assertEqual(exported['observations']['needs'][-1]['status'], 'unresolved')
        self.assertEqual(manifest['inputs']['observations']['sha256'], original_hash)
        for language, label, title_label in [('en', 'Supplied translation (not verified)', 'Supplied title translation (not verified)'),
                                              ('zh-TW', '提供的翻譯（未經驗證）', '提供的標題翻譯（未經驗證）')]:
            with self.subTest(language=language):
                markup = files['reader.' + language + '.html'].decode()
                self.assertIn(label, markup)
                self.assertIn(title_label, markup)
                self.assertIn(language + ' supplied brief &lt;script&gt;bad&lt;/script&gt;', markup)
                self.assertIn(language + ' translated relevance &lt;img src=x&gt;', markup)
                self.assertNotIn('<script>bad</script>', markup)
                self.assertNotIn('<img src=x>', markup)
                self.assertIn(self.observations['brief'], markup)
                self.assertIn(self.observations['completion']['reason'], markup)
                self.assertIn('Original residual need', markup)
                self.assertIn('N2', markup)
                self.assertIn('partial', markup)
                self.assertIn('unresolved', markup)
                self.assertIn(language + ' translated residual need', markup)
                self.assertIn(language + ' supplied reason', markup)
                brief_section = markup.split('<section id="brief">', 1)[1].split('</section>', 1)[0]
                completion_section = markup.split('<section id="completion">', 1)[1].split('</section>', 1)[0]
                needs_section = markup.split('<section id="needs">', 1)[1].split('</section>', 1)[0]
                self.assertIn(language + ' supplied brief', brief_section)
                self.assertIn(self.observations['brief'], brief_section)
                self.assertIn(language + ' supplied reason', completion_section)
                self.assertIn(self.observations['completion']['reason'], completion_section)
                self.assertIn('N2', needs_section)
                self.assertIn('unresolved', needs_section)
                self.assertIn(language + ' translated residual need', needs_section)
                target = markup.split('<article id="' + reader.source_anchor(two) + '">', 1)[1].split('</article>', 1)[0]
                self.assertIn(two['title'], target)
                self.assertIn(two['relevance'], target)
                self.assertIn(language + ' translated title', target)
                self.assertIn(language + ' translated relevance', target)
                other = markup.split('<article id="' + reader.source_anchor(one) + '">', 1)[1].split('</article>', 1)[0]
                self.assertNotIn(language + ' translated title', other)
                self.assertNotIn(language + ' translated relevance', other)
                reader.verify_links(files)

    def test_translation_titles_in_indexes_bind_to_exact_version_and_language(self):
        self.observations['needs'].append({'id': 'N2', 'text': 'Original residual need', 'families': [], 'status': 'unresolved'})
        self.observations['completion']['residual_need_ids'] = ['N2']
        self.save_inputs()
        one, two = self.observations['sources'][:2]
        for language in ('en', 'zh-TW'):
            self.content[language]['format'] = 'native-reader-content/1.1'
            self.content[language]['observation_translations'] = {
                'observations_sha256': hashlib.sha256(self.obs.read_bytes()).hexdigest(),
                'run_id': self.observations['run_id'], 'project_id': self.observations['project_id'],
                'brief': language + ' translated brief', 'completion_reason': language + ' translated reason',
                'needs': [{'id': 'N2', 'text': language + ' translated need'}],
                'sources': [{'source_id': two['id'], 'work_id': two['work_id'], 'version': two['version'],
                             'title': language + ' title <img src=x>', 'relevance': language + ' relevance'},
                            {'source_id': one['id'], 'work_id': one['work_id'], 'version': one['version'],
                             'title': language + ' S1 title'}]}
        self.save_inputs()
        _, files, _ = self.prepared()

        class LangAndLinks(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.stack = []
                self.text = []
                self.links = []
                self.anchor = None
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                lang = attrs.get('lang', self.stack[-1][1] if self.stack else None)
                if tag not in {'meta', 'link', 'br', 'hr', 'img', 'input'}:
                    self.stack.append((tag, lang))
                if tag == 'a':
                    self.anchor = [attrs.get('href'), []]
            def handle_data(self, value):
                lang = self.stack[-1][1] if self.stack else None
                if self.text and self.text[-1][1] == lang:
                    self.text[-1] = (self.text[-1][0] + value, lang)
                else:
                    self.text.append((value, lang))
                if self.anchor is not None:
                    self.anchor[1].append(value)
            def handle_endtag(self, tag):
                if tag == 'a' and self.anchor is not None:
                    self.links.append((self.anchor[0], ''.join(self.anchor[1])))
                    self.anchor = None
                while self.stack:
                    current, _ = self.stack.pop()
                    if current == tag:
                        break

        for language, label in [('en', 'Supplied title translation (not verified)'),
                                ('zh-TW', '提供的標題翻譯（未經驗證）')]:
            with self.subTest(language=language):
                markup = files['reader.' + language + '.html'].decode()
                self.assertIn('title &lt;img src=x&gt;', markup)
                self.assertNotIn('<img src=x>', markup)
                parsed = LangAndLinks()
                parsed.feed(markup)
                parsed.close()
                for original in (self.observations['brief'], self.observations['completion']['reason'],
                                 'Original residual need', two['title'], two['relevance']):
                    self.assertTrue(any(original in text and lang == '' for text, lang in parsed.text))
                for translation in (language + ' translated brief', language + ' translated reason',
                                    language + ' translated need', language + ' title <img src=x>', language + ' relevance'):
                    self.assertTrue(any(translation in text and lang == language for text, lang in parsed.text))
                for label_text in (label,):
                    self.assertTrue(any(label_text in text and lang == language for text, lang in parsed.text))
                for section in ('categories', 'literature'):
                    fragment = markup.split('<section id="' + section + '">', 1)[1]
                    if section == 'categories':
                        fragment = fragment.split('<section id="literature">', 1)[0]
                    else:
                        fragment = fragment.split('</section>', 1)[0]
                    links = LangAndLinks()
                    links.feed(fragment)
                    target = [text for href, text in links.links if href == '#' + reader.source_anchor(two)]
                    self.assertEqual(len(target), 1)
                    self.assertIn(two['title'], target[0])
                    self.assertIn(label, target[0])
                    self.assertIn(language + ' title <img src=x>', target[0])
                    self.assertIn(two['id'], target[0])
                    self.assertIn(two['version'], target[0])
                    other = [text for href, text in links.links if href == '#' + reader.source_anchor(one)]
                    self.assertEqual(len(other), 1)
                    self.assertIn(language + ' S1 title', other[0])
                    self.assertIn(one['id'], other[0])
                    self.assertIn(one['version'], other[0])
                    self.assertNotIn(language + ' title <img src=x>', other[0])
                    if section == 'literature':
                        work = [text for href, text in links.links if href == '#work-' + reader.token(one['work_id'])]
                        self.assertEqual(len(work), 1)
                        self.assertNotIn(language + ' S1 title', work[0])
                        self.assertNotIn(language + ' title <img src=x>', work[0])
                        self.assertNotIn(label, work[0])
        reader.verify_links(files)

    def test_observation_translation_overlay_optional_and_legacy_unchanged(self):
        self.save_inputs()
        _, original, original_manifest = self.prepared()
        for language in ('en', 'zh-TW'):
            self.content[language]['format'] = 'native-reader-content/1.1'
        self.save_inputs()
        _, newer, newer_manifest = self.prepared()
        # Only the content input hash in the footer changes when the format
        # marker changes; the actual reader content and bibliography stay equal.
        for key in ('reader.en.html', 'reader.zh-TW.html'):
            self.assertEqual(newer[key].split(b'<footer>')[0], original[key].split(b'<footer>')[0])
            self.assertNotIn(b'<span lang="">', newer[key])
        self.assertEqual(newer['references.bib'], original['references.bib'])
        self.assertEqual(json.loads(newer['native-reader.json'])['observations'], self.observations)
        self.assertEqual(newer_manifest['inputs']['observations'], original_manifest['inputs']['observations'])
        for language in ('en', 'zh-TW'):
            self.content[language]['format'] = 'native-reader-content/1.0'
            self.content[language]['observation_translations'] = {'observations_sha256': hashlib.sha256(self.obs.read_bytes()).hexdigest(),
                'run_id': self.observations['run_id'], 'project_id': self.observations['project_id']}
        self.rejected()

    def test_sparse_translation_matches_unknown_version_without_invention(self):
        self.save_inputs()
        source = self.observations['sources'][2]
        self.assertIsNone(source['version'])
        self.content['en']['format'] = 'native-reader-content/1.1'
        self.content['en']['observation_translations'] = {
            'observations_sha256': hashlib.sha256(self.obs.read_bytes()).hexdigest(),
            'run_id': self.observations['run_id'], 'project_id': self.observations['project_id'],
            'sources': [{'source_id': source['id'], 'work_id': source['work_id'],
                         'version': None, 'relevance': 'only translated relevance'}],
        }
        self.save_inputs()
        _, files, _ = self.prepared()
        markup = files['reader.en.html'].decode()
        source_page = markup.split('<article id="' + reader.source_anchor(source) + '">', 1)[1].split('</article>', 1)[0]
        self.assertIn('only translated relevance', source_page)
        self.assertIn('Unknown version (null)', source_page)
        self.assertIn(source['relevance'], source_page)
        self.assertIn('Original title', source_page)
        self.assertNotIn('Supplied title translation (not verified)', source_page)
        self.assertNotIn('only translated relevance', files['reader.zh-TW.html'].decode())
        self.assertEqual(json.loads(files['native-reader.json'])['observations'], self.observations)

    def test_observation_translation_rejects_mismatch_and_scientific_overrides(self):
        self.save_inputs()
        source = self.observations['sources'][0]
        original = {'observations_sha256': hashlib.sha256(self.obs.read_bytes()).hexdigest(),
                    'run_id': self.observations['run_id'], 'project_id': self.observations['project_id'],
                    'brief': 'translated', 'needs': [{'id': 'N1', 'text': 'need'}],
                    'sources': [{'source_id': source['id'], 'work_id': source['work_id'], 'version': source['version'], 'relevance': 'relevance'}]}
        cases = [
            lambda v: v.update(observations_sha256='0' * 64),
            lambda v: v.update(observations_sha256='bad'),
            lambda v: v.update(run_id='wrong-run'),
            lambda v: v.update(project_id='wrong-project'),
            lambda v: v.update(language='zh-TW'),
            lambda v: v.update(status='bounded-complete'),
            lambda v: v.update(residual_need_ids=[]),
            lambda v: v['needs'].append({'id': 'N1', 'text': 'duplicate'}),
            lambda v: v['needs'][0].update(id='N-missing'),
            lambda v: v['needs'][0].update(status='covered'),
            lambda v: v['sources'].append(dict(v['sources'][0])),
            lambda v: v['sources'][0].update(source_id='missing-source'),
            lambda v: v['sources'][0].update(work_id='wrong-work'),
            lambda v: v['sources'][0].update(version='wrong-version'),
            lambda v: v['sources'][0].update(version=None),
            lambda v: v['sources'][0].pop('source_id'),
            lambda v: v['sources'][0].update(reading_level='full-text'),
            lambda v: v['sources'][0].update(attempt_ids=[]),
            lambda v: v.update(needs='not-an-array'),
            lambda v: v.update(sources='not-an-array'),
            lambda v: v.update(brief='bad\x00control'),
            lambda v: v.update(brief=''),
            lambda v: v.pop('observations_sha256'),
            lambda v: v.pop('run_id'),
            lambda v: v.pop('project_id'),
        ]
        self.content['en']['format'] = 'native-reader-content/1.1'
        for index, mutate in enumerate(cases):
            with self.subTest(case=index):
                value = copy.deepcopy(original)
                mutate(value)
                self.content['en']['observation_translations'] = value
                self.rejected()
        self.content['en']['observation_translations'] = copy.deepcopy(original)
        self.content['en']['language'] = 'zh-TW'
        self.rejected()
        self.content['en']['language'] = 'en'
        self.save_inputs()
        # Semantically identical JSON with distinct input bytes must fail binding.
        self.obs.write_bytes(self.obs.read_bytes() + b'\n')
        with self.assertRaises((reader.ReaderError, ValueError, TypeError)):
            self.prepared()

    def test_translation_overlay_duplicate_json_fields_are_rejected(self):
        self.save_inputs()
        self.content['en']['format'] = 'native-reader-content/1.1'
        self.content['en']['observation_translations'] = {
            'observations_sha256': hashlib.sha256(self.obs.read_bytes()).hexdigest(),
            'run_id': self.observations['run_id'], 'project_id': self.observations['project_id'],
            'brief': 'translated'}
        self.save_inputs()
        raw = self.en.read_text(encoding='utf-8')
        self.assertEqual(raw.count('"brief": "translated"'), 1)
        raw = raw.replace('"brief": "translated"', '"brief": "translated", "brief": "duplicate"')
        self.en.write_text(raw, encoding='utf-8')
        with self.assertRaisesRegex(reader.ReaderError, 'duplicate JSON key'):
            self.prepared()

    def test_invalid_overlay_fails_without_creating_output(self):
        self.content['en']['format'] = 'native-reader-content/1.1'
        self.content['en']['observation_translations'] = {'observations_sha256': '0' * 64,
            'run_id': self.observations['run_id'], 'project_id': self.observations['project_id'], 'brief': 'not bound'}
        self.save_inputs()
        output = self.root / 'must-not-be-created'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = reader.main(['--observations', str(self.obs), '--content-en', str(self.en), '--output-dir', str(output)])
        self.assertNotEqual(code, 0)
        self.assertFalse(output.exists())

    def test_category_label_is_escaped_and_unclassified_source_not_invented(self):
        self.content["en"]["records"][0]["category"]["label"] = '<svg onload="alert(1)">'
        self.save_inputs()
        _, files, _ = self.prepared()
        markup = files["reader.en.html"].decode()
        categories = markup.split('<section id="categories">', 1)[1].split('<section id="literature">', 1)[0]
        self.assertNotIn('<svg', categories)
        self.assertIn('&lt;svg', categories)
        self.assertNotIn('#' + reader.source_anchor(self.observations["sources"][2]), categories)

    def test_empty_bibliography_is_distinct_from_omitted_bibliography(self):
        empty = {"format": "native-reader-bibliography/1.0", "records": []}
        self.bib.write_bytes(reader.canonical(empty))
        for prose in (True, False):
            results = {}
            for supplied in (True, False):
                with self.subTest(bilingual_prose=prose, bibliography_supplied=supplied):
                    inputs, files, manifest = reader.prepare(self.obs, self.en if prose else None, self.zh if prose else None,
                                                             self.bib if supplied else None)
                    output = reader.generate(self.root / ("empty-bib-" + str(prose) + "-" + str(supplied)), inputs, files, manifest)
                    exported = json.loads((output / "native-reader.json").read_bytes())
                    delivered_manifest = json.loads((output / "manifest.json").read_bytes())
                    results[supplied] = (output / "references.bib").read_bytes()
                    self.assertEqual(exported["bibliography"], empty if supplied else None)
                    self.assertEqual(exported["bib_keys"], {})
                    self.assertEqual(delivered_manifest["bibliography_records"], 0)
                    self.assertEqual("bibliography" in delivered_manifest["inputs"], supplied)
                    if supplied:
                        self.assertEqual(delivered_manifest["inputs"]["bibliography"]["sha256"], hashlib.sha256(self.bib.read_bytes()).hexdigest())
            self.assertEqual(results[True], results[False])
            self.assertEqual(results[True], b"% Supplied verified bibliography only; verification is caller-recorded.\n\n")

    def test_check_only_writes_nothing(self):
        before = self.snapshot(self.root)
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = reader.main(["--observations", str(self.obs), "--content-en", str(self.en), "--bibliography", str(self.bib), "--check-only"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(stdout.getvalue())["writes"])
        self.assertEqual(self.snapshot(self.root), before)

    def test_delivery_notes_and_selected_attachments_are_discoverable_in_each_language(self):
        sidecar = self.root / "assessment-status.sidecar.json"
        readme = self.root / "README.md"
        sidecar.write_bytes(reader.canonical({"synthetic_recorded_counts": {"screened": 3, "included": 1, "global_total": None}}))
        readme.write_text("Synthetic supplied assessment limits; no scientific acceptance.\n", encoding="utf-8")
        for language, note in [("en", "Synthetic recorded counts: screened 3, included 1; global total unknown."),
                               ("zh-TW", "合成紀錄：已篩選 3 項、納入 1 項；全域總數未知。")]:
            self.content[language]["delivery_notes"] = [note, '<script>supplied note remains text</script>']
        self.save_inputs()
        inputs, files, manifest = reader.prepare(self.obs, self.en, self.zh, self.bib, attachments=[sidecar, readme])
        for language in ("en", "zh-TW"):
            markup = files["reader." + language + ".html"].decode()
            page = reader.Navigation()
            page.feed(markup)
            self.assertTrue({sidecar.name, readme.name} <= set(page.links))
            self.assertIn(self.content[language]["delivery_notes"][0], markup)
            self.assertIn("&lt;script&gt;supplied note remains text&lt;/script&gt;", markup)
            self.assertNotIn("<script>", markup)
        exported = json.loads(files["native-reader.json"])
        self.assertEqual(exported["observations"], self.observations)
        self.assertEqual(exported["content"], self.content)
        self.assertEqual([entry["name"] for entry in exported["attachments"]], [readme.name, sidecar.name])
        for path in (readme, sidecar):
            self.assertEqual(files[path.name], path.read_bytes())
            self.assertEqual(manifest["outputs"][path.name]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        _, reverse_files, reverse_manifest = reader.prepare(self.obs, self.en, self.zh, self.bib, attachments=[readme, sidecar])
        self.assertEqual((files, manifest), (reverse_files, reverse_manifest))
        output = reader.generate(self.root / "with-attachments", inputs, files, manifest)
        self.assertEqual((output / sidecar.name).read_bytes(), sidecar.read_bytes())
        self.assertEqual((output / readme.name).read_bytes(), readme.read_bytes())

    def test_supplied_pdf_is_opaque_copied_hashed_and_linked_in_both_readers(self):
        # Deliberately not a valid PDF: no parser, validity or language claim.
        pdf = self.root / "report.PDF"
        raw = b"\x00\xffopaque supplied bytes\n"
        pdf.write_bytes(raw)
        text = self.root / "notes.txt"
        text.write_bytes(b"unchanged UTF-8 text\n")
        inputs, files, manifest = reader.prepare(self.obs, self.en, self.zh, self.bib, attachments=[pdf, text])
        self.assertEqual(files[pdf.name], raw)
        self.assertEqual(files[text.name], text.read_bytes())
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(manifest["inputs"]["attachment:" + pdf.name]["sha256"], digest)
        self.assertEqual(manifest["outputs"][pdf.name]["sha256"], digest)
        exported = json.loads(files["native-reader.json"])
        self.assertEqual(next(a for a in exported["attachments"] if a["name"] == pdf.name)["sha256"], digest)
        for lang, label in [("en", "Supplied PDF attachment (language/content not verified):"),
                            ("zh-TW", "提供的 PDF 附件（語言及內容未經驗證）：")]:
            markup = files["reader." + lang + ".html"].decode()
            self.assertIn('<a download href="report.PDF">', markup)
            self.assertIn(label, markup)
            self.assertNotIn("<embed", markup)
            self.assertNotIn("<iframe", markup)
        output = reader.generate(self.root / "with-pdf", inputs, files, manifest)
        self.assertEqual((output / pdf.name).read_bytes(), raw)
        self.assertEqual(json.loads((output / "manifest.json").read_bytes())["outputs"][pdf.name]["sha256"], digest)

    def test_pdf_limits_names_collisions_and_linked_inputs(self):
        pdf = self.root / "Report.pdf"
        pdf.write_bytes(b"x" * reader.LIMIT)
        _, files, _ = reader.prepare(self.obs, self.en, attachments=[pdf])
        self.assertEqual(len(files[pdf.name]), reader.LIMIT)
        pdf.write_bytes(b"x" * (reader.LIMIT + 1))
        with self.assertRaisesRegex(reader.ReaderError, "exceeds 4 MiB"):
            reader.prepare(self.obs, self.en, attachments=[pdf])
        pdf.write_bytes(b"opaque")
        for name in ("bad name.pdf", "report.pdf.exe", "report.pdf.html"):
            path = self.root / name
            path.write_bytes(b"opaque")
            with self.subTest(name=name), self.assertRaises(reader.ReaderError):
                reader.prepare(self.obs, self.en, attachments=[path])
        other = self.root / "other-pdf"
        other.mkdir()
        duplicate = other / "report.PDF"
        duplicate.write_bytes(b"different")
        with self.assertRaisesRegex(reader.ReaderError, "duplicate attachment"):
            reader.prepare(self.obs, self.en, attachments=[pdf, duplicate])
        link = self.root / "linked.pdf"
        try:
            link.symlink_to(pdf)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaisesRegex(reader.ReaderError, "linked paths"):
                reader.prepare(self.obs, self.en, attachments=[link])
        hardlink = self.root / "hardlink.pdf"
        try:
            os.link(pdf, hardlink)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaisesRegex(reader.ReaderError, "single-link regular file"):
                reader.prepare(self.obs, self.en, attachments=[pdf])

    def test_changed_pdf_leaves_partial_output_without_completion_manifest(self):
        pdf = self.root / "report.pdf"
        original = b"old\x00\xff"
        pdf.write_bytes(original)
        inputs, files, manifest = reader.prepare(self.obs, self.en, self.zh, attachments=[pdf])
        pdf.write_bytes(b"new\x00\xfe")
        output = self.root / "changed-pdf"
        with self.assertRaisesRegex(reader.ReaderError, "input changed during generation"):
            reader.generate(output, inputs, files, manifest)
        self.assertTrue(output.is_dir())
        self.assertEqual((output / pdf.name).read_bytes(), original)
        self.assertTrue((output / "reader.en.html").exists())
        self.assertFalse((output / "manifest.json").exists())

    def test_check_only_with_attachments_and_delivery_notes_writes_nothing(self):
        readme = self.root / "README.md"
        readme.write_text("Synthetic supporting notes.\n", encoding="utf-8")
        self.content["en"]["delivery_notes"] = ["Synthetic supplied counts, not renderer decisions."]
        self.save_inputs()
        before = self.snapshot(self.root)
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = reader.main(["--observations", str(self.obs), "--content-en", str(self.en), "--attachment", str(readme), "--check-only"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(stdout.getvalue())["writes"])
        self.assertEqual(self.snapshot(self.root), before)

    def test_invalid_delivery_notes_are_rejected_without_changing_observations(self):
        for notes in ("not an array", [""], [None], ["unsafe\x00note"]):
            with self.subTest(notes=notes):
                self.content["en"]["delivery_notes"] = notes
                self.rejected()

    def test_attachments_reject_unsafe_names_collisions_nontext_and_excess_count(self):
        for name, raw in [("active.html", b"<script>active</script>"), ("native-reader.json", b"{}"),
                          ("manifest.json", b"{}"), ("bad name.txt", b"text"),
                          ("bad.txt", b"\xff"), ("nul.txt", b"unsafe\x00text")]:
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(raw)
                with self.assertRaises((reader.ReaderError, UnicodeError)):
                    reader.prepare(self.obs, self.en, attachments=[path])
        other = self.root / "other"
        other.mkdir()
        first, second = self.root / "README.md", other / "readme.md"
        first.write_text("one", encoding="utf-8")
        second.write_text("two", encoding="utf-8")
        with self.assertRaisesRegex(reader.ReaderError, "duplicate attachment"):
            reader.prepare(self.obs, self.en, attachments=[first, second])
        with self.assertRaisesRegex(reader.ReaderError, "at most 8 attachments"):
            reader.prepare(self.obs, self.en, attachments=[first] * 9)
        with self.assertRaisesRegex(reader.ReaderError, "input or output parent is missing"):
            reader.prepare(self.obs, self.en, attachments=[self.root / "absent.txt"])

    def test_attachment_change_prevents_a_complete_manifest(self):
        path = self.root / "README.md"
        path.write_text("original supplied limits", encoding="utf-8")
        inputs, files, manifest = reader.prepare(self.obs, self.en, attachments=[path])
        path.write_text("changed supplied limits", encoding="utf-8")
        output = self.root / "changed-attachment"
        with self.assertRaisesRegex(reader.ReaderError, "input changed during generation"):
            reader.generate(output, inputs, files, manifest)
        self.assertFalse((output / "manifest.json").exists())

    def test_required_export_discoverability_detects_an_omitted_valid_link(self):
        readme = self.root / "README.md"
        readme.write_text("Synthetic supporting limits", encoding="utf-8")
        _, files, _ = reader.prepare(self.obs, self.en, self.zh, attachments=[readme])
        files["reader.zh-TW.html"] = files["reader.zh-TW.html"].replace(b'href="README.md"', b'href="native-reader.json"')
        reader.verify_links(files)  # All links that remain are valid; discoverability is a separate invariant.
        with self.assertRaisesRegex(reader.ReaderError, "required export is not discoverable"):
            reader.verify_links(files, required_exports=["README.md"])

    def test_same_inputs_are_byte_deterministic_and_preserve_existing_output(self):
        inputs, files, manifest = self.prepared()
        first = reader.generate(self.root / "first", inputs, files, manifest)
        inputs2, files2, manifest2 = self.prepared()
        second = reader.generate(self.root / "second", inputs2, files2, manifest2)
        self.assertEqual(files, files2)
        self.assertEqual(manifest, manifest2)
        self.assertEqual({p.name: p.read_bytes() for p in first.iterdir()}, {p.name: p.read_bytes() for p in second.iterdir()})
        before = self.snapshot(first)
        with self.assertRaises(reader.ReaderError):
            reader.generate(first, inputs, files, manifest)
        self.assertEqual(self.snapshot(first), before)

    def test_escaping_blocks_active_html_and_bibtex_injection(self):
        _, files, _ = self.prepared()
        page = files["reader.en.html"].decode()
        self.assertNotIn("<script>", page)
        self.assertNotIn("<img", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("&lt;img", page)
        bib = files["references.bib"].decode()
        self.assertEqual(bib.count("@misc{"), 5)
        self.assertNotIn(r"\write18", bib)
        self.assertIn(r"\textbackslash{}write18", bib)
        self.assertIn(r"\textbraceleft{}Author\textbraceright{}", bib)
        key = reader.bib_key(self.observations["sources"][2])
        entry = bib.split("@misc{" + key + ",", 1)[1].split("@misc{", 1)[0]
        self.assertNotIn("year =", entry)
        self.assertNotIn("author =", entry)

    def test_bibliography_metadata_is_visible_per_version_and_safely_escaped(self):
        # The same work has two versions; each must retain its own supplied metadata.
        one, two = self.bibliography["records"][:2]
        one.update({"authors": ['A <svg onload="bad"> & {Name}', r"B \write18"],
                    "year": 2024, "venue": 'Journal <script> & _%{}',
                    "doi": "10.1234/abc&def", "url": "https://example.test/a?x=1&y=2"})
        two.update({"authors": ["Second Version Author"], "year": 2025, "venue": "Other venue",
                    "doi": "10.1234/second", "url": "https://example.test/second"})
        self.save_inputs()
        _, files, _ = self.prepared()
        self.assertEqual(json.loads(files["native-reader.json"])["bibliography"], self.bibliography)
        source_one, source_two = self.observations["sources"][:2]
        key_one, key_two = reader.bib_key(source_one), reader.bib_key(source_two)
        self.assertNotEqual(key_one, key_two)
        for lang in ("en", "zh-TW"):
            with self.subTest(lang=lang):
                markup = files["reader." + lang + ".html"].decode()
                sec_one = markup.split('<section id="bib-' + key_one + '">', 1)[1].split('</section>', 1)[0]
                sec_two = markup.split('<section id="bib-' + key_two + '">', 1)[1].split('</section>', 1)[0]
                for value in ('A &lt;svg onload=&quot;bad&quot;&gt; &amp; {Name}',
                              r'B \write18', '2024', 'Journal &lt;script&gt; &amp; _%{}',
                              '10.1234/abc&amp;def', 'https://example.test/a?x=1&amp;y=2'):
                    self.assertIn(value, sec_one)
                for label in (('Authors (supplied display names)', 'Year', 'Venue', 'DOI', 'URL') if lang == 'en' else ('作者（提供的顯示名稱）', '年份', '出版處', 'DOI', 'URL')):
                    self.assertIn(label, sec_one)
                self.assertIn('<li>A &lt;svg onload=&quot;bad&quot;&gt; &amp; {Name}</li>', sec_one)
                self.assertIn(r'<li>B \write18</li>', sec_one)
                self.assertIn('S1 / work-one / v1', sec_one)
                self.assertIn('S2 / work-one / v2', sec_two)
                self.assertNotIn('<svg', sec_one)
                self.assertNotIn('<script>', sec_one)
                self.assertNotIn('Second Version Author', sec_one)
                self.assertIn('Second Version Author', sec_two)
                self.assertIn('2025', sec_two)
                self.assertNotIn('2024', sec_two)
                self.assertNotIn('Not supplied' if lang == 'en' else '未提供', sec_one)
        bib = files["references.bib"].decode()
        entry_one = bib.split('@misc{' + key_one + ',', 1)[1].split('\n}', 1)[0]
        entry_two = bib.split('@misc{' + key_two + ',', 1)[1].split('\n}', 1)[0]
        self.assertIn(r'\textbackslash{}write18', entry_one)
        self.assertIn(r'\textbraceleft{}Name\textbraceright{}', entry_one)
        self.assertIn(r'Journal <script> \& \_\%\textbraceleft{}\textbraceright{}', entry_one)
        self.assertIn('Second Version Author', entry_two)
        self.assertNotIn('Second Version Author', entry_one)

    def test_bibliography_missing_fields_are_explicit_not_inferred(self):
        record = self.bibliography["records"][0]
        for field in ("authors", "year", "venue", "doi", "url"):
            record.pop(field, None)  # optional fields can be absent rather than null
        self.save_inputs()
        _, files, _ = self.prepared()
        key = reader.bib_key(self.observations["sources"][0])
        for lang, missing in (("en", "Not supplied"), ("zh-TW", "未提供")):
            with self.subTest(lang=lang):
                markup = files["reader." + lang + ".html"].decode()
                sec = markup.split('<section id="bib-' + key + '">', 1)[1].split('</section>', 1)[0]
                self.assertEqual(sec.count(missing), 5)
                self.assertNotIn('2020', sec)
        entry = files["references.bib"].decode().split('@misc{' + key + ',', 1)[1].split('\n}', 1)[0]
        for field in ('author', 'year', 'journal', 'doi', 'url'):
            self.assertNotIn('  ' + field + ' =', entry)
        # An empty author list has no names and is also displayed as missing.
        record["authors"] = []
        self.save_inputs()
        _, files, _ = self.prepared()
        sec = files["reader.en.html"].decode().split('<section id="bib-' + key + '">', 1)[1].split('</section>', 1)[0]
        self.assertEqual(sec.count('Not supplied'), 5)
        record['venue'] = 'One known field'
        record['year'] = 2026
        self.save_inputs()
        _, files, _ = self.prepared()
        sec = files['reader.en.html'].decode().split('<section id="bib-' + key + '">', 1)[1].split('</section>', 1)[0]
        self.assertEqual(sec.count('Not supplied'), 3)
        self.assertIn('One known field', sec)
        self.assertIn('2026', sec)

    def test_author_names_preserve_order_duplicates_and_validation(self):
        names = ["J. Wang", "A. Chen", "J. Wang"]
        self.bibliography["records"][0]["authors"] = names
        self.save_inputs()
        _, files, _ = self.prepared()
        exported = json.loads(files["native-reader.json"])
        self.assertEqual(exported["bibliography"]["records"][0]["authors"], names)
        self.assertIn("author = {{J. Wang} and {A. Chen} and {J. Wang}}", files["references.bib"].decode())
        for invalid in ([""], ["J. Wang", " "], [None], "J. Wang"):
            with self.subTest(invalid=invalid):
                self.bibliography["records"][0]["authors"] = invalid
                self.rejected()
        self.bibliography["records"][0]["authors"] = names
        self.observations["sources"][0]["attempt_ids"] = ["A1", "A1"]
        self.save_inputs()
        with self.assertRaisesRegex(reader.ReaderError, "duplicate reference"):
            self.prepared()

    def test_bibliography_1_0_export_is_byte_compatible(self):
        source = self.observations["sources"][0]
        source["title"] = "One"
        self.bibliography["records"] = [self.bibliography["records"][0]]
        record = self.bibliography["records"][0]
        record.update({"title": "One", "authors": ["Alice Smith", "Institute of Water"],
                       "year": 2020, "venue": "Journal", "doi": "10.1234/example",
                       "url": "https://example.test/x"})
        self.save_inputs()
        _, files, _ = self.prepared()
        key = reader.bib_key(source)
        expected = ("% Supplied verified bibliography only; verification is caller-recorded.\n"
                    + "@misc{" + key + ",\n"
                    + "  title = {One},\n  author = {{Alice Smith} and {Institute of Water}},\n"
                    + "  year = {2020},\n  journal = {Journal},\n  doi = {10.1234/example},\n"
                    + "  url = {https://example.test/x}\n}\n").encode()
        self.assertEqual(files["references.bib"], expected)
        record["author_kinds"] = ["person", "literal"]
        self.rejected()  # 1.0 must not silently change behavior.

    def test_bibliography_1_1_kinds_preserve_order_identity_and_escape(self):
        self.bibliography["format"] = "native-reader-bibliography/1.1"
        one, two = self.bibliography["records"][:2]
        one["authors"] = ["Alice Smith", "Bob Jones"]
        one["author_kinds"] = ["person", "person"]
        two["authors"] = ["Claire <Test> & Name", "Institute {Water} & Co"]
        two["author_kinds"] = ["person", "literal"]
        self.save_inputs()
        _, files, manifest = self.prepared()
        self.assertEqual(manifest["bibliography_records"], 5)
        exported = json.loads(files["native-reader.json"])
        self.assertEqual(exported["bibliography"], self.bibliography)
        first, second = self.observations["sources"][:2]
        key1, key2 = reader.bib_key(first), reader.bib_key(second)
        self.assertNotEqual(key1, key2)
        self.assertEqual(exported["bib_keys"]["S1"], key1)
        self.assertEqual(exported["bib_keys"]["S2"], key2)
        bib = files["references.bib"].decode()
        e1 = bib.split("@misc{" + key1 + ",", 1)[1].split("\n}", 1)[0]
        e2 = bib.split("@misc{" + key2 + ",", 1)[1].split("\n}", 1)[0]
        self.assertIn("author = {Alice Smith and Bob Jones}", e1)
        self.assertIn(r"author = {Claire <Test> \& Name and {Institute \textbraceleft{}Water\textbraceright{} \& Co}}", e2)
        for language in ("en", "zh-TW"):
            html = files["reader." + language + ".html"].decode()
            sec1 = html.split('<section id="bib-' + key1 + '">', 1)[1].split('</section>', 1)[0]
            sec2 = html.split('<section id="bib-' + key2 + '">', 1)[1].split('</section>', 1)[0]
            self.assertIn('S1 / work-one / v1', sec1)
            self.assertIn('S2 / work-one / v2', sec2)
            self.assertIn('Claire &lt;Test&gt; &amp; Name', sec2)
            self.assertNotIn('Claire', sec1)

    def test_bibliography_1_1_omitted_kinds_stay_literal(self):
        one = self.bibliography["records"][0]
        one["authors"] = ["Alice Smith", "World Health Organization"]
        self.save_inputs()
        _, before, _ = self.prepared()
        self.bibliography["format"] = "native-reader-bibliography/1.1"
        self.save_inputs()
        _, after, _ = self.prepared()
        self.assertEqual(before["references.bib"], after["references.bib"])
        self.assertIn(b"author = {{Alice Smith} and {World Health Organization}}", after["references.bib"])

    def test_bibliography_1_1_rejects_bad_kinds_and_ambiguous_person(self):
        self.bibliography["format"] = "native-reader-bibliography/1.1"
        record = self.bibliography["records"][0]
        record["authors"] = ["Alice Smith", "Organization"]
        for bad in (None, [], ["person"], ["person", "person", "literal"], ["person", "unknown"],
                    ["person", None], "person"):
            with self.subTest(kinds=bad):
                record["author_kinds"] = bad
                self.rejected()
        for name in ("Alice and Bob", "Alice AND Bob", "Alice\tand\nBob"):
            with self.subTest(person=name):
                record["authors"] = [name]
                record["author_kinds"] = ["person"]
                self.rejected()
                record["author_kinds"] = ["literal"]
                self.save_inputs()
                self.prepared()  # Literal strings retain the existing behavior.
        record["authors"] = []
        record["author_kinds"] = []
        self.save_inputs()
        self.prepared()
        record["authors"] = None
        record["author_kinds"] = []
        self.rejected()
        del record["authors"]
        self.rejected()

    @unittest.skipUnless(shutil.which("bibtex"), "BibTeX executable not available")
    def test_bibtex_person_particle_suffix_and_literal_controls(self):
        self.bibliography["format"] = "native-reader-bibliography/1.1"
        self.bibliography["records"] = [self.bibliography["records"][0]]
        record = self.bibliography["records"][0]
        record["authors"] = ["Alice Smith", "Ludwig van Beethoven", "Brown, Jr, Alice", "World Health Organization"]
        record["author_kinds"] = ["person", "person", "person", "literal"]
        self.save_inputs()
        _, files, _ = self.prepared()
        (self.root / "test.bib").write_bytes(files["references.bib"])
        (self.root / "test.aux").write_text('\\citation{*}\n\\bibstyle{names}\n\\bibdata{test}\n')
        (self.root / "names.bst").write_text('''ENTRY { author } {} {}
FUNCTION {misc} {
  author #1 "{ff}|{vv}|{ll}|{jj}" format.name$ write$ newline$
  author #2 "{ff}|{vv}|{ll}|{jj}" format.name$ write$ newline$
  author #3 "{ff}|{vv}|{ll}|{jj}" format.name$ write$ newline$
  author #4 "{ff}|{vv}|{ll}|{jj}" format.name$ write$ newline$
}
READ
ITERATE {call.type$}
''')
        run = subprocess.run([shutil.which("bibtex"), "test"], cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        output = (self.root / "test.bbl").read_text()
        self.assertEqual(output.splitlines(), ["Alice||Smith|", "Ludwig|van|Beethoven|", "Alice||Brown|Jr", "||{World Health Organization}|"])

    def test_doi_rejects_control_characters_in_both_bibliography_versions(self):
        record = self.bibliography["records"][0]
        for version in ("1.0", "1.1"):
            with self.subTest(version=version):
                self.bibliography["format"] = "native-reader-bibliography/" + version
                for suffix in ("a\x00b", "a\x01b", "a\x1fb", "a\x7fb", "a\u0080b", "a\u0085b", "a\u009fb", "a\tb", "a\nb", "a\rb"):
                    with self.subTest(suffix=repr(suffix)):
                        record["doi"] = "10.1234/" + suffix
                        self.rejected()
                record["doi"] = "10.1234/valid-doi_2026"
                self.save_inputs()
                _, files, _ = self.prepared()
                self.assertEqual(json.loads(files["native-reader.json"])["bibliography"]["records"][0]["doi"], record["doi"])
                self.assertIn(record["doi"], files["reader.en.html"].decode())
                self.assertIn(record["doi"].encode(), files["references.bib"])

    def test_person_comma_grammar_rejects_empty_or_excess_components(self):
        self.bibliography["format"] = "native-reader-bibliography/1.1"
        record = self.bibliography["records"][0]
        record["author_kinds"] = ["person"]
        for name in ("Alice, Bob, Carol, Dave", "Alice,", ", Bob", ",", "Alice,,Bob", "Alice, Bob,", ", Alice, Bob", "Alice, , Bob", "A, -", "-, A", "A, -, B", "A, B, -", "---", "A, - - -"):
            with self.subTest(invalid=name):
                record["authors"] = [name]
                self.rejected()
        for name in ("Alice Smith", "Ludwig van Beethoven", "van Beethoven, Ludwig", "Brown, Jr, Alice", "A, B-C"):
            with self.subTest(valid=name):
                record["authors"] = [name]
                self.save_inputs()
                _, files, _ = self.prepared()
                self.assertEqual(json.loads(files["native-reader.json"])["bibliography"]["records"][0]["authors"], [name])
                key = reader.bib_key(self.observations["sources"][0])
                self.assertIn('@misc{' + key, files["references.bib"].decode())
        # Literal/legacy names are not reinterpreted as person syntax.
        record["authors"] = ["Institute, Region, Division, Program"]
        record["author_kinds"] = ["literal"]
        self.save_inputs()
        self.prepared()
        self.bibliography["format"] = "native-reader-bibliography/1.0"
        del record["author_kinds"]
        self.save_inputs()
        self.prepared()

    @unittest.skipUnless(shutil.which("bibtex"), "BibTeX executable not available")
    def test_bibtex_excess_person_commas_are_rejected_before_export(self):
        # Real parser negative control demonstrates the rejected syntax breaks
        # format.name$; no TeX process or network is invoked.
        name = "Alice, Bob, Carol, Dave"
        (self.root / "test.bib").write_text('@misc{x, author={' + name + '}}\n')
        (self.root / "test.aux").write_text('\\citation{*}\n\\bibstyle{names}\n\\bibdata{test}\n')
        (self.root / "names.bst").write_text('ENTRY { author } {} {}\nFUNCTION {misc} { author #1 "{ff}|{vv}|{ll}|{jj}" format.name$ write$ newline$ }\nREAD\nITERATE {call.type$}\n')
        run = subprocess.run([shutil.which("bibtex"), "test"], cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("too many commas", (run.stdout + run.stderr).lower())
        self.bibliography["format"] = "native-reader-bibliography/1.1"
        record = self.bibliography["records"][0]
        record["authors"] = [name]
        record["author_kinds"] = ["person"]
        self.rejected()

    @unittest.skipUnless(shutil.which("bibtex"), "BibTeX executable not available")
    def test_bibtex_separator_only_person_component_negative_control(self):
        (self.root / "test.aux").write_text('\\citation{*}\n\\bibstyle{names}\n\\bibdata{test}\n')
        (self.root / "names.bst").write_text('ENTRY { author } {} {}\nFUNCTION {misc} { author #1 "{ff}|{vv}|{ll}|{jj}" format.name$ write$ newline$ }\nREAD\nITERATE {call.type$}\n')
        self.bibliography["format"] = "native-reader-bibliography/1.1"
        record = self.bibliography["records"][0]
        record["author_kinds"] = ["person"]
        for name in ("A, -",):
            with self.subTest(name=name):
                (self.root / "test.bib").write_text('@misc{x, author={' + name + '}}\n')
                run = subprocess.run([shutil.which("bibtex"), "test"], cwd=self.root, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
                record["authors"] = [name]
                self.rejected()
        # A substantive hyphenated component must not be rejected.
        self.bibliography["records"] = [record]
        name = "A, B-C"
        record["authors"] = [name]
        self.save_inputs()
        _, files, _ = self.prepared()
        (self.root / "test.bib").write_bytes(files["references.bib"])
        run = subprocess.run([shutil.which("bibtex"), "test"], cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("B-C||A|", (self.root / "test.bbl").read_text())
        # An input tilde is encoded as a literal TeX macro, not the BibTeX
        # name separator that a raw, unencoded tilde would be.
        record["authors"] = ["A, ~"]
        self.save_inputs()
        _, files, _ = self.prepared()
        (self.root / "test.bib").write_bytes(files["references.bib"])
        run = subprocess.run([shutil.which("bibtex"), "test"], cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn(r"\textasciitilde{}||A|", (self.root / "test.bbl").read_text())

    def test_person_braces_rejected_without_changing_legacy_or_literal(self):
        self.bibliography["format"] = "native-reader-bibliography/1.1"
        record = self.bibliography["records"][0]
        for name in ("Alice {Smith", "Alice Smith}", "}{", "Alice }Smith{", "A {{Name} Smith", "Alice {Example} Smith", "{Q}"):
            with self.subTest(person=name):
                record["authors"] = [name]
                record["author_kinds"] = ["person"]
                self.rejected()
                # The same input remains accepted in literal and 1.0 forms;
                # brace serialization is intentionally hardened for both.
                record["author_kinds"] = ["literal"]
                self.save_inputs()
                self.prepared()
                self.bibliography["format"] = "native-reader-bibliography/1.0"
                del record["author_kinds"]
                self.save_inputs()
                self.prepared()
                self.bibliography["format"] = "native-reader-bibliography/1.1"

    @unittest.skipUnless(shutil.which("bibtex"), "BibTeX executable not available")
    def test_bibtex_person_brace_field_injection_negative_and_escaped_positive(self):
        (self.root / "test.aux").write_text('\\citation{*}\n\\bibstyle{names}\n\\bibdata{test}\n')
        (self.root / "names.bst").write_text('ENTRY { author note } {} {}\nFUNCTION {misc} { author write$ newline$ note empty$ { "" } { note } if$ write$ newline$ }\nREAD\nITERATE {call.type$}\n')
        bib = self.root / "test.bib"
        injected_name = 'Alice }, note = "Injected"'
        # Historical legacy encoding, not the current serializer: BibTeX
        # interprets backslash-braces as grouping and exposes field injection.
        legacy_tex = injected_name.replace('}', r'\}')
        bib.write_text('@misc{x, author={' + legacy_tex + '}}\n')
        negative = subprocess.run([shutil.which("bibtex"), "test"], cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(negative.returncode, 0, negative.stdout + negative.stderr)
        self.assertIn('Injected', (self.root / 'test.bbl').read_text())
        self.bibliography["format"] = "native-reader-bibliography/1.1"
        self.bibliography["records"] = [self.bibliography["records"][0]]
        record = self.bibliography["records"][0]
        record["authors"] = [injected_name]
        record["author_kinds"] = ["person"]
        self.rejected()
        record["authors"] = ["Alice & Smith"]
        self.save_inputs()
        _, files, _ = self.prepared()
        bib.write_bytes(files["references.bib"])
        positive = subprocess.run([shutil.which("bibtex"), "test"], cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(positive.returncode, 0, positive.stdout + positive.stderr)
        result = (self.root / 'test.bbl').read_text()
        self.assertIn(r'Alice \& Smith', result)
        self.assertNotIn('Injected', result)

    @unittest.skipUnless(shutil.which("bibtex"), "BibTeX executable not available")
    def test_bibtex_fields_retain_escaped_values_without_injected_fields_or_entries(self):
        # BibTeX, not TeX, parses this private synthetic fixture. No TeX process
        # is invoked. The note field and extra record are injection sentinels.
        from urllib.parse import quote

        self.bibliography["records"] = self.bibliography["records"][:2]
        payloads = [
            r'Title }, note = "INJECTED", } @misc{injected, title={X} \bad {open',
            r'Title {balanced} and }unmatched \\tail',
        ]
        for version in ("1.0", "1.1"):
            with self.subTest(bibliography=version):
                self.bibliography["format"] = "native-reader-bibliography/" + version
                for i, record in enumerate(self.bibliography["records"]):
                    source = self.observations["sources"][i]
                    source["title"] = record["title"] = payloads[i]
                    record["authors"] = [r'Group }, note = "INJECTED" {A} \cmd', r'Person \backslash']
                    record["year"] = 2024 + i
                    record["venue"] = r'Venue }, note = "INJECTED" {balanced} \tail'
                    record["doi"] = '10.1234/a},note="INJECTED"{b}\\z'
                    record["url"] = 'https://example.test/x},note="INJECTED"{b}\\z'
                    if version == "1.1":
                        record["author_kinds"] = ["literal", "person"]
                    else:
                        record.pop("author_kinds", None)
                self.save_inputs()
                _, files, manifest = self.prepared()
                self.assertEqual(json.loads(files["native-reader.json"])["bibliography"], self.bibliography)
                self.assertEqual(manifest["bibliography_records"], 2)
                (self.root / "test.bib").write_bytes(files["references.bib"])
                (self.root / "test.aux").write_text('\\citation{*}\n\\bibstyle{fields}\n\\bibdata{test}\n')
                (self.root / "fields.bst").write_text('''ENTRY { title author journal doi url note } {} {}
FUNCTION {misc} {
  "START" write$ newline$
  "KEY:" write$ cite$ write$ newline$
  "TITLE:" write$ title write$ newline$
  "AUTHOR:" write$ author write$ newline$
  "JOURNAL:" write$ journal write$ newline$
  "DOI:" write$ doi write$ newline$
  "URL:" write$ url write$ newline$
  "NOTE:" write$ note empty$ { "NO_NOTE" } { note } if$ write$ newline$
  "END" write$ newline$
}
READ
ITERATE {call.type$}
''')
                run = subprocess.run([shutil.which("bibtex"), "test"], cwd=self.root, capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                lines = (self.root / "test.bbl").read_text().splitlines()
                self.assertEqual(lines.count("START"), 2)
                self.assertEqual(lines.count("END"), 2)
                blocks, current, field = {}, None, None
                labels = ("KEY", "TITLE", "AUTHOR", "JOURNAL", "DOI", "URL", "NOTE")
                for line in lines:
                    if line == "START":
                        current = {}
                    elif line == "END":
                        self.assertEqual(set(current), set(labels))
                        blocks[current["KEY"]] = current
                        current, field = None, None
                    elif current is not None:
                        label = next((label for label in labels if line.startswith(label + ":")), None)
                        if label is not None:
                            field = label
                            current[field] = line[len(label) + 1:]
                        else:
                            self.assertIsNotNone(field)
                            current[field] += " " + line.lstrip()
                self.assertEqual(set(blocks), {reader.bib_key(s) for s in self.observations["sources"][:2]})
                # Independent oracle for the proposed single-pass character encoding.
                mapping = {"\\": r"\textbackslash{}", "{": r"\textbraceleft{}", "}": r"\textbraceright{}", "$": r"\$", "&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\n": " ", "\r": " ", "\t": " "}
                def encoded(value):
                    return "".join(mapping.get(c, c) for c in value)
                for i, record in enumerate(self.bibliography["records"]):
                    block = blocks[reader.bib_key(self.observations["sources"][i])]
                    title, authors, journal, doi, url, note = (block[k] for k in ("TITLE", "AUTHOR", "JOURNAL", "DOI", "URL", "NOTE"))
                    self.assertEqual(title, encoded(record["title"]))
                    first = "{" + encoded(record["authors"][0]) + "}"
                    second = encoded(record["authors"][1])
                    if version == "1.0":
                        second = "{" + second + "}"
                    self.assertEqual(authors, first + " and " + second)
                    self.assertEqual(journal, encoded(record["venue"]))
                    safe = ":/?#[]@!$&'()*+,;=%-._~"
                    self.assertEqual(doi, quote(record["doi"], safe=safe))
                    self.assertEqual(url, quote(record["url"], safe=safe))
                    self.assertEqual(note, "NO_NOTE")

    def test_wrong_work_even_with_same_version_is_rejected(self):
        self.content["en"]["records"][0]["work_id"] = "wrong-work"
        self.rejected()

    def test_wrong_nullable_version_is_rejected(self):
        self.bibliography["records"][2]["version"] = "made-up-version"
        self.rejected()

    def test_missing_and_duplicate_identity_are_errors(self):
        for field in ("id", "work_id", "version"):
            with self.subTest(field=field):
                self.observations, self.content, self.bibliography = fixture()
                del self.observations["sources"][0][field]
                self.rejected()
        self.observations, self.content, self.bibliography = fixture()
        self.observations["sources"].append(copy.deepcopy(self.observations["sources"][0]))
        self.rejected()

    def test_unknown_cross_reference_is_rejected(self):
        for target, field, value in [
            ("source", "need_ids", ["missing"]), ("source", "attempt_ids", ["missing"]),
            ("content", "source_id", "missing"), ("bib", "verification_ref", "missing"),
        ]:
            with self.subTest(target=target, field=field):
                self.observations, self.content, self.bibliography = fixture()
                record = self.observations["sources"][0] if target == "source" else self.content["en"]["records"][0] if target == "content" else self.bibliography["records"][0]
                record[field] = value
                self.rejected()

    def test_claim_scope_and_reference_must_match_recorded_scope(self):
        for change in ("scope", "reference", "duplicate", "locator", "language-binding"):
            with self.subTest(change=change):
                self.observations, self.content, self.bibliography = fixture()
                claim = self.content["en"]["records"][1]["claims"][0]
                if change == "scope":
                    claim["reading_level"] = "full-text"
                elif change == "reference":
                    claim["reading_ref"] = "different-source"
                elif change == "duplicate":
                    self.content["en"]["records"][1]["claims"].append(copy.deepcopy(claim))
                elif change == "locator":
                    claim["locator"] = None
                else:
                    claim["locator"] = "different binding from zh-TW"
                self.rejected()

    def test_presentation_cannot_upgrade_reading(self):
        self.content["en"]["records"][1]["reading_level"] = "full-text"
        self.rejected()

    def test_schema_reading_levels_are_preserved_exactly(self):
        self.observations["sources"][0]["reading_level"] = "body"
        self.rejected()

    def test_language_mismatch_and_missing_file_are_rejected(self):
        self.content["en"]["language"] = "zh-TW"
        self.rejected()
        with self.assertRaisesRegex(reader.ReaderError, "input or output parent is missing"):
            reader.prepare(self.obs, self.root / "absent-language.json")

    def test_unsafe_source_and_bibliography_urls_are_rejected(self):
        for uri in ("javascript:alert(1)", "data:text/html,evil", "file:///private", "ftp://example.test/x", "https://user:pass@example.test/x"):
            with self.subTest(uri=uri):
                self.observations, self.content, self.bibliography = fixture()
                self.observations["sources"][0]["locator"] = uri
                self.rejected()
                self.observations, self.content, self.bibliography = fixture()
                self.bibliography["records"][0]["url"] = uri
                self.rejected()

    def test_bad_json_duplicate_keys_and_nonfinite_values_are_rejected(self):
        for raw in (b'{"format":1,"format":2}', b'{"bad":NaN}', b'{"bad":Infinity}', b'{"bad":1e999}', b'not JSON'):
            with self.subTest(raw=raw):
                self.obs.write_bytes(raw)
                with self.assertRaises((reader.ReaderError, ValueError)):
                    reader.prepare(self.obs)

    def test_unsafe_material_references_and_input_size_are_rejected(self):
        for name in ("../outside", "/absolute", "C:\\outside", ".GIT/config", ".research/state"):
            with self.subTest(name=name):
                self.observations, self.content, self.bibliography = fixture()
                self.observations["sources"][0]["material"] = {"path": name, "sha256": "a" * 64}
                self.rejected()
        self.obs.write_bytes(b" " * (reader.LIMIT + 1))
        with self.assertRaisesRegex(reader.ReaderError, "exceeds 4 MiB"):
            reader.prepare(self.obs)

    def fifo_swap_rejected(self, stage):
        # The child alone performs the potentially blocking open. subprocess.run
        # kills and reaps that owned child on timeout, even on a regressed reader.
        code = """
import importlib.util
import os
from pathlib import Path
import sys
from unittest.mock import patch

script, root, stage = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
spec = importlib.util.spec_from_file_location("fifo_reader", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
target = root / "observations.json"
real_open = os.open
reads = 0

def swap_before_open(path, flags, *args, **kwargs):
    global reads
    if Path(path) == target:
        reads += 1
        if reads == (1 if stage == "prepare" else 2):
            target.rename(root / "original-observations.json")
            os.mkfifo(target)
    return real_open(path, flags, *args, **kwargs)

with patch.object(module.os, "open", swap_before_open):
    result = module.main([
        "--observations", str(target),
        "--content-en", str(root / "content.en.json"),
        "--content-zh-TW", str(root / "content.zh-TW.json"),
        "--bibliography", str(root / "bibliography.json"),
        "--output-dir", str(root / "new-output"),
    ])
raise SystemExit(result)
"""
        mirror = ROOT / "src/research_hub/skills_data/research-hub/scripts/render_native_reader.py"
        _, expected_files, _ = self.prepared()
        for script in (SCRIPT, mirror):
            with self.subTest(script=script, stage=stage):
                with tempfile.TemporaryDirectory(dir=self.root) as temporary:
                    root = Path(temporary)
                    for source in (self.obs, self.en, self.zh, self.bib):
                        (root / source.name).write_bytes(source.read_bytes())
                    existing = root / "existing-output"
                    existing.mkdir()
                    (existing / "user-note.txt").write_bytes(b"preserve existing output")
                    before = self.snapshot(root)
                    result = subprocess.run(
                        [sys.executable, "-I", "-S", "-B", "-c", code,
                         str(script), str(root), stage],
                        capture_output=True, timeout=5, check=False,
                    )
                    self.assertEqual(result.returncode, 1, result.stderr.decode(errors="replace"))
                    self.assertEqual(result.stdout, b"")
                    failure = json.loads(result.stderr)
                    self.assertEqual(failure["status"], "failed")
                    self.assertIn("single-link regular file", failure["error"])
                    self.assertTrue((root / self.obs.name).is_fifo())
                    original = root / "original-observations.json"
                    self.assertEqual((original.read_bytes(), original.stat().st_mtime_ns),
                                     before[self.obs.name])
                    for name, snapshot in before.items():
                        if name != self.obs.name:
                            path = root / name
                            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), snapshot)
                    output = root / "new-output"
                    self.assertFalse((output / "manifest.json").exists())
                    if stage == "prepare":
                        self.assertFalse(output.exists())
                    else:
                        self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()},
                                         expected_files)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "mkfifo") and hasattr(os, "O_NONBLOCK"),
                         "FIFO replacement requires POSIX nonblocking open")
    def test_fifo_swap_during_prepare_fails_without_writes(self):
        self.fifo_swap_rejected("prepare")

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "mkfifo") and hasattr(os, "O_NONBLOCK"),
                         "FIFO replacement requires POSIX nonblocking open")
    def test_fifo_swap_during_final_recheck_preserves_incomplete_output(self):
        self.fifo_swap_rejected("recheck")

    def test_hardlinked_input_is_rejected(self):
        import os
        alias = self.root / "hardlink.json"
        try:
            os.link(self.obs, alias)
        except OSError as error:
            self.skipTest("hardlink creation unavailable: " + type(error).__name__)
        with self.assertRaisesRegex(reader.ReaderError, "single-link regular file"):
            reader.prepare(self.obs)

    def test_traversal_overlap_and_existing_empty_output_are_rejected(self):
        with self.assertRaises(reader.ReaderError):
            reader.prepare(self.root / "nested" / ".." / "observations.json")
        inputs, files, manifest = self.prepared()
        before = self.snapshot(self.root)
        with self.assertRaises(reader.ReaderError):
            reader.generate(self.root, inputs, files, manifest)
        self.assertEqual(before, self.snapshot(self.root))
        existing = self.root / "empty"
        existing.mkdir()
        with self.assertRaises(reader.ReaderError):
            reader.generate(existing, inputs, files, manifest)
        self.assertFalse(list(existing.iterdir()))

    def test_output_parent_symlink_is_rejected_without_writing_through(self):
        inputs, files, manifest = self.prepared()
        input_snapshot = {key: (path.read_bytes(), path.stat().st_mtime_ns) for key, (path, _, _) in inputs.items()}
        target = self.root / "symlink-target"
        target.mkdir()
        (target / "sentinel.txt").write_bytes(b"preserve this file")
        before = self.snapshot(target)
        link = self.root / "linked-parent"
        try:
            link.symlink_to(target, target_is_directory=True)
        except NotImplementedError:
            self.skipTest("directory symlinks are not implemented on this platform")
        except OSError as error:
            unsupported = {errno.ENOSYS, getattr(errno, "ENOTSUP", errno.ENOSYS), getattr(errno, "EOPNOTSUPP", errno.ENOSYS)}
            if getattr(error, "winerror", None) in {50, 1314} or error.errno in unsupported:
                self.skipTest("directory symlink unsupported or Windows privilege unavailable: " + str(error))
            raise
        self.assertTrue(link.is_symlink())
        with self.assertRaisesRegex(reader.ReaderError, "linked paths"):
            reader.generate(link / "output", inputs, files, manifest)
        self.assertEqual(self.snapshot(target), before)
        self.assertFalse((target / "output").exists())
        self.assertEqual({key: (path.read_bytes(), path.stat().st_mtime_ns) for key, (path, _, _) in inputs.items()}, input_snapshot)

    def test_partial_file_write_is_preserved_and_fresh_retry_succeeds(self):
        inputs, files, manifest = self.prepared()
        input_snapshot = {key: (path.read_bytes(), path.stat().st_mtime_ns) for key, (path, _, _) in inputs.items()}
        first_name = sorted(files)[0]
        self.assertGreater(len(files[first_name]), 1)
        prefix = files[first_name][:len(files[first_name]) // 2]
        output = self.root / "partial-file"
        attempted = []

        def fail_after_prefix(path, data):
            attempted.append(path.name)
            self.assertEqual((path.name, data), (first_name, files[first_name]))
            with path.open("xb") as stream:
                stream.write(prefix)
            raise OSError("synthetic partial write failure")

        with patch.object(reader, "write_file", side_effect=fail_after_prefix):
            with self.assertRaisesRegex(OSError, "synthetic partial write failure"):
                reader.generate(output, inputs, files, manifest)
        self.assertEqual(attempted, [first_name])
        self.assertEqual({path.name for path in output.iterdir()}, {first_name})
        self.assertEqual((output / first_name).read_bytes(), prefix)
        self.assertFalse((output / "manifest.json").exists())
        partial_snapshot = self.snapshot(output)
        with self.assertRaisesRegex(reader.ReaderError, "output already exists"):
            reader.generate(output, inputs, files, manifest)
        self.assertEqual(self.snapshot(output), partial_snapshot)
        retry = reader.generate(self.root / "partial-file-retry", inputs, files, manifest)
        self.assertEqual({name: (retry / name).read_bytes() for name in files}, files)
        self.assertEqual(json.loads((retry / "manifest.json").read_bytes()), manifest)
        self.assertEqual(self.snapshot(output), partial_snapshot)
        self.assertEqual({key: (path.read_bytes(), path.stat().st_mtime_ns) for key, (path, _, _) in inputs.items()}, input_snapshot)

    def test_interrupted_generation_has_no_completed_manifest(self):
        inputs, files, manifest = self.prepared()
        output = self.root / "partial"
        original = reader.write_file
        calls = []
        def interrupt(path, data):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("synthetic interrupted write")
            original(path, data)
        with patch.object(reader, "write_file", side_effect=interrupt):
            with self.assertRaises(OSError):
                reader.generate(output, inputs, files, manifest)
        self.assertTrue(output.exists())
        self.assertFalse((output / "manifest.json").exists())
        with self.assertRaises(reader.ReaderError):
            reader.generate(output, inputs, files, manifest)

    def test_recovery_keeps_invocation_acknowledgment_separate_from_file_consistency(self):
        inputs, files, manifest = self.prepared()
        input_snapshot = {key: (path.read_bytes(), path.stat().st_mtime_ns) for key, (path, _, _) in inputs.items()}
        original_write, original_generate = reader.write_file, reader.generate
        manifest_bytes = reader.canonical(manifest)

        def arguments(output):
            return ["--observations", str(self.obs), "--content-en", str(self.en), "--content-zh-TW", str(self.zh),
                    "--bibliography", str(self.bib), "--output-dir", str(output)]

        for scenario in ("manifest-fsync-error", "lost-postwrite-ack"):
            with self.subTest(scenario=scenario):
                output = self.root / scenario
                stdout, stderr = io.StringIO(), io.StringIO()
                intercepted = []

                def fail_manifest_fsync(path, data):
                    if data == manifest_bytes:
                        intercepted.append("fsync")
                        with patch.object(reader.os, "fsync", side_effect=OSError("synthetic manifest fsync failure")):
                            return original_write(path, data)
                    return original_write(path, data)

                def interrupt_after_write(*args, **kwargs):
                    original_generate(*args, **kwargs)
                    raise SystemExit("synthetic lost acknowledgment")

                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    if scenario == "manifest-fsync-error":
                        with patch.object(reader, "write_file", side_effect=fail_manifest_fsync):
                            code = reader.main(arguments(output))
                        self.assertEqual(code, 1)
                        self.assertEqual(intercepted, ["fsync"])
                        failure = json.loads(stderr.getvalue())
                        self.assertEqual(failure["status"], "failed")
                        self.assertIn("synthetic manifest fsync failure", failure["error"])
                    else:
                        with patch.object(reader, "generate", side_effect=interrupt_after_write):
                            with self.assertRaisesRegex(SystemExit, "synthetic lost acknowledgment"):
                                reader.main(arguments(output))
                        self.assertEqual(stderr.getvalue(), "")
                self.assertEqual(stdout.getvalue(), "")  # No successful invocation acknowledgment.

                for key, (path, expected, _) in inputs.items():
                    self.assertEqual(path.read_bytes(), expected)
                    self.assertEqual(manifest["inputs"][key], {"name": path.name, "bytes": len(expected), "sha256": hashlib.sha256(expected).hexdigest()})
                for name, expected in files.items():
                    actual = (output / name).read_bytes()
                    self.assertEqual(actual, expected)
                    self.assertEqual(manifest["outputs"][name], {"bytes": len(actual), "sha256": hashlib.sha256(actual).hexdigest()})
                marker = output / "manifest.json"
                if scenario == "lost-postwrite-ack":
                    self.assertTrue(marker.is_file())
                if marker.is_file():  # A future stronger publication strategy may leave no final marker after fsync failure.
                    self.assertEqual(marker.read_bytes(), manifest_bytes)
                    self.assertEqual(json.loads(marker.read_bytes())["status"], "complete")

                before = self.snapshot(output)
                repeated_stdout, repeated_stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(repeated_stdout), contextlib.redirect_stderr(repeated_stderr):
                    self.assertEqual(reader.main(arguments(output)), 1)
                self.assertEqual(repeated_stdout.getvalue(), "")
                repeat_failure = json.loads(repeated_stderr.getvalue())
                self.assertEqual(repeat_failure["status"], "failed")
                self.assertIn("output already exists", repeat_failure["error"])
                self.assertEqual(self.snapshot(output), before)

                retry = self.root / (scenario + "-retry")
                retry_stdout, retry_stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(retry_stdout), contextlib.redirect_stderr(retry_stderr):
                    self.assertEqual(reader.main(arguments(retry)), 0)
                acknowledgment = json.loads(retry_stdout.getvalue())
                self.assertEqual(acknowledgment["status"], "generated")
                self.assertEqual(retry_stderr.getvalue(), "")
                self.assertEqual(acknowledgment["manifest_sha256"], hashlib.sha256((retry / "manifest.json").read_bytes()).hexdigest())
                self.assertEqual(json.loads((retry / "manifest.json").read_bytes()), manifest)
                self.assertEqual({name: (retry / name).read_bytes() for name in files}, files)
                self.assertEqual(self.snapshot(output), before)
                self.assertEqual({key: (path.read_bytes(), path.stat().st_mtime_ns) for key, (path, _, _) in inputs.items()}, input_snapshot)

    def test_broken_generated_links_are_detected(self):
        for markup in (b'<a href="missing.json">bad</a>', b'<a href="#absent">bad</a>', b'<a href="../outside">bad</a>'):
            with self.subTest(markup=markup):
                with self.assertRaises(reader.ReaderError):
                    reader.verify_links({"reader.en.html": markup})

    def test_isolated_cli_needs_no_hub_site_packages_or_model(self):
        output = self.root / "isolated"
        unicode_input = self.root / "observations-🌿.json"
        self.obs.rename(unicode_input)
        command = [sys.executable, "-I", "-S", "-B", str(SCRIPT), "--observations", str(unicode_input), "--content-en", str(self.en), "--content-zh-TW", str(self.zh), "--bibliography", str(self.bib)]
        check = subprocess.run([*command, "--check-only"], capture_output=True, timeout=30, check=False)
        self.assertEqual(check.returncode, 0, check.stderr.decode(errors="replace"))
        self.assertEqual(json.loads(check.stdout)["manifest_preview"]["inputs"]["observations"]["name"], unicode_input.name)
        self.assertFalse(output.exists())
        command.extend(["--output-dir", str(output)])
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(json.loads(result.stdout)["languages"], ["en", "zh-TW"])
        self.assertTrue((output / "manifest.json").is_file())

    def test_recovery_guidance_distinguishes_consistency_and_acknowledgment(self):
        references = [SCRIPT.parent.parent / "references/native-discovery-export.md",
                      ROOT / "src/research_hub/skills_data/research-hub/references/native-discovery-export.md"]
        for path in references:
            with self.subTest(path=path):
                flat = " ".join(path.read_text(encoding="utf-8").split())
                for clause in ("matching input and output hashes establish only present artifact consistency",
                               "do not establish that the invocation succeeded", "successful zero exit",
                               "`status: generated`", "`manifest_sha256`", "failed or unknown invocation",
                               "same verified unchanged inputs", "fresh output directory"):
                    self.assertIn(clause, flat)

    def test_documented_script_location_guidance_uses_loaded_resource(self):
        guidance = (SCRIPT.parent.parent / "references/native-discovery-export.md").read_text(encoding="utf-8")
        section = guidance.split("## Optional standalone reader (no Hub runtime)", 1)[1]
        flat = " ".join(section.split())
        for clause in ("actual loaded `SKILL.md`", "relative to that file's directory", "Keep the working directory", "Do not guess user/cache paths", "same-named project file", "If the loaded skill has no accessible helper", "retain the native report", "`skill://` is not a shell pathname"):
            self.assertIn(clause, flat)
        self.assertNotIn("python skills/research-hub/scripts/render_native_reader.py", section)
        self.assertEqual(section.count('python "<resolved-reader-script>"'), 2)

    def test_script_location_from_loaded_skill_preserves_project_cwd(self):
        loaded = self.root / "loaded skill with spaces"
        project = self.root / "user project with spaces"
        loaded.mkdir()
        project.mkdir()
        skill_md = loaded / "SKILL.md"
        skill_md.write_bytes((SCRIPT.parent.parent / "SKILL.md").read_bytes())
        selected_script = skill_md.resolve().parent / "scripts/render_native_reader.py"
        selected_script.parent.mkdir()
        selected_script.write_bytes(SCRIPT.read_bytes())
        for source, name in ((self.obs, "observations.json"), (self.en, "reader.en.json"), (self.zh, "reader.zh-TW.json"), (self.bib, "bibliography.json")):
            (project / name).write_bytes(source.read_bytes())
        relative = Path("skills/research-hub/scripts/render_native_reader.py")
        self.assertFalse((project / relative).exists())
        old = subprocess.run([sys.executable, "-I", "-S", "-B", str(relative), "--help"], cwd=project, capture_output=True, timeout=10)
        self.assertEqual(old.returncode, 2)
        command = [sys.executable, "-I", "-S", "-B", str(selected_script), "--observations", "observations.json", "--content-en", "reader.en.json", "--content-zh-TW", "reader.zh-TW.json", "--bibliography", "bibliography.json"]
        project_before, loaded_before = self.snapshot(project), self.snapshot(loaded)
        checked = subprocess.run([*command, "--check-only"], cwd=project, capture_output=True, timeout=30)
        self.assertEqual(checked.returncode, 0, checked.stderr.decode(errors="replace"))
        self.assertFalse(json.loads(checked.stdout)["writes"])
        self.assertEqual(self.snapshot(project), project_before)
        self.assertEqual(self.snapshot(loaded), loaded_before)
        generated = subprocess.run([*command, "--output-dir", "new-reader-output"], cwd=project, capture_output=True, timeout=30)
        self.assertEqual(generated.returncode, 0, generated.stderr.decode(errors="replace"))
        self.assertEqual(Path(json.loads(generated.stdout)["output_dir"]), project / "new-reader-output")
        self.assertTrue((project / "new-reader-output/manifest.json").is_file())
        self.assertEqual(self.snapshot(loaded), loaded_before)

    def test_packaged_script_is_the_exact_source_mirror(self):
        mirror = ROOT / "src/research_hub/skills_data/research-hub/scripts/render_native_reader.py"
        self.assertEqual(SCRIPT.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
