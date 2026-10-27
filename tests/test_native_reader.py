"""Offline synthetic acceptance for the optional standard-library skill renderer."""
import contextlib
import copy
import hashlib
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

    def test_check_only_writes_nothing(self):
        before = self.snapshot(self.root)
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = reader.main(["--observations", str(self.obs), "--content-en", str(self.en), "--bibliography", str(self.bib), "--check-only"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(stdout.getvalue())["writes"])
        self.assertEqual(self.snapshot(self.root), before)

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

    def test_packaged_script_is_the_exact_source_mirror(self):
        mirror = ROOT / "src/research_hub/skills_data/research-hub/scripts/render_native_reader.py"
        self.assertEqual(SCRIPT.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
