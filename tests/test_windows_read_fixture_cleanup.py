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


def _exercise_before_child(tmp_path, monkeypatch, outcome):
    """Exercise fixture state transitions without claiming Windows kernel behavior."""
    selected = tmp_path / 'selected'
    moved = tmp_path / 'old'
    outside = tmp_path / 'outside'
    calls = {'rename': 0, 'junction': 0, 'removed': 0}
    path_type = type(tmp_path)
    original_rename = path_type.rename

    def rename(path, target):
        if path == selected:
            calls['rename'] += 1
            if outcome == 'rename_blocked':
                raise PermissionError('synthetic pinned-directory rename refusal')
        return original_rename(path, target)

    def junction(path, target):
        assert path == selected and target == outside
        calls['junction'] += 1
        # A placeholder for state testing only; this is not an actual reparse point.
        path.mkdir()

    def cleanup(path):
        if calls['junction']:
            assert path == selected
            path.rmdir()
            calls['removed'] += 1

    def original_child(native, handle, name, directory):
        if outcome == 'unsafe_return':
            return 1
        raise OSError('synthetic no-follow read refusal')

    def read(root, relative, limit):
        assert root == tmp_path and relative == 'selected/input.txt'
        if outcome == 'premature_error':
            raise OSError('synthetic unrelated earlier failure')
        try:
            native_tests.r.NativeRead.child(object(), None, 'selected', True)
        except OSError:
            if outcome == 'outside_mutated':
                (outside / 'input.txt').write_bytes(b'changed')
            raise
        return b'other synthetic scope'

    with monkeypatch.context() as patch:
        patch.setattr(path_type, 'rename', rename)
        patch.setattr(native_tests, 'junction', junction)
        patch.setattr(native_tests, '_remove_owned_junction', cleanup)
        patch.setattr(native_tests.r.NativeRead, 'child', original_child)
        patch.setattr(native_tests.r, 'read_bytes', read)
        native_tests.test_reparse_ancestor_never_returns_other_bytes(
            tmp_path, patch, 'before_child')
    return calls


@pytest.mark.parametrize('outcome', ['rename_blocked', 'junction_installed'])
def test_before_child_accepts_only_observed_safe_outcomes(tmp_path, monkeypatch, outcome):
    calls = _exercise_before_child(tmp_path, monkeypatch, outcome)
    assert calls['rename'] == 1
    if outcome == 'rename_blocked':
        assert calls == {'rename': 1, 'junction': 0, 'removed': 0}
        assert (tmp_path / 'selected/input.txt').read_bytes() == b'original'
        assert not (tmp_path / 'old').exists()
    else:
        assert calls == {'rename': 1, 'junction': 1, 'removed': 1}
        assert not (tmp_path / 'selected').exists()
        assert (tmp_path / 'old/input.txt').read_bytes() == b'original'


@pytest.mark.parametrize('outcome', ['premature_error', 'outside_mutated'])
def test_before_child_rejects_unexercised_or_mutated_scope(tmp_path, monkeypatch, outcome):
    with pytest.raises(AssertionError):
        _exercise_before_child(tmp_path, monkeypatch, outcome)


def test_before_child_still_requires_read_refusal(tmp_path, monkeypatch):
    with pytest.raises(pytest.fail.Exception, match='DID NOT RAISE'):
        _exercise_before_child(tmp_path, monkeypatch, 'unsafe_return')
