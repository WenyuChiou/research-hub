"""Offline synthetic acceptance for the optional standard-library skill renderer."""
import contextlib
import copy
import errno
import hashlib
from html.parser import HTMLParser
import importlib.util
import io
import json
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
                elif self.in_header and tag == "nav" and dict(attrs).get("aria-label") == "Exports":
                    self.in_exports = True
                elif self.in_header and tag == "a" and self.in_exports:
                    self.anchor = [dict(attrs).get("href"), []]
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
                expected_links = [("reader." + lang + ".html", lang) for lang in expected_languages]
                for language in expected_languages:
                    with self.subTest(language=language):
                        header = HeaderNavigation()
                        header.feed((output / ("reader." + language + ".html")).read_text(encoding="utf-8"))
                        header.close()
                        language_links = [(href, label) for href, label in header.links if href and href.startswith("reader.") and href.endswith(".html")]
                        self.assertEqual(language_links, expected_links)
                        for href, _ in language_links:
                            self.assertTrue((output / href).is_file())
                        if not both:
                            self.assertFalse((output / "reader.zh-TW.html").exists())
                            self.assertIn("Languages not supplied: zh-TW", header.paragraphs)

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
        self.assertIn(r"\{Author\}", bib)
        key = reader.bib_key(self.observations["sources"][2])
        entry = bib.split("@misc{" + key + ",", 1)[1].split("@misc{", 1)[0]
        self.assertNotIn("year =", entry)
        self.assertNotIn("author =", entry)

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
