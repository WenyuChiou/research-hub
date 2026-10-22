"""Synthetic capability process results only; no CLI, accounts or providers."""
from concurrent.futures import ThreadPoolExecutor
import subprocess
import threading
from types import SimpleNamespace

import pytest
from research_hub.workspace import executor

FLAGS = '--ignore-user-config --sandbox --ephemeral --output-last-message --strict-config'


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    executor.codex_capability.cache_clear()
    monkeypatch.setattr(executor, 'codex_command', lambda: ['synthetic-codex'])
    yield
    executor.codex_capability.cache_clear()


def output(command):
    return SimpleNamespace(returncode=0, stdout=FLAGS if command[1] == 'exec' else '\n'.join(executor.DISABLED_FEATURES), stderr='')


def install(monkeypatch, run):
    monkeypatch.setattr(executor, 'subprocess', SimpleNamespace(run=run, TimeoutExpired=subprocess.TimeoutExpired))


def test_shared_decreasing_budget_success_and_copy(monkeypatch):
    now = [0.0]; calls = []
    monkeypatch.setattr(executor, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    def run(command, **kwargs):
        calls.append(kwargs['timeout']); now[0] += 2
        return output(command)
    install(monkeypatch, run)
    value = executor.codex_capability()
    assert value['status'] == 'available' and calls == [10, 8, 6]
    value['status'] = 'corrupted'
    now[0] += 1000
    assert executor.codex_capability()['status'] == 'available' and len(calls) == 3
    executor.codex_capability.cache_clear()
    assert executor.codex_capability()['status'] == 'available' and len(calls) == 6


@pytest.mark.parametrize('honor_timeout', [True, False])
def test_budget_exhaustion_stops_later_probe_and_recovers(monkeypatch, honor_timeout):
    now = [0.0]; calls = []; slow = [True]
    monkeypatch.setattr(executor, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    def run(command, **kwargs):
        calls.append(kwargs['timeout'])
        if slow[0]:
            if honor_timeout and kwargs['timeout'] < 6:
                now[0] += kwargs['timeout']
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            now[0] += 6
        return output(command)
    install(monkeypatch, run)
    assert executor.codex_capability()['status'] == 'unavailable'
    assert calls == [10, 4]  # Never start login, even if a process returns late.
    assert executor.codex_capability()['status'] == 'unavailable' and len(calls) == 2
    with pytest.raises(executor.WorkspaceError):
        executor.run_codex(None, None, None)
    assert len(calls) == 2
    slow[0] = False; now[0] += 2.01
    assert executor.codex_capability()['status'] == 'available' and len(calls) == 5


@pytest.mark.parametrize('stage', [1, 2, 3])
def test_failed_validation_negative_cache_expires(monkeypatch, stage):
    now = [0.0]; calls = []; failed = [True]
    monkeypatch.setattr(executor, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    def run(command, **kwargs):
        calls.append(command)
        value = output(command)
        if failed[0] and len(calls) == stage: value.returncode = 1
        return value
    install(monkeypatch, run)
    assert executor.codex_capability()['status'] == 'unavailable' and len(calls) == stage
    assert executor.codex_capability()['status'] == 'unavailable' and len(calls) == stage
    failed[0] = False; now[0] += 2.01
    assert executor.codex_capability()['status'] == 'available' and len(calls) == stage + 3


def test_concurrent_cold_callers_share_one_chain(monkeypatch):
    entered = threading.Event(); release = threading.Event(); calls = []
    def run(command, **kwargs):
        calls.append(command); entered.set()
        assert release.wait(2)
        return output(command)
    install(monkeypatch, run)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(executor.codex_capability)
        assert entered.wait(1)
        others = [pool.submit(executor.codex_capability) for _ in range(2)]
        release.set()
        assert all(f.result(timeout=2)['status'] == 'available' for f in [first, *others])
    assert len(calls) == 3


def test_waiter_budget_does_not_overwrite_owner_cache(monkeypatch):
    entered = threading.Event(); release = threading.Event(); calls = []
    def run(command, **kwargs):
        calls.append(command); entered.set()
        assert release.wait(2)
        return output(command)
    install(monkeypatch, run)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(executor.codex_capability)
        assert entered.wait(1)
        monkeypatch.setattr(executor, 'CAPABILITY_PROBE_BUDGET_SECONDS', .03)
        try:
            assert executor.codex_capability()['status'] == 'unavailable'
            assert len(calls) == 1
        finally: release.set()
        assert first.result(timeout=2)['status'] == 'available'
    assert executor.codex_capability()['status'] == 'available' and len(calls) == 3


def test_invalidation_waits_for_owner_and_cannot_be_overwritten(monkeypatch):
    entered = threading.Event(); release = threading.Event(); clearing = threading.Event(); calls = []
    def run(command, **kwargs):
        calls.append(command); entered.set()
        assert release.wait(2)
        return output(command)
    def clear():
        clearing.set(); executor.codex_capability.cache_clear()
    install(monkeypatch, run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(executor.codex_capability); assert entered.wait(1)
        invalidation = pool.submit(clear); assert clearing.wait(1)
        assert not invalidation.done()
        release.set(); first.result(timeout=2); invalidation.result(timeout=2)
    assert executor.codex_capability()['status'] == 'available' and len(calls) == 6


@pytest.mark.parametrize('error', [OSError('synthetic'), RuntimeError('unexpected synthetic')])
def test_exception_releases_lock(monkeypatch, error):
    def run(*args, **kwargs): raise error
    install(monkeypatch, run)
    if isinstance(error, OSError): assert executor.codex_capability()['status'] == 'unavailable'
    else:
        with pytest.raises(RuntimeError): executor.codex_capability()
    executor.codex_capability.cache_clear()
    install(monkeypatch, lambda command, **kwargs: output(command))
    assert executor.codex_capability()['status'] == 'available'


def test_lock_wait_consumes_probe_budget(monkeypatch):
    now = [0.0]; began = threading.Event(); calls = []
    def clock():
        value = now[0]; began.set(); return value
    monkeypatch.setattr(executor, 'time', SimpleNamespace(monotonic=clock))
    def run(command, **kwargs):
        calls.append(kwargs['timeout']); return output(command)
    install(monkeypatch, run)
    executor._capability_lock.acquire()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(executor.codex_capability)
        try:
            assert began.wait(1); now[0] = 3
        finally: executor._capability_lock.release()
        assert future.result(timeout=2)['status'] == 'available'
    assert calls == [7, 7, 7]


def test_late_final_probe_does_not_report_available(monkeypatch):
    now = [0.0]; calls = []
    monkeypatch.setattr(executor, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    def run(command, **kwargs):
        calls.append(kwargs['timeout']); now[0] += 3 if len(calls) < 3 else 5
        return output(command)
    install(monkeypatch, run)
    assert executor.codex_capability()['status'] == 'unavailable'
    assert calls == [10, 7, 4]
