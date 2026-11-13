"""Real loopback HTTP + SQLite with synthetic sources, not browser acceptance."""
import json
import threading
from urllib.request import urlopen

import pytest

from research_hub.workspace.server import WorkspaceServer
from tests.test_workspace_native_summary import setup, envelope, POSIX


@pytest.mark.skipif(not POSIX, reason='Pinned POSIX source-file reads')
def test_native_summary_restart_navigation_and_recovery(setup):
    w, record, artifact, text = setup
    native, value = envelope(setup)
    value['sections']['methods'][0].update(
        status='analyst_inference', reason='Synthetic inference', evidence=[])
    value['sections']['limitations'][0].update(
        status='unknown', reason='Not established', evidence=[])
    saved = native.import_summary('p', envelope=json.dumps(value))['native_summary']
    other = w.add_record('p', kind='source', data={
        'id': 'other', 'title': 'Unrelated synthetic source',
        'locator': 'https://example.invalid/other'})
    before = w.db_path.read_bytes()
    original = w.root / 'source.txt'
    moved = w.root / 'temporarily-unavailable.txt'

    # Two separate HTTP server instances reopen the same persisted workspace.
    for restart in range(2):
        server = WorkspaceServer(w.root, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}/api/v1/projects/p/native-summary'

        def read(source_id):
            with urlopen(base + '?source_record_id=' + source_id, timeout=5) as response:
                assert response.status == 200
                return json.load(response)

        def hidden(status):
            result = read(record['id'])
            assert result == {'ok': True, 'status': status, 'native_summary': None,
                              'human_acceptance': 'pending',
                              'semantic_support': 'not_assessed'}

        try:
            current = read(record['id'])
            assert current['status'] == 'current'
            assert current['native_summary'] == saved
            # Repeated source selection must not reuse the previous source's prose.
            assert read(other['id'])['status'] == 'missing'
            assert read(other['id'])['native_summary'] is None
            assert read(record['id'])['native_summary'] == saved
            original.rename(moved)
            hidden('unavailable')
            moved.rename(original)
            assert read(record['id'])['native_summary'] == saved
            original.write_text('Changed synthetic source', encoding='utf-8')
            hidden('stale')
            original.write_text(text, encoding='utf-8')
            assert read(record['id'])['native_summary'] == saved
            assert w.db_path.read_bytes() == before
        finally:
            if moved.exists():
                moved.rename(original)
            original.write_text(text, encoding='utf-8')
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            assert not thread.is_alive()
    assert w.db_path.read_bytes() == before
