"""POSIX sidecar unlink observations: synthetic races, no provider I/O."""
import os
import inspect
from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

from research_hub.summary_journal import JournalError, SummaryJournal

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX unlink semantics only')


def setup_sidecar(tmp_path, suffix="-journal"):
    journal = SummaryJournal(tmp_path / 'selected')
    journal.path.parent.mkdir(parents=True)
    sidecar = Path(str(journal.path) + suffix)
    sidecar.write_bytes(b'synthetic')
    return journal, sidecar


def detached():
    return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=0, st_file_attributes=0)


@pytest.mark.parametrize('suffix', ['-journal', '-wal', '-shm'])
@pytest.mark.parametrize('replacement', ['missing', 'regular', 'symlink', 'hardlink', 'directory', 'persistent-zero', 'permission', 'io-error'])
def test_one_reobservation_validates_current_named_sidecar(tmp_path, monkeypatch, replacement, suffix):
    journal, sidecar = setup_sidecar(tmp_path, suffix)
    outside = tmp_path / 'outside'
    outside.write_bytes(b'preserve outside')
    original = Path.lstat
    observations = []
    def lstat(path, *args, **kwargs):
        if path != sidecar:
            return original(path, *args, **kwargs)
        observations.append(len(observations) + 1)
        if len(observations) == 1:
            sidecar.unlink()
            if replacement == 'regular':
                sidecar.write_bytes(b'replacement')
            elif replacement == 'symlink':
                sidecar.symlink_to(outside)
            elif replacement == 'hardlink':
                sidecar.hardlink_to(outside)
            elif replacement == 'directory':
                sidecar.mkdir()
            return detached()
        if replacement == 'persistent-zero':
            return detached()
        if replacement == 'permission':
            raise PermissionError('synthetic denied')
        if replacement == 'io-error':
            raise OSError('synthetic I/O error')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', lstat)
    if replacement in {'missing', 'regular'}:
        assert journal.list() == []
    elif replacement == 'permission':
        with pytest.raises(PermissionError, match='synthetic denied'):
            journal.list()
    elif replacement == 'io-error':
        with pytest.raises(OSError, match='synthetic I/O error'):
            journal.list()
    else:
        with pytest.raises(JournalError) as caught:
            journal.list()
        assert caught.value.code == 'unsafe_path'
    assert observations == [1, 2]
    assert outside.read_bytes() == b'preserve outside'
    assert not journal.path.exists()


def test_database_zero_is_never_reobserved_as_sidecar(tmp_path, monkeypatch):
    journal = SummaryJournal(tmp_path / 'selected')
    journal.path.parent.mkdir(parents=True)
    journal.path.write_bytes(b'synthetic')
    original = Path.lstat
    seen = []
    def lstat(path, *args, **kwargs):
        if path == journal.path and inspect.currentframe().f_back.f_code.co_name == '_check_path':
            seen.append(1)
            return detached()
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(JournalError) as caught:
        journal._check_path()
    assert caught.value.code == 'unsafe_path'
    assert seen == [1]


def test_reobservation_parent_validation_fails_closed(tmp_path, monkeypatch):
    import research_hub.summary_journal as module
    journal, sidecar = setup_sidecar(tmp_path)
    original_safe = module.safe_path
    original_lstat = Path.lstat
    seen = []
    def checked(root, path):
        if path == sidecar.parent:
            seen.append(1)
            if len(seen) == 2:
                raise PermissionError('parent denied')
        return original_safe(root, path)
    def lstat(path, *args, **kwargs):
        if path == sidecar:
            return detached()
        return original_lstat(path, *args, **kwargs)
    monkeypatch.setattr(module, 'safe_path', checked)
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(PermissionError, match='parent denied'):
        journal._check_path()
    assert seen == [1, 1]


