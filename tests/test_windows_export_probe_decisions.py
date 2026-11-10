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


# Import locally supported workspace fixture so fixture lookup below exercises
# the same dependencies as the native module even when Linux skips its tests.
from tests.test_workspace_task_summary import candidate  # noqa: E402,F401


def test_native_fixture_contract_resolves_with_repository_plugins(request):
    import inspect

    fixtures = set()
    for name, test in vars(probes).items():
        if name.startswith('test_native_'):
            fixtures.update(inspect.signature(test).parameters)
    fixtures.discard('boundary')  # Parametrized value, not a fixture.
    assert 'tmp_path_factory' not in fixtures
    assert fixtures == {'candidate', 'tmp_path', 'monkeypatch', 'capsys'}
    for name in sorted(fixtures):
        request.getfixturevalue(name)


@pytest.mark.parametrize('outcome', ['pass', 'skip', 'fail'])
def test_native_receipt_reports_only_actual_outcome(capsys, outcome):
    from contextlib import contextmanager

    disabled_calls = []

    @contextmanager
    def disabled():
        # Keep output captured here while proving the production helper explicitly
        # disables capture. These portable receipts are not native evidence.
        disabled_calls.append(True)
        yield

    @probes.native_receipt('portable-receipt-check')
    def exercise(*, capsys):
        if outcome == 'skip':
            pytest.skip('PRIVATE synthetic path')
        if outcome == 'fail':
            raise AssertionError('Synthetic failure')
        return 'completed'

    fake_capture = SimpleNamespace(disabled=disabled)
    if outcome == 'pass':
        assert exercise(capsys=fake_capture) == 'completed'
    else:
        exception = pytest.skip.Exception if outcome == 'skip' else AssertionError
        with pytest.raises(exception):
            exercise(capsys=fake_capture)
    output = capsys.readouterr().out
    assert 'PRIVATE' not in output
    if outcome == 'fail':
        assert output == '' and disabled_calls == []
    else:
        assert disabled_calls == [True]
        assert f': {outcome.upper()}' in output
        assert 'gate unverified' in output if outcome == 'skip' else ': SKIP' not in output


@pytest.mark.parametrize('test', [
    probes.test_native_unc_complete_exporter,
    probes.test_native_unc_identity_fault_fails_closed,
])
def test_unc_output_uses_owned_sibling_and_cleans_on_skip(test, candidate, tmp_path, monkeypatch, capsys):
    from contextlib import nullcontext
    import inspect

    parents = []
    root = candidate[0].workspace.root

    def unavailable(path):
        assert path.is_dir() and path.parent == tmp_path.parent
        assert not path.is_relative_to(root)
        parents.append(path)
        pytest.skip('Existing loopback share unavailable; UNC gate unverified')

    monkeypatch.setattr(probes, 'require_existing_loopback_share', unavailable)
    args = {'candidate': candidate, 'tmp_path': tmp_path, 'monkeypatch': monkeypatch,
            'capsys': SimpleNamespace(disabled=nullcontext)}
    args = {key: value for key, value in args.items() if key in inspect.signature(test).parameters}
    with pytest.raises(pytest.skip.Exception):
        test(**args)
    assert len(parents) == 1 and not parents[0].exists()
    assert root.is_dir()
    output = capsys.readouterr().out
    assert ': SKIP (loopback share unavailable; gate unverified)' in output
    assert ': PASS' not in output
