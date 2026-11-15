"""Portable fixture-cleanup contracts, not native Windows acceptance."""
from types import SimpleNamespace
import pytest
from tests import test_windows_native_summary_read as native_tests

MOUNT_POINT = 0xA0000003


class LegacyPath:
    """Python 3.10/3.11 shape: no Path.is_junction method."""
    def __init__(self, *, tag=0, error=None):
        self.tag, self.error, self.reads = tag, error, 0
    def lstat(self):
        self.reads += 1
        if self.error is not None:
            raise self.error
        return SimpleNamespace(st_reparse_tag=self.tag)


@pytest.fixture
def removals(monkeypatch):
    calls = []
    # The constant is Windows-only, even in CPython 3.10.
    monkeypatch.setattr(native_tests, 'stat', SimpleNamespace(IO_REPARSE_TAG_MOUNT_POINT=MOUNT_POINT))
    monkeypatch.setattr(native_tests, 'os', SimpleNamespace(rmdir=calls.append))
    return calls


def test_legacy_path_removes_only_owned_junction(removals):
    path = LegacyPath(tag=MOUNT_POINT)
    assert not hasattr(path, 'is_junction')
    native_tests._remove_owned_junction(path)
    assert path.reads == 1 and removals == [path]


@pytest.mark.parametrize('tag', [0, 0xA000000C, 0x9000001A])
def test_other_entries_are_never_removed(removals, tag):
    path = LegacyPath(tag=tag)
    native_tests._remove_owned_junction(path)
    assert path.reads == 1 and removals == []


def test_absent_owned_link_needs_no_cleanup(removals):
    path = LegacyPath(error=FileNotFoundError('synthetic absent link'))
    native_tests._remove_owned_junction(path)
    assert path.reads == 1 and removals == []


@pytest.mark.parametrize('error', [PermissionError('synthetic denied metadata'), OSError('synthetic metadata failure')])
def test_other_metadata_errors_are_not_suppressed(removals, error):
    with pytest.raises(type(error), match=str(error)):
        native_tests._remove_owned_junction(LegacyPath(error=error))
    assert removals == []


def test_remove_failure_is_not_suppressed(removals, monkeypatch):
    path = LegacyPath(tag=MOUNT_POINT)
    def fail(actual):
        assert actual is path
        raise PermissionError('synthetic removal denied')
    monkeypatch.setattr(native_tests.os, 'rmdir', fail)
    with pytest.raises(PermissionError, match='synthetic removal denied'):
        native_tests._remove_owned_junction(path)
