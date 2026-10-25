"""CI-collected private BLOB contracts; synthetic direct service, never sockets.

Retains the useful boundaries from generate_sqlite_ui_fixture and the prior
fault/HTTP proof without importing their process-global guards or launching HTTP.
"""
import base64
from contextlib import contextmanager
from email.message import Message
import io
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

from research_hub.workspace import executor, text_intake, writing
from research_hub.workspace._sqlite_server import SQLiteWorkspaceService, SQLiteWorkspaceServer
from research_hub.workspace.core import WorkspaceError, digest, encoded
from research_hub.workspace.server import WorkspaceHandler, WorkspaceServer
from research_hub.workspace.service import WorkspaceService


def forbidden(*args, **kwargs):
    raise AssertionError('Synthetic contract forbids network, subprocess and file publication')


@contextmanager
def commit_fault(stage):
    """Delegate real SQLite writes; inject only the specified acknowledgement fault."""
    real = sqlite3.connect
    class Connection:
        def __init__(self, *args, **kwargs): self.inner = real(*args, **kwargs)
        @property
        def row_factory(self): return self.inner.row_factory
        @row_factory.setter
        def row_factory(self, value): self.inner.row_factory = value
        def execute(self, sql, *args):
            result = self.inner.execute(sql, *args)
            if stage in ('artifacts', 'records', 'source_text_blobs') and sql.startswith('INSERT INTO ' + stage + ' '):
                raise OSError('Synthetic insert acknowledgement lost')
            return result
        def commit(self):
            if stage == 'before_commit': raise OSError('Synthetic precommit failure')
            self.inner.commit()
            if stage == 'after_commit': raise OSError('Synthetic commit acknowledgement lost')
        def rollback(self): return self.inner.rollback()
        def close(self): return self.inner.close()
    with patch('research_hub.workspace.core.sqlite3.connect', Connection):
        yield


class SQLiteContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hub-ci-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for obj, name in [(socket, 'socket'), (socket, 'create_connection'),
                          (subprocess, 'Popen'), (text_intake, '_publish_copy')]:
            guard = patch.object(obj, name, side_effect=forbidden)
            guard.start(); self.addCleanup(guard.stop)
        for obj, name in [(executor, 'codex_capability'), (writing, 'writing_capability')]:
            stub = patch.object(obj, name, return_value={'status': 'unavailable', 'message': 'Synthetic optional probe not performed'})
            stub.start(); self.addCleanup(stub.stop)
        self.service = SQLiteWorkspaceService(self.root)
        self.ws = self.service.workspace
        self.ws.create_project(id='synthetic', title='Synthetic source only')
        self.ws.create_project(id='other', title='Other synthetic project')
        self.raw = '\ufeffPREFIX\r\nSelected 😀 abstract.\r\nSUFFIX'.encode('utf-8')
        self.identity = {'version': 1, 'workspace_instance_id': self.ws.preparation_namespace(), 'key': str(uuid.uuid4())}
        self.payload = {'project_id': 'synthetic', 'intake_request': self.identity, 'title': 'Synthetic title',
                        'reading_scope': 'unknown', 'input_kind': 'file', 'format': 'md',
                        'content_base64': base64.b64encode(self.raw).decode('ascii')}

    def save(self, **changes):
        return self.service.dispatch('project', 'source_text', {**self.payload, **changes})

    def lookup(self):
        return self.service.dispatch('project', 'source_text_lookup', {'project_id': 'synthetic',
            'workspace_instance_id': self.identity['workspace_instance_id'], 'key': self.identity['key']})

    def expect_code(self, code, call):
        with self.assertRaises(WorkspaceError) as caught: call()
        self.assertEqual(caught.exception.code, code)

    def test_exact_bytes_replay_read_only_lookup_and_no_generic_disclosure(self):
        saved = self.save()
        self.assertEqual(self.save()['artifact'], saved['artifact'])
        self.expect_code('request_key_conflict', lambda: self.save(title='Changed intent'))
        before = self.ws.db_path.read_bytes()
        found = self.lookup()
        preview = self.service.dispatch('project', 'preview_text', {'project_id': 'synthetic', 'artifact_id': saved['artifact']['id']})
        self.assertEqual(self.ws.db_path.read_bytes(), before)
        self.assertEqual(found['intake']['state'], 'found')
        self.assertEqual(preview['preview']['text'].encode('utf-8'), self.raw)
        self.assertEqual(preview['preview']['reference'], 'hub-source:' + saved['record']['id'])
        self.assertNotIn('path', saved['artifact'])
        self.assertNotIn('path', preview['preview'])
        self.assertEqual(saved['record']['data']['identity_status'], 'unverified')
        self.assertEqual(saved['record']['data']['human_acceptance'], 'pending')
        snapshot = self.service.dispatch('project', 'show', {'project_id': 'synthetic'})
        metadata = encoded([snapshot['artifacts'], snapshot['records']])
        # Newline escapes in JSON must not make this non-disclosure check vacuous.
        for sentinel in ('PREFIX', 'Selected 😀 abstract.', 'SUFFIX'):
            self.assertNotIn(sentinel, metadata)
        self.assertFalse((self.root / 'hub-sources').exists())
        self.assertEqual(len(self.ws.artifacts('synthetic')), 1)

    def test_profile3_exact_selected_range_prepare_replay_and_legacy_profile2(self):
        saved = self.save(); selected = 'Selected 😀 abstract.'; start = self.raw.decode().index(selected)
        payload = {'project_id': 'synthetic', 'operation': 'paper-abstract-draft', 'mode': 'handoff',
                   'prepare_request': {**self.identity, 'key': str(uuid.uuid4())},
                   'source_selection': {'artifact_id': saved['artifact']['id'], 'source_record_id': saved['record']['id'], 'start': start, 'end': start + len(selected)}}
        task = self.service.dispatch('task', 'create', payload)['task']
        rd = task['request']['research_draft']
        self.assertEqual(rd['profile']['profile_version'], 3)
        self.assertEqual(rd['source_pack']['text'], selected)
        self.assertEqual(self.service.dispatch('task', 'create', payload)['task']['id'], task['id'])
        handoff = encoded(self.service.dispatch('task', 'handoff', {'task_id': task['id']}))
        self.assertNotIn('PREFIX', handoff); self.assertNotIn('SUFFIX', handoff)
        self.assertFalse(list(self.root.rglob('selected-source.txt')))
        (self.root / 'legacy.txt').write_bytes(b'Legacy abstract.')
        artifact = self.ws.register_artifact('synthetic', path='legacy.txt', role='evidence')
        record = self.ws.add_record('synthetic', kind='source', data={'title': 'Legacy', 'locator': 'fixture:legacy'})
        legacy = self.service.dispatch('task', 'create', {'project_id': 'synthetic', 'operation': 'paper-abstract-draft',
            'source_selection': {'artifact_id': artifact['id'], 'source_record_id': record['id'], 'start': 0, 'end': 16}})['task']
        self.assertEqual(legacy['request']['research_draft']['profile']['profile_version'], 2)

    def test_corrupt_blob_and_unknown_storage_version_fail_closed(self):
        saved = self.save(); artifact_id = saved['artifact']['id']
        with self.ws.db(write=True) as db:
            db.execute('UPDATE source_text_blobs SET content=? WHERE artifact_id=?', (self.raw.replace(b'PREFIX', b'BROKEN'), artifact_id))
        self.expect_code('stale_input', lambda: self.service.dispatch('project', 'preview_text', {'project_id': 'synthetic', 'artifact_id': artifact_id}))
        found = self.lookup()
        self.assertEqual(found['preview_status'], 'stale'); self.assertIsNone(found['preview'])
        self.assertFalse(found['artifact']['current'])
        with self.ws.db(write=True) as db:
            db.execute("UPDATE workspace_metadata SET value=? WHERE name='source_text_storage'", ('{"schema_version":999,"minimum_reader":"future"}',))
        self.expect_code('unsupported_storage', lambda: self.service.dispatch('project', 'preview_text', {'project_id': 'synthetic', 'artifact_id': artifact_id}))

    def test_cross_project_preview_cannot_read_blob(self):
        saved = self.save()
        with self.assertRaises(WorkspaceError):
            self.service.dispatch('project', 'preview_text', {'project_id': 'other', 'artifact_id': saved['artifact']['id']})
        self.assertEqual(self.ws.artifacts('other'), [])

    def test_public_defaults_do_not_enable_private_blob(self):
        public = WorkspaceService(self.root)
        self.assertIs(type(public._text_intake()), text_intake.TextIntake)
        self.assertNotIn('storage', public._text_intake_capability())
        self.assertIs(WorkspaceServer._service_type, WorkspaceService)
        self.assertIs(SQLiteWorkspaceServer._service_type, SQLiteWorkspaceService)
        self.assertEqual(self.service._text_intake_capability()['storage'], {'kind': 'workspace_blob', 'version': 1})

    def test_transaction_faults_preserve_truth_and_same_identity_replay(self):
        for stage in ('artifacts', 'records', 'source_text_blobs', 'before_commit', 'after_commit'):
            with self.subTest(stage=stage):
                # Independent project and key per fault, never reset an uncertain operation.
                project = stage.replace('_', '-')
                self.ws.create_project(id=project, title='Synthetic fault')
                payload = {**self.payload, 'project_id': project, 'intake_request': {**self.identity, 'key': str(uuid.uuid4())}}
                with commit_fault(stage):
                    self.expect_code('storage_unavailable', lambda: self.service.dispatch('project', 'source_text', payload))
                found = self.service.dispatch('project', 'source_text_lookup', {'project_id': project,
                    'workspace_instance_id': self.identity['workspace_instance_id'], 'key': payload['intake_request']['key']})
                committed = stage == 'after_commit'
                self.assertEqual(found['intake']['state'], 'found' if committed else 'not_observed')
                self.assertEqual(len(self.ws.artifacts(project)), int(committed))
                replay = self.service.dispatch('project', 'source_text', payload)
                self.assertEqual(replay['intake']['disposition'], 'existing' if committed else 'created')
                self.assertEqual(replay['preview']['text'].encode(), self.raw)
                self.assertEqual(len(self.ws.artifacts(project)), 1)
                self.assertEqual(len(self.ws.records(project)), 1)
        self.assertFalse((self.root / 'hub-sources').exists())

    def test_request_admission_and_human_proof_do_not_leak_between_calls(self):
        # Direct actual handler methods, NOT a socket/HTTP transport acceptance.
        server = SQLiteWorkspaceServer.__new__(SQLiteWorkspaceServer)
        server.service = self.service
        server.server_port = 43210; server.csrf = 'synthetic-csrf'; server.human = 'synthetic-human'
        def request(path, payload=None, extra=None, csrf=True):
            handler = WorkspaceHandler.__new__(WorkspaceHandler)
            handler.server = server; handler.path = '/api/v1' + path
            handler.headers = Message()
            headers = {'Host': '127.0.0.1:43210', **(extra or {})}
            if payload is not None:
                raw = json.dumps(payload).encode()
                headers.update({'Content-Type': 'application/json', 'Content-Length': str(len(raw))})
                if csrf: headers['X-CSRF-Token'] = server.csrf
                handler.rfile = io.BytesIO(raw)
            for name, value in headers.items(): handler.headers[name] = value
            replies = []
            handler._reply = lambda status, body, *args: replies.append((status, body))
            (handler.do_GET if payload is None else handler.do_POST)()
            self.assertEqual(len(replies), 1)
            return replies[0]
        for headers in ({'Host': 'example.invalid'}, {'Origin': 'https://example.invalid'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(request('/projects/synthetic/source-text', self.payload, headers)[0], 403)
                self.assertEqual(request('/workspace', extra=headers)[0], 403)
        self.assertEqual(request('/projects/synthetic/source-text', self.payload, csrf=False)[0], 403)
        self.assertEqual(self.ws.records('synthetic'), [])
        status, saved = request('/projects/synthetic/source-text', self.payload)
        self.assertEqual(status, 200)
        self.assertEqual(saved['preview']['text'].encode(), self.raw)
        def awaiting():
            task = self.service.tasks.create('synthetic', operation='review')
            return self.service.tasks.import_result(task['id'], prose='Synthetic transport only.', input_hash=digest(task['request']))
        first, second = awaiting(), awaiting()
        def decision(task): return {'outcome': 'accept', 'actor': 'synthetic', 'rationale': 'Synthetic fixture not evidence verification', 'action_hash': task['action_hash']}
        self.assertEqual(request('/tasks/' + first['id'] + '/decision', decision(first), {'X-Human-Token': server.human})[0], 200)
        status, denied = request('/tasks/' + second['id'] + '/decision', decision(second))
        self.assertEqual(status, 403); self.assertEqual(denied['code'], 'human_required')
        self.assertEqual(self.service.tasks.get(second['id'])['status'], 'awaiting_human')
