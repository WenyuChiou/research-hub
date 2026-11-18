"""Bounded snapshot CLI; synthetic inputs, not host/scientific acceptance."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from research_hub.workspace.cli import add_workspace_parsers, dispatch_workspace
from research_hub.workspace.core import WorkspaceError, encoded
from research_hub.workspace.native_summary import MAX_ENVELOPE
from research_hub.workspace.native_summary_handoff import compose, preview
from tests.test_native_summary_handoff import snapshot
from tests.test_workspace_native_summary import setup, envelope, POSIX

SAFE_READ = POSIX or os.name == 'nt'


def invoke(root, *extra):
    parser = argparse.ArgumentParser()
    add_workspace_parsers(parser.add_subparsers(dest='command'))
    args = parser.parse_args(['project', 'native-summary-compose', '--root', str(root),
                             '--project', 'p', '--source-record-id', 'source',
                             '--context-path', 'context.json', '--sections-path', 'sections.json', *extra])
    return dispatch_workspace(args)


@pytest.fixture
def files(tmp_path):
    context, sections = snapshot()
    (tmp_path / 'context.json').write_text(encoded({'ok': True, 'context': context}), encoding='utf-8')
    (tmp_path / 'sections.json').write_text(encoded(sections), encoding='utf-8')
    return tmp_path, context, sections


@pytest.mark.skipif(not SAFE_READ, reason='Supported pinned file reads')
@pytest.mark.parametrize('structured', [False, True])
def test_cli_preview_never_opens_ledger_or_writes(files, capsys, monkeypatch, structured):
    root, c, s = files
    import research_hub.workspace.cli as cli
    import research_hub.workspace.core as core
    def forbidden(*a, **k):
        pytest.fail('Preview must not open or initialize a workspace ledger')
    monkeypatch.setattr(cli, 'call_workspace', forbidden)
    monkeypatch.setattr(cli, 'WorkspaceService', forbidden)
    monkeypatch.setattr(core.Workspace, '__init__', forbidden)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    assert invoke(root, *(['--json'] if structured else [])) == 0
    out = capsys.readouterr()
    assert out.err == ''
    result = json.loads(out.out)
    if structured:
        assert result['mode'] == 'preview' and result['binding'] == 'snapshot_only'
        assert result['human_acceptance'] == 'pending'
        assert result['semantic_support'] == 'not_assessed'
        result = result['envelope']
    assert result == compose(c, s)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    assert not (root / '.research').exists()


@pytest.mark.skipif(not SAFE_READ, reason='Supported pinned file reads')
@pytest.mark.parametrize('path,raw', [
    ('context.json', b'{"ok":true,"ok":true,"context":{}}'),
    ('sections.json', b'{"why":[],"why":[]}'),
    ('sections.json', b'{"why":NaN}'),
    ('sections.json', b'{"why":Infinity}'),
    ('sections.json', b'[' * 2000 + b']' * 2000),
    ('sections.json', b'\xff'),
    ('context.json', b'{"ok":false,"context":{}}'),
    ('context.json', b'{"ok":true,"context":{},"extra":0}'),
    ('sections.json', b'null'),
], ids=['context-duplicate', 'sections-duplicate', 'nan', 'infinity', 'deep',
        'invalid-utf8', 'false-wrapper', 'extra-wrapper', 'null-sections'])
def test_strict_input_errors_are_bounded_and_redacted(files, capsys, path, raw):
    root, _, _ = files
    (root / path).write_bytes(raw)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    assert invoke(root, '--json') == 1
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] is False and 'envelope' not in result
    assert len(result['error']) < 150 and str(root) not in result['error']
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


@pytest.mark.skipif(not SAFE_READ, reason='Supported pinned file reads')
@pytest.mark.parametrize('filename,limit', [('context.json', 2 * MAX_ENVELOPE), ('sections.json', MAX_ENVELOPE)])
def test_raw_input_byte_boundary(files, capsys, filename, limit):
    root, _, _ = files
    path = root / filename
    raw = path.read_bytes()
    path.write_bytes(raw + b' ' * (limit - len(raw)))
    assert invoke(root) == 0
    capsys.readouterr()
    path.write_bytes(path.read_bytes() + b' ')
    assert invoke(root) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['code'] == 'context_limit'


@pytest.mark.skipif(not SAFE_READ, reason='Supported pinned file reads')
@pytest.mark.parametrize('project,source', [('other', 'source'), ('p', 'other')])
def test_explicit_selected_identity_required(files, project, source):
    root, _, _ = files
    with pytest.raises(WorkspaceError, match='different selected'):
        preview(root, project, source_record_id=source, context_path='context.json', sections_path='sections.json')


@pytest.mark.skipif(not SAFE_READ, reason='Supported pinned file reads')
@pytest.mark.parametrize('path', ['../outside.json', '/absolute.json', 'a//b', 'a/../b', 'a\\b', '.'])
def test_no_unselected_path_fallback(files, path):
    root, _, _ = files
    with pytest.raises(WorkspaceError):
        preview(root, 'p', source_record_id='source', context_path=path, sections_path='sections.json')


@pytest.mark.skipif(not POSIX, reason='Native POSIX symlink probe, not Windows reparse acceptance')
@pytest.mark.parametrize('kind', ['root', 'ancestor', 'leaf', 'sections-leaf'])
def test_symlink_inputs_rejected_without_reading_outside(files, kind):
    root, _, _ = files
    selected = root
    context_path, sections_path = 'context.json', 'sections.json'
    if kind == 'root':
        selected = root / 'linked-root'
        selected.symlink_to(root, target_is_directory=True)
    elif kind == 'ancestor':
        (root / 'linked').symlink_to(root, target_is_directory=True)
        context_path = 'linked/context.json'
    else:
        (root / 'linked.json').symlink_to(root / ('context.json' if kind == 'leaf' else 'sections.json'))
        if kind == 'leaf':
            context_path = 'linked.json'
        else:
            sections_path = 'linked.json'
    with pytest.raises(WorkspaceError):
        preview(selected, 'p', source_record_id='source', context_path=context_path, sections_path=sections_path)


def test_unsupported_reader_does_not_fall_back(files, monkeypatch, capsys):
    import research_hub.workspace.native_summary as native
    def unavailable(*a, **k):
        raise WorkspaceError('Safe read unavailable', 'unsupported_capability')
    monkeypatch.setattr(native, 'read_path', unavailable)
    assert invoke(files[0]) == 1
    assert json.loads(capsys.readouterr().out)['code'] == 'unsupported_capability'


@pytest.mark.skipif(not POSIX, reason='Existing POSIX fixture; native Windows separate')
def test_fresh_cli_preview_import_and_stale_gate(setup, tmp_path):
    w, record, artifact, text = setup
    native, old = envelope(setup)
    context = native.context('p', source_record_id=record['id'], selections=[
        {'artifact_id': artifact['id'], 'start': 0, 'end': len(text)}])
    sections = copy.deepcopy(old['sections'])
    for items in sections.values():
        for item in items:
            for quote in item['evidence']:
                del quote['start']; del quote['end']
    (w.root / 'context.json').write_text(encoded(context), encoding='utf-8')
    (w.root / 'sections.json').write_text(encoded(sections), encoding='utf-8')
    import research_hub
    env = {**os.environ, 'PYTHONPATH': str(Path(research_hub.__file__).resolve().parent.parent)}
    def command(operation, *extra):
        return subprocess.run([sys.executable, '-m', 'research_hub', 'project', operation,
            '--root', str(w.root), '--project', 'p', *extra], env=env, cwd=tmp_path,
            capture_output=True, text=True, encoding='utf-8', timeout=15)
    before = w.db_path.read_bytes()
    result = command('native-summary-compose', '--source-record-id', record['id'],
                     '--context-path', 'context.json', '--sections-path', 'sections.json')
    assert result.returncode == 0 and not result.stderr
    value = json.loads(result.stdout)
    assert value == old and w.db_path.read_bytes() == before
    (w.root / 'authored.json').write_text(result.stdout, encoding='utf-8')
    imported = command('native-summary-import', '--path', 'authored.json')
    assert imported.returncode == 0
    assert json.loads(imported.stdout)['native_summary']['human_acceptance'] == 'pending'
    before = w.db_path.read_bytes()
    (w.root / 'source.txt').write_text('Changed after snapshot', encoding='utf-8')
    # Snapshot-only composition still succeeds; it must NOT claim currentness.
    result = command('native-summary-compose', '--source-record-id', record['id'],
                     '--context-path', 'context.json', '--sections-path', 'sections.json', '--json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['binding'] == 'snapshot_only'
    rejected = command('native-summary-import', '--path', 'authored.json')
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)['code'] == 'stale_input'
    assert w.db_path.read_bytes() == before
