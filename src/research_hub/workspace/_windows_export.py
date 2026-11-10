"""Windows handle-relative output, with no path-based creation fallback.

Only the output ancestors and explicitly selected workspace roots are opened.
All are held without write/delete sharing until the output stream closes. Native
candidate acceptance (including reparse, alias and UNC cases) is a separate gate;
portable tests of this module do not establish Windows filesystem behavior.
"""
from contextlib import ExitStack, contextmanager
import ctypes
import os
from pathlib import PureWindowsPath


# Fixed Windows ABI widths, even when portable tests run on an LP64 host.
ULONG = ctypes.c_uint32
USHORT = ctypes.c_uint16
HANDLE = ctypes.c_void_p
NTSTATUS = ctypes.c_int32


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", USHORT), ("MaximumLength", USHORT), ("Buffer", ctypes.c_void_p)]


class OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Length", ULONG), ("RootDirectory", HANDLE),
                ("ObjectName", ctypes.POINTER(UNICODE_STRING)), ("Attributes", ULONG),
                ("SecurityDescriptor", ctypes.c_void_p),
                ("SecurityQualityOfService", ctypes.c_void_p)]


class IO_STATUS_BLOCK(ctypes.Structure):
    _fields_ = [("StatusOrPointer", ctypes.c_void_p), ("Information", ctypes.c_size_t)]


class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
    _fields_ = [("FileAttributes", ULONG), ("ReparseTag", ULONG)]


class FILE_ID_INFO(ctypes.Structure):
    _fields_ = [("VolumeSerialNumber", ctypes.c_uint64), ("FileId", ctypes.c_ubyte * 16)]


_DIRECTORY_ACCESS = 0x1000A0  # SYNCHRONIZE | FILE_READ_ATTRIBUTES | FILE_TRAVERSE
_SHARE_READ = 1
_OPEN_REPARSE_POINT = 0x200000
_SYNCHRONOUS_IO_NONALERT = 0x20
_DIRECTORY_FILE = 1
_NON_DIRECTORY_FILE = 0x40
_FILE_OPEN, _FILE_CREATE = 1, 2
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    prefix + number for prefix in ("COM", "LPT") for number in "123456789¹²³"
}


def _component(value):
    # Reject names whose Win32 stat/resolve spelling differs from NT creation.
    if (not value or value in (".", "..") or value.endswith((" ", "."))
            or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in value)
            or value.split(".", 1)[0].rstrip(" ").upper() in _RESERVED):
        raise ValueError("Invalid Windows path component")
    try:
        raw = value.encode("utf-16-le")
    except UnicodeError:
        raise ValueError("Invalid Windows path encoding") from None
    if len(raw) > 65532:
        raise ValueError("Windows path component too long")
    return raw


def _parts(path, *, directory=False):
    path = PureWindowsPath(path)
    anchor = path.anchor
    if not path.is_absolute() or anchor.startswith(("\\\\?", "\\\\.")):
        raise ValueError("Use an ordinary absolute drive or UNC path")
    if anchor.startswith("\\\\"):
        server, share = anchor[2:].rstrip("\\").split("\\")
        _component(server)
        _component(share)
        root = "\\\\?\\UNC\\" + anchor[2:]
    elif len(path.drive) == 2 and path.drive[0].isascii() and path.drive[0].isalpha():
        root = "\\\\?\\" + anchor
    else:
        raise ValueError("Use an ordinary absolute drive or UNC path")
    parts = path.parts[1:]
    if not parts and not directory:
        raise ValueError("Select an output file, not a root directory")
    for part in parts:
        _component(part)
    return root, parts


