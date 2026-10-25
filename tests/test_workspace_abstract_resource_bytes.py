"""Git checkout conversion simulation, not native Windows execution.

Pinned package instructions must reach checkout byte-identical to Git blobs;
researcher-owned source text is never normalized to make an integrity check pass.
"""
from pathlib import Path
import subprocess

import pytest

from research_hub.workspace import research_draft as route
from research_hub.workspace.core import WorkspaceError


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = 'src/research_hub/skills_data/_profiles/abstract-draft-instructions-v1/'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    target = tmp_path / 'checkout'
    target.mkdir()
    git(target, 'init', '--quiet')
    (target / '.gitattributes').write_bytes((ROOT / '.gitattributes').read_bytes())
    paths = []
    for relative, expected in route.FILES.items():
        package = PROFILE_ROOT + relative
        blob = git(ROOT, 'show', 'HEAD:' + package)
        assert route._sha(blob) == expected, 'Pin must match authoritative Git blob'
        for prefix in (PROFILE_ROOT,):
            path = target / (prefix + relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            paths.append(path)
    git(target, '-c', 'core.autocrlf=false', 'add', '--all')
    for path in paths:
        path.unlink()
    git(target, '-c', 'core.autocrlf=true', 'checkout-index', '--all', '--force')
    monkeypatch.setattr(route, '__file__', str(target / 'src/research_hub/workspace/research_draft.py'))
    return target


@pytest.mark.parametrize('version', [1, 2, 3])
def test_autocrlf_checkout_preserves_strict_profile_pins(checkout, version):
    adapter = route.AbstractDraftAdapter(version)
    assert adapter.manifest['files'] == route.FILES
    for relative, expected in route.FILES.items():
        package = checkout / PROFILE_ROOT / relative
        assert route._sha(package.read_bytes()) == expected
        assert package.read_bytes() == git(ROOT, 'show', 'HEAD:' + PROFILE_ROOT + relative)


@pytest.mark.parametrize('version', [1, 2, 3])
@pytest.mark.parametrize('relative', list(route.FILES))
@pytest.mark.parametrize('change', ['content', 'crlf'])
def test_changed_instruction_bytes_still_fail_closed(checkout, relative, change, version):
    # Set every fixture to the authoritative bytes before intentionally corrupting
    # one member: the test must detect that member, not an earlier checkout defect.
    for member in route.FILES:
        path = checkout / PROFILE_ROOT / member
        path.write_bytes(git(ROOT, 'show', 'HEAD:' + PROFILE_ROOT + member))
    path = checkout / PROFILE_ROOT / relative
    raw = path.read_bytes()
    path.write_bytes(raw + b'changed' if change == 'content' else raw.replace(b'\n', b'\r\n'))
    with pytest.raises(WorkspaceError) as error:
        route.AbstractDraftAdapter(version)
    assert error.value.code == 'adapter_changed'
