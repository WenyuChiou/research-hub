"""Portable ownership tests and real Windows-only acceptance probes.

Portable tests do NOT verify Win32 security or NTFS semantics.
"""
import ctypes
import os
import subprocess
import pytest
from research_hub.workspace import _windows_export as w


class NativeFake:
    def __init__(self, tmp_path, fail=None):
        self.path = tmp_path / 'output'
        self.calls = []
        self.fail = fail
        self.next = 99
    def root(self, path):
        self.calls.append(('root', path))
        if self.fail == "root":
            raise OSError("synthetic root failure")
        self.next += 1
        return self.next
    def child(self, parent, name, directory):
        self.calls.append(('child', parent, name, directory))
        if self.fail == name:
            raise OSError('synthetic error')
        self.next += 1
        return self.next
    def close(self, handle):
        self.calls.append(('close', handle))
        if self.fail == "close" and handle == 101:
            raise OSError("synthetic close failure")
    def identity(self, handle):
        self.calls.append(("identity", handle))
        if self.fail == "identity":
            raise OSError("synthetic unsupported identity")
        return (5, handle)
    def fd(self, handle):
        if self.fail == 'fd':
            raise OSError('synthetic fd conversion error')
        return os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)


def test_fixed_width_abi():
    assert ctypes.sizeof(w.ULONG) == 4
    assert ctypes.sizeof(w.NTSTATUS) == 4
    assert ctypes.sizeof(w.UNICODE_STRING) == (16 if ctypes.sizeof(w.HANDLE) == 8 else 8)
    assert ctypes.sizeof(w.OBJECT_ATTRIBUTES) == (48 if ctypes.sizeof(w.HANDLE) == 8 else 24)
    assert ctypes.sizeof(w.IO_STATUS_BLOCK) == ctypes.sizeof(w.HANDLE) * 2
    assert ctypes.sizeof(w.FILE_ATTRIBUTE_TAG_INFO) == 8
    assert ctypes.sizeof(w.FILE_ID_INFO) == 24
    assert w.FILE_ID_INFO.FileId.offset == 8
    assert w.UNICODE_STRING.Buffer.offset == (8 if ctypes.sizeof(w.HANDLE) == 8 else 4)
    assert w.OBJECT_ATTRIBUTES.RootDirectory.offset == ctypes.sizeof(w.HANDLE)


@pytest.mark.parametrize('path', ['relative.zip', 'C:relative.zip', r'C:\a\..\x.zip', r'C:\a\x.zip:stream', r'\\.\C:\a.zip', r'\\?\C:\a.zip', 'C:\\a\\x.'])
def test_reject_ambiguous_paths(path):
    with pytest.raises(ValueError):
        w._parts(path)


def test_unc_and_unicode_paths():
    assert w._parts(r'\\server\share\資料\輸出.zip') == ('\\\\?\\UNC\\server\\share\\', ('資料', '輸出.zip'))


@pytest.mark.parametrize('failure,closed', [('root', []), ('parent', [100]), ('file.zip', [101, 100]), ('fd', [102,101,100]), (None,[101,100])])
def test_ownership_and_no_fallback(tmp_path, failure, closed):
    fake = NativeFake(tmp_path, failure)
    if failure:
        with pytest.raises(OSError):
            with w.destination_stream(r'C:\parent\file.zip', _native=fake):
                pytest.fail('unexpected stream')
        assert not fake.path.exists()
    else:
        with w.destination_stream(r'C:\parent\file.zip', _native=fake) as stream:
            assert not any(call[0] == 'close' for call in fake.calls)
            stream.write(b'selected synthetic bytes')
        assert fake.path.read_bytes() == b'selected synthetic bytes'
        assert stream.closed
    assert [x[1] for x in fake.calls if x[0] == 'close'] == closed


def test_body_exception_closes_all(tmp_path):
    fake = NativeFake(tmp_path)
    with pytest.raises(RuntimeError):
        with w.destination_stream(r'C:\parent\file.zip', _native=fake) as stream:
            raise RuntimeError('interrupted')
    assert stream.closed
    assert fake.calls[-2:] == [('close',101), ('close',100)]


windows = pytest.mark.skipif(os.name != 'nt', reason='Real Windows required; mocks are not native acceptance')


@windows
def test_native_normal_unicode_exclusive_and_release(tmp_path):
    parent = tmp_path / '資料'
    parent.mkdir()
    output = parent / '證據.zip'
    with w.destination_stream(str(output)) as stream:
        stream.write(b'synthetic selected bytes')
    assert output.read_bytes() == b'synthetic selected bytes'
    with pytest.raises(OSError):
        with w.destination_stream(str(output)):
            pytest.fail('overwrote output')
    assert output.read_bytes() == b'synthetic selected bytes'
    parent.rename(tmp_path / 'released')