class _Native:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows native output requires Windows")
        import msvcrt
        self.msvcrt = msvcrt
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.nt = ctypes.WinDLL("ntdll")
        self.kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ULONG, ULONG, ctypes.c_void_p, ULONG, ULONG, HANDLE]
        self.kernel.CreateFileW.restype = HANDLE
        self.kernel.CloseHandle.argtypes = [HANDLE]
        self.kernel.CloseHandle.restype = ctypes.c_int
        self.kernel.GetFileInformationByHandleEx.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p, ULONG]
        self.kernel.GetFileInformationByHandleEx.restype = ctypes.c_int
        self.nt.NtCreateFile.argtypes = [ctypes.POINTER(HANDLE), ULONG, ctypes.POINTER(OBJECT_ATTRIBUTES),
            ctypes.POINTER(IO_STATUS_BLOCK), ctypes.c_void_p, ULONG, ULONG, ULONG, ULONG, ctypes.c_void_p, ULONG]
        self.nt.NtCreateFile.restype = NTSTATUS
        self.nt.RtlNtStatusToDosError.argtypes = [NTSTATUS]
        self.nt.RtlNtStatusToDosError.restype = ULONG

    def close(self, handle):
        if not self.kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def _info(self, handle, kind, info):
        if not self.kernel.GetFileInformationByHandleEx(handle, kind, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info

    def check_directory(self, handle):
        info = self._info(handle, 9, FILE_ATTRIBUTE_TAG_INFO())
        if not info.FileAttributes & 0x10 or info.FileAttributes & 0x400:
            raise OSError("Output ancestor is not a plain directory")

    def identity(self, handle):
        info = self._info(handle, 18, FILE_ID_INFO())
        identifier = bytes(info.FileId)
        if not any(identifier):
            raise OSError("Directory identity unavailable")
        return info.VolumeSerialNumber, identifier

    def root(self, path):
        # No write/delete sharing: existing incompatible handles cause refusal;
        # new reparse mutation/rename handles cannot be acquired while pinned.
        handle = self.kernel.CreateFileW(path, _DIRECTORY_ACCESS, _SHARE_READ, None, 3,
                                         0x02000000 | _OPEN_REPARSE_POINT, None)
        if handle in (None, 0, _INVALID_HANDLE):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.check_directory(handle)
            return handle
        except BaseException:
            self.close(handle)
            raise

    def child(self, parent, component, directory):
        raw = _component(component)
        buf = ctypes.create_string_buffer(raw + b"\0\0")
        name = UNICODE_STRING(len(raw), len(raw) + 2, ctypes.cast(buf, ctypes.c_void_p))
        attrs = OBJECT_ATTRIBUTES(ctypes.sizeof(OBJECT_ATTRIBUTES), parent, ctypes.pointer(name),
                                  0x1040, None, None)  # OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE
        handle, status = HANDLE(), IO_STATUS_BLOCK()
        result = self.nt.NtCreateFile(
            ctypes.byref(handle), _DIRECTORY_ACCESS if directory else 0x40100000,
            ctypes.byref(attrs), ctypes.byref(status), None, 0x80, _SHARE_READ,
            _FILE_OPEN if directory else _FILE_CREATE,
            _OPEN_REPARSE_POINT | _SYNCHRONOUS_IO_NONALERT
            | (_DIRECTORY_FILE if directory else _NON_DIRECTORY_FILE), None, 0)
        if result < 0:
            raise ctypes.WinError(self.nt.RtlNtStatusToDosError(result))
        if handle.value in (None, 0, _INVALID_HANDLE):
            raise OSError("Native open returned no handle")
        try:
            # Do not accept pending/reparse statuses or an unexpected disposition.
            if result != 0 or status.Information != (1 if directory else 2):
                raise OSError("Native open did not complete as requested")
            if directory:
                self.check_directory(handle.value)
            return handle.value
        except BaseException:
            self.close(handle.value)
            raise

    def fd(self, handle):
        # Successful conversion transfers sole ownership to the CRT descriptor.
        return self.msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)


@contextmanager
def destination_stream(path, *, workspace_roots=(), _native=None):
    """Pin ancestors and selected roots, then exclusively create one output.

    File-ID equality catches aliases of a selected workspace in the output
    ancestry. Unsupported identities, open failures and sharing conflicts fail
    closed, before leaf creation. No source files or directory lists are read.
    """
    root, parts = _parts(path)
    selected = [_parts(path, directory=True) for path in dict.fromkeys(workspace_roots)]
    native = _native if _native is not None else _Native()
    with ExitStack() as stack:
        def pin_root(name):
            handle = native.root(name)
            stack.callback(native.close, handle)
            return handle

        def pin_child(parent, name):
            handle = native.child(parent, name, True)
            stack.callback(native.close, handle)
            return handle

        ancestors = [pin_root(root)]
        for part in parts[:-1]:
            ancestors.append(pin_child(ancestors[-1], part))
        if selected:
            identities = {native.identity(handle) for handle in ancestors}
            for selected_root, selected_parts in selected:
                handle = pin_root(selected_root)
                for part in selected_parts:
                    handle = pin_child(handle, part)
                if native.identity(handle) in identities:
                    raise ValueError("Bundle must be outside selected workspaces")

        handle = native.child(ancestors[-1], parts[-1], False)
        try:
            fd = native.fd(handle)
        except BaseException:
            native.close(handle)
            raise
        try:
            stream = os.fdopen(fd, "wb")
        except BaseException:
            os.close(fd)
            raise
        with stream:
            yield stream
