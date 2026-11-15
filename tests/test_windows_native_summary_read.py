"""Synthetic native Windows tests; never read user research or change ACLs."""
import copy
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from research_hub.workspace import _windows_read as r
from research_hub.workspace.core import Workspace, WorkspaceError
from research_hub.workspace.native_summary import NativeSummary, SECTIONS, FIELDS, read_path

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows filesystem acceptance")


@pytest.mark.parametrize('raw,limit', [(b'', 0), (b'abc', 3), (b'abcd', 3),
    ('Synthetic \u4e2d\u6587 \U0001f331'.encode(), 100)])
def test_native_bounded_read(tmp_path, raw, limit):
    d = tmp_path / 'sub'; d.mkdir()
    (d / '\u6587.txt').write_bytes(raw)
    assert r.read_bytes(tmp_path, 'sub/\u6587.txt', limit) == raw[:limit+1]


@pytest.mark.parametrize('name', ['', '/x', 'a//b', 'a/./b', 'a/../b', '../x',
    'a\\b', 'C:foo', 'C:/foo', 'a:stream', '//host/share', '\\\\?\\C:\\x',
    'NUL.txt', 'con', 'LPT1.log', 'a.', 'a ', 'a/\x00', 'a/\x1b', 'a?'])
def test_unsafe_spelling_before_native(name):
    class NoNative:
        def root(self, *args):
            pytest.fail('Unsafe spelling reached a native open')
    with pytest.raises(ValueError):
        r.read_bytes('C:\\synthetic', name, 12, _native=NoNative())


@pytest.mark.parametrize('root', ['\\\\host\\share\\root', '\\\\?\\C:\\root', '//host/share/root'])
def test_unc_device_rejected_before_native(root):
    with pytest.raises(ValueError):
        r.read_bytes(root, 'x', 12, _native=object())


@pytest.mark.parametrize('drive_type', [0, 1, 2, 4, 5, 6])
def test_nonfixed_drive_refused_before_open(tmp_path, monkeypatch, drive_type):
    native = r.NativeRead()
    def kind(*args): return drive_type
    def forbidden(*args): pytest.fail('Unsupported drive reached CreateFileW')
    monkeypatch.setattr(native.kernel, 'GetDriveTypeW', kind)
    monkeypatch.setattr(native.kernel, 'CreateFileW', forbidden)
    with pytest.raises(OSError):
        r.read_bytes(tmp_path, 'input.txt', 10, _native=native)


def test_missing_file_is_not_created(tmp_path):
    with pytest.raises(OSError):
        r.read_bytes(tmp_path, 'missing.txt', 20)
    assert not (tmp_path / 'missing.txt').exists()


def test_directory_leaf_rejected(tmp_path):
    (tmp_path / 'directory').mkdir()
    with pytest.raises(OSError):
        r.read_bytes(tmp_path, 'directory', 20)


def test_pinned_ancestor_and_leaf_block_mutation(tmp_path):
    parent = tmp_path / 'selected'; parent.mkdir()
    leaf = parent / 'input.txt'; leaf.write_bytes(b'synthetic original')
    with r.source_stream(tmp_path, 'selected/input.txt') as stream:
        with pytest.raises(OSError): parent.rename(tmp_path / 'moved')
        with pytest.raises(OSError): leaf.rename(parent / 'moved.txt')
        with pytest.raises(OSError): leaf.write_bytes(b'changed')
        assert stream.read() == b'synthetic original'
    # Closure must release both leaf and ancestor handles.
    leaf.write_bytes(b'after close')
    parent.rename(tmp_path / 'moved')


def test_existing_writer_fails_closed(tmp_path):
    leaf = tmp_path / 'input.txt'; leaf.write_bytes(b'synthetic original')
    with leaf.open('r+b'):
        with pytest.raises(OSError): r.read_bytes(tmp_path, 'input.txt', 30)
    assert r.read_bytes(tmp_path, 'input.txt', 30) == b'synthetic original'


