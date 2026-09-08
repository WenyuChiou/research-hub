"""Bounded child lifetime without breaking out of the host's sandbox/job.

Windows uses a nested kill-on-close Job Object. A gated launcher cannot spawn
the executor until attachment succeeds. POSIX uses a small parent-liveness
supervisor and a separate executor process group. Neither path retries work.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def process_alive(pid: int) -> bool:
    """Conservative liveness check; never use Windows os.kill(pid, 0)."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        api.GetExitCodeProcess.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # Access denied is not proof of death.
        try:
            code = wintypes.DWORD()
            return not api.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class WindowsJob:
    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("min_working", ctypes.c_size_t),
                        ("max_working", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                        ("peak_job", ctypes.c_size_t)]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.SetInformationJobObject.restype = wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype = wintypes.BOOL
        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.TerminateJobObject.restype = wintypes.BOOL
        self.api.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        self.api.QueryInformationJobObject.restype = wintypes.BOOL
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def attach(self, pid):
        import ctypes
        process = self.api.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.api.CloseHandle(process)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None

    def terminate_and_drain(self):
        """Job termination is asynchronous; wait for descendants, not just leader."""
        import ctypes
        from ctypes import wintypes
        class Accounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_longlong) for name in ("user", "kernel", "period_user", "period_kernel")] + [(name, wintypes.DWORD) for name in ("faults", "total", "active", "terminated")]
        if not self.api.TerminateJobObject(self.handle, 125):
            raise ctypes.WinError(ctypes.get_last_error())
        deadline = time.monotonic() + 8
        while True:
            info = Accounting()
            if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.active == 0:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError("Executor descendants are still terminating; preserve temporary files")
            time.sleep(0.05)


@contextmanager
def guarded_process(command, *, cwd, stdin, stdout, stderr, timeout):
    """Yield a Popen; closing the context terminates all owned descendants."""
    gate = Path(cwd) / "executor.start"
    job = WindowsJob() if os.name == "nt" else None
    process = None
    try:
        launcher = [sys.executable, "-I", str(Path(__file__).resolve()), str(gate),
                    str(os.getpid()), str(timeout + 10), *command]
        process = subprocess.Popen(launcher, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr,
                                   shell=False, start_new_session=os.name != "nt")
        if job:
            job.attach(process.pid)  # Fail closed; no breakaway or unguarded fallback.
        with gate.open("x", encoding="ascii") as stream:
            stream.write("start")
        yield process
    finally:
        if job:
            try:
                job.terminate_and_drain()
            finally:
                job.close()
        elif process and process.poll() is None:
            process.terminate()  # Supervisor handles TERM and drains its child group.
        if process:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def _supervise():
    gate, parent, seconds, *command = sys.argv[1:]
    parent, seconds = int(parent), float(seconds)
    deadline = time.monotonic() + 10
    while not Path(gate).is_file():
        if time.monotonic() >= deadline or (os.name != "nt" and os.getppid() != parent):
            return 125
        time.sleep(0.05)
    if os.name == "nt":
        # Children inherit the attached job. The parent owns its only handle.
        return subprocess.call(command)
    stopping = False
    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    child = subprocess.Popen(command, start_new_session=True)
    deadline = time.monotonic() + seconds
    try:
        while child.poll() is None:
            if stopping or os.getppid() != parent or time.monotonic() >= deadline:
                return 124
            time.sleep(0.1)
        return child.returncode
    finally:
        # Kill the group even if its leader exited, so detached-in-group helpers
        # cannot outlive this scoped task. Deliberate setsid escape is not a sandbox.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(_supervise())
