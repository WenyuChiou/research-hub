"""Synthetic standalone delivery checks: output consistency, not research acceptance.

Cross-file checks and two explicitly selected CLI environment variants are
offline tests; output equality does not prove general network isolation or
independence from every possible integration setting.
"""
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

# Resolve the repository's tests package explicitly for pytest and direct CLI.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_native_reader import SCRIPT, fixture, reader

EXPORTS_LABELS = {"Exports", "匯出及語言"}
BIB_LABEL = {"en": "Bibliography", "zh-TW": "參考書目"}
PDF_LABEL = {
    "en": "Supplied PDF attachment (language/content not verified): ",
    "zh-TW": "提供的 PDF 附件（語言及內容未經驗證）：",
}


class DeliveryPage(HTMLParser):
    """Collect header and article links and IDs from generated HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.header_nav_links, self.all_links = [], [], []
        self.article_bib_links = {}
        self.article_back_links, self.work_sections = {}, {}
        self._section_stack = []
        self._in_header = self._in_header_nav = False
        self._article = self._anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "header":
            self._in_header = True
        elif tag == "nav" and self._in_header and attrs.get("aria-label") in EXPORTS_LABELS:
            self._in_header_nav = True
        elif tag == "section":
            section_id = attrs.get("id")
            self._section_stack.append(section_id)
            if section_id and section_id.startswith("work-"):
                self.work_sections.setdefault(section_id, set())
        elif tag == "article" and "id" in attrs:
            self._article = attrs["id"]
            self.article_bib_links.setdefault(self._article, [])
            self.article_back_links.setdefault(self._article, [])
            for section_id in reversed(self._section_stack):
                if section_id and section_id.startswith("work-"):
                    self.work_sections.setdefault(section_id, set()).add(self._article)
                    break
        if tag == "a":
            self._anchor = [attrs, []]

    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._anchor is not None:
            attrs, parts = self._anchor
            text = "".join(parts)
            self._anchor = None
            self.all_links.append((attrs, text))
            if self._in_header_nav:
                self.header_nav_links.append((attrs, text))
            if self._article is not None and attrs.get("href", "").startswith("#bib-"):
                self.article_bib_links[self._article].append((attrs["href"], text))
            if self._article is not None and attrs.get("href") == "#contents":
                self.article_back_links[self._article].append(attrs["href"])
        elif tag == "nav":
            self._in_header_nav = False
        elif tag == "header":
            self._in_header = False
        elif tag == "section" and self._section_stack:
            self._section_stack.pop()
        elif tag == "article":
            self._article = None


def parse_page(markup):
    page = DeliveryPage()
    page.feed(markup)
    page.close()
    return page


def bib_keys_in(bib_text):
    return re.findall(r"^@misc\{([^,]+),", bib_text, flags=re.M)


class NativeReaderDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-reader-delivery-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.observations, self.content, self.bibliography = fixture()
        self.obs = self.root / "observations.json"
        self.en = self.root / "content.en.json"
        self.zh = self.root / "content.zh-TW.json"
        self.bib = self.root / "bibliography.json"
        self.save_inputs()

    def save_inputs(self):
        for path, payload in [(self.obs, self.observations), (self.en, self.content["en"]),
                              (self.zh, self.content["zh-TW"]), (self.bib, self.bibliography)]:
            path.write_bytes(reader.canonical(payload))

    def test_header_exports_nav_links_json_and_bibtex_in_each_generated_page(self):
        # Variants: bilingual with bibliography, English-only with
        # bibliography, bilingual without bibliography. In every variant
        # each generated page must expose both machine exports in its
        # header Exports nav, and the linked files must be the generated
        # bytes recorded in the manifest.
        variants = [
            ("bilingual", True, True),
            ("en-only", False, True),
            ("bilingual-no-bibliography", True, False),
        ]
        for name, both, with_bib in variants:
            with self.subTest(variant=name):
                inputs, files, manifest = reader.prepare(
                    self.obs, self.en, self.zh if both else None, self.bib if with_bib else None)
                output = reader.generate(self.root / ("exports-" + name), inputs, files, manifest)
                languages = ["en", "zh-TW"] if both else ["en"]
                for language in languages:
                    page = parse_page((output / ("reader." + language + ".html")).read_text(encoding="utf-8"))
                    nav = {(attrs.get("href"), text) for attrs, text in page.header_nav_links}
                    self.assertIn(("native-reader.json", "JSON"), nav)
                    self.assertIn(("references.bib", "BibTeX"), nav)
                    for export in ("native-reader.json", "references.bib"):
                        self.assertEqual((output / export).read_bytes(), files[export])
                        self.assertEqual(manifest["outputs"][export]["sha256"],
                                         hashlib.sha256(files[export]).hexdigest())

    def test_bibtex_file_matches_html_bibliography_and_article_links(self):
        inputs, files, manifest = reader.prepare(self.obs, self.en, self.zh, self.bib)
        output = reader.generate(self.root / "bib-correspondence", inputs, files, manifest)
        exported = json.loads(files["native-reader.json"])
        bib_text = (output / "references.bib").read_text(encoding="utf-8")
        keys = bib_keys_in(bib_text)
        self.assertEqual(set(keys), set(exported["bib_keys"].values()))
        self.assertEqual(len(keys), manifest["bibliography_records"])
        self.assertEqual(len(keys), len(set(keys)))
        for language in ("en", "zh-TW"):
            with self.subTest(language=language):
                page = parse_page((output / ("reader." + language + ".html")).read_text(encoding="utf-8"))
                expected_sections = {"bib-" + key for key in exported["bib_keys"].values()}
                found_sections = {item for item in page.ids if item.startswith("bib-")}
                self.assertEqual(found_sections, expected_sections)
                for source in self.observations["sources"]:
                    key = exported["bib_keys"][source["id"]]
                    article = reader.source_anchor(source)
                    self.assertIn(("#bib-" + key, BIB_LABEL[language]), page.article_bib_links[article])
        # Negative control: with no bibliography input, no bib section and
        # no article bib link may be invented in either page.
        _, files, _ = reader.prepare(self.obs, self.en, self.zh)
        exported = json.loads(files["native-reader.json"])
        self.assertEqual(exported["bib_keys"], {})
        for language in ("en", "zh-TW"):
            page = parse_page(files["reader." + language + ".html"].decode())
            self.assertEqual([item for item in page.ids if item.startswith("bib-")], [])
            self.assertEqual([link for links in page.article_bib_links.values() for link in links], [])

    def test_each_article_returns_to_contents_and_works_match_in_both_languages(self):
        _, files, _ = reader.prepare(self.obs, self.en, self.zh, self.bib)
        pages = {lang: parse_page(files["reader." + lang + ".html"].decode("utf-8"))
                 for lang in ("en", "zh-TW")}
        expected_works = {}
        for source in self.observations["sources"]:
            section = "work-" + reader.token(source["work_id"])
            expected_works.setdefault(section, set()).add(reader.source_anchor(source))
        expected_articles = set().union(*expected_works.values())
        for language, page in pages.items():
            with self.subTest(language=language):
                self.assertEqual(page.work_sections, expected_works)
                self.assertEqual(set(page.article_back_links), expected_articles)
                for article in expected_articles:
                    self.assertIn("#contents", page.article_back_links[article], article)
        for prefix in ("source-", "work-", "bib-", "claim-"):
            with self.subTest(prefix=prefix):
                english = {item for item in pages["en"].ids if item.startswith(prefix)}
                chinese = {item for item in pages["zh-TW"].ids if item.startswith(prefix)}
                self.assertTrue(english)
                self.assertEqual(english, chinese)
        # An extra empty work section must not disappear from the comparison.
        tampered = files["reader.en.html"].decode("utf-8").replace(
            "</main>", '<section id="work-extra"></section></main>', 1)
        self.assertNotEqual(parse_page(tampered).work_sections, expected_works)

    def test_explicit_pdf_link_is_in_header_nav_and_absent_without_attachment(self):
        pdf = self.root / "report.PDF"
        pdf.write_bytes(b"\x00\xffopaque supplied bytes\n")
        notes = self.root / "notes.txt"
        notes.write_bytes(b"unchanged UTF-8 text\n")
        _, files, _ = reader.prepare(self.obs, self.en, self.zh, self.bib, attachments=[pdf, notes])
        for language in ("en", "zh-TW"):
            with self.subTest(language=language, variant="bilingual"):
                page = parse_page(files["reader." + language + ".html"].decode())
                pdf_links = [(attrs, text) for attrs, text in page.header_nav_links
                             if attrs.get("href") == "report.PDF"]
                self.assertEqual(len(pdf_links), 1)
                attrs, text = pdf_links[0]
                self.assertIn("download", attrs)
                self.assertEqual(text, PDF_LABEL[language] + "report.PDF")
                txt_links = [(attrs, text) for attrs, text in page.header_nav_links
                             if attrs.get("href") == "notes.txt"]
                self.assertEqual(len(txt_links), 1)
                self.assertEqual(txt_links[0][1], "notes.txt")
        # English-only generation: the PDF link is on the only page made.
        _, files, _ = reader.prepare(self.obs, self.en, bibliography=self.bib, attachments=[pdf])
        self.assertNotIn("reader.zh-TW.html", files)
        page = parse_page(files["reader.en.html"].decode())
        self.assertEqual([text for attrs, text in page.header_nav_links if attrs.get("href") == "report.PDF"],
                         [PDF_LABEL["en"] + "report.PDF"])
        # PDF with no bibliography: the PDF link and the header-only
        # references.bib link must both still be in the header nav.
        _, files, _ = reader.prepare(self.obs, self.en, self.zh, attachments=[pdf])
        for language in ("en", "zh-TW"):
            page = parse_page(files["reader." + language + ".html"].decode())
            nav_hrefs = {attrs.get("href") for attrs, _ in page.header_nav_links}
            self.assertIn("report.PDF", nav_hrefs)
            self.assertIn("references.bib", nav_hrefs)
        # Negative control: with no attachment, no download anchor and no
        # PDF label may appear in either page.
        _, files, _ = reader.prepare(self.obs, self.en, self.zh, self.bib)
        for language in ("en", "zh-TW"):
            page = parse_page(files["reader." + language + ".html"].decode())
            self.assertEqual([attrs.get("href") for attrs, _ in page.all_links if "download" in attrs], [])
            self.assertNotIn(PDF_LABEL[language], files["reader." + language + ".html"].decode())

    def test_standalone_reader_outputs_match_two_selected_environments(self):
        project = self.root / "project"
        project.mkdir()
        for name, payload in [("observations.json", self.observations), ("content.en.json", self.content["en"]),
                              ("content.zh-TW.json", self.content["zh-TW"]), ("bibliography.json", self.bibliography)]:
            (project / name).write_bytes(reader.canonical(payload))
        empty_home = self.root / "empty-home"
        empty_home.mkdir()
        base_env = {"PATH": os.defpath, "HOME": str(empty_home), "USERPROFILE": str(empty_home),
                    "TMPDIR": str(self.root), "TEMP": str(self.root), "TMP": str(self.root)}
        if os.name == "nt" and "SystemRoot" in os.environ:
            # CPython process startup on Windows needs this non-secret OS path.
            base_env["SystemRoot"] = os.environ["SystemRoot"]
        junk_env = dict(base_env, ZOTERO_API_KEY="junk-not-a-key", OBSIDIAN_VAULT="/nonexistent",
                        NOTEBOOKLM_SESSION="junk", RESEARCH_HUB_API_KEY="junk",
                        RESEARCH_HUB_HOME="/nonexistent")
        outputs = {}
        for name, env in [("scrubbed", base_env), ("junk", junk_env)]:
            out = project / ("out-" + name)
            command = [sys.executable, "-I", "-S", "-B", str(SCRIPT),
                       "--observations", "observations.json", "--content-en", "content.en.json",
                       "--content-zh-TW", "content.zh-TW.json", "--bibliography", "bibliography.json",
                       "--output-dir", "out-" + name]
            result = subprocess.run(command, cwd=project, env=env, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertEqual(json.loads(result.stdout)["status"], "generated")
            self.assertTrue((out / "manifest.json").is_file())
            outputs[name] = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
        self.assertEqual(outputs["scrubbed"], outputs["junk"])
        self.assertEqual(set(outputs["scrubbed"]),
                         {"reader.en.html", "reader.zh-TW.html", "references.bib",
                          "native-reader.json", "manifest.json"})
        inputs, files, manifest = reader.prepare(self.obs, self.en, self.zh, self.bib)
        for name, data in files.items():
            self.assertEqual(outputs["scrubbed"][name], data)
        self.assertEqual(outputs["scrubbed"]["manifest.json"], reader.canonical(manifest))


if __name__ == "__main__":
    unittest.main()
