"""Narrow experimental saved-text storage, not a VFS or a public capability.

Legacy artifacts have no storage descriptor and retain their exact file contract.
Only explicitly initialized synthetic/prototype workspaces receive the BLOB table.
No source files, cleanup, database exports or automatic text transmission.
"""
import hashlib
import json
import sqlite3

from .core import WorkspaceError, encoded, file_hash, safe_path

FEATURE = {'schema_version': 1, 'minimum_reader': 'workspace-source-text-blob-v1'}


def has_table(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_text_blobs'").fetchone())


def check_schema(db, *, required=False):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspace_metadata'").fetchone():
        if required:
            raise WorkspaceError('Saved-text schema is unavailable', 'unsupported_storage')
        return
    # One statement snapshot: a first save may commit between separate autocommit
    # SELECTs. Never combine an old absent marker with a newly committed table.
    marker, table_exists = db.execute(
        "SELECT (SELECT value FROM workspace_metadata WHERE name='source_text_storage'), "
        "EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_text_blobs')"
    ).fetchone()
    if marker is not None:
        try:
            feature = json.loads(marker)
            valid = feature == FEATURE and type(feature.get('schema_version')) is int
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid or not table_exists:
            raise WorkspaceError('Saved-text schema version is unavailable', 'unsupported_storage')
    elif required or table_exists:
        raise WorkspaceError('Saved-text schema version is unavailable', 'unsupported_storage')


def initialize(db):
    check_schema(db)
    db.execute('''CREATE TABLE IF NOT EXISTS source_text_blobs (
        artifact_id TEXT PRIMARY KEY REFERENCES artifacts(id),
        project_id TEXT NOT NULL REFERENCES projects(id),
        source_record_id TEXT NOT NULL UNIQUE REFERENCES records(id),
        storage_version INTEGER NOT NULL CHECK(storage_version=1),
        format TEXT NOT NULL CHECK(format IN ('txt','md')),
        sha256 TEXT NOT NULL, byte_length INTEGER NOT NULL CHECK(byte_length BETWEEN 1 AND 40000),
        content BLOB NOT NULL CHECK(typeof(content)='blob' AND length(content)=byte_length))''')
    db.execute("INSERT OR IGNORE INTO workspace_metadata VALUES ('source_text_storage', ?)", (encoded(FEATURE),))


def is_blob(artifact):
    if 'storage' not in artifact:
        return False
    descriptor = artifact['storage']
    if (not isinstance(descriptor, dict) or descriptor != {'kind': 'workspace_blob', 'version': 1, 'blob_id': artifact.get('id')}
            or type(descriptor.get('version')) is not int or not isinstance(descriptor.get('blob_id'), str)
            or 'path' in artifact or artifact.get('role') != 'evidence'):
        raise WorkspaceError('Unsupported evidence storage descriptor', 'unsupported_storage')
    return True


def reference(artifact):
    if is_blob(artifact):
        if not isinstance(artifact.get('source_record_id'), str):
            raise WorkspaceError('Saved-text source linkage unavailable', 'ledger_unavailable')
        return 'hub-source:' + artifact['source_record_id']
    return artifact['path']


def identity(artifact):
    if is_blob(artifact):
        return encoded({'reference': reference(artifact), 'storage': artifact['storage'], 'format': artifact.get('format'),
                        'byte_length': artifact.get('byte_length')})
    return artifact['path']


def row(db, artifact):
    if not is_blob(artifact):
        raise WorkspaceError('Expected saved-text storage', 'unsupported_storage')
    check_schema(db, required=True)
    try:
        found = db.execute('SELECT artifact_id,project_id,source_record_id,storage_version,format,sha256,byte_length, '
                           'typeof(content) AS content_type,length(content) AS actual_length, '
                           'substr(content,1,40001) AS content FROM source_text_blobs WHERE artifact_id=?', (artifact['id'],)).fetchone()
    except sqlite3.DatabaseError as error:
        raise WorkspaceError('Saved-text schema is unreadable', 'unsupported_storage') from error
    if found is None:
        raise WorkspaceError('Saved-text bytes are missing', 'ledger_unavailable')
    record = db.execute('SELECT project,kind,body FROM records WHERE id=?', (artifact.get('source_record_id'),)).fetchone()
    registered = db.execute('SELECT project,body FROM artifacts WHERE id=?', (artifact['id'],)).fetchone()
    try:
        data = json.loads(record['body']) if record else {}
        intake = data.get('intake', {})
        stored = json.loads(registered['body']) if registered else {}
        valid = (record and registered and record['kind'] == 'source' and record['project'] == registered['project'] == found['project_id'] == artifact.get('project_id')
                 and found['source_record_id'] == artifact.get('source_record_id') and found['storage_version'] == 1
                 and found['format'] == artifact.get('format') == intake.get('format') and found['format'] in ('txt', 'md')
                 and found['sha256'] == artifact.get('sha256') == intake.get('sha256')
                 and type(found['byte_length']) is int and 0 < found['byte_length'] <= 40000
                 and found['byte_length'] == artifact.get('byte_length') and found['content_type'] == 'blob'
                 and found['actual_length'] == found['byte_length'] and isinstance(found['content'], bytes)
                 and len(found['content']) == found['byte_length'] and intake.get('artifact_id') == artifact['id']
                 and all(stored.get(k) == artifact.get(k) for k in ('id', 'project_id', 'source_record_id', 'storage', 'format', 'byte_length', 'sha256', 'role')))
    except (TypeError, ValueError, KeyError, AttributeError):
        valid = False
    if not valid:
        raise WorkspaceError('Saved-text linkage is inconsistent', 'ledger_unavailable')
    return found


def read_blob(workspace, artifact):
    with workspace.db() as db:
        raw = row(db, artifact)['content']
    if hashlib.sha256(raw).hexdigest() != artifact['sha256']:
        raise WorkspaceError('Saved-text bytes changed', 'stale_input')
    try:
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise WorkspaceError('Saved text is not strict UTF-8', 'invalid_source') from error
    if not text.lstrip('\ufeff').strip() or '\x00' in text:
        raise WorkspaceError('Saved text is invalid', 'invalid_source')
    return raw


def current_hash(workspace, artifact):
    if is_blob(artifact):
        return hashlib.sha256(read_blob(workspace, artifact)).hexdigest()
    return file_hash(safe_path(workspace.root, artifact['path'], exists=True))


def coverage(artifact):
    if not is_blob(artifact):
        return None
    return {'artifact_id': artifact['id'], 'reference': reference(artifact), 'storage': artifact['storage'],
            'sha256': artifact['sha256'], 'coverage': 'content_not_supplied', 'scientific_support': 'not_assessed',
            'warning': 'Saved text content was not supplied. Do not infer or summarize its findings from metadata.'}