def junction(link, target):
    result = subprocess.run(['cmd', '/d', '/c', 'mklink', '/J', str(link), str(target)],
                            capture_output=True, timeout=10)
    if result.returncode:
        pytest.skip('Synthetic junction creation unavailable; no settings changed')


@pytest.mark.parametrize('boundary', ['existing_ancestor', 'workspace_ancestor', 'before_child'])
def test_reparse_ancestor_never_returns_other_bytes(tmp_path, monkeypatch, boundary):
    outside = tmp_path / 'outside'; outside.mkdir()
    (outside / 'input.txt').write_bytes(b'other synthetic scope')
    selected = tmp_path / 'selected'
    moved = tmp_path / 'old'
    if boundary == 'before_child':
        selected.mkdir(); (selected / 'input.txt').write_bytes(b'original')
        original = r.NativeRead.child
        def child(native, handle, name, directory):
            if name == 'selected':
                selected.rename(moved)
                junction(selected, outside)
            return original(native, handle, name, directory)
        monkeypatch.setattr(r.NativeRead, 'child', child)
    else:
        junction(selected, outside)
    try:
        with pytest.raises(OSError):
            if boundary == 'workspace_ancestor':
                r.read_bytes(selected, 'input.txt', 50)
            else:
                r.read_bytes(tmp_path, 'selected/input.txt', 50)
        assert (outside / 'input.txt').read_bytes() == b'other synthetic scope'
    finally:
        if selected.is_junction():
            os.rmdir(selected)  # Exactly this owned synthetic junction, not target.


def test_leaf_symlink_refused_if_available(tmp_path):
    target = tmp_path / 'target.txt'; target.write_bytes(b'synthetic target')
    link = tmp_path / 'link.txt'
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip('Native symlink creation unavailable; no privilege changes')
    try:
        with pytest.raises(OSError): r.read_bytes(tmp_path, 'link.txt', 30)
    finally:
        link.unlink()


def test_hardlink_alias_writer_sharing_if_available(tmp_path):
    target = tmp_path / 'target.txt'; target.write_bytes(b'synthetic target')
    alias = tmp_path / 'alias.txt'
    try: os.link(target, alias)
    except OSError: pytest.skip('Synthetic hardlink unavailable; no permissions changed')
    with r.source_stream(tmp_path, 'target.txt') as stream:
        with pytest.raises(OSError): alias.write_bytes(b'changed')
        assert stream.read() == b'synthetic target'


def test_leaf_validation_failure_releases_handles(tmp_path, monkeypatch):
    leaf = tmp_path / 'input.txt'; leaf.write_bytes(b'synthetic')
    original = r.NativeRead._info
    def fail_leaf(native, handle, kind, info):
        result = original(native, handle, kind, info)
        if kind == 9 and not result.FileAttributes & 0x10:
            raise OSError('synthetic information failure')
        return result
    monkeypatch.setattr(r.NativeRead, '_info', fail_leaf)
    with pytest.raises(OSError): r.read_bytes(tmp_path, 'input.txt', 20)
    leaf.rename(tmp_path / 'after.txt')


def test_native_fd_conversion_failure_releases_handles(tmp_path, monkeypatch):
    leaf = tmp_path / 'input.txt'; leaf.write_bytes(b'synthetic')
    def failure(*args): raise OSError('synthetic conversion failure')
    monkeypatch.setattr(r.NativeRead, 'read_fd', failure)
    with pytest.raises(OSError): r.read_bytes(tmp_path, 'input.txt', 20)
    leaf.rename(tmp_path / 'after.txt')


def test_fdopen_failure_releases_handles(tmp_path, monkeypatch):
    leaf = tmp_path / 'input.txt'; leaf.write_bytes(b'synthetic')
    def failure(*args): raise OSError('synthetic fdopen failure')
    monkeypatch.setattr(r.os, 'fdopen', failure)
    with pytest.raises(OSError): r.read_bytes(tmp_path, 'input.txt', 20)
    leaf.rename(tmp_path / 'after.txt')


