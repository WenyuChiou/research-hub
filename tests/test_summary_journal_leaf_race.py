"""Synthetic leaf disappearance during old split containment observations."""
from pathlib import Path
import inspect
import pytest
from research_hub.summary_journal import SummaryJournal

@pytest.mark.parametrize('suffix', ['-journal', '-wal', '-shm'])
def test_sqlite_leaf_vanishes_after_containment_exists(tmp_path, monkeypatch, suffix):
    journal = SummaryJournal(tmp_path)
    journal.path.parent.mkdir()
    leaf = Path(str(journal.path) + suffix)
    leaf.write_bytes(b'synthetic')
    original = Path.exists
    removed = []
    def exists(path):
        result = original(path)
        if path == leaf and result and inspect.currentframe().f_back.f_code.co_name == 'safe_path':
            path.unlink()
            removed.append(str(path))
        return result
    monkeypatch.setattr(Path, 'exists', exists)
    assert journal.list() == []
    # A one-observation implementation need not call exists on the leaf.
    assert not journal.path.exists()

@pytest.mark.parametrize('links', [0, 2])
def test_unknown_or_multiple_leaf_links_remain_fail_closed(tmp_path, monkeypatch, links):
    from types import SimpleNamespace
    import stat
    from research_hub.summary_journal import JournalError
    journal = SummaryJournal(tmp_path)
    journal.path.parent.mkdir()
    leaf = Path(str(journal.path) + '-journal')
    leaf.write_bytes(b'synthetic')
    original = Path.lstat
    def observed(path, *args, **kwargs):
        if path == leaf:
            return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=links, st_file_attributes=0)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', observed)
    with pytest.raises(JournalError) as caught:
        journal.list()
    assert caught.value.code == 'unsafe_path'
    assert f'links={links}' in str(caught.value)
    assert 'leaf=-journal' in str(caught.value)
    assert 'mode=0x8000' in str(caught.value) and 'attributes=0x0' in str(caught.value)
    assert str(tmp_path) not in str(caught.value)
    assert not journal.path.exists()


def test_persistent_database_retains_full_path_validation(tmp_path, monkeypatch):
    import research_hub.summary_journal as module
    journal = SummaryJournal(tmp_path)
    original = module.safe_path
    seen = []
    def checked(root, path):
        seen.append(path)
        return original(root, path)
    monkeypatch.setattr(module, 'safe_path', checked)
    assert journal.list() == []
    assert journal.path in seen
    assert all(path in (journal.path, journal.path.parent) for path in seen)


def test_sidecar_parent_symlink_still_fails_without_database_write(tmp_path):
    from research_hub.summary_journal import JournalError
    selected = tmp_path / 'selected'
    selected.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    journal = SummaryJournal(selected)
    try:
        journal.path.parent.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, 'winerror', None) == 1314:
            pytest.skip('Symlink privilege unavailable')
        raise
    with pytest.raises(JournalError) as caught:
        journal.list()
    assert caught.value.code == 'unsafe_path'
    assert list(outside.iterdir()) == []
