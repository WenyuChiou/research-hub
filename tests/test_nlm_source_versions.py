"""Offline payload freshness/resume contract; no NotebookLM account required."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.clusters import Cluster, ClusterRegistry
from research_hub.notebooklm import upload
from research_hub.notebooklm.client import UploadResult


@pytest.fixture
def setup(tmp_path, monkeypatch):
    hub = tmp_path / 'hub'
    hub.mkdir()
    cfg = SimpleNamespace(research_hub_dir=hub, clusters_file=hub / 'clusters.yaml')
    cluster = Cluster(slug='alpha', name='Alpha')
    registry = ClusterRegistry(cfg.clusters_file)
    registry.clusters['alpha'] = cluster
    registry.save()
    bundle = hub / 'bundles' / 'alpha-20261023T000000Z'
    bundle.mkdir(parents=True)
    pdf = bundle / 'paper.pdf'
    pdf.write_bytes(b'%PDF synthetic v1')
    entry = {'action': 'pdf', 'pdf_path': str(pdf), 'doi': '10.1234/synthetic'}
    calls = []
    state = {'fail': False, 'mutate': False, 'raise': False}

    class FakeClient:
        def find_or_create_notebook(self, name):
            return SimpleNamespace(notebook_id='synthetic', url='https://example.invalid/notebook', name=name)
        def set_active_notebook(self, notebook_id):
            pass
        def upload_pdf(self, path):
            if state['mutate']:
                pdf.write_bytes(b'%PDF changed while SDK reading snapshot')
            calls.append((path, path.read_bytes()))
            if state['raise']:
                raise RuntimeError('synthetic interrupted upload')
            return UploadResult(source_kind='pdf', path_or_url=str(path), success=not state['fail'], error='validation failed' if state['fail'] else '')
        def upload_text(self, text, title=''):
            calls.append(('text', text.encode()))
            return UploadResult(source_kind='text', path_or_url=title, success=not state['fail'], error='validation failed' if state['fail'] else '')
        def upload_url(self, url):
            calls.append(('url', url))
            return UploadResult(source_kind='url', path_or_url=url, success=not state['fail'], error='validation failed' if state['fail'] else '')
        def list_sources(self, notebook_id):
            return []
        def close(self):
            pass

    monkeypatch.setattr(upload, '_make_client', lambda *a, **kw: FakeClient())
    monkeypatch.setattr(upload.time, 'sleep', lambda _: None)

    def run(**kwargs):
        (bundle / 'manifest.json').write_text(json.dumps({'entries': [entry]}))
        return upload.upload_cluster(cluster, cfg, **kwargs)

    return SimpleNamespace(cfg=cfg, cluster=cluster, pdf=pdf, entry=entry, calls=calls,
                           state=state, run=run, cache=hub / 'nlm_cache.json')


def version_cache(s, shard=False):
    cache = json.loads(s.cache.read_text())['alpha']
    return cache['shard_source_versions']['Alpha [1/1]'] if shard else cache['source_versions']


@pytest.mark.parametrize('kind', ['pdf', 'text'])
@pytest.mark.parametrize('shard', [False, True])
def test_equal_then_changed_payload_preserves_resume_and_warns(setup, capsys, kind, shard):
    s = setup
    if kind == 'text':
        s.entry.clear()
        s.entry.update(action='text', doi='10.1234/synthetic', text='original abstract')
    options = {'over_cap_strategy': 'shard'} if shard else {}
    first = s.run(**options)
    assert first.success_count == 1
    assert len(version_cache(s, shard)) == 1
    equal = s.run(**options)
    assert equal.skipped_already_uploaded == 1 and equal.errors == []
    if kind == 'pdf':
        s.pdf.write_bytes(b'%PDF modified v2')
    else:
        s.entry['text'] = 'changed abstract'
    changed = s.run(**options)
    assert changed.fail_count == 0 and changed.success_count == 0
    assert changed.skipped_already_uploaded == 1 and len(s.calls) == 1
    assert changed.errors[0]['error'] == 'source_version_conflict'
    assert changed.errors[0]['severity'] == 'warning'
    assert 'NOT updated' in changed.errors[0]['message']
    assert capsys.readouterr().out == ''


def test_legacy_cache_unknown_never_backfills_current_bytes(setup, capsys):
    s = setup
    s.cache.write_text(json.dumps({'alpha': {'uploaded_sources': [str(s.pdf)]}}))
    report = s.run()
    assert not s.calls and report.fail_count == 0
    assert report.errors[0]['error'] == 'source_version_unknown'
    assert version_cache(s) == {}
    assert 'legacy cache' in report.errors[0]['message']
    assert capsys.readouterr().out == ''


def test_url_freshness_unverified_without_fetch(setup):
    s = setup
    s.entry.clear()
    s.entry.update(action='url', url='https://example.invalid/paper')
    s.run()
    report = s.run()
    assert len(s.calls) == 1
    assert version_cache(s) == {}
    assert report.errors[0]['error'] == 'source_freshness_unverified'
    assert report.fail_count == 0


@pytest.mark.parametrize('shard', [False, True])
def test_failed_attempt_has_no_version_and_retry_succeeds(setup, shard):
    s = setup
    options = {'over_cap_strategy': 'shard'} if shard else {}
    s.state['fail'] = True
    assert s.run(**options).fail_count == 1
    assert version_cache(s, shard) == {}
    s.state['fail'] = False
    assert s.run(**options).success_count == 1
    assert len(version_cache(s, shard)) == 1
    assert s.run(**options).skipped_already_uploaded == 1
    assert len(s.calls) == 4


def test_snapshot_records_submitted_bytes_despite_original_race(setup):
    s = setup
    original = s.pdf.read_bytes()
    s.state['mutate'] = True
    report = s.run()
    path, sent = s.calls[0]
    assert sent == original and s.pdf.read_bytes() != sent
    assert path.name == s.pdf.name and path != s.pdf and not path.exists()
    assert report.uploaded[0].path_or_url == str(s.pdf)
    assert version_cache(s)[str(s.pdf)]['sha256'] == hashlib.sha256(sent).hexdigest()
    assert s.run().errors[0]['error'] == 'source_version_conflict'


def test_snapshot_cleanup_on_exception_no_success_checkpoint(setup):
    s = setup
    s.state['raise'] = True
    with pytest.raises(RuntimeError, match='interrupted'):
        s.run()
    assert not s.calls[0][0].exists()
    assert version_cache(s) == {}


def test_cached_missing_pdf_unknown_not_equal(setup):
    s = setup
    s.run()
    s.pdf.unlink()
    report = s.run()
    assert len(s.calls) == 1
    assert report.errors[0]['error'] == 'source_version_unknown'


def test_new_missing_pdf_fails_without_network_or_version(setup):
    s = setup
    s.pdf.unlink()
    report = s.run()
    assert report.fail_count == 1 and not s.calls and version_cache(s) == {}


def test_empty_text_has_no_payload_evidence():
    assert upload._payload_version({'action': 'text', 'text': ''}) is None


@pytest.mark.parametrize("shard", [False, True])
def test_dry_run_reports_conflict_without_cache_write(setup, shard):
    s = setup
    s.run()
    options = {"over_cap_strategy": "shard"} if shard else {}
    if shard:
        s.run(**options)
    previous = s.cache.read_bytes()
    s.pdf.write_bytes(b'changed')
    calls_before = len(s.calls)
    report = s.run(dry_run=True, **options)
    assert report.errors[0]['error'] == 'source_version_conflict'
    assert len(s.calls) == calls_before and s.cache.read_bytes() == previous


@pytest.mark.parametrize('shard', [False, True])
def test_partial_success_checkpoint_survives_interruption(setup, monkeypatch, shard):
    s = setup
    other = dict(s.entry, pdf_path=str(s.pdf.with_name('second.pdf')))
    Path(other['pdf_path']).write_bytes(b'other')
    manifest = s.pdf.parent / 'manifest.json'
    manifest.write_text(json.dumps({'entries': [s.entry, other]}))
    real = upload._attempt_versioned_upload
    def interrupted(client, entry, log):
        if entry is other or entry.get('pdf_path') == other['pdf_path']:
            raise RuntimeError('interrupted second file')
        return real(client, entry, log)
    monkeypatch.setattr(upload, '_attempt_versioned_upload', interrupted)
    options = {'over_cap_strategy': 'shard'} if shard else {}
    with pytest.raises(RuntimeError, match='interrupted second'):
        upload.upload_cluster(s.cluster, s.cfg, **options)
    assert str(s.pdf) in version_cache(s, shard)
    assert other['pdf_path'] not in version_cache(s, shard)
    monkeypatch.setattr(upload, '_attempt_versioned_upload', real)
    result = upload.upload_cluster(s.cluster, s.cfg, **options)
    assert result.success_count == 1 and result.skipped_already_uploaded == 1


def test_cli_advisory_visible_without_changing_exit(setup, monkeypatch, capsys):
    from research_hub import cli_notebooklm
    s = setup
    s.run()
    s.pdf.write_bytes(b'changed')
    monkeypatch.setattr(cli_notebooklm, 'get_config', lambda: s.cfg)
    monkeypatch.setattr(cli_notebooklm, '_preflight_nlm_session', lambda *a, **kw: None)
    assert cli_notebooklm._nlm_upload('alpha', False, True, True) == 0
    assert 'NOT updated' in capsys.readouterr().out


def test_json_and_mcp_advisories_are_structured(setup, monkeypatch, capsys):
    from research_hub.auto import AutoReport
    from research_hub.cli import main
    from research_hub import mcp_server
    s = setup
    s.run()
    s.pdf.write_bytes(b'changed')
    def fake_auto(*a, **kw):
        report = s.run()
        return AutoReport(cluster_slug='alpha', cluster_created=False, nlm_warnings=report.errors,
                          nlm_deferred=True, nlm_error='Source version conflict')
    monkeypatch.setattr('research_hub.auto.auto_pipeline', fake_auto)
    monkeypatch.setenv('RESEARCH_HUB_ROOT', str(s.cfg.research_hub_dir))
    assert main(['auto', 'synthetic', '--no-show', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert 'source_version_conflict' in json.dumps(result)
    result = mcp_server.auto_research_topic('synthetic')
    assert result['nlm_warnings'][0]['error'] == 'source_version_conflict'
    assert result['nlm_deferred'] is True
    assert capsys.readouterr().out == ''


def test_connector_preserves_advisory(setup):
    from research_hub.connectors._notebooklm_adapter import NotebookLMConnector
    s = setup
    s.run()
    s.pdf.write_bytes(b'changed')
    report = NotebookLMConnector().upload(s.cluster, s.cfg)
    assert report.warnings[0]['error'] == 'source_version_conflict'


def test_cached_unreadable_pdf_is_unknown(setup, monkeypatch):
    s = setup
    s.run()
    original_open = Path.open
    def guarded_open(path, *args, **kwargs):
        if path == s.pdf:
            raise PermissionError('synthetic permission denial')
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded_open)
    report = s.run()
    assert len(s.calls) == 1 and report.fail_count == 0
    assert report.errors[0]['error'] == 'source_version_unknown'


def test_shard_cli_advisory_visible_without_changing_exit(setup, monkeypatch, capsys):
    from research_hub import cli_notebooklm
    s = setup
    s.run(over_cap_strategy='shard')
    s.pdf.write_bytes(b'changed')
    monkeypatch.setattr(cli_notebooklm, 'get_config', lambda: s.cfg)
    monkeypatch.setattr(cli_notebooklm, '_preflight_nlm_session', lambda *a, **kw: None)
    assert cli_notebooklm._nlm_shard('alpha', 'recent', 50, False, True) == 0
    assert 'NOT updated' in capsys.readouterr().out


@pytest.mark.parametrize('shard', [False, True])
def test_cleanup_failure_after_success_preserves_checkpoint(setup, monkeypatch, shard):
    s = setup
    real_temp = upload.tempfile.TemporaryDirectory
    class CleanupFails:
        def __enter__(self):
            self.temp = real_temp(prefix='research-hub-test-')
            return self.temp.__enter__()
        def __exit__(self, *args):
            self.temp.__exit__(*args)
            raise OSError('synthetic cleanup failure after successful upload')
    monkeypatch.setattr(upload.tempfile, 'TemporaryDirectory', lambda **kw: CleanupFails())
    options = {'over_cap_strategy': 'shard'} if shard else {}
    first = s.run(**options)
    assert first.success_count == 1 and first.fail_count == 0
    assert first.errors[0]['error'] == 'source_snapshot_cleanup_failed'
    assert str(s.pdf) in version_cache(s, shard)
    second = s.run(**options)
    assert second.skipped_already_uploaded == 1 and len(s.calls) == 1
