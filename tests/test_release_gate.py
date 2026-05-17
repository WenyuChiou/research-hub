"""Meta-tests for the mechanical release gate (plan Phase 1).

The release gate exists because v0.89.1 + v0.91.0 both shipped RED
because the pytest scope was narrowed under time pressure (no
pytest / e2e `--ignore`'d). These tests lock the gate's CONTRACT so
the e2e-exclusion class of failure can't silently reappear.

Pure static assertions on the gate scripts — deliberately NO
execution of release-check.sh (it runs the full suite incl this
file → infinite recursion). The plan explicitly calls for grepping
the script's constructed command rather than running it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_RELEASE_CHECK = _REPO / "scripts" / "release-check.sh"
_INSTALLER = _REPO / "scripts" / "install_release_gate.sh"


@pytest.fixture(scope="module")
def release_check_src() -> str:
    assert _RELEASE_CHECK.is_file(), f"missing {_RELEASE_CHECK}"
    return _RELEASE_CHECK.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def installer_src() -> str:
    assert _INSTALLER.is_file(), f"missing {_INSTALLER}"
    return _INSTALLER.read_text(encoding="utf-8")


# --- release-check.sh contract -------------------------------------------

def test_release_check_runs_pytest(release_check_src: str) -> None:
    assert "python -m pytest tests/" in release_check_src


def test_release_check_does_NOT_ignore_e2e(release_check_src: str) -> None:
    """The whole point of the gate. If anyone adds an e2e --ignore
    here, this test fails loudly."""
    assert "test_dashboard_executor_e2e" not in release_check_src, (
        "release-check.sh must NOT --ignore the e2e suite — that is "
        "exactly the v0.91.0 failure this gate prevents."
    )


def test_release_check_only_allowed_ignore_is_v065(release_check_src: str) -> None:
    """Exactly one --ignore is permitted (documented env issue).
    Any additional --ignore is a silent scope cut."""
    ignores = [
        tok for tok in release_check_src.split()
        if tok.startswith("--ignore=")
    ]
    assert ignores == ["--ignore=tests/test_v065_extras_install.py"], (
        f"unexpected --ignore set in release-check.sh: {ignores}"
    )


def test_release_check_uses_fresh_basetemp(release_check_src: str) -> None:
    """Fresh --basetemp makes the gate immune to a locally
    icacls-polluted .pytest-work (the v0.91.0 root cause)."""
    assert "--basetemp=" in release_check_src
    assert "mktemp -d" in release_check_src


def test_release_check_enforces_clean_tree(release_check_src: str) -> None:
    assert "git status --porcelain" in release_check_src


def test_release_check_enforces_version_sync(release_check_src: str) -> None:
    assert "__version__" in release_check_src
    assert "pyproject.toml" in release_check_src


def test_release_check_writes_sha_bound_marker(release_check_src: str) -> None:
    assert "RELEASE_GATE_PASSED" in release_check_src
    assert "git rev-parse HEAD" in release_check_src


# --- pre-push hook contract (embedded in installer heredoc) --------------

def test_hook_gates_only_version_tags(installer_src: str) -> None:
    assert "refs/tags/v*" in installer_src


def test_hook_resolves_tag_commit_failclosed(installer_src: str) -> None:
    """--verify --quiet => unresolvable ref is EMPTY (refuse), not
    the literal '<ref>^{commit}' string git rev-parse echoes without
    --verify (the bug caught while building the gate)."""
    assert "git rev-parse --verify --quiet" in installer_src


def test_hook_sha_binds_marker_to_tag_commit(installer_src: str) -> None:
    assert "RELEASE_GATE_PASSED" in installer_src
    assert "marker_sha" in installer_src
    assert "tag_commit" in installer_src


def test_hook_consumes_marker_on_success(installer_src: str) -> None:
    assert 'rm -f "$MARKER"' in installer_src


def test_hook_documents_bypass(installer_src: str) -> None:
    assert "--no-verify" in installer_src