@windows
@pytest.mark.parametrize('target', ['parent', 'ancestor'])
def test_native_pins_parent_and_ancestor(tmp_path, target):
    ancestor = tmp_path / 'ancestor'
    parent = ancestor / 'parent'
    parent.mkdir(parents=True)
    with w.destination_stream(str(parent / 'result.zip')) as stream:
        with pytest.raises(OSError):
            (parent if target == 'parent' else ancestor).rename(tmp_path / 'moved')
        stream.write(b'synthetic')
    ancestor.rename(tmp_path / 'released')


@windows
@pytest.mark.parametrize('nested', [False, True])
def test_native_refuses_junction_without_workspace_write(tmp_path, nested):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    redirect = tmp_path / 'redirect'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(redirect), str(workspace)], capture_output=True)
    if result.returncode:
        pytest.skip('Junction creation unavailable; not a security pass')
    try:
        if nested:
            (workspace / 'nested').mkdir()
        output = redirect / 'nested' / 'result.zip' if nested else redirect / 'result.zip'
        before = sorted(str(p.relative_to(workspace)) for p in workspace.rglob('*'))
        with pytest.raises(OSError):
            with w.destination_stream(str(output)):
                pytest.fail('accepted junction')
        assert sorted(str(p.relative_to(workspace)) for p in workspace.rglob('*')) == before
    finally:
        os.rmdir(redirect)


@pytest.mark.parametrize('name', [
    'CON', 'con.txt', 'NUL', 'PRN.zip', 'AUX.zip', 'LPT1', 'COM9.txt',
    'COM¹.txt', 'COM²', 'LPT³', 'CONIN$', 'CONOUT$.txt', 'nul .zip',
    'bad\x00name', 'bad\nname', 'wild*', 'what?', 'quote"', 'pipe|', '<bad>',
    'data:stream', 'space ', 'dot.', '\ud800',
])
def test_reject_names_with_different_win32_interpretations(name):
    with pytest.raises(ValueError):
        w._parts('C:\\parent\\' + name)


@pytest.mark.parametrize('path', [
    'C:\\', '\\\\server\\share\\', 'C:bundle.zip', '\\bundle.zip',
    '\\\\?\\UNC\\server\\share\\file.zip', '\\\\?\\GLOBALROOT\\Device\\file',
    '\\\\.\\pipe\\file', '\\??\\C:\\file', '\\\\server\\share.\\file',
    '\\\\server\\share \\file', '1:\\file.zip',
])
def test_reject_roots_and_namespaces(path):
    with pytest.raises(ValueError):
        w._parts(path)


@pytest.mark.parametrize('path,expected', [
    ('C:\\file.zip', ('\\\\?\\C:\\', ('file.zip',))),
    ('c:/資料/😀.zip', ('\\\\?\\c:\\', ('資料', '😀.zip'))),
    ('\\\\server\\share\\資料\\😀.zip', ('\\\\?\\UNC\\server\\share\\', ('資料', '😀.zip'))),
])
def test_ordinary_drive_and_unc_spelling(path, expected):
    assert w._parts(path) == expected


def test_source_root_can_be_a_drive_or_share_root():
    assert w._parts('C:\\', directory=True) == ('\\\\?\\C:\\', ())
    assert w._parts('\\\\server\\share\\', directory=True) == ('\\\\?\\UNC\\server\\share\\', ())


def test_invalid_path_opens_no_handles(tmp_path):
    fake = NativeFake(tmp_path)
    with pytest.raises(ValueError):
        with w.destination_stream(r'C:\parent\NUL.zip', _native=fake):
            pytest.fail('invalid path accepted')
    assert fake.calls == []


def test_invalid_selected_root_opens_no_handles(tmp_path):
    fake = NativeFake(tmp_path)
    with pytest.raises(ValueError):
        with w.destination_stream(r'C:\parent\file.zip', workspace_roots=[r'\\?\C:\workspace'], _native=fake):
            pytest.fail('invalid root accepted')
    assert fake.calls == []


def test_fdopen_failure_closes_transferred_fd_and_ancestors(tmp_path, monkeypatch):
    fake = NativeFake(tmp_path)
    transferred = []
    def fail(fd, *args, **kwargs):
        transferred.append(fd)
        raise OSError('synthetic fdopen error')
    monkeypatch.setattr(w.os, 'fdopen', fail)
    with pytest.raises(OSError):
        with w.destination_stream(r'C:\parent\file.zip', _native=fake):
            pytest.fail('stream opened')
    with pytest.raises(OSError):
        os.fstat(transferred[0])
    assert fake.calls[-2:] == [('close', 101), ('close', 100)]
    # Partial output is retained. Never unlink by path after an ownership error.
    assert fake.path.read_bytes() == b''


