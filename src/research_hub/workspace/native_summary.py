"""Explicit authored, source-bound summaries. Validation is not semantic acceptance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import PurePosixPath

from .core import WorkspaceError, digest, encoded, now

SCHEMA = 'native-source-summary-v1'
SECTIONS = ('why', 'objective', 'methods', 'findings', 'conclusions', 'key_points', 'limitations')
MAX_ENVELOPE = 256 * 1024
MAX_FILE = 4 * 1024 * 1024
PRIVATE_FIELDS = {'native_summary', 'native_summary_history'}
FIELDS = {'schema', 'project_id', 'source_record_id', 'source', 'source_revision',
          'expected_revision', 'selections', 'sections', 'reading_scope'}
MARKERS = {'human_acceptance': 'pending', 'semantic_support': 'not_assessed'}


def fail(message='Invalid native summary envelope', code='invalid_source'):
    raise WorkspaceError(message, code)


def _string(value, limit=MAX_ENVELOPE):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        fail()
    try:
        if len(value.encode('utf-8')) > limit:
            fail()
    except UnicodeError:
        fail()
    return value


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            fail('Duplicate JSON keys are not allowed')
        result[k] = v
    return result


def parse(raw):
    _string(raw)
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: fail())
        # Also reject escaped NUL and surrogate code points in all JSON strings.
        def walk(v):
            if isinstance(v, str):
                if '\x00' in v:
                    fail()
                v.encode('utf-8')
            elif isinstance(v, dict):
                for k, child in v.items():
                    walk(k)
                    walk(child)
            elif isinstance(v, list):
                for child in v:
                    walk(child)
        walk(value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        fail()


def project_records(records):
    """Exclude ONLY native authored prose, not other legacy scientific fields."""
    return [{**r, 'data': {k: v for k, v in r['data'].items() if k not in PRIVATE_FIELDS}}
            if r.get('kind') == 'source' and isinstance(r.get('data'), dict) else r for r in records]


def snapshot_records(records):
    """Presence only in library transport; never disclose unvalidated saved prose."""
    return [{**projected, **({'native_summary_available': True}
                            if original.get('kind') == 'source'
                            and isinstance(original.get('data'), dict)
                            and 'native_summary' in original['data'] else {})}
            for original, projected in zip(records, project_records(records))]


def contains_native(records):
    return any(isinstance(r, dict) and r.get('kind') == 'source'
               and isinstance(r.get('data'), dict) and PRIVATE_FIELDS.intersection(r['data'])
               for r in records) if isinstance(records, list) else False


def read_path(workspace, relative, limit):
    """Pin every directory and leaf; never resolve/follow user-supplied symlinks."""
    from .text_intake import _directory, _read_file, _verify_location
    if not (os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY')
            and os.open in os.supports_dir_fd):
        fail('Safe native-summary file reads are unavailable on this platform', 'unsupported_capability')
    _string(relative, 4096)
    p = PurePosixPath(relative)
    if p.is_absolute() or '\\' in relative or any(x in ('', '.', '..') for x in relative.split('/')):
        fail('Select a workspace-relative regular file', 'unsafe_path')
    try:
        with _directory(workspace.root, p.parts[:-1], create=False, private=False) as directory:
            raw = _read_file(directory, p.name, limit=limit)
            _verify_location(workspace, p.parts[:-1], directory, private=False)
    except OSError as exc:
        raise WorkspaceError('Selected file is unavailable', 'source_unavailable') from exc
    if len(raw) > limit:
        fail('Selected file exceeds the native-summary limit', 'context_limit')
    return raw


def _record(db, project, source):
    _string(project, 2000)
    _string(source, 2000)
    row = db.execute("SELECT body FROM records WHERE project=? AND id=? AND kind='source'", (project, source)).fetchone()
    if row is None:
        fail('Selected project source is unavailable')
    data = json.loads(row[0])
    if not isinstance(data, dict):
        fail()
    for key in ('title', 'locator'):
        _string(data.get(key), 2000)
    return {'id': source, 'kind': 'source', 'data': data}


def _scope(record):
    value = record['data'].get('reading_scope', 'unknown')
    return _string(value, 2000)


def _base(record):
    return digest(project_records([record])[0])


def _selection(workspace, db, project, source, selections):
    if not isinstance(selections, list) or not 1 <= len(selections) <= 8:
        fail('Select one to eight owned evidence files')
    result, texts, seen = [], {}, set()
    for s in selections:
        if not isinstance(s, dict) or set(s) != {'artifact_id', 'start', 'end'}:
            fail()
        aid = _string(s['artifact_id'], 2000)
        if aid in seen:
            fail('Select each artifact only once')
        seen.add(aid)
        row = db.execute('SELECT body FROM artifacts WHERE project=? AND id=?', (project, aid)).fetchone()
        a = json.loads(row[0]) if row else {}
        if (a.get('id') != aid or a.get('project_id') != project or a.get('source_record_id') != source
                or a.get('role') != 'evidence' or a.get('superseded_by')):
            fail('Evidence must be current and owned by the selected source')
        from ._source_storage import is_blob, row as blob_row
        if is_blob(a):
            raw = blob_row(db, a)['content']
        else:
            path = a.get('path')
            if not isinstance(path, str) or PurePosixPath(path).suffix.lower() not in {'.txt', '.md'}:
                fail('Native summaries require UTF-8 txt or md evidence')
            raw = read_path(workspace, path, MAX_FILE)
        sha = hashlib.sha256(raw).hexdigest()
        if sha != a.get('sha256'):
            fail('Selected evidence changed', 'stale_input')
        try:
            text = raw.decode('utf-8')
        except UnicodeError:
            fail('Selected evidence is not UTF-8')
        _string(text, MAX_FILE)
        start, end = s['start'], s['end']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            fail('Invalid Python Unicode selection offsets')
        selected = text[start:end]
        _string(selected, MAX_ENVELOPE)
        result.append({**s, 'sha256': sha, 'text_sha256': hashlib.sha256(selected.encode('utf-8')).hexdigest()})
        texts[aid] = text
    if sum(len(texts[s['artifact_id']][s['start']:s['end']].encode('utf-8')) for s in result) > MAX_ENVELOPE:
        fail('Selected text exceeds the context limit', 'context_limit')
    return result, texts


def validate(value, *, saved=False):
    keys = FIELDS | (set(MARKERS) | {'saved_at'} if saved else set())
    if not isinstance(value, dict) or set(value) != keys or value.get('schema') != SCHEMA:
        fail()
    if saved and (any(value.get(k) != v for k, v in MARKERS.items()) or not isinstance(value['saved_at'], str)):
        fail()
    for key in ('project_id', 'source_record_id'):
        _string(value[key], 2000)
    for key in ('source_revision', 'expected_revision'):
        v = value[key]
        if not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v):
            fail()
    if not isinstance(value['source'], dict) or set(value['source']) != {'title', 'locator'}:
        fail()
    for v in value['source'].values():
        _string(v, 2000)
    _string(value['reading_scope'], 2000)
    sels = value['selections']
    if not isinstance(sels, list) or not 1 <= len(sels) <= 8:
        fail()
    seen = set()
    for s in sels:
        if not isinstance(s, dict) or set(s) != {'artifact_id', 'start', 'end', 'sha256', 'text_sha256'}:
            fail()
        _string(s['artifact_id'], 2000)
        if s['artifact_id'] in seen:
            fail()
        seen.add(s['artifact_id'])
        if type(s['start']) is not int or type(s['end']) is not int or not 0 <= s['start'] < s['end']:
            fail()
        for key in ('sha256', 'text_sha256'):
            v = s[key]
            if not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v):
                fail()
    sections = value['sections']
    if not isinstance(sections, dict) or set(sections) != set(SECTIONS):
        fail()
    for items in sections.values():
        if not isinstance(items, list) or not 1 <= len(items) <= 12:
            fail()
        for item in items:
            if not isinstance(item, dict) or set(item) != {'text', 'status', 'reason', 'evidence'}:
                fail()
            _string(item['text'], 12000)
            _string(item['reason'], 12000)
            if item['status'] not in ('supported', 'analyst_inference', 'unknown'):
                fail()
            evidence = item['evidence']
            if not isinstance(evidence, list) or len(evidence) > 8 or (item['status'] == 'supported' and not evidence):
                fail()
            for e in evidence:
                if not isinstance(e, dict) or set(e) != {'artifact_id', 'quote', 'start', 'end'}:
                    fail()
                _string(e['artifact_id'], 2000)
                _string(e['quote'], 12000)
                if type(e['start']) is not int or type(e['end']) is not int or e['start'] < 0 or e['end'] <= e['start']:
                    fail()
    # A bounded serialized object, including escaped Unicode, not just prose.
    if len(encoded(value).encode('utf-8')) > MAX_ENVELOPE:
        fail('Native summary exceeds envelope limit', 'context_limit')


def _bound(workspace, db, record, value):
    validate(value, saved='saved_at' in value)
    if value['reading_scope'] != _scope(record) or value['source'] != {k: record['data'][k] for k in ('title', 'locator')} or value['source_revision'] != _base(record):
        fail('Source revision changed', 'stale_input')
    current, texts = _selection(workspace, db, value['project_id'], value['source_record_id'],
                               [{k: s[k] for k in ('artifact_id', 'start', 'end')} for s in value['selections']])
    if current != value['selections']:
        fail('Evidence selection changed', 'stale_input')
    for items in value['sections'].values():
        for item in items:
            for e in item['evidence']:
                s = next((s for s in current if s['artifact_id'] == e['artifact_id']), None)
                if s is None or not s['start'] <= e['start'] < e['end'] <= s['end'] or texts[e['artifact_id']][e['start']:e['end']] != e['quote']:
                    fail('Evidence quote does not match selected Python Unicode range')


class NativeSummary:
    def __init__(self, workspace):
        self.workspace = workspace

    def context(self, project_id, *, source_record_id, selections):
        with self.workspace.db() as db:
            record = _record(db, project_id, source_record_id)
            selected, texts = _selection(self.workspace, db, project_id, source_record_id, selections)
        return {'ok': True, 'context': {'schema': SCHEMA, 'project_id': project_id,
                'source_record_id': source_record_id, 'source': {k: record['data'][k] for k in ('title', 'locator')},
                'reading_scope': _scope(record), 'source_revision': _base(record), 'expected_revision': digest(record), 'selections': selected,
                'selected_text': {s['artifact_id']: texts[s['artifact_id']][s['start']:s['end']] for s in selected},
                'coordinate_frame': 'file/python-unicode-codepoints', **MARKERS}}

    def import_summary(self, project_id, *, envelope=None, path=None):
        if (envelope is None) == (path is None):
            fail('Provide exactly one authored envelope or workspace-relative path')
        if path is not None:
            try:
                envelope = read_path(self.workspace, path, MAX_ENVELOPE).decode('utf-8')
            except UnicodeError:
                fail()
        value = parse(envelope)
        validate(value)
        if value['project_id'] != project_id:
            fail('Summary belongs to a different project')
        with self.workspace.db(write=True) as db:
            record = _record(db, project_id, value['source_record_id'])
            _bound(self.workspace, db, record, value)
            data = record['data']
            previous, history = data.get('native_summary'), data.get('native_summary_history', [])
            if not isinstance(history, list) or len(history) > 20:
                fail('Existing native summary history requires review')
            for entry in history:
                validate(entry, saved=True)
            if previous is not None:
                validate(previous, saved=True)
                if {k: previous[k] for k in FIELDS} == value:
                    return {'ok': True, 'reused': True, 'native_summary': previous}
            if value['expected_revision'] != digest(record):
                fail('Source or summary changed; reload context', 'stale_input')
            # The stored envelope must fit the same bound as subsequent reads.
            # Validate metadata overhead before mutating either summary or history.
            saved = {**value, **MARKERS, 'saved_at': now()}
            validate(saved, saved=True)
            if previous is not None:
                if len(history) == 20:
                    fail('Native summary history is full; no history was discarded', 'history_full')
                data['native_summary_history'] = [*history, previous]
            data['native_summary'] = saved
            db.execute("UPDATE records SET body=? WHERE project=? AND id=? AND kind='source'",
                       (encoded(data), project_id, record['id']))
        return {'ok': True, 'reused': False, 'native_summary': data['native_summary']}

    def read(self, project_id, *, source_record_id):
        with self.workspace.db() as db:
            record = _record(db, project_id, source_record_id)
            value = record['data'].get('native_summary')
            status = 'missing'
            if value is not None:
                try:
                    validate(value, saved=True)
                    if value.get('project_id') != project_id or value.get('source_record_id') != source_record_id:
                        fail()
                    _bound(self.workspace, db, record, value)
                    status = 'current'
                except WorkspaceError as error:
                    # Inability to read is unknown, not evidence of a changed
                    # source. Both outcomes still hide all saved prose.
                    status = ('unavailable' if error.code in {'unsupported_capability', 'source_unavailable'}
                              else 'stale')
                except (ValueError, TypeError, KeyError, AttributeError):
                    status = 'stale'
        return {'ok': True, 'status': status, 'native_summary': value if status == 'current' else None, **MARKERS}


    def export_markdown(self, project_id, *, source_record_id):
        """Render only a currently bound selected summary; never write a vault."""
        from .native_summary_markdown import render
        result = self.read(project_id, source_record_id=source_record_id)
        if result['status'] != 'current':
            return {'ok': False, 'status': result['status'], 'markdown': None,
                    'code': 'summary_not_current', **MARKERS}
        return {'ok': True, 'status': 'current', 'markdown': render(result['native_summary']),
                'format': 'markdown', **MARKERS}
