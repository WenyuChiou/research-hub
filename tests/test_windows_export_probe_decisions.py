"""Portable checks of UNC probe decisions, not native filesystem acceptance."""
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from tests import test_windows_export_acceptance as probes


@pytest.mark.parametrize('results,expected,calls', [
    ([0, 0], None, 2),
    ([2], pytest.skip.Exception, 1),
    (['timeout'], pytest.skip.Exception, 1),
    ([1], pytest.fail.Exception, 1),
    ([0, 3], pytest.fail.Exception, 2),
    ([0, 1], pytest.fail.Exception, 2),
    ([0, 'timeout'], pytest.fail.Exception, 2),
])
def test_share_availability_and_identity_decisions(monkeypatch, results, expected, calls):
    local = Path('synthetic-local')
    alias = Path('synthetic-alias')
    observed = []
    monkeypatch.setattr(probes, 'ordinary_unc', lambda path: alias)

    def run(args, *, capture_output, timeout):
        assert capture_output and timeout == 10
        observed.append(args)
        result = results[len(observed) - 1]
        if result == 'timeout':
            raise subprocess.TimeoutExpired(args, timeout)
        # Error details must never be emitted in the failure message.
        return SimpleNamespace(returncode=result, stderr=b'PRIVATE sentinel')

    monkeypatch.setattr(probes.subprocess, 'run', run)
    if expected:
        with pytest.raises(expected) as error:
            probes.require_existing_loopback_share(local)
        assert 'PRIVATE' not in str(error.value)
    else:
        assert probes.require_existing_loopback_share(local) == alias
    assert len(observed) == calls
    assert 'isdir' in observed[0][2] and 'samefile' not in observed[0][2]
    assert observed[0][3:] == [str(alias)]
    if calls == 2:
        assert 'samefile' in observed[1][2]
        assert observed[1][3:] == [str(alias), str(local)]
