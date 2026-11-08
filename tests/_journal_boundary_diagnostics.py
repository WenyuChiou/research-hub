"""Failure-only metadata for the synthetic parallel journal test, not a repair."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import threading
import time


def _native_metadata(path):
    if os.name != 'nt':
        return {'available': False}
    import ctypes
    from ctypes import wintypes as w

    class Info(ctypes.Structure):
        _fields_ = [('attributes', w.DWORD), ('times', w.DWORD * 6),
                    ('volume', w.DWORD), ('size_high', w.DWORD), ('size_low', w.DWORD),
                    ('links', w.DWORD), ('index_high', w.DWORD), ('index_low', w.DWORD)]

    class Standard(ctypes.Structure):
        _fields_ = [('allocation', ctypes.c_longlong), ('size', ctypes.c_longlong),
                    ('links', w.DWORD), ('delete_pending', ctypes.c_ubyte), ('directory', ctypes.c_ubyte)]

    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    api.CreateFileW.restype = w.HANDLE
    api.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.POINTER(Info)]
    api.GetFileInformationByHandle.restype = w.BOOL
    api.GetFileInformationByHandleEx.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    api.GetFileInformationByHandleEx.restype = w.BOOL
    api.CloseHandle.argtypes, api.CloseHandle.restype = [w.HANDLE], w.BOOL
    result = []
    for share in (0, 7):
        # READ_ATTRIBUTES; OPEN_EXISTING; BACKUP_SEMANTICS | OPEN_REPARSE_POINT.
        handle = api.CreateFileW(str(path), 0x80, share, None, 3, 0x02200000, None)
        row = {'share': share, 'open_error': ctypes.get_last_error() if handle == ctypes.c_void_p(-1).value else 0}
        result.append(row)
        if row['open_error'] or handle == ctypes.c_void_p(-1).value:
            continue
        try:
            info, standard = Info(), Standard()
            if api.GetFileInformationByHandle(handle, ctypes.byref(info)):
                row.update(links=info.links, attributes=info.attributes, volume=info.volume,
                           inode=(info.index_high << 32) | info.index_low)
            else:
                row['info_error'] = ctypes.get_last_error()
            if api.GetFileInformationByHandleEx(handle, 1, ctypes.byref(standard), ctypes.sizeof(standard)):
                row.update(standard_links=standard.links, delete_pending=bool(standard.delete_pending),
                           directory=bool(standard.directory))
            else:
                row['standard_error'] = ctypes.get_last_error()
        finally:
            if not api.CloseHandle(handle):
                row['close_error'] = ctypes.get_last_error()
    return result


class JournalBoundaryDiagnostics:
    """Return original values/errors; observe only this fixture's direct check."""
    def __init__(self, patch, journal_class, database, native=_native_metadata):
        self.events, self.dropped = [], 0
        self._lock, self._active, self._slots = threading.Lock(), {}, {}
        self._start, self._native = time.perf_counter_ns(), native
        leaves = {Path(str(database) + suffix): suffix or 'database'
                  for suffix in ('', '-journal', '-wal', '-shm')}
        original_lstat = Path.lstat
        check_code = journal_class._check_path.__code__
        original_db, original_commit = journal_class._db, journal_class._commit

        def observed_lstat(path, *args, **kwargs):
            selected = sys._getframe(1).f_code is check_code and path in leaves
            started = time.perf_counter_ns() - self._start if selected else None
            try:
                info = original_lstat(path, *args, **kwargs)
            except OSError as error:
                if selected and not isinstance(error, FileNotFoundError):
                    self._record(path, leaves[path], started, time.perf_counter_ns() - self._start, error=error)
                raise
            ended = time.perf_counter_ns() - self._start if selected else None
            if selected and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                             or getattr(info, 'st_file_attributes', 0) & 0x400):
                self._record(path, leaves[path], started, ended, info=info)
            return info

        @contextmanager
        def observed_db(owner, *args, **kwargs):
            with self._phase('db_context', kwargs.get('write', False)):
                with original_db(owner, *args, **kwargs) as connection:
                    with self._phase('transaction_body', kwargs.get('write', False)):
                        yield connection

        def observed_commit(owner, connection):
            with self._phase('commit', True):
                return original_commit(owner, connection)

        patch(Path, 'lstat', observed_lstat)
        patch(journal_class, '_db', observed_db)
        patch(journal_class, '_commit', observed_commit)

    @contextmanager
    def _phase(self, phase, write):
        worker = threading.get_ident()
        with self._lock:
            slot = self._slots.setdefault(worker, len(self._slots) + 1)
            previous = self._active.get(worker)
            self._active[worker] = {'worker': slot, 'phase': phase, 'write': bool(write)}
        try:
            yield
        finally:
            with self._lock:
                if previous is None:
                    self._active.pop(worker, None)
                else:
                    self._active[worker] = previous

    def _record(self, path, leaf, started, ended, *, info=None, error=None):
        with self._lock:
            if len(self.events) == 4:
                self.dropped += 1
                return
            event = {'leaf': leaf, 'stat_start_ns': started, 'stat_end_ns': ended,
                     'native_start_ns': time.perf_counter_ns() - self._start,
                     'active_before_native': list(self._active.values())}
            if info is not None:
                event['stat'] = {name: getattr(info, name, None) for name in
                                 ('st_mode', 'st_nlink', 'st_ino', 'st_dev', 'st_file_attributes', 'st_size')}
            else:
                event['stat_error'] = {'type': type(error).__name__, 'errno': error.errno,
                                       'winerror': getattr(error, 'winerror', None)}
            self.events.append(event)
        # Later, non-atomic observation: never replace the original result/error.
        try:
            event['native_after_lstat'] = self._native(path)
        except Exception as native_error:
            event['native_error_type'] = type(native_error).__name__
        with self._lock:
            event.update(native_end_ns=time.perf_counter_ns() - self._start,
                         active_after_native=list(self._active.values()))

    def emit(self):
        runtime = {'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version, 'platform': sys.platform}
        if os.name == 'nt':
            runtime['windows_build'] = sys.getwindowsversion().build
        print('SYNTHETIC_JOURNAL_BOUNDARY ' + json.dumps(
            {'runtime': runtime, 'events': self.events, 'dropped': self.dropped}, sort_keys=True))