def test_non_posix_zero_does_not_trigger_reobservation(tmp_path, monkeypatch):
    import research_hub.summary_journal as module
    journal, sidecar = setup_sidecar(tmp_path)
    original = Path.lstat
    observed = []
    def lstat(path, *args, **kwargs):
        if path == sidecar:
            observed.append(1)
            return detached()
        return original(path, *args, **kwargs)
    monkeypatch.setattr(module, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(JournalError) as caught:
        journal._check_path()
    assert caught.value.code == 'unsafe_path'
    assert observed == [1]


@pytest.mark.parametrize('when', ['initial', 'replacement'])
def test_reparse_metadata_is_rejected_even_with_zero(tmp_path, monkeypatch, when):
    journal, sidecar = setup_sidecar(tmp_path)
    original = Path.lstat
    observed = []
    def lstat(path, *args, **kwargs):
        if path == sidecar:
            observed.append(1)
            if when == 'initial' or len(observed) == 2:
                return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=0 if when == 'initial' else 1, st_file_attributes=0x400)
            return detached()
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(JournalError) as caught:
        journal._check_path()
    assert caught.value.code == 'unsafe_path'
    assert len(observed) == (1 if when == 'initial' else 2)


@pytest.mark.parametrize('kind', ['hardlink', 'symlink', 'directory', 'reparse'])
def test_initial_unsafe_metadata_never_reobserved(tmp_path, monkeypatch, kind):
    journal, sidecar = setup_sidecar(tmp_path)
    original = Path.lstat
    observed = []
    def lstat(path, *args, **kwargs):
        if path == sidecar:
            observed.append(1)
            return SimpleNamespace(st_mode={'symlink': stat.S_IFLNK, 'directory': stat.S_IFDIR}.get(kind, stat.S_IFREG),
                                   st_nlink=2 if kind == 'hardlink' else 1,
                                   st_file_attributes=0x400 if kind == 'reparse' else 0)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(JournalError) as caught:
        journal._check_path()
    assert caught.value.code == 'unsafe_path'
    assert observed == [1]


def test_reobservation_parent_workspace_error_remains_unsafe_path(tmp_path, monkeypatch):
    import research_hub.summary_journal as module
    from research_hub.workspace.core import WorkspaceError
    journal, sidecar = setup_sidecar(tmp_path)
    original_safe, original_lstat = module.safe_path, Path.lstat
    parent_calls = []
    def checked(root, path):
        if path == sidecar.parent:
            parent_calls.append(1)
            if len(parent_calls) == 2:
                raise WorkspaceError('synthetic containment refusal')
        return original_safe(root, path)
    def lstat(path, *args, **kwargs):
        return detached() if path == sidecar else original_lstat(path, *args, **kwargs)
    monkeypatch.setattr(module, 'safe_path', checked)
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(JournalError) as caught:
        journal._check_path()
    assert caught.value.code == 'unsafe_path'
    assert parent_calls == [1, 1]


def test_initialized_journal_read_survives_transient_sidecar(tmp_path, monkeypatch):
    from research_hub.summary_journal import scope_digest
    journal = SummaryJournal(tmp_path / 'selected')
    journal.root.mkdir()
    source = {'reference': 'synthetic:abstract', 'sha256': 'a' * 64, 'coverage': 'abstract'}
    targets = {'local': 'raw/cluster/paper.md'}
    authorization = {'kind': 'legacy_cli_explicit_apply', 'reference': 'synthetic-invocation',
                     'scope_sha256': scope_digest(source, targets)}
    before = journal.reserve('synthetic-operation', source, targets, authorization)
    sidecar = Path(str(journal.path) + '-journal')
    sidecar.write_bytes(b'transient synthetic sidecar')
    original = Path.lstat
    observed = []
    def lstat(path, *args, **kwargs):
        if path == sidecar and inspect.currentframe().f_back.f_code.co_name == '_check_path':
            observed.append(1)
            if len(observed) == 1:
                sidecar.unlink()
                return detached()
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', lstat)
    after = journal.get('synthetic-operation')
    assert after == before
    assert observed == [1, 1]