@pytest.mark.parametrize('fault', ['pending', 'wrong_disposition', 'invalid_handle'])
def test_abnormal_native_completion_releases_handles(tmp_path, monkeypatch, fault):
    leaf = tmp_path / 'input.txt'; leaf.write_bytes(b'synthetic')
    native = r.NativeRead()
    original = native.nt.NtCreateFile
    def changed(*args):
        result = original(*args)
        if args[8] & r.w._NON_DIRECTORY_FILE and result == 0:
            if fault == 'pending':
                return 0x103  # Fault injected after a real completed open.
            if fault == 'wrong_disposition':
                ctypes.cast(args[3], ctypes.POINTER(r.w.IO_STATUS_BLOCK)).contents.Information = 2
            if fault == 'invalid_handle':
                handle = ctypes.cast(args[0], ctypes.POINTER(r.w.HANDLE))
                native.close(handle.contents.value)
                handle.contents.value = None
        return result
    monkeypatch.setattr(native.nt, 'NtCreateFile', changed)
    with pytest.raises(OSError): r.read_bytes(tmp_path, 'input.txt', 20, _native=native)
    leaf.rename(tmp_path / 'after.txt')


def test_adapter_bounds_and_safe_errors(tmp_path):
    class W: root = tmp_path
    (tmp_path / 'input.txt').write_bytes(b'abcd')
    with pytest.raises(WorkspaceError) as limit: read_path(W(), 'input.txt', 3)
    assert limit.value.code == 'context_limit'
    with pytest.raises(WorkspaceError) as missing: read_path(W(), 'private-name.txt', 9)
    assert missing.value.code == 'source_unavailable'
    assert 'private-name' not in str(missing.value)
    with pytest.raises(WorkspaceError) as unsafe: read_path(W(), '../x', 9)
    assert unsafe.value.code == 'unsafe_path'


def test_isolated_native_summary_roundtrip(tmp_path):
    w = Workspace(tmp_path)
    w.create_project(id='p', title='Synthetic', archetype='review', goal='Test')
    source = w.add_record('p', kind='source', data={'title':'Synthetic paper',
        'locator':'https://example.invalid/selected', 'reading_scope':'Synthetic selected text'})
    text = 'Synthetic observed fact. ' + 'x' * 47000
    (tmp_path / 'source.txt').write_text(text, encoding='utf-8')
    a = w.register_artifact('p', path='source.txt', role='evidence', source_record_id=source['id'])
    n = NativeSummary(w)
    c = n.context('p', source_record_id=source['id'], selections=[{'artifact_id':a['id'], 'start':0, 'end':len(text)}])['context']
    v = {k:copy.deepcopy(c[k]) for k in FIELDS if k != 'sections'}
    v['sections'] = {key:[{'text':'Synthetic claim', 'status':('supported','analyst_inference','unknown')[i % 3],
        'reason':'Caller assessment, not acceptance', 'evidence':[{'artifact_id':a['id'], 'quote':text[:23], 'start':0, 'end':23}]}]
        for i,key in enumerate(SECTIONS)}
    result = n.import_summary('p', envelope=json.dumps(v))
    assert result['native_summary']['human_acceptance'] == 'pending'
    assert result['native_summary']['semantic_support'] == 'not_assessed'
    fresh = NativeSummary(Workspace(tmp_path)).read('p', source_record_id=source['id'])
    assert fresh['status'] == 'current'
    assert fresh['native_summary']['sections'] == v['sections']
    assert n.import_summary('p', envelope=json.dumps(v))['reused']
    (tmp_path / 'source.txt').write_text('changed', encoding='utf-8')
    stale = n.read('p', source_record_id=source['id'])
    assert stale['native_summary'] is None
