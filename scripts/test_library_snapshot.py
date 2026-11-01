import json
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from library_snapshot import frontmatter_only, snapshot, main


class LibrarySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / ".research_hub").mkdir()
        (self.root / ".research_hub" / "clusters.yaml").write_text(
            "clusters:\n  selected:\n    name: Selected collection\n    status: active\n", encoding="utf-8")
        self.folder = self.root / "raw" / "selected"
        self.folder.mkdir(parents=True)

    def test_only_frontmatter_is_decoded_and_sources_remain_notes(self):
        path = self.folder / "one.md"
        path.write_bytes(b"---\ntitle: Synthetic source\nyear: 2024\ndoi: 10.1000/example\nlabels: [core]\n---\nBODY MUST NOT BE READ\xff")
        before = path.read_bytes()
        item = snapshot(self.root, ["selected"])
        self.assertEqual(len(item["notes"]), 1)
        self.assertEqual(item["notes"][0]["kind"], "library-note")
        self.assertEqual(item["notes"][0]["data"]["doi"], "10.1000/example")
        self.assertNotIn("BODY", json.dumps(item))
        self.assertFalse(item["body_read"])
        self.assertEqual(path.read_bytes(), before)

    def test_unselected_folders_are_not_read(self):
        other = self.root / "raw" / "unselected"
        other.mkdir()
        (other / "private.md").write_bytes(b"\xff\xff")
        (self.folder / "one.md").write_text("---\ntitle: Allowed\n---\n", encoding="utf-8")
        self.assertEqual(len(snapshot(self.root, ["selected"])["notes"]), 1)

    def test_duplicate_or_oversized_metadata_is_unknown_not_dropped(self):
        (self.folder / "duplicate.md").write_text("---\ntitle: First\ntitle: Second\n---\n", encoding="utf-8")
        (self.folder / "large.md").write_text("---\ntitle: " + "x" * 140000, encoding="utf-8")
        notes = snapshot(self.root, ["selected"])["notes"]
        self.assertEqual(len(notes), 2)
        self.assertTrue(all(note["data"]["metadata_status"] == "unavailable" for note in notes))
        self.assertTrue(all("abstract" not in note["data"] for note in notes))

    def test_selection_cannot_escape_or_silently_use_missing_collection(self):
        for slug in ["../outside", "unselected"]:
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                snapshot(self.root, [slug])

    def test_multiline_saved_abstract_is_metadata_not_body(self):
        path = self.folder / "one.md"
        path.write_text("---\ntitle: Synthetic\nabstract: |\n  Saved abstract line\n---\nUnselected body", encoding="utf-8")
        fm, meta = frontmatter_only(path)
        self.assertEqual(meta["abstract"].strip(), "Saved abstract line")
        self.assertNotIn("Unselected body", fm)

    def test_windows_reparse_component_is_rejected_before_note_read(self):
        (self.folder / "one.md").write_text("---\ntitle: Synthetic\n---\n", encoding="utf-8")
        original = Path.lstat
        def attributes(path, *args, **kwargs):
            return SimpleNamespace(st_mode=original(path).st_mode, st_file_attributes=0x400, st_reparse_tag=0xA0000003) if path == self.folder else original(path, *args, **kwargs)
        with patch.object(Path, "lstat", autospec=True, side_effect=attributes), self.assertRaisesRegex(ValueError, "Reparse"):
            snapshot(self.root, ["selected"])

    def test_reader_stops_at_frontmatter_boundary_without_buffering(self):
        path = self.folder / "boundary.md"
        prefix = b"---\ntitle: Synthetic\n---\n"
        path.write_bytes(prefix + b"PRIVATE BODY")
        positions = []
        class RecordingStream(io.BytesIO):
            def __exit__(self, *args):
                positions.append(self.tell())
                return super().__exit__(*args)
        stream = RecordingStream(path.read_bytes())
        with patch("library_snapshot.os.fdopen", return_value=stream) as opened:
            frontmatter_only(path)
        self.assertEqual(positions, [len(prefix)])
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(opened.call_args.args[1:], ("rb",))
        self.assertEqual(opened.call_args.kwargs, {"buffering": 0, "closefd": False})
        with self.assertRaises(OSError):
            os.fstat(opened.call_args.args[0])

    def test_registry_folder_binding_is_used_instead_of_slug(self):
        registry = self.root / ".research_hub" / "clusters.yaml"
        registry.write_text("clusters:\n  selected:\n    name: Selected collection\n    obsidian_subfolder: bound-folder\n    status: active\n", encoding="utf-8")
        bound = self.root / "raw" / "bound-folder"
        bound.mkdir()
        (bound / "right.md").write_text("---\ntitle: Bound note\n---\n", encoding="utf-8")
        (self.folder / "wrong.md").write_text("---\ntitle: Unselected note\n---\n", encoding="utf-8")
        notes = snapshot(self.root, ["selected"])["notes"]
        self.assertEqual([note["data"]["title"] for note in notes], ["Bound note"])
        self.assertEqual(notes[0]["data"]["note_path"], "raw/bound-folder/right.md")

    def test_registry_binding_escape_rejects_before_note_read(self):
        (self.root / "outside").mkdir()
        registry = self.root / ".research_hub" / "clusters.yaml"
        registry.write_text("clusters:\n  selected:\n    name: Selected collection\n    obsidian_subfolder: ../outside\n    status: active\n", encoding="utf-8")
        with patch("library_snapshot.frontmatter_only", side_effect=AssertionError("No note read allowed")), self.assertRaises(ValueError):
            snapshot(self.root, ["selected"])

    def test_duplicate_selected_folder_bindings_reject_ambiguous_export(self):
        registry = self.root / ".research_hub" / "clusters.yaml"
        registry.write_text("clusters:\n  selected:\n    name: First\n    obsidian_subfolder: selected\n  alias:\n    name: Second\n    obsidian_subfolder: selected\n", encoding="utf-8")
        (self.folder / "one.md").write_text("---\ntitle: Synthetic\n---\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "same folder"):
            snapshot(self.root, ["selected", "alias"])

    def test_hardlinked_output_replaces_link_without_changing_vault_note(self):
        (self.folder / "one.md").write_text("---\ntitle: Synthetic selected note\n---\n", encoding="utf-8")
        unselected = self.root / "raw" / "unselected"
        unselected.mkdir()
        note = unselected / "one.md"
        original = b"---\ntitle: Synthetic preserved note\n---\nPRIVATE SYNTHETIC BODY\n"
        note.write_bytes(original)
        with tempfile.TemporaryDirectory() as destination:
            output = Path(destination) / "snapshot.json"
            os.link(note, output)
            with patch("sys.argv", ["library_snapshot", "--vault", str(self.root), "--collection", "selected", "--output", str(output)]):
                self.assertEqual(main(), 0)
            self.assertEqual(note.read_bytes(), original)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["notes"][0]["data"]["title"], "Synthetic selected note")
            self.assertNotEqual(note.stat().st_ino, output.stat().st_ino)

    def test_output_aliasing_selected_note_rejects_without_changing_either_link(self):
        note = self.folder / "one.md"
        original = b"---\ntitle: Synthetic preserved note\n---\n"
        note.write_bytes(original)
        with tempfile.TemporaryDirectory() as destination:
            output = Path(destination) / "snapshot.json"
            os.link(note, output)
            with patch("sys.argv", ["library_snapshot", "--vault", str(self.root), "--collection", "selected", "--output", str(output)]):
                self.assertEqual(main(), 1)
            self.assertEqual(note.read_bytes(), original)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(note.stat().st_ino, output.stat().st_ino)

    def test_failed_publication_keeps_destination_and_removes_owned_temp(self):
        with tempfile.TemporaryDirectory() as destination:
            output = Path(destination) / "snapshot.json"
            original = b"previous synthetic snapshot"
            output.write_bytes(original)
            with patch("sys.argv", ["library_snapshot", "--vault", str(self.root), "--collection", "selected", "--output", str(output)]), patch("os.replace", side_effect=OSError("Synthetic publication failure")):
                self.assertEqual(main(), 1)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual([p.name for p in Path(destination).iterdir()], ["snapshot.json"])


if __name__ == "__main__":
    unittest.main()