def test_cleanup_error_still_attempts_every_ancestor(tmp_path):
    fake = NativeFake(tmp_path, fail='close')
    with pytest.raises(OSError, match='close failure'):
        with w.destination_stream(r'C:\parent\file.zip', _native=fake) as stream:
            stream.write(b'synthetic')
    assert stream.closed
    assert fake.calls[-2:] == [('close', 101), ('close', 100)]


@pytest.mark.parametrize('matching_ancestor', [100, 101])
def test_selected_root_alias_identity_refused_before_create(tmp_path, matching_ancestor):
    fake = NativeFake(tmp_path)
    # Root 102 + selected workspace 103, compared with output root 100/parent 101.
    fake.identity = lambda handle: (5, matching_ancestor if handle == 103 else handle)
    with pytest.raises(ValueError, match='outside selected workspaces'):
        with w.destination_stream(r'C:\parent\file.zip', workspace_roots=[r'D:\workspace'], _native=fake):
            pytest.fail('alias accepted')
    assert not any(call[0] == 'child' and call[-1] is False for call in fake.calls)
    assert fake.calls[-4:] == [('close', 103), ('close', 102), ('close', 101), ('close', 100)]
    assert not fake.path.exists()


def test_same_fileid_on_other_volume_not_mistaken_for_alias(tmp_path):
    fake = NativeFake(tmp_path)
    fake.identity = lambda handle: (6 if handle == 103 else 5, 101)
    with w.destination_stream(r'C:\parent\file.zip', workspace_roots=[r'D:\workspace'], _native=fake) as stream:
        stream.write(b'synthetic')
        assert not any(call[0] == 'close' for call in fake.calls)
    assert fake.calls[-4:] == [('close', 103), ('close', 102), ('close', 101), ('close', 100)]


@pytest.mark.parametrize('failure', ['identity', 'workspace'])
def test_selected_root_open_or_identity_failure_has_no_output(tmp_path, failure):
    fake = NativeFake(tmp_path, fail=failure)
    with pytest.raises(OSError):
        with w.destination_stream(r'C:\parent\file.zip', workspace_roots=[r'D:\workspace'], _native=fake):
            pytest.fail('failed root accepted')
    assert not fake.path.exists()
    assert not any(call[0] == 'child' and call[-1] is False for call in fake.calls)
    assert fake.calls[-2:] == [('close', 101), ('close', 100)]


@windows
def test_native_identity_exclusion_and_release(tmp_path):
    workspace = tmp_path / 'workspace'
    nested = workspace / 'nested'
    nested.mkdir(parents=True)
    output = nested / 'result.zip'
    with pytest.raises(ValueError, match='outside selected workspaces'):
        with w.destination_stream(str(output), workspace_roots=[str(workspace)]):
            pytest.fail('created output within selected workspace')
    assert not output.exists()
    workspace.rename(tmp_path / 'released')


@windows
def test_native_output_file_cannot_be_renamed_while_open(tmp_path):
    output = tmp_path / 'result.zip'
    with w.destination_stream(str(output)) as stream:
        with pytest.raises(OSError):
            output.rename(tmp_path / 'moved.zip')
        stream.write(b'synthetic')
        stream.flush()
        assert output.stat().st_ino == os.fstat(stream.fileno()).st_ino
    output.rename(tmp_path / 'released.zip')


@pytest.fixture
def native_calls(monkeypatch):
    """Invoke actual ctypes-building methods with a fake kernel, never Windows."""
    from types import SimpleNamespace
    calls = []
    native = w._Native.__new__(w._Native)
    native.kernel = SimpleNamespace(
        CloseHandle=lambda handle: calls.append(('close', handle)) or 1,
        GetFileInformationByHandleEx=None,
    )
    native.nt = SimpleNamespace(
        NtCreateFile=None,
        RtlNtStatusToDosError=lambda status: calls.append(('map_error', status)) or 5,
    )
    monkeypatch.setattr(ctypes, 'WinError', lambda code: OSError(code, 'synthetic native error'), raising=False)
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 5, raising=False)
    return native, calls


def test_native_child_builds_utf16_relative_abi_and_exclusive_flags(native_calls):
    native, calls = native_calls
    def create(handle, access, attrs, status, allocation, attributes, sharing, disposition, options, ea, length):
        obj = ctypes.cast(attrs, ctypes.POINTER(w.OBJECT_ATTRIBUTES)).contents
        name = obj.ObjectName.contents
        assert obj.Length == ctypes.sizeof(w.OBJECT_ATTRIBUTES)
        assert obj.RootDirectory == 123
        assert obj.Attributes == 0x1040
        assert obj.SecurityDescriptor is None and obj.SecurityQualityOfService is None
        assert ctypes.string_at(name.Buffer, name.Length) == '資料😀.zip'.encode('utf-16-le')
        assert name.MaximumLength == name.Length + 2
        assert ctypes.string_at(name.Buffer + name.Length, 2) == b'\0\0'
        assert (access, attributes, sharing, disposition, options) == (0x40100000, 0x80, 1, 2, 0x200060)
        assert allocation is None and ea is None and length == 0
        ctypes.cast(handle, ctypes.POINTER(w.HANDLE))[0] = 456
        ctypes.cast(status, ctypes.POINTER(w.IO_STATUS_BLOCK)).contents.Information = 2
        return 0
    native.nt.NtCreateFile = create
    assert native.child(123, '資料😀.zip', False) == 456
    assert calls == []


