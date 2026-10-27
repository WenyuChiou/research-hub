"""Standard-library checks for observation, rejection and privacy invariants."""
from contextlib import contextmanager, ExitStack, redirect_stdout
import io
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from _journal_boundary_diagnostics import JournalBoundaryDiagnostics, _native_metadata


class BoundaryDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.database = Path(self.temporary.name) / 'summary-operations.sqlite3'
        self.database.write_bytes(b'synthetic')
        self.rejection = ValueError('original security rejection')
        self.info = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_nlink=1,
                                    st_ino=123, st_dev=456, st_file_attributes=0x20, st_size=9)
        rejection, database = self.rejection, self.database

        class Journal:
            def _check_path(owner):
                info = database.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_file_attributes & 0x400:
                    raise rejection
                return info

            @contextmanager
            def _db(owner, *, write=False):
                owner._check_path()
                yield owner
                if write:
                    owner._commit(owner)

            def _commit(owner, connection):
                return owner._check_path()

        self.Journal = Journal

    def replace(self, owner, name, value):
        self.stack.enter_context(patch.object(owner, name, value))

    def install(self, *, native=lambda path: {'unit_stub': True}, lstat=None):
        original = Path.lstat
        def observed(path, *args, **kwargs):
            if path == self.database:
                return lstat() if lstat else self.info
            return original(path, *args, **kwargs)
        self.replace(Path, 'lstat', observed)
        return JournalBoundaryDiagnostics(self.replace, self.Journal, self.database, native=native)

    def test_good_result_object_and_connection_are_unchanged(self):
        trace = self.install(native=lambda path: self.fail('native query on valid result'))
        journal = self.Journal()
        self.assertIs(journal._check_path(), self.info)
        with journal._db(write=True) as connection:
            self.assertIs(connection, journal)
        self.assertEqual(trace.events, [])
        self.assertEqual(trace._active, {})

    def test_zero_links_hardlink_and_reparse_are_still_rejected(self):
        trace = self.install()
        for links, attributes in ((0, 0x20), (2, 0x20), (1, 0x420)):
            self.info.st_nlink, self.info.st_file_attributes = links, attributes
            with self.assertRaises(ValueError) as caught:
                self.Journal()._check_path()
            self.assertIs(caught.exception, self.rejection)
        self.assertEqual(len(trace.events), 3)
        self.assertEqual(trace.events[0]['stat']['st_nlink'], 0)

    def test_original_lstat_error_is_not_masked_or_dumped(self):
        error = PermissionError(13, 'DO_NOT_DUMP_PRIVATE_PATH_OR_CONTENT')
        error.winerror = 32
        def fail():
            raise error
        trace = self.install(lstat=fail)
        with self.assertRaises(PermissionError) as caught:
            self.Journal()._check_path()
        self.assertIs(caught.exception, error)
        self.assertEqual(trace.events[0]['stat_error']['winerror'], 32)
        self.assertNotIn('DO_NOT_DUMP', str(trace.events))

    def test_normal_disappearance_is_passed_through_without_extra_observation(self):
        error = FileNotFoundError(2, 'private path')
        def fail():
            raise error
        trace = self.install(lstat=fail)
        with self.assertRaises(FileNotFoundError) as caught:
            self.Journal()._check_path()
        self.assertIs(caught.exception, error)
        self.assertEqual(trace.events, [])

    def test_native_error_cannot_mask_original_rejection_and_output_is_bounded(self):
        calls = []
        def fail_native(path):
            calls.append(True)
            raise RuntimeError('DO_NOT_DUMP_PRIVATE_PATH_OR_CONTENT')
        trace = self.install(native=fail_native)
        self.info.st_nlink = 0
        for _ in range(6):
            with self.assertRaises(ValueError) as caught:
                self.Journal()._check_path()
            self.assertIs(caught.exception, self.rejection)
        output = io.StringIO()
        with redirect_stdout(output):
            trace.emit()
        text = output.getvalue()
        self.assertEqual((len(trace.events), trace.dropped, len(calls)), (4, 2, 4))
        self.assertNotIn('DO_NOT_DUMP', text)
        self.assertNotIn(str(self.database), text)
        self.assertLess(len(text), 12000)

    def test_commit_phase_and_original_error_are_preserved(self):
        calls = []
        def changing():
            calls.append(True)
            self.info.st_nlink = 1 if len(calls) == 1 else 0
            return self.info
        trace = self.install(lstat=changing)
        with self.assertRaises(ValueError) as caught:
            with self.Journal()._db(write=True):
                pass
        self.assertIs(caught.exception, self.rejection)
        self.assertEqual(trace.events[0]['active_before_native'][0]['phase'], 'commit')
        self.assertEqual(trace._active, {})

    def test_lstat_outside_original_check_is_not_observed(self):
        trace = self.install()
        self.info.st_nlink = 0
        self.assertIs(self.database.lstat(), self.info)
        self.assertEqual(trace.events, [])

    @unittest.skipUnless(os.name == 'nt', 'Windows metadata API')
    def test_native_metadata_of_closed_synthetic_file(self):
        rows = _native_metadata(self.database)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row['open_error'], 0)
            self.assertEqual((row['links'], row['standard_links']), (1, 1))
            self.assertFalse(row['delete_pending'])


if __name__ == '__main__':
    unittest.main()
