"""Isolated candidate: local-drive, handle-relative Windows reads.

This does not enable text-copy publication, UNC/SMB access, or any installation.
No path-open fallback is permitted. Every ancestor stays pinned until the
read-only leaf stream closes. Reparse points and ambiguous Win32 names fail.
"""
from contextlib import ExitStack, contextmanager
import ctypes
import os
import stat

from . import _windows_export as w

_READ_ACCESS = 0x100081  # SYNCHRONIZE | FILE_READ_ATTRIBUTES | FILE_READ_DATA


class NativeRead(w._Native):
    def root(self, path):
        # Drive letters can also name remote mappings. Do not let those become
        # an implicit network/credential-bearing read through this local API.
        self.kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
        self.kernel.GetDriveTypeW.restype = w.ULONG
        ordinary = path[4:] if path.startswith('\\\\?\\') else path
        if self.kernel.GetDriveTypeW(ordinary) != 3:  # DRIVE_FIXED only
            raise OSError('Selected workspace is not on a fixed local drive')
        return super().root(path)

    def leaf(self, parent, component):
        raw = w._component(component)
        buf = ctypes.create_string_buffer(raw + b"\0\0")
        name = w.UNICODE_STRING(len(raw), len(raw) + 2, ctypes.cast(buf, ctypes.c_void_p))
        attrs = w.OBJECT_ATTRIBUTES(ctypes.sizeof(w.OBJECT_ATTRIBUTES), parent,
                                   ctypes.pointer(name), 0x1040, None, None)
        handle, status = w.HANDLE(), w.IO_STATUS_BLOCK()
        result = self.nt.NtCreateFile(
            ctypes.byref(handle), _READ_ACCESS, ctypes.byref(attrs),
            ctypes.byref(status), None, 0, w._SHARE_READ, w._FILE_OPEN,
            w._OPEN_REPARSE_POINT | w._SYNCHRONOUS_IO_NONALERT | w._NON_DIRECTORY_FILE,
            None, 0)
        if result < 0:
            raise ctypes.WinError(self.nt.RtlNtStatusToDosError(result))
        if handle.value in (None, 0, w._INVALID_HANDLE):
            raise OSError("Native read returned no handle")
        try:
            if result != 0 or status.Information != 1:
                raise OSError("Native read did not open an existing file")
            info = self._info(handle.value, 9, w.FILE_ATTRIBUTE_TAG_INFO())
            if info.FileAttributes & (0x10 | 0x400):
                raise OSError("Selected input is not a plain file")
            self.kernel.GetFileType.argtypes = [w.HANDLE]
            self.kernel.GetFileType.restype = w.ULONG
            if self.kernel.GetFileType(handle.value) != 1:  # FILE_TYPE_DISK
                raise OSError("Selected input is not a disk file")
            return handle.value
        except BaseException:
            self.close(handle.value)
            raise

    def read_fd(self, handle):
        return self.msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)


def components(relative):
    # Check raw spelling BEFORE a path class can normalize away '.' or empty parts.
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("Select a workspace-relative regular file")
    parts = tuple(relative.split("/"))
    for part in parts:
        w._component(part)
    return parts


@contextmanager
def source_stream(root, relative, *, _native=None):
    parts = components(relative)
    # Deliberately exclude UNC/device roots: no network/credential side effects.
    spelling = os.fspath(root)
    if spelling.startswith(("\\\\", "//")):
        raise ValueError("Only local-drive workspace reads are supported")
    anchor, ancestors = w._parts(spelling, directory=True)
    native = _native if _native is not None else NativeRead()
    with ExitStack() as stack:
        parent = native.root(anchor)
        stack.callback(native.close, parent)
        for part in (*ancestors, *parts[:-1]):
            parent = native.child(parent, part, True)
            stack.callback(native.close, parent)
        handle = native.leaf(parent, parts[-1])
        try:
            fd = native.read_fd(handle)
        except BaseException:
            native.close(handle)
            raise
        try:
            stream = os.fdopen(fd, "rb")
        except BaseException:
            os.close(fd)
            raise
        with stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise OSError("Selected input is not a regular file")
            yield stream


def read_bytes(root, relative, limit, *, _native=None):
    if type(limit) is not int or not 0 <= limit <= 4 * 1024 * 1024:
        raise ValueError("Invalid bounded read limit")
    with source_stream(root, relative, _native=_native) as stream:
        return stream.read(limit + 1)