def test_native_directory_flags_and_reparse_inspection(native_calls):
    native, calls = native_calls
    def create(handle, access, attrs, status, allocation, attributes, sharing, disposition, options, ea, length):
        assert (access, sharing, disposition, options) == (0x1000A0, 1, 1, 0x200021)
        ctypes.cast(handle, ctypes.POINTER(w.HANDLE))[0] = 456
        ctypes.cast(status, ctypes.POINTER(w.IO_STATUS_BLOCK)).contents.Information = 1
        return 0
    def info(handle, kind, data, size):
        assert (handle, kind, size) == (456, 9, 8)
        ctypes.cast(data, ctypes.POINTER(w.FILE_ATTRIBUTE_TAG_INFO)).contents.FileAttributes = 0x410
        return 1
    native.nt.NtCreateFile = create
    native.kernel.GetFileInformationByHandleEx = info
    with pytest.raises(OSError, match='plain directory'):
        native.child(123, 'parent', True)
    assert calls == [('close', 456)]


@pytest.mark.parametrize('attribute', [0, 0x400, 0x410])
def test_native_directory_refuses_file_and_reparse(native_calls, attribute):
    native, _ = native_calls
    def info(handle, kind, data, size):
        ctypes.cast(data, ctypes.POINTER(w.FILE_ATTRIBUTE_TAG_INFO)).contents.FileAttributes = attribute
        return 1
    native.kernel.GetFileInformationByHandleEx = info
    with pytest.raises(OSError, match='plain directory'):
        native.check_directory(123)


@pytest.mark.parametrize('failure', ['status', 'unexpected_disposition', 'no_handle', 'pending'])
def test_native_create_failure_has_exact_ownership(native_calls, failure):
    native, calls = native_calls
    def create(handle, access, attrs, status, *args):
        if failure not in ('status', 'no_handle'):
            ctypes.cast(handle, ctypes.POINTER(w.HANDLE))[0] = 456
        ctypes.cast(status, ctypes.POINTER(w.IO_STATUS_BLOCK)).contents.Information = 1
        return -1 if failure == 'status' else 0x103 if failure == 'pending' else 0
    native.nt.NtCreateFile = create
    with pytest.raises(OSError):
        native.child(123, 'output.zip', False)
    assert calls == ([('map_error', -1)] if failure == 'status' else
                     [] if failure == 'no_handle' else [('close', 456)])


@pytest.mark.parametrize('failure', ['open', 'inspect'])
def test_native_root_failure_and_flags(native_calls, failure):
    native, calls = native_calls
    def create(path, access, sharing, security, disposition, options, template):
        assert path == '\\\\?\\C:\\'
        assert (access, sharing, security, disposition, options, template) == (0x1000A0, 1, None, 3, 0x2200000, None)
        return w._INVALID_HANDLE if failure == 'open' else 123
    native.kernel.CreateFileW = create
    native.kernel.GetFileInformationByHandleEx = lambda *args: 0
    with pytest.raises(OSError):
        native.root('\\\\?\\C:\\')
    assert calls == ([] if failure == 'open' else [('close', 123)])


@pytest.mark.parametrize('failure', ['query', 'zero_id'])
def test_native_identity_unavailable_fails_closed(native_calls, failure):
    native, _ = native_calls
    native.kernel.GetFileInformationByHandleEx = lambda *args: failure != 'query'
    with pytest.raises(OSError):
        native.identity(123)


def test_native_identity_uses_full_volume_and_128_bit_id(native_calls):
    native, _ = native_calls
    def info(handle, kind, data, size):
        assert (handle, kind, size) == (123, 18, 24)
        value = ctypes.cast(data, ctypes.POINTER(w.FILE_ID_INFO)).contents
        value.VolumeSerialNumber = 2**40 + 3
        value.FileId[:] = bytes(range(16))
        return 1
    native.kernel.GetFileInformationByHandleEx = info
    assert native.identity(123) == (2**40 + 3, bytes(range(16)))


def test_native_close_failure_is_not_silently_successful(native_calls):
    native, _ = native_calls
    native.kernel.CloseHandle = lambda *args: 0
    with pytest.raises(OSError):
        native.close(123)
