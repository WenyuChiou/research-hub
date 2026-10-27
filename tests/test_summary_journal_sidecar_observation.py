"""Synthetic disappearance at the journal metadata observation boundary."""
import inspect
from pathlib import Path

import pytest

from research_hub.summary_journal import SummaryJournal


@pytest.mark.parametrize('suffix', ['-journal', '-wal', '-shm'])
def test_sidecar_disappearing_at_metadata_observation_is_absent(tmp_path, monkeypatch, suffix):
    journal = SummaryJournal(tmp_path)
    journal.path.parent.mkdir()
    sidecar = Path(str(journal.path) + suffix)
    sidecar.write_bytes(b'synthetic transient sidecar')
    calls = []
    for method in ('stat', 'lstat'):
        original = getattr(Path, method)
        def observed(path, *args, _original=original, **kwargs):
            # Delete only at journal's final metadata call, not inside safe_path
            # or Path.exists; no mocked success or containment bypass.
            if path == sidecar and inspect.currentframe().f_back.f_code.co_name == '_check_path':
                calls.append(str(path))
                path.unlink()
            return _original(path, *args, **kwargs)
        monkeypatch.setattr(Path, method, observed)
    assert journal.list() == []
    assert calls == [str(sidecar)]
    assert not journal.path.exists()


@pytest.mark.parametrize('error', [PermissionError('synthetic denied'), OSError('synthetic I/O error')])
def test_metadata_errors_other_than_absence_are_not_suppressed(tmp_path, monkeypatch, error):
    journal = SummaryJournal(tmp_path)
    original = Path.lstat
    def observed(path, *args, **kwargs):
        if path == journal.path and inspect.currentframe().f_back.f_code.co_name == '_check_path':
            raise error
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', observed)
    with pytest.raises(type(error), match='synthetic'):
        journal.list()
    assert not journal.path.exists()


@pytest.mark.parametrize('replacement', ['symlink', 'hardlink', 'directory', 'reparse'])
def test_unsafe_replacement_at_final_observation_is_rejected(tmp_path, monkeypatch, replacement):
    from types import SimpleNamespace
    import stat
    from research_hub.summary_journal import JournalError
    journal = SummaryJournal(tmp_path)
    journal.path.parent.mkdir()
    sidecar = Path(str(journal.path) + '-journal')
    sidecar.write_bytes(b'synthetic')
    original = Path.lstat
    def observed(path, *args, **kwargs):
        if path == sidecar and inspect.currentframe().f_back.f_code.co_name == '_check_path':
            return SimpleNamespace(st_mode={'symlink': stat.S_IFLNK, 'directory': stat.S_IFDIR}.get(replacement, stat.S_IFREG), st_nlink=2 if replacement == 'hardlink' else 1, st_file_attributes=0x400 if replacement == 'reparse' else 0)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', observed)
    with pytest.raises(JournalError) as caught:
        journal.list()
    assert caught.value.code == 'unsafe_path'
    assert sidecar.read_bytes() == b'synthetic'
    assert not journal.path.exists()


@pytest.mark.parametrize('kind', ['symlink', 'hardlink'])
def test_actual_leaf_link_swap_after_containment_is_rejected(tmp_path, monkeypatch, kind):
    from research_hub.summary_journal import JournalError
    journal = SummaryJournal(tmp_path / 'selected')
    journal.path.parent.mkdir(parents=True)
    sidecar = Path(str(journal.path) + '-journal')
    sidecar.write_bytes(b'synthetic')
    outside = tmp_path / 'outside'
    outside.write_bytes(b'preserve outside')
    original = Path.lstat
    swapped = []
    def observed(path, *args, **kwargs):
        if path == sidecar and inspect.currentframe().f_back.f_code.co_name == '_check_path':
            path.unlink()
            try:
                if kind == 'symlink':
                    path.symlink_to(outside)
                else:
                    path.hardlink_to(outside)
            except OSError as exc:
                if kind == 'symlink' and getattr(exc, 'winerror', None) == 1314:
                    pytest.skip('Symlink privilege unavailable')
                raise
            swapped.append(kind)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', observed)
    with pytest.raises(JournalError) as caught:
        journal.list()
    assert caught.value.code == 'unsafe_path'
    assert swapped == [kind]
    assert outside.read_bytes() == b'preserve outside'
    assert not journal.path.exists()


def test_containment_disappearance_error_is_not_suppressed(tmp_path, monkeypatch):
    import research_hub.summary_journal as module
    journal = SummaryJournal(tmp_path)
    def unavailable(*args, **kwargs):
        raise FileNotFoundError('synthetic containment observation failed')
    monkeypatch.setattr(module, 'safe_path', unavailable)
    with pytest.raises(FileNotFoundError, match='containment observation'):
        journal.list()
