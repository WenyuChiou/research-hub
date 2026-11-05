"""Deterministic process-local scheduling models, not native Windows acceptance."""
import gc
import sqlite3
import stat
import threading
import weakref
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from research_hub import summary_journal as module
from research_hub.summary_journal import JournalError, SummaryJournal, scope_digest


_WAIT = 3


def _reserve(journal, operation='operation'):
    source = {'reference': 'synthetic:abstract', 'sha256': 'a' * 64, 'coverage': 'abstract'}
    targets = {'zotero': 'synthetic:parent:summary'}
    authorization = {'kind': 'legacy_cli_explicit_apply', 'reference': 'synthetic',
                     'scope_sha256': scope_digest(source, targets)}
    return journal.reserve(operation, source, targets, authorization)


def _thread(action):
    errors = []
    def run():
        try:
            action()
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, errors


def _join(thread):
    thread.join(_WAIT)
    assert not thread.is_alive(), 'synthetic journal worker did not terminate'


class _ContentionProbe:
    """Signal demonstrated lock contention, not merely thread start/scheduling."""
    def __init__(self, lock, decision, blocked):
        self.lock, self.decision, self.blocked = lock, decision, blocked

    def acquire(self, **kwargs):
        if self.lock.acquire(blocking=False):
            return True
        self.blocked.set()
        self.decision.set()
        return self.lock.acquire(**kwargs)

    def release(self):
        self.lock.release()


