"""Portable ABI contract checks; these are not native filesystem acceptance."""
import ctypes
import os
from types import SimpleNamespace

import pytest

from research_hub.workspace import _windows_read as r


def fixture_native(*, completion=0, disposition=1, attributes=0x80, disk_type=1,
                   invalid_handle=False, info_error=False):
    calls, closed = [], []

    def create(handle, access, attrs, status, allocation, file_attrs, share,
               creation, options, ea, length):
        attrs = ctypes.cast(attrs, ctypes.POINTER(r.w.OBJECT_ATTRIBUTES)).contents
        name = attrs.ObjectName.contents
        calls.append({'parent':attrs.RootDirectory, 'name':ctypes.string_at(name.Buffer, name.Length).decode('utf-16-le'),
                      'object_attributes':attrs.Attributes, 'access':access, 'share':share,
                      'creation':creation, 'options':options, 'allocation':allocation,
                      'file_attrs':file_attrs, 'ea':ea, 'length':length})
        ctypes.cast(handle, ctypes.POINTER(r.w.HANDLE)).contents.value = None if invalid_handle else 42
        ctypes.cast(status, ctypes.POINTER(r.w.IO_STATUS_BLOCK)).contents.Information = disposition
        return completion

    def file_type(handle):
        assert handle == 42
        return disk_type

    def info(handle, kind, value):
        assert handle == 42 and kind == 9
        if info_error:
            raise OSError('Synthetic handle-info failure')
        value.FileAttributes = attributes
        return value

    native = object.__new__(r.NativeRead)
    native.nt = SimpleNamespace(NtCreateFile=create)
    native.kernel = SimpleNamespace(GetFileType=file_type)
    native._info = info
    native.close = closed.append
    return native, calls, closed


def test_leaf_uses_existing_readonly_parent_relative_no_reparse_abi():
    native, calls, closed = fixture_native()
    assert native.leaf(17, '\u6587.txt') == 42
    assert calls == [{'parent':17, 'name':'\u6587.txt', 'object_attributes':0x1040,
        'access':0x100081, 'share':1, 'creation':1, 'options':0x200060,
        'allocation':None, 'file_attrs':0, 'ea':None, 'length':0}]
    assert closed == []  # Successful handle ownership transfers to caller.


@pytest.mark.parametrize('change', [dict(completion=0x103), dict(disposition=2),
    dict(attributes=0x400), dict(attributes=0x10), dict(disk_type=3), dict(info_error=True)])
def test_leaf_abnormal_completion_closes_once(change):
    native, calls, closed = fixture_native(**change)
    with pytest.raises(OSError): native.leaf(17, 'x.txt')
    assert len(calls) == 1 and closed == [42]


def test_invalid_handle_is_not_closed_as_a_real_handle():
    native, calls, closed = fixture_native(invalid_handle=True)
    with pytest.raises(OSError): native.leaf(17, 'x.txt')
    assert closed == []


def test_crt_descriptor_requests_readonly_binary(monkeypatch):
    native, calls, closed = fixture_native()
    converted = []
    def convert(handle, flags):
        converted.append((handle, flags))
        return 11
    native.msvcrt = SimpleNamespace(open_osfhandle=convert)
    monkeypatch.setattr(os, 'O_BINARY', 0x8000, raising=False)
    assert native.read_fd(42) == 11
    assert converted == [(42, os.O_RDONLY | 0x8000)]
