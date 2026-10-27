"""Optional local native-agent observations. No execution or semantic attestation."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from functools import lru_cache
from urllib.parse import urlencode

from jsonschema import Draft202012Validator

from .core import WorkspaceError, encoded, safe_path
from . import text_intake as local_files

MAX_PROFILE_BYTES = 4 * 1024 * 1024
MAX_MATERIAL_BYTES = 64 * 1024 * 1024
MAX_TOTAL_MATERIAL_BYTES = 128 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise WorkspaceError(message, 'invalid_discovery_profile')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'Duplicate JSON keys are not supported')
        result[key] = value
    return result


@lru_cache(maxsize=1)
def _validator():
    path = Path(__file__).parents[1] / 'schemas/research-discovery-observations-1.0.json'
    return Draft202012Validator(json.loads(path.read_text(encoding='utf-8')))


@contextmanager
def _open_regular(workspace, target):
    if not local_files.publication_supported():
        raise WorkspaceError('Safe discovery file access is unavailable on this platform; portable native export remains usable', 'unsupported_capability')
    relative = target.relative_to(workspace.root)
    with local_files._directory(workspace.root, relative.parts[:-1], create=False, private=False) as directory:
        fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            _require(stat.S_ISREG(os.fstat(fd).st_mode), 'Discovery inputs must be regular files')
            stream = os.fdopen(fd, 'rb')
            fd = None
            with stream:
                yield stream
            local_files._verify_location(workspace, relative.parts[:-1], directory, private=False)
        finally:
            if fd is not None:
                os.close(fd)


def _read_profile(workspace, path):
    target = safe_path(workspace.root, path, exists=True)
    try:
        with _open_regular(workspace, target) as stream:
            raw = stream.read(MAX_PROFILE_BYTES + 1)
        _require(len(raw) <= MAX_PROFILE_BYTES, 'Discovery profile exceeds the byte limit')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        # No input values in diagnostics: the profile can contain private research.
        error = next(_validator().iter_errors(value), None)
        if error is not None:
            location = '$' + ''.join(f'[{part}]' if isinstance(part, int) else '.' + str(part) for part in error.absolute_path)
            raise WorkspaceError(f'Discovery profile invalid at {location[:200]} ({error.validator})', 'invalid_discovery_profile')
        encoded(value).encode('utf-8')  # reject lone surrogates before paths/output
    except WorkspaceError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WorkspaceError('Discovery profile is not bounded valid UTF-8 JSON', 'invalid_discovery_profile') from exc
    return raw, value


def _ids(rows):
    ids = [row['id'] for row in rows]
    _require(len(ids) == len(set(ids)), 'Duplicate discovery IDs')
    return set(ids)


def _relative_path(path):
    _require(not path.startswith('/') and '\\' not in path and ':' not in path
             and path.split('/')[0].casefold() not in {'.research', '.git'}
             and all(part not in ('', '.', '..') for part in path.split('/')),
             'Discovery material path must be a confined relative path')


def _assess(workspace, project_id, value, raw):
    _require(value['project_id'] == project_id, 'Discovery profile belongs to another project')
    needs = _ids(value['needs']); attempts = _ids(value['attempts']); _ids(value['sources'])
    unresolved = {n['id'] for n in value['needs'] if n['status'] != 'covered'}
    residual = value['completion']['residual_need_ids']
    _require(len(residual) == len(set(residual)) and set(residual) <= needs, 'Invalid residual need references')
    _require(unresolved <= set(residual), 'Unresolved needs must remain in the completion record')
    if value['completion']['status'] == 'bounded-complete':
        _require(not residual, 'Unresolved needs cannot be bounded-complete')
    materials = []
    for a in value['attempts']:
        _require(a['need_ids'] and len(a['need_ids']) == len(set(a['need_ids']))
                 and set(a['need_ids']) <= needs, 'Invalid attempt need references')
        receipt = a['receipt']
        if receipt is not None:
            _require(receipt['reference'] is not None or receipt['material'] is not None, 'Empty receipt is not evidence')
            if receipt['material'] is not None:
                materials.append(('attempt', a['id'], receipt['material']))
        if a['status'] == 'observed':
            _require(a['tool'] is not None and receipt is not None, 'Observed attempts require a tool and observation reference')
        else:
            _require(a['outcome'] == 'unknown' and a['result_count'] is None,
                     'Unobserved attempts cannot claim a result')
        if a['outcome'] in {'timeout','denied','error','unknown'}:
            _require(a['result_count'] is None, 'Unknown or failed result count cannot be zero')
        if a['outcome'] == 'empty':
            _require(a['kind'] == 'search' and a['result_count'] == 0, 'Empty search requires an observed zero count')
        if a['kind'] == 'read':
            _require(a['result_count'] is None, 'Read observations are not search result counts')
    for need in value['needs']:
        if need['status'] == 'covered':
            _require(any(need['id'] in a['need_ids'] and a['status'] == 'observed'
                         and a['outcome'] in {'success', 'empty'} for a in value['attempts']),
                     'Covered needs require an observed successful attempt, not just a declaration')
    for source in value['sources']:
        _require(source['need_ids'] and len(source['need_ids']) == len(set(source['need_ids']))
                 and set(source['need_ids']) <= needs, 'Invalid source relevance need references')
        _require(len(source['attempt_ids']) == len(set(source['attempt_ids']))
                 and set(source['attempt_ids']) <= attempts, 'Invalid source attempt references')
        if source['reading_level'] in {'abstract','excerpt','full-text'}:
            _require(source['reading_ref'] is not None, 'Reading level requires an observation reference')
        if source['material'] is not None:
            materials.append(('source', source['id'], source['material']))
    bindings = []; cache = {}; total = 0
    for kind, ident, material in materials:
        path = material['path']; _relative_path(path)
        if path not in cache:
            target = safe_path(workspace.root, path)  # unsafe paths are errors, not unknown
            try:
                h = hashlib.sha256(); size = 0
                with _open_regular(workspace, target) as stream:
                    while chunk := stream.read(65536):
                        size += len(chunk); total += len(chunk)
                        _require(size <= MAX_MATERIAL_BYTES and total <= MAX_TOTAL_MATERIAL_BYTES,
                                 'Discovery material exceeds the processing byte limit')
                        h.update(chunk)
                cache[path] = ('read', h.hexdigest())
            except (FileNotFoundError, PermissionError, IsADirectoryError):
                cache[path] = ('unavailable', None)
        state, digest = cache[path]
        bindings.append({'kind':kind,'id':ident,'status':('current' if digest == material['sha256'] else 'stale') if state == 'read' else 'unknown'})
    return {'structure':'valid','binding':'current' if all(b['status']=='current' for b in bindings) else 'not-current',
            'input_sha256':hashlib.sha256(raw).hexdigest(),'material_bindings':bindings,
            'material_reference_count':len(bindings),
            'receipt_scope':'caller-observed; saved captures are byte-checked, not authenticated',
            'declared_attempts':sum(a['status']=='declared' for a in value['attempts']),
            'planned_attempts':sum(a['status']=='planned' for a in value['attempts']),
            'unavailable_attempts':sum(a['status']=='unavailable' for a in value['attempts']),
            'caller_observed_attempts':sum(a['status']=='observed' for a in value['attempts']),
            'unknown_source_versions':[s['id'] for s in value['sources'] if s['version'] is None],
            'unbound_source_material':[s['id'] for s in value['sources'] if s['material'] is None],
            'completion':value['completion'],'execution_verified':False,'semantic_assessment':'not-performed',
            'human_selection':'outside-checker','execution_authorized':False,
            'limits':['Observations and reading levels are caller supplied, not authenticated execution or reading proof.',
                      'Hashes bind selected bytes, not authenticity, semantic support, completeness or future file stability.']}


def check_profile(workspace, project_id, path):
    raw, value = _read_profile(workspace, path)
    return _assess(workspace, project_id, value, raw)


def save_profile(workspace, project_id, path):
    workspace.project(project_id)
    raw, value = _read_profile(workspace, path)
    report = _assess(workspace, project_id, value, raw)
    _require(report['binding'] == 'current', 'Changed or unavailable material cannot be saved as a current snapshot')
    snapshot = (encoded(value) + '\n').encode('utf-8')
    _require(len(snapshot) <= MAX_PROFILE_BYTES, 'Canonical discovery profile exceeds the byte limit')
    digest = hashlib.sha256(snapshot).hexdigest()
    relative = f'hub-discovery/{digest}.json'
    local_files._publish_copy(workspace, relative, snapshot, limit=MAX_PROFILE_BYTES)
    try:
        artifact = workspace.register_artifact(project_id, path=relative, role='evidence', expected_sha256=digest)
    except WorkspaceError:
        raise
    except (OSError, sqlite3.Error):
        return {'ok':False,'code':'registration_incomplete','snapshot_path':relative,
                'snapshot_sha256':digest,'message':'Snapshot saved; registration not confirmed. Explicit same-input save can reconcile; no task or external action ran.'}
    return {'ok':True,'artifact':artifact,'report':report,'snapshot_sha256':digest,
            'view_path':'/app/#literature?' + urlencode({'project':project_id,'discovery':artifact['id']})}


def _registered_profile(workspace, project_id, artifact_id):
    workspace.project(project_id)
    with workspace.db() as db:
        row = db.execute('SELECT body FROM artifacts WHERE project=? AND id=?', (project_id, artifact_id)).fetchone()
    item = json.loads(row[0]) if row else None
    _require(isinstance(item, dict) and item.get('role') == 'evidence' and item.get('path','').startswith('hub-discovery/'),
             'Discovery artifact is not registered in this project')
    raw, value = _read_profile(workspace, item['path'])
    _require(hashlib.sha256(raw).hexdigest() == item['sha256'], 'Registered discovery snapshot changed')
    return item, raw, value


def replay_profile(workspace, project_id, artifact_id):
    item, raw, value = _registered_profile(workspace, project_id, artifact_id)
    report = _assess(workspace, project_id, value, raw)
    return {'ok':report['binding'] == 'current','artifact':{**item, 'current':True},'report':report}


def view_profile(workspace, project_id, artifact_id):
    """Read-only display of one validated snapshot; never disclose capture contents."""
    item, raw, value = _registered_profile(workspace, project_id, artifact_id)
    report = _assess(workspace, project_id, value, raw)
    # Explicit display allowlist: receipt references/material paths are not UI data.
    source_fields = ('id', 'work_id', 'title', 'locator', 'access', 'need_ids',
                     'relevance', 'version', 'reading_level', 'attempt_ids')
    attempt_fields = ('id', 'need_ids', 'kind', 'tool', 'input', 'status', 'outcome', 'result_count')
    return {'ok': True, 'artifact': {'id': item['id'], 'sha256': item['sha256'],
                                   'registered_at': item.get('registered_at')},
            'report': report,
            'discovery': {'format': value['format'], 'project_id': value['project_id'],
                          'run_id': value['run_id'], 'brief': value['brief'],
                          'needs': value['needs'], 'completion': value['completion'],
                          'sources': [{k: source[k] for k in source_fields} for source in value['sources']],
                          'attempts': [{k: attempt[k] for k in attempt_fields} for attempt in value['attempts']]}}
