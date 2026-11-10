"""Real Windows probes. Skips are missing evidence, never acceptance passes.

All mutations use synthetic test directories. No shares, credentials, mounts,
privileges, or machine settings are created or changed. Hooks only synchronize
boundary events or record calls; actual filesystem operations remain native.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from research_hub.workspace import _windows_export as w
from research_hub.workspace import stage1_inputs as exporter
from tests.test_workspace_batch_audit import manifest, snapshot
from tests.test_workspace_task_summary import candidate  # noqa: F401

pytestmark = [
    pytest.mark.skipif(os.name != 'nt', reason='Native Windows acceptance required'),
    pytest.mark.timeout(30),
]


def junction(link, target):
    result = subprocess.run(
        ['cmd', '/d', '/c', 'mklink', '/J', str(link), str(target)],
        capture_output=True, timeout=10,
    )
    assert result.returncode == 0, 'Synthetic junction creation failed'


@pytest.mark.parametrize('boundary', ['ancestor_open', 'leaf_create'])
def test_native_mutation_at_open_create_boundary(tmp_path, monkeypatch, boundary):
    ancestor = tmp_path / 'ancestor'
    parent = ancestor / 'parent'
    parent.mkdir(parents=True)
    selected = tmp_path / 'selected'
    (selected / 'parent').mkdir(parents=True)
    before = snapshot(selected)
    moved = tmp_path / 'moved'
    output = parent / 'result.zip'
    original = w._Native.child
    triggered = []

    def child(native, handle, name, directory):
        hit = (directory and name == 'ancestor' if boundary == 'ancestor_open'
               else not directory and name == output.name)
        if hit:
            assert not triggered
            triggered.append(name)
            if boundary == 'ancestor_open':
                # Swap after traversal starts, immediately before real NtCreateFile.
                ancestor.rename(moved)
                junction(ancestor, selected)
            else:
                # Every ancestor must already be pinned before real leaf creation.
                with pytest.raises(OSError):
                    ancestor.rename(moved)
                with pytest.raises(OSError):
                    parent.rename(tmp_path / 'moved-parent')
        return original(native, handle, name, directory)

    monkeypatch.setattr(w._Native, 'child', child)
    try:
        if boundary == 'ancestor_open':
            with pytest.raises(OSError):
                with w.destination_stream(str(output), workspace_roots=[str(selected)]):
                    pytest.fail('Reparse mutation reached output stream')
            assert not (moved / 'parent' / 'result.zip').exists()
        else:
            with w.destination_stream(str(output), workspace_roots=[str(selected)]) as stream:
                stream.write(b'synthetic selected bytes')
            assert output.read_bytes() == b'synthetic selected bytes'
            ancestor.rename(moved)  # Native handles must also be released.
        assert triggered
        assert snapshot(selected) == before
    finally:
        if boundary == 'ancestor_open' and moved.exists() and ancestor.exists():
            os.rmdir(ancestor)  # Remove only the synthetic junction, not its target.


def trace_native(monkeypatch):
    identities, leaves = [], []
    identity, child = w._Native.identity, w._Native.child

    def observed_identity(native, handle):
        value = identity(native, handle)
        identities.append(value)
        return value

    def observed_child(native, handle, name, directory):
        if not directory:
            leaves.append(name)
        return child(native, handle, name, directory)

    monkeypatch.setattr(w._Native, 'identity', observed_identity)
    monkeypatch.setattr(w._Native, 'child', observed_child)
    return identities, leaves


def test_native_short_name_alias_identity_before_leaf(tmp_path, monkeypatch):
    selected = tmp_path / 'selected-workspace-with-long-name'
    selected.mkdir()
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, w.ULONG]
    kernel.GetShortPathNameW.restype = w.ULONG
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel.GetShortPathNameW(str(selected), buffer, len(buffer))
    assert 0 < length < len(buffer), 'Native short-path query failed'
    alias = Path(buffer.value)
    if str(alias).casefold() == str(selected).casefold():
        pytest.skip('No existing alternate 8.3 name; alias acceptance remains unverified')
    assert os.path.samefile(alias, selected)
    identities, leaves = trace_native(monkeypatch)
    with pytest.raises(ValueError, match='outside selected workspaces'):
        with w.destination_stream(str(alias / 'result.zip'), workspace_roots=[str(selected)]):
            pytest.fail('Actual alias accepted')
    assert identities[-1] in identities[:-1]
    assert leaves == []
    assert list(selected.iterdir()) == []
    selected.rename(tmp_path / 'released')


def ordinary_unc(path):
    path = Path(path).absolute()
    assert len(path.drive) == 2 and path.drive[1] == ':'
    return Path('\\\\localhost\\' + path.drive[0] + '$\\').joinpath(*path.parts[1:])


def require_existing_loopback_share(path):
    """Bound the read-only availability check; never enable or configure SMB."""
    unc = ordinary_unc(path)
    availability_script = ('import os,sys; '
                           'sys.exit(0 if os.path.isdir(sys.argv[1]) else 2)')
    try:
        result = subprocess.run([sys.executable, '-c', availability_script, str(unc)],
                                capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        pytest.skip('Existing loopback share unavailable within 10s; UNC gate unverified')
    if result.returncode == 2:
        pytest.skip('Existing loopback share unavailable; UNC gate unverified')
    if result.returncode != 0:
        pytest.fail('Loopback share availability probe failed unexpectedly')

    # Reachability is established. Identity disagreement, query errors, and
    # timeouts are now failures, never environment-absence skips. No writes yet.
    identity_script = ('import os,sys; '
                       'sys.exit(0 if os.path.samefile(sys.argv[1],sys.argv[2]) else 3)')
    try:
        result = subprocess.run([sys.executable, '-c', identity_script, str(unc), str(path)],
                                capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        pytest.fail('Reachable loopback share identity query timed out; no writes allowed')
    if result.returncode != 0:
        pytest.fail('Reachable loopback share identity mismatch or query failure; no writes allowed')
    return unc


def test_native_unc_complete_exporter(candidate, tmp_path_factory):
    output_parent = tmp_path_factory.mktemp('unc-output')
    unc_parent = require_existing_loopback_share(output_parent)
    root = candidate[0].workspace.root
    before = snapshot(root)
    output = unc_parent / 'bundle.zip'
    # Once availability is established, unsupported native operations are errors,
    # not skips. CI must expose any actual exporter incompatibility.
    report = exporter.export(manifest(candidate), output)
    assert report['counts']['prepared'] == 1
    with zipfile.ZipFile(output_parent / 'bundle.zip') as archive:
        assert json.loads(archive.read('manifest.json')) == report
        for entry in report['entries']:
            for item in entry['files']:
                raw = archive.read(item['path'])
                assert len(raw) == item['bytes']
                assert hashlib.sha256(raw).hexdigest() == item['sha256']
    assert snapshot(root) == before


def test_native_unc_workspace_alias_exporter_refused(candidate, monkeypatch):
    root = candidate[0].workspace.root
    alias = require_existing_loopback_share(root)
    before = snapshot(root)
    identities, leaves = trace_native(monkeypatch)
    with pytest.raises(ValueError, match='outside selected workspaces'):
        exporter.export(manifest(candidate), alias / 'forbidden.zip')
    assert identities and identities[-1] in identities[:-1]
    assert leaves == []
    assert snapshot(root) == before


def test_native_unc_identity_fault_fails_closed(candidate, tmp_path_factory, monkeypatch):
    """Fault injection after a REAL UNC identity query; not unsupported-SMB evidence."""
    output_parent = tmp_path_factory.mktemp('unc-fail-closed')
    alias = require_existing_loopback_share(output_parent)
    before = snapshot(candidate[0].workspace.root)
    identity = w._Native.identity
    queried = []

    def unavailable(native, handle):
        queried.append(identity(native, handle))
        raise OSError('Synthetic identity capability loss')

    monkeypatch.setattr(w._Native, 'identity', unavailable)
    _, leaves = trace_native(monkeypatch)
    with pytest.raises(OSError, match='Synthetic identity capability loss'):
        exporter.export(manifest(candidate), alias / 'forbidden.zip')
    assert queried and leaves == []
    assert list(output_parent.iterdir()) == []
    assert snapshot(candidate[0].workspace.root) == before
