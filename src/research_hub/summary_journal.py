"""Private schema2 journal used by the legacy summary apply connection.

No provider/model I/O, retries, human-approval claims, pruning or Workspace DB
migration in this module. Actual apply reserves before destination I/O, not
before prior model generation. This Python API is not an authentication boundary
or a generic exposed CLI/MCP tool; adapter acknowledgements are caller reports.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import sqlite3
import stat
import uuid

from .workspace.core import WorkspaceError, encoded, safe_path

# Byte limits follow existing abstract-response (100k), bounded task prose (2m,
# made byte-based here), and setup metadata (8KiB) conventions. Never truncate.
MAX_CANDIDATE_BYTES = 100_000
MAX_SNAPSHOT_BYTES = 2_000_000
MAX_METADATA_BYTES = 8_192
SCHEMA_VERSION = '2'
_AUTH_KINDS = {'legacy_cli_explicit_apply', 'legacy_mcp_apply_invocation', 'legacy_parent_apply_invocation'}
_OBSERVATIONS = {'not_observed', 'matching_content', 'changed', 'read_denied', 'unavailable', 'ambiguous', 'restored', 'preserved_newer', 'compensation_unknown'}
_TERMINAL = {'confirmed', 'rejected'}


class JournalError(ValueError):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def scope_digest(source, targets):
    """Invocation scope only; not a Workspace approval or authentication token."""
    return _hash(encoded({'source': source, 'targets': targets}).encode('utf-8'))


def _metadata(value):
    try:
        raw = encoded(value)
    except (TypeError, ValueError) as exc:
        raise JournalError('Invalid journal metadata', 'invalid_input') from exc
    if len(raw.encode('utf-8')) > MAX_METADATA_BYTES:
        raise JournalError('Journal metadata exceeds byte limit', 'too_large')
    return raw


def _text(value):
    return isinstance(value, str) and bool(value) and '\x00' not in value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise JournalError('Invalid operation identity', 'invalid_input')


def _validate_scope(source, targets, authorization):
    if not isinstance(source, dict) or set(source) != {'reference', 'sha256', 'coverage'} or not _text(source['reference']) or not isinstance(source['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', source['sha256']) or not isinstance(source['coverage'], str) or source['coverage'] not in {'abstract', 'partial', 'full', 'unknown'}:
        raise JournalError('Invalid selected source binding', 'invalid_input')
    if not isinstance(targets, dict) or not targets or not set(targets) <= {'local', 'zotero'} or not all(_text(v) for v in targets.values()):
        raise JournalError('Invalid logical targets', 'invalid_input')
    if not isinstance(authorization, dict) or set(authorization) != {'kind', 'reference', 'scope_sha256'} or not isinstance(authorization['kind'], str) or authorization['kind'] not in _AUTH_KINDS or not _text(authorization['reference']) or authorization['scope_sha256'] != scope_digest(source, targets):
        raise JournalError('Explicit unchanged legacy invocation scope is required', 'invalid_authorization')


def _validation_path(path):
    """Use one Windows namespace for strict journal containment checks only.

    CPython may retain an extended prefix if a sidecar disappears during its
    resolve checks. Give both the approved root and fixed children that prefix
    up front; do not retry/ignore an escape or alter SQLite I/O paths.
    """
    if not isinstance(path, PureWindowsPath):
        return path
    text = str(path)
    prefix = "\\\\?\\"
    if text.startswith(prefix):
        tail = text[len(prefix):]
        if tail[:4].upper() == 'UNC\\':
            text = '\\\\' + tail[4:]
        elif re.match(r'^[A-Za-z]:\\', tail):
            text = tail
        else:
            raise JournalError('Unsupported Windows path namespace', 'unsafe_path')
    ordinary = PureWindowsPath(text)
    if not ordinary.is_absolute() or '..' in ordinary.parts:
        raise JournalError('Ambiguous Windows validation path', 'unsafe_path')
    if re.fullmatch(r'[A-Za-z]:', ordinary.drive):
        return type(path)(prefix + str(ordinary))
    components = ordinary.drive[2:].split('\\') if ordinary.drive.startswith('\\\\') else []
    if len(components) == 2 and all(c and c not in {'.', '..', '?'} and ':' not in c for c in components):
        return type(path)(prefix + 'UNC\\' + str(ordinary)[2:])
    raise JournalError('Unsupported Windows path namespace', 'unsafe_path')


class SummaryJournal:
    def __init__(self, root):
        original = Path(root).expanduser().absolute()
        if original.is_symlink() or (original.exists() and getattr(original.lstat(), 'st_file_attributes', 0) & 0x400):
            raise JournalError('Linked journal root is not allowed', 'unsafe_path')
        self.root = original.resolve()
        self.path = self.root / '.research_hub' / 'summary-operations.sqlite3'

    def _check_path(self):
        try:
            for path in (self.path, *(Path(str(self.path) + suffix) for suffix in ('-journal', '-wal', '-shm'))):
                safe_path(_validation_path(self.root), _validation_path(path))
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    # SQLite can remove a sidecar between containment validation
                    # and this observation. Absence was already allowed; do not
                    # suppress permission errors or retry a failed safety check.
                    continue
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or getattr(info, 'st_file_attributes', 0) & 0x400):
                    raise JournalError('Journal must be a regular unlinked file', 'unsafe_path')
        except WorkspaceError as exc:
            raise JournalError(str(exc), 'unsafe_path') from exc

    def _commit(self, db):
        db.commit()

    @contextmanager
    def _db(self, *, write=False, initialize=False):
        self._check_path()
        if not self.path.exists() and not initialize:
            raise JournalError('No recorded summary operations', 'not_initialized')
        if initialize:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        db = None
        try:
            db = sqlite3.connect(self.path if write else self.path.as_uri() + '?mode=ro', uri=not write, timeout=5)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            if write:
                db.execute('PRAGMA synchronous=FULL')
                db.execute('BEGIN IMMEDIATE')
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables and initialize:
                for sql in (
                    'CREATE TABLE metadata(name TEXT PRIMARY KEY, value TEXT NOT NULL)',
                    'CREATE TABLE operations(id TEXT PRIMARY KEY, body TEXT NOT NULL)',
                    'CREATE TABLE target_claims(target TEXT PRIMARY KEY, operation_id TEXT NOT NULL REFERENCES operations(id))',
                    'CREATE TABLE materials(operation_id TEXT NOT NULL REFERENCES operations(id), kind TEXT NOT NULL, sha256 TEXT NOT NULL, content BLOB NOT NULL, PRIMARY KEY(operation_id,kind))',
                    'CREATE TABLE observations(id INTEGER PRIMARY KEY, operation_id TEXT NOT NULL REFERENCES operations(id), sink TEXT NOT NULL, body TEXT NOT NULL)',
                ):
                    db.execute(sql)
                db.executemany('INSERT INTO metadata VALUES (?,?)', [('schema_version', SCHEMA_VERSION), ('instance_id', str(uuid.uuid4()))])
                tables = {'metadata', 'operations', 'target_claims', 'materials', 'observations'}
            if tables != {'metadata', 'operations', 'target_claims', 'materials', 'observations'}:
                raise JournalError('Unsupported journal schema; preserve it', 'unsupported_schema')
            row = db.execute("SELECT value FROM metadata WHERE name='schema_version'").fetchone()
            if row is None or row[0] != SCHEMA_VERSION:
                raise JournalError('Unsupported journal schema version', 'unsupported_schema')
            instance = db.execute("SELECT value FROM metadata WHERE name='instance_id'").fetchone()
            if instance is None or not isinstance(instance[0], str):
                raise JournalError('Missing journal instance identity', 'unsupported_schema')
            try:
                uuid.UUID(instance[0])
            except ValueError as exc:
                raise JournalError('Invalid journal instance identity', 'unsupported_schema') from exc
            yield db
            if write:
                self._commit(db)
        except sqlite3.Error as exc:
            raise JournalError('Journal storage unavailable; no dispatch authorized', 'storage_unavailable') from exc
        finally:
            if db is not None:
                db.close()  # rolls back any uncommitted transaction

    def _get(self, db, operation_id):
        _id(operation_id)
        row = db.execute('SELECT substr(body,1,8193) AS body,length(CAST(body AS BLOB)) AS size FROM operations WHERE id=?', (operation_id,)).fetchone()
        if row is None:
            raise JournalError('Unknown summary operation', 'not_found')
        try:
            if row['size'] > MAX_METADATA_BYTES:
                raise ValueError('metadata oversized')
            body = json.loads(row['body'])
            if body['id'] != operation_id or type(body['schema_version']) is not int or body['schema_version'] != int(SCHEMA_VERSION) or type(body['revision']) is not int:
                raise ValueError('identity/schema mismatch')
            if not isinstance(body['sinks'], dict) or set(body['sinks']) != set(body['targets']):
                raise ValueError('sink mismatch')
            if not body['sinks'] or not set(body['sinks']) <= {'local', 'zotero'}:
                raise ValueError('invalid sink')
            for sink in body['sinks'].values():
                if sink['state'] not in {'prepared_unsent', 'dispatching', 'unknown', 'confirmed', 'rejected', 'compensated', 'conflicted'}:
                    raise ValueError('invalid state')
                if sink['state'] != 'prepared_unsent' and not _text(sink['dispatch_token']):
                    raise ValueError('missing dispatch identity')
            _validate_scope(body['source'], body['targets'], body['authorization'])
            candidate = body['candidate_sha256']
            if candidate is not None and (not isinstance(candidate, str) or not re.fullmatch('[0-9a-f]{64}', candidate)):
                raise ValueError('invalid candidate binding')
            if body['revision'] < 0:
                raise ValueError('invalid revision')
        except (ValueError, TypeError, KeyError) as exc:
            raise JournalError('Corrupt operation metadata; preserve it', 'corrupt_operation') from exc
        return body

    def _save(self, db, body):
        body['revision'] += 1
        # BEGIN IMMEDIATE serializes writers; revision is still explicit for
        # future caller contracts and evidence, not a lock against other apps.
        db.execute('UPDATE operations SET body=? WHERE id=?', (_metadata(body), body['id']))

    def reserve(self, operation_id, source, targets, authorization):
        """Explicit new intent or exact same-ID lookup; claims precede generation."""
        _id(operation_id)
        _metadata({'source': source, 'targets': targets, 'authorization': authorization})
        _validate_scope(source, targets, authorization)
        identity = {'source': source, 'targets': targets, 'authorization': authorization}
        with self._db(write=True, initialize=True) as db:
            if db.execute('SELECT 1 FROM operations WHERE id=?', (operation_id,)).fetchone():
                body = self._get(db, operation_id)
                if any(body[k] != v for k, v in identity.items()):
                    raise JournalError('Operation identity changed; no implicit new intent', 'intent_conflict')
                return body
            claims = [_hash(encoded([sink, target]).encode()) for sink, target in targets.items()]
            for claim in claims:
                if db.execute('SELECT 1 FROM target_claims WHERE target=?', (claim,)).fetchone():
                    raise JournalError('Target has an unresolved operation; check original receipt', 'target_unresolved')
            body = {'schema_version': int(SCHEMA_VERSION), 'id': operation_id, 'revision': 0, **identity,
                    'candidate_sha256': None, 'sinks': {sink: {'state': 'prepared_unsent', 'dispatch_token': None} for sink in targets}}
            db.execute('INSERT INTO operations VALUES (?,?)', (operation_id, _metadata(body)))
            db.executemany('INSERT INTO target_claims VALUES (?,?)', [(claim, operation_id) for claim in claims])
            return body

    def get(self, operation_id):
        with self._db() as db:
            return self._get(db, operation_id)

    def list(self, *, after='', limit=50):
        if type(limit) is not int or not 1 <= limit <= 50 or not isinstance(after, str):
            raise JournalError('Invalid bounded page', 'invalid_input')
        self._check_path()
        if not self.path.exists():
            return []
        with self._db() as db:
            return [self._get(db, r[0]) for r in db.execute('SELECT id FROM operations WHERE id>? ORDER BY id LIMIT ?', (after, limit))]

    def stage(self, operation_id, candidate, *, before=None, after=None):
        materials = {'candidate': candidate}
        if before is not None:
            materials['before'] = before
        if after is not None:
            materials['after'] = after
        for kind, raw in materials.items():
            if not isinstance(raw, bytes):
                raise JournalError('Materials require exact UTF-8 bytes', 'invalid_input')
            if len(raw) > (MAX_CANDIDATE_BYTES if kind == 'candidate' else MAX_SNAPSHOT_BYTES):
                raise JournalError('Material exceeds byte limit; no truncation', 'too_large')
            try:
                raw.decode('utf-8')
            except UnicodeError as exc:
                raise JournalError('Material is not UTF-8', 'invalid_input') from exc
        with self._db(write=True) as db:
            body = self._get(db, operation_id)
            if body['candidate_sha256'] is not None:
                kinds = [r[0] for r in db.execute('SELECT kind FROM materials WHERE operation_id=?', (operation_id,))]
                existing = {kind: self._material(db, operation_id, kind) for kind in kinds}
                if existing != materials:
                    raise JournalError('Staged material is immutable', 'intent_conflict')
                return body
            if any(s['state'] != 'prepared_unsent' for s in body['sinks'].values()) or ('local' in body['targets'] and set(materials) != {'candidate', 'before', 'after'}):
                raise JournalError('Cannot stage incomplete or dispatched material', 'invalid_transition')
            db.executemany('INSERT INTO materials VALUES (?,?,?,?)', [(operation_id, kind, _hash(raw), raw) for kind, raw in materials.items()])
            body['candidate_sha256'] = _hash(candidate)
            self._save(db, body)
            return body

    def material(self, operation_id, kind):
        with self._db() as db:
            self._get(db, operation_id)
            return self._material(db, operation_id, kind)

    def _material(self, db, operation_id, kind):
        if kind not in {'candidate', 'before', 'after'}:
            raise JournalError('Unknown material kind', 'invalid_input')
        limit = MAX_CANDIDATE_BYTES if kind == 'candidate' else MAX_SNAPSHOT_BYTES
        row = db.execute('SELECT sha256,length(content) AS size,substr(content,1,?) AS content FROM materials WHERE operation_id=? AND kind=?', (limit + 1, operation_id, kind)).fetchone()
        if row is None or row['size'] > limit or not isinstance(row['content'], bytes) or _hash(row['content']) != row['sha256']:
            raise JournalError('Material missing or changed; no dispatch', 'corrupt_material')
        return row['content']

    def dispatch(self, operation_id, sink):
        """Durably claim only; caller receives token after commit, no I/O callback."""
        with self._db(write=True) as db:
            body = self._get(db, operation_id)
            if sink not in body['sinks'] or body['sinks'][sink]['state'] != 'prepared_unsent' or body['candidate_sha256'] is None:
                raise JournalError('Dispatch not allowed; unknown is never replayable', 'invalid_transition')
            if _hash(self._material(db, operation_id, 'candidate')) != body['candidate_sha256']:
                raise JournalError('Candidate binding changed', 'corrupt_material')
            if sink == 'local':
                for kind in ('before', 'after'):
                    self._material(db, operation_id, kind)
            body['sinks'][sink] = {'state': 'dispatching', 'dispatch_token': str(uuid.uuid4())}
            self._save(db, body)
            return body

    def recover(self, operation_id):
        """Explicit recovery never dispatches; in-flight work may still acknowledge."""
        with self._db(write=True) as db:
            body = self._get(db, operation_id)
            changed = False
            for sink in body['sinks'].values():
                if sink['state'] == 'dispatching':
                    sink['state'] = 'unknown'
                    changed = True
            if changed:
                self._save(db, body)
            return body

    def acknowledge(self, operation_id, sink, dispatch_token, outcome):
        """Trusted adapter seam only: confirmed or positively rejected response.

        Never call from a generic content lookup, HTTP exception, or user string.
        No provider I/O occurs in this module. Token binds the exact
        claimed attempt, not authentication or proof of scientific acceptance.
        """
        if outcome not in _TERMINAL:
            raise JournalError('Unknown outcome is not a terminal receipt', 'invalid_input')
        with self._db(write=True) as db:
            body = self._get(db, operation_id)
            state = body['sinks'].get(sink)
            if state is None or not dispatch_token or state['dispatch_token'] != dispatch_token:
                raise JournalError('Acknowledgement belongs to another dispatch', 'stale_dispatch')
            if 'compensation' in state:
                # This token identifies the original write, not the newer
                # compensation attempt. Its late acknowledgement cannot resolve
                # uncertainty about whether the original bytes were restored.
                if outcome == 'confirmed' and state.get('write_acknowledged') is True:
                    return body
                raise JournalError('Original acknowledgement cannot resolve compensation', 'invalid_transition')
            if state['state'] == outcome:
                return body
            if state['state'] not in {'dispatching', 'unknown'}:
                raise JournalError('Conflicting terminal acknowledgement', 'invalid_transition')
            state['state'] = outcome
            state['basis'] = 'caller_reported_adapter_ack'
            self._save(db, body)
            if all(s['state'] in _TERMINAL for s in body['sinks'].values()):
                db.execute('DELETE FROM target_claims WHERE operation_id=?', (operation_id,))
            return body

    def observe(self, operation_id, sink, status):
        """Observation never changes write outcome/identity or clears a claim."""
        if status not in _OBSERVATIONS:
            raise JournalError('Unsupported observation', 'invalid_input')
        with self._db(write=True) as db:
            body = self._get(db, operation_id)
            if sink not in body['sinks']:
                raise JournalError('Observation outside operation scope', 'invalid_input')
            observation = _metadata({'status': status})
            latest = db.execute('SELECT body FROM observations WHERE operation_id=? AND sink=? ORDER BY id DESC LIMIT 1', (operation_id, sink)).fetchone()
            if latest is None or latest[0] != observation:
                db.execute('INSERT INTO observations(operation_id,sink,body) VALUES (?,?,?)', (operation_id, sink, observation))
            return body

    def observations(self, operation_id, *, after=0, limit=50):
        """Bounded receipt observations, no payload or automatic provider lookup."""
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 50:
            raise JournalError('Invalid observation page', 'invalid_input')
        with self._db() as db:
            self._get(db, operation_id)
            rows = db.execute('SELECT id,sink,substr(body,1,8193) AS body,length(CAST(body AS BLOB)) AS size FROM observations WHERE operation_id=? AND id>? ORDER BY id LIMIT ?', (operation_id, after, limit))
            result = []
            for row in rows:
                try:
                    value = json.loads(row['body'])
                    if row['size'] > MAX_METADATA_BYTES or value.get('status') not in _OBSERVATIONS:
                        raise ValueError('invalid observation')
                except (ValueError, TypeError, AttributeError) as exc:
                    raise JournalError('Corrupt observation; preserve it', 'corrupt_operation') from exc
                result.append({'id': row['id'], 'sink': row['sink'], **value})
            return result

    def conflicts(self, targets):
        """Exact logical-target lookup; no scans or provider calls."""
        self._check_path()
        if not self.path.exists():
            return []
        if not isinstance(targets, dict) or not targets or not set(targets) <= {'local', 'zotero'} or not all(_text(t) for t in targets.values()):
            raise JournalError('Invalid targets', 'invalid_input')
        with self._db() as db:
            found = set()
            for sink, target in targets.items():
                key = _hash(encoded([sink, target]).encode())
                row = db.execute('SELECT operation_id FROM target_claims WHERE target=?', (key,)).fetchone()
                if row:
                    self._get(db, row[0])
                    found.add(row[0])
            return sorted(found)

    def reject_unsent(self, operation_id, sink):
        """Trusted caller stopped before dispatch; not a not-found observation."""
        with self._db(write=True) as db:
            body = self._get(db, operation_id)
            state = body['sinks'].get(sink)
            if state is None or state['state'] != 'prepared_unsent':
                raise JournalError('Dispatched work cannot be marked unsent', 'invalid_transition')
            state.update(state='rejected', dispatch_token='unsent', basis='caller_reported_predispatch_refusal')
            self._save(db, body)
            if all(s['state'] in _TERMINAL for s in body['sinks'].values()):
                db.execute('DELETE FROM target_claims WHERE operation_id=?', (operation_id,))
            return body

    def compensation(self, operation_id, dispatch_token, status):
        """Record effective local state separately from the historical write ack."""
        if status not in {'restored', 'preserved_newer', 'compensation_unknown'}:
            raise JournalError('Invalid compensation outcome', 'invalid_input')
        with self._db(write=True) as db:
            body = self._get(db, operation_id)
            sink = body['sinks'].get('local')
            if sink is None or not dispatch_token or sink['dispatch_token'] != dispatch_token:
                raise JournalError('Compensation belongs to another dispatch', 'stale_dispatch')
            if sink['state'] not in {'dispatching', 'unknown'}:
                raise JournalError('Cannot overwrite terminal local outcome', 'invalid_transition')
            sink.update(state={'restored': 'compensated', 'preserved_newer': 'conflicted', 'compensation_unknown': 'unknown'}[status],
                        write_acknowledged=True, compensation=status)
            self._save(db, body)
            return body

    def lookup_for_apply(self, operation_id):
        """Explicit apply-only lookup serialized with first-use initialization.

        Unlike public get/list, this may initialize the empty private journal.
        It never claims a target or authorizes sink I/O by itself.
        """
        _id(operation_id)
        with self._db(write=True, initialize=True) as db:
            if not db.execute('SELECT 1 FROM operations WHERE id=?', (operation_id,)).fetchone():
                return None
            return self._get(db, operation_id)