@pytest.mark.parametrize('phase', ['commit', 'close', 'rollback_close'])
@pytest.mark.parametrize('operation', ['get', 'list', 'conflicts', 'recover', 'lookup'])
def test_second_instance_guard_waits_for_entire_connection_lifetime(tmp_path, monkeypatch, phase, operation):
    writer, reader = SummaryJournal(tmp_path), SummaryJournal(tmp_path)
    _reserve(writer)
    window, decision, blocked = threading.Event(), threading.Event(), threading.Event()
    observations = []
    connect, commit, lstat = sqlite3.connect, SummaryJournal._commit, Path.lstat
    writer_id = []

    def pause():
        window.set()
        assert decision.wait(_WAIT), 'neither blocked acquisition nor unsafe guard observation occurred'

    def controlled_commit(journal, db):
        if threading.get_ident() == writer_id[0]:
            if phase == 'commit':
                pause()
            if phase == 'rollback_close':
                raise sqlite3.OperationalError('synthetic rollback')
        return commit(journal, db)

    class Connection:
        def __init__(self, db):
            object.__setattr__(self, 'db', db)
        def __getattr__(self, name):
            return getattr(self.db, name)
        def __setattr__(self, name, value):
            setattr(self.db, name, value)
        def close(self):
            try:
                if threading.get_ident() == writer_id[0] and phase != 'commit':
                    pause()
                self.db.close()
            finally:
                if threading.get_ident() == writer_id[0]:
                    window.clear()

    def observed_lstat(path, *args, **kwargs):
        if (str(path) == str(writer.path) + '-journal' and window.is_set()
                and threading.get_ident() != writer_id[0]):
            observations.append('zero-link-during-' + phase)
            decision.set()
            # Exercise the actual unchanged non-POSIX guard, not a substitute.
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_nlink=0, st_file_attributes=0x20)
        return lstat(path, *args, **kwargs)

    # Works on the exact old baseline as well: no candidate-only import or
    # missing-helper failure can account for the negative control.
    if hasattr(reader, '_lock'):
        reader._lock = _ContentionProbe(reader._lock, decision, blocked)
    monkeypatch.setattr(module, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(module.sqlite3, 'connect', lambda *a, **kw: Connection(connect(*a, **kw)))
    monkeypatch.setattr(SummaryJournal, '_commit', controlled_commit)
    monkeypatch.setattr(Path, 'lstat', observed_lstat)

    def write():
        writer_id.append(threading.get_ident())
        writer.observe('operation', 'zotero', 'not_observed')

    calls = {'get': lambda: reader.get('operation'), 'list': reader.list,
             'conflicts': lambda: reader.conflicts({'zotero': 'synthetic:parent:summary'}),
             'recover': lambda: reader.recover('operation'),
             'lookup': lambda: reader.lookup_for_apply('operation')}
    wt, writer_errors = _thread(write)
    rt = None
    try:
        assert window.wait(_WAIT), 'writer did not enter the controlled lifecycle window'
        rt, reader_errors = _thread(calls[operation])
        _join(wt)
        _join(rt)
        assert reader_errors == [], [(type(exc).__name__, str(exc)) for exc in reader_errors]
        assert observations == [], 'guard observed another worker before connection close'
        assert blocked.is_set(), 'test did not demonstrate lock contention'
        if phase == 'rollback_close':
            assert len(writer_errors) == 1 and writer_errors[0].code == 'storage_unavailable'
        else:
            assert writer_errors == []
    finally:
        decision.set()
        _join(wt)
        if rt is not None:
            _join(rt)


def test_first_use_initialization_is_inside_shared_lock(tmp_path, monkeypatch):
    first, second = SummaryJournal(tmp_path), SummaryJournal(tmp_path)
    entered, decision, blocked = threading.Event(), threading.Event(), threading.Event()
    original = SummaryJournal._commit
    def commit(journal, db):
        if journal is first:
            entered.set()
            assert decision.wait(_WAIT)
        return original(journal, db)
    second._lock = _ContentionProbe(second._lock, decision, blocked)
    monkeypatch.setattr(SummaryJournal, '_commit', commit)
    a, ae = _thread(lambda: first.lookup_for_apply('new'))
    b = None
    try:
        assert entered.wait(_WAIT)
        b, be = _thread(lambda: second.lookup_for_apply('new'))
        _join(a); _join(b)
        assert ae == be == [] and blocked.is_set()
        assert second.list() == []
    finally:
        decision.set(); _join(a)
        if b is not None: _join(b)


def test_different_roots_progress_while_one_commit_is_paused(tmp_path, monkeypatch):
    first, second = SummaryJournal(tmp_path / 'a'), SummaryJournal(tmp_path / 'b')
    entered, release = threading.Event(), threading.Event()
    original = SummaryJournal._commit
    def commit(journal, db):
        if journal is first:
            entered.set()
            assert release.wait(_WAIT)
        return original(journal, db)
    monkeypatch.setattr(SummaryJournal, '_commit', commit)
    thread, errors = _thread(lambda: first.lookup_for_apply('new'))
    try:
        assert entered.wait(_WAIT)
        assert second.lookup_for_apply('new') is None
        assert not errors and thread.is_alive()
    finally:
        release.set(); _join(thread)
    assert errors == []


@pytest.mark.parametrize('method', ['list', 'conflicts'])
def test_empty_public_reads_do_not_initialize_and_reenter(tmp_path, method):
    journal = SummaryJournal(tmp_path)
    with journal._serialized():
        result = journal.list() if method == 'list' else journal.conflicts({'zotero': 'synthetic'})
    assert result == []
    assert not journal.path.parent.exists()


def test_timeout_never_reaches_guard_or_changes_claims(tmp_path, monkeypatch):
    owner, waiter = SummaryJournal(tmp_path), SummaryJournal(tmp_path)
    before = _reserve(owner)
    held, release = threading.Event(), threading.Event()
    def hold():
        with owner._serialized():
            held.set()
            assert release.wait(_WAIT)
    thread, errors = _thread(hold)
    try:
        assert held.wait(_WAIT)
        monkeypatch.setattr(module, '_JOURNAL_LOCK_TIMEOUT', 0)
        monkeypatch.setattr(waiter, '_check_path', lambda: pytest.fail('guard ran without serialization'))
        with pytest.raises(JournalError) as caught:
            waiter.dispatch('operation', 'zotero')
        assert caught.value.code == 'storage_unavailable'
    finally:
        release.set(); _join(thread)
    assert errors == [] and owner.get('operation') == before


@pytest.mark.parametrize('failure', ['guard', 'connect', 'body', 'commit', 'close'])
def test_every_exception_releases_lock_for_another_thread(tmp_path, monkeypatch, failure):
    journal = SummaryJournal(tmp_path)
    _reserve(journal)
    connect = sqlite3.connect
    class BadClose:
        def __init__(self, db): object.__setattr__(self, 'db', db)
        def __getattr__(self, name): return getattr(self.db, name)
        def __setattr__(self, name, value): setattr(self.db, name, value)
        def close(self):
            self.db.close()
            raise sqlite3.OperationalError('synthetic close failure')
    with monkeypatch.context() as patch:
        if failure == 'guard':
            patch.setattr(journal, '_check_path', lambda: (_ for _ in ()).throw(JournalError('synthetic guard', 'unsafe_path')))
        elif failure == 'connect':
            patch.setattr(module.sqlite3, 'connect', lambda *a, **kw: (_ for _ in ()).throw(sqlite3.OperationalError('synthetic connect')))
        elif failure == 'commit':
            patch.setattr(journal, '_commit', lambda db: (_ for _ in ()).throw(sqlite3.OperationalError('synthetic commit')))
        elif failure == 'close':
            patch.setattr(module.sqlite3, 'connect', lambda *a, **kw: BadClose(connect(*a, **kw)))
        with pytest.raises((JournalError, sqlite3.Error, ValueError)):
            with journal._db(write=True):
                if failure == 'body': raise ValueError('synthetic transaction body')
    other = SummaryJournal(tmp_path)
    thread, errors = _thread(lambda: other.get('operation'))
    _join(thread)
    assert errors == []


def test_canonical_ancestor_alias_uses_same_lock(tmp_path):
    real = tmp_path / 'real'; real.mkdir()
    root = real / 'root'; root.mkdir()
    alias = tmp_path / 'alias'
    try:
        alias.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('symlink creation unavailable')
    first, second = SummaryJournal(root), SummaryJournal(alias / 'root')
    assert first.path == second.path and first._lock is second._lock
    with pytest.raises(JournalError): SummaryJournal(alias)


@pytest.mark.parametrize('a,b', [
    (r'C:\selected\.research_hub\summary-operations.sqlite3', r'\\?\c:\SELECTED\.research_hub\summary-operations.sqlite3'),
    (r'\\server\share\selected\.research_hub\summary-operations.sqlite3', r'\\?\UNC\SERVER\SHARE\selected\.research_hub\summary-operations.sqlite3'),
])
def test_windows_namespace_and_case_aliases_share_lock(a, b):
    first = module._journal_lock(PureWindowsPath(a))
    assert first is module._journal_lock(PureWindowsPath(b))


def test_registry_retains_live_owners_and_reclaims_unused_locks(tmp_path):
    journal = SummaryJournal(tmp_path)
    lock = journal._lock
    ref = weakref.ref(lock)
    assert SummaryJournal(tmp_path)._lock is lock
    del journal
    gc.collect()
    assert ref() is lock
    del lock
    gc.collect()
    assert ref() is None


@pytest.mark.parametrize('sink', ['local', 'zotero'])
def test_destination_io_does_not_hold_journal_lock(tmp_path, monkeypatch, sink):
    from research_hub import summarize
    from tests.test_summary_journal_apply import ENTRY, FakeZotero
    cfg = SimpleNamespace(root=tmp_path, raw=tmp_path / 'raw', research_hub_dir=tmp_path / '.research_hub',
                          zotero_library_id='123', zotero_library_type='user')
    note = cfg.raw / 'cluster' / 'paper.md'; note.parent.mkdir(parents=True)
    note.write_text('---\ntitle: Synthetic\nzotero-key: PARENT01\n---\n\n## Abstract\n\nSynthetic abstract.\n\n## Personal notes\n\nSynthetic annotation.\n', encoding='utf-8')
    reads = []
    def inspect():
        journal = SummaryJournal(tmp_path)
        thread, errors = _thread(lambda: reads.append(journal.list()))
        _join(thread)
        assert errors == []
    remote = FakeZotero()
    if sink == 'local':
        write = summarize._write_note_text
        def local_write(path, text): inspect(); return write(path, text)
        monkeypatch.setattr(summarize, '_write_note_text', local_write)
    else:
        write = remote.create_items
        def remote_write(items): inspect(); return write(items)
        monkeypatch.setattr(remote, 'create_items', remote_write)
    result = summarize.apply_summaries(cfg, 'cluster', [ENTRY], zot=remote)
    assert result.errors == [] and result.applied == ['paper']
    assert len(reads) == 1 and len(reads[0]) == 1


def test_constructor_does_not_move_existing_guard_failure_outside_apply_try(tmp_path, monkeypatch):
    def rejected(path):
        raise JournalError('synthetic namespace rejection', 'unsafe_path')
    monkeypatch.setattr(module, '_validation_path', rejected)
    journal = SummaryJournal(tmp_path)
    with pytest.raises(JournalError) as caught:
        journal.list()
    assert caught.value.code == 'unsafe_path'


@pytest.mark.parametrize('dispatched', [False, True])
def test_guard_and_recovery_failure_preserve_identity_claims_and_dispatch_evidence(tmp_path, monkeypatch, dispatched):
    from research_hub import summarize
    from tests.test_summary_journal_apply import ENTRY, FakeZotero
    cfg = SimpleNamespace(root=tmp_path, raw=tmp_path / 'raw', research_hub_dir=tmp_path / '.research_hub',
                          zotero_library_id='123', zotero_library_type='user')
    note = cfg.raw / 'cluster' / 'paper.md'; note.parent.mkdir(parents=True)
    note.write_text('---\ntitle: Synthetic\nzotero-key: PARENT01\n---\n\n## Abstract\n\nSynthetic abstract.\n\n## Personal notes\n\nSynthetic annotation.\n', encoding='utf-8')
    original = note.read_bytes()
    remote = FakeZotero()
    check, dispatch, create = SummaryJournal._check_path, SummaryJournal.dispatch, remote.create_items
    rejecting = False
    def guard(journal):
        if rejecting:
            raise JournalError('synthetic unsafe sidecar; preserve history', 'unsafe_path')
        return check(journal)
    def dispatch_gate(journal, operation, sink):
        nonlocal rejecting
        if not dispatched:
            rejecting = True
        return dispatch(journal, operation, sink)
    def create_then_fail_receipt(items):
        nonlocal rejecting
        result = create(items)
        rejecting = True
        return result
    with monkeypatch.context() as patch:
        patch.setattr(SummaryJournal, '_check_path', guard)
        patch.setattr(SummaryJournal, 'dispatch', dispatch_gate)
        patch.setattr(remote, 'create_items', create_then_fail_receipt)
        result = summarize.apply_summaries(cfg, 'cluster', [ENTRY], zot=remote)
    assert result.errors and 'requires reconciliation' in result.errors[0]
    receipt = result.receipts[0]
    assert receipt['status'] == 'receipt_unavailable'
    assert receipt['dispatch_may_have_started'] is True
    assert receipt['current_attempt_dispatched'] is dispatched
    assert remote.writes == int(dispatched)
    assert (note.read_bytes() != original) is dispatched
    journal = SummaryJournal(tmp_path)
    body = journal.get(receipt['operation_id'])
    assert journal.conflicts(body['targets']) == [body['id']]
    assert {s['state'] for s in body['sinks'].values()} == ({'dispatching'} if dispatched else {'prepared_unsent'})
    if dispatched:
        fresh = FakeZotero()
        again = summarize.apply_summaries(cfg, 'cluster', [ENTRY], zot=fresh)
        assert again.errors and fresh.reads == fresh.writes == 0
        assert again.receipts[0]['operation_id'] == body['id']
        changed = summarize.apply_summaries(cfg, 'cluster', [{**ENTRY, 'methodology': 'changed'}], zot=fresh)
        assert changed.errors and fresh.reads == fresh.writes == 0
        assert changed.receipts[0]['operation_id'] == body['id']
        assert journal.conflicts(body['targets']) == [body['id']]
        assert {s['state'] for s in journal.get(body['id'])['sinks'].values()} == {'unknown'}
