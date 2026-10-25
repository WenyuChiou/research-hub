"""Pure Windows path/stdlib models: no native Windows filesystem acceptance."""
from pathlib import PurePosixPath, PureWindowsPath
import pytest
from research_hub.summary_journal import _validation_path, JournalError, SummaryJournal

@pytest.mark.parametrize('root', [r'D:\selected',r'\\server\share\selected'])
def test_same_approved_root_and_sidecar_use_stable_namespace(root):
    root=PureWindowsPath(root);child=root/'.research_hub/summary-operations.sqlite3-journal'
    extended=_validation_path(child)
    assert extended==_validation_path(extended)
    assert extended.is_relative_to(_validation_path(root))
    assert not _validation_path(root.parent/'outside/file').is_relative_to(_validation_path(root))
    assert not _validation_path(PureWindowsPath('E:/other/file')).is_relative_to(_validation_path(root))

@pytest.mark.parametrize('value',[r'D:relative',r'D:\selected\..\outside',r'\\?\GLOBALROOT\Device\HarddiskVolume1',r'\\.\C:\selected',r'\\?\Volume{abc}\selected'])
def test_ambiguous_or_device_namespaces_are_not_reinterpreted(value):
    with pytest.raises(JournalError):_validation_path(PureWindowsPath(value))

def test_posix_validation_and_database_io_paths_unchanged(tmp_path):
    posix=PurePosixPath("/selected")
    assert _validation_path(posix) is posix
    journal=SummaryJournal(tmp_path)
    assert journal.path==tmp_path.resolve()/'.research_hub/summary-operations.sqlite3'

@pytest.mark.parametrize('root',[r'D:\selected',r'\\server\share\selected'])
def test_modeled_extended_resolution_keeps_approved_containment(root):
    # The separate evidence probe executes CPython3.12's exact two-OS-call
    # branch. This portable CI control models its retained-prefix outcome.
    root=PureWindowsPath(root);child=root/'.research_hub/summary-operations.sqlite3-journal'
    resolved=_validation_path(child)
    assert not resolved.is_relative_to(root)
    assert resolved.is_relative_to(_validation_path(root))
    assert not _validation_path(root.parent/'outside/file').is_relative_to(_validation_path(root))

@pytest.mark.parametrize('suffix',['-journal','-wal','-shm'])
def test_known_sidecar_links_are_still_rejected(tmp_path,suffix):
    from pathlib import Path
    journal=SummaryJournal(tmp_path/'selected');journal.path.parent.mkdir(parents=True)
    outside=tmp_path/'outside';outside.write_bytes(b'untouched')
    sidecar=Path(str(journal.path)+suffix)
    try:sidecar.symlink_to(outside)
    except OSError as exc:
        if getattr(exc,'winerror',None)==1314:pytest.skip('Symlink privilege unavailable')
        raise
    with pytest.raises(JournalError) as error:journal.list()
    assert error.value.code=='unsafe_path' and outside.read_bytes()==b'untouched'
    assert not journal.path.exists()

def test_known_sidecar_reparse_is_still_rejected(tmp_path,monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    import stat
    journal=SummaryJournal(tmp_path/'selected');journal.path.parent.mkdir(parents=True)
    sidecar=Path(str(journal.path)+'-journal');sidecar.write_bytes(b'untouched')
    original=Path.lstat
    def lstat(path,*args,**kwargs):
        if str(path).removeprefix('\\\\?\\')==str(sidecar):
            return SimpleNamespace(st_mode=stat.S_IFREG,st_file_attributes=0x400)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',lstat)
    with pytest.raises(JournalError) as error:journal.list()
    assert error.value.code=='unsafe_path' and sidecar.read_bytes()==b'untouched'
    assert not journal.path.exists()
