"""Journal connection for actual legacy apply; no provider implementation here.

Generation precedes this seam in summarize_cluster. The scope here is durable
claims before destination I/O, not before model invocation. No automatic retry.
"""
from dataclasses import asdict
import hashlib
from pathlib import Path

from .summary_journal import SummaryJournal, JournalError, MAX_SNAPSHOT_BYTES, MAX_CANDIDATE_BYTES, scope_digest
from .workspace.core import encoded, safe_path


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _receipt(journal, operation_id):
    body = journal.get(operation_id)
    return {'operation_id': operation_id, 'version': 2, 'sinks': body['sinks'],
            'authorization': body['authorization'],
            'source_sha256': body['source']['sha256'], 'source_coverage': body['source']['coverage'],
            'source_provenance': 'apply_time_extracted_abstract_not_attested_model_input',
            'candidate_sha256': body['candidate_sha256'], 'observations': journal.observations(operation_id)}


def apply_entry(cfg, paper, summary, zot, write_obsidian, write_zotero, *, provenance):
    # Import at call time to keep the established synthetic seams patchable.
    from . import summarize as s
    result = s._PerPaperOutcome(slug=summary.paper_slug)
    if not write_obsidian and not write_zotero:
        result.applied = True
        return result
    root = getattr(cfg, 'root', None)
    if root is None:
        control = getattr(cfg, 'research_hub_dir', None)
        root = Path(control).parent if control is not None else Path(cfg.raw).parent
    journal = SummaryJournal(root)
    operation_id = None
    blocking_ids = []
    local_written = False
    original = new_text = None
    tokens = {}
    try:
        path = safe_path(Path(cfg.raw).resolve(), Path(paper['path']).absolute(), exists=True)
        targets = {}
        if write_obsidian:
            targets['local'] = str(path)
        if write_zotero:
            library_id = getattr(zot, 'library_id', None) or getattr(cfg, 'zotero_library_id', None)
            library_type = getattr(zot, 'library_type', None) or getattr(cfg, 'zotero_library_type', None)
            library_type = {'users': 'user', 'groups': 'group'}.get(library_type, library_type)
            if not isinstance(library_id, (str, int)) or isinstance(library_id, bool) or not str(library_id) or library_type not in {'user', 'group'}:
                raise JournalError('Exact remote library identity is required before writes', 'destination_unknown')
            configured_id = getattr(cfg, 'zotero_library_id', None)
            configured_type = getattr(cfg, 'zotero_library_type', None)
            configured_type = {'users': 'user', 'groups': 'group'}.get(configured_type, configured_type)
            # Numeric aliases must not bypass an unresolved logical target.
            library_id = str(int(str(library_id))) if str(library_id).isdigit() else str(library_id)
            if configured_id is not None and str(configured_id).isdigit():
                configured_id = str(int(str(configured_id)))
            if ((configured_id is not None and str(configured_id) != str(library_id)) or
                    (configured_type is not None and configured_type != library_type)):
                raise JournalError('Configured destination and client identity disagree; no writes', 'destination_changed')
            if not paper.get('zotero_key'):
                raise JournalError('no zotero-key in frontmatter', 'destination_unknown')
            targets['zotero'] = encoded([library_type, str(library_id), paper['zotero_key'], 'research-hub:summary:v1'])
        # This hash binds the already extracted abstract used by this legacy
        # pipeline, not original PDF bytes/full-note personal content.
        source = {'reference': str(path) + '#legacy-extracted-abstract-v1',
                  'sha256': _sha(paper['abstract'].encode('utf-8')), 'coverage': 'abstract'}
        html = s._build_zotero_note_html(paper, summary) if write_zotero else None
        candidate = encoded({'summary': asdict(summary), 'zotero_html': html}).encode('utf-8')
        if len(candidate) > MAX_CANDIDATE_BYTES:
            raise JournalError('Candidate exceeds byte limit; no claim or write', 'too_large')
        operation_id = _sha(encoded({'scope': scope_digest(source, targets), 'candidate': _sha(candidate)}).encode())
        auth = {'kind': provenance, 'reference': 'legacy-apply:' + operation_id, 'scope_sha256': scope_digest(source, targets)}
        # Pure local preflight precedes reservation so invalid/oversized input
        # cannot strand a new target claim. Generation has already happened.
        existing = journal.lookup_for_apply(operation_id)
        if existing is not None:
            # A retry through another transport retains original invocation
            # provenance; it cannot manufacture a new approval or new intent.
            auth = existing['authorization']
        if (existing is None or existing['candidate_sha256'] is None) and write_obsidian:
            with path.open('rb') as handle:
                before = handle.read(MAX_SNAPSHOT_BYTES + 1)
            if len(before) > MAX_SNAPSHOT_BYTES:
                raise JournalError('Local snapshot exceeds byte limit; original preserved', 'too_large')
            original = before.decode('utf-8')
            new_text = s._replace_obsidian_block(original, summary)
            if len(new_text.encode('utf-8')) > MAX_SNAPSHOT_BYTES:
                raise JournalError('Intended note exceeds byte limit; original preserved', 'too_large')
        try:
            body = journal.reserve(operation_id, source, targets, auth)
        except JournalError as exc:
            if exc.code == 'target_unresolved':
                blocking_ids = journal.conflicts(targets)
                if blocking_ids:
                    # Preserve the durable blocker even if reading its receipt
                    # fails; never substitute the new, unrecorded candidate ID.
                    operation_id = blocking_ids[0]
                    result.receipt = _receipt(journal, operation_id)
                    result.receipt['blocking_operation_ids'] = blocking_ids
            raise
        states = [v['state'] for v in body['sinks'].values()]
        if states and all(v == 'confirmed' for v in states):
            result.receipt = _receipt(journal, operation_id)
            result.skipped_reason = 'already confirmed; existing receipt returned without another write'
            return result
        if any(v != 'prepared_unsent' for v in states):
            journal.recover(operation_id)
            raise JournalError('Original operation requires reconciliation; no automatic retry', 'reconcile_required')
        if write_obsidian:
            if original is None:
                # Prepared-unsent recovery reuses immutable exact staged bytes.
                original = journal.material(operation_id, 'before').decode('utf-8')
                new_text = journal.material(operation_id, 'after').decode('utf-8')
                before = original.encode('utf-8')
            journal.stage(operation_id, candidate, before=before, after=new_text.encode('utf-8'))
        else:
            journal.stage(operation_id, candidate)
        if write_obsidian:
            tokens['local'] = journal.dispatch(operation_id, 'local')['sinks']['local']['dispatch_token']
            # Guard against an already-visible change since snapshot/staging.
            with path.open('rb') as handle:
                current = handle.read(MAX_SNAPSHOT_BYTES + 1)
            if current != original.encode('utf-8'):
                raise JournalError('Local note changed before write; preserved', 'source_changed')
            s._write_note_text(path, new_text)
            local_written = True
        if write_zotero:
            def before_write():
                tokens['zotero'] = journal.dispatch(operation_id, 'zotero')['sinks']['zotero']['dispatch_token']
            try:
                result.warning = s._write_zotero_child_note(zot, paper['zotero_key'], html, before_write=before_write)
            except Exception as exc:
                status = None
                if local_written:
                    rollback = s._rollback_summary_note(path, original, new_text)
                    status = ('restored' if rollback.startswith('local note restored') else
                              'preserved_newer' if rollback.startswith('local rollback skipped') else 'compensation_unknown')
                else:
                    rollback = ''
                journal.recover(operation_id)
                if status is not None:
                    journal.observe(operation_id, 'local', status)
                    journal.compensation(operation_id, tokens['local'], status)
                # No callback means ownership/read/commit failed before remote
                # dispatch. Do not mistake transport exceptions after callback
                # for proven rejection, even if their text says offline/conflict.
                if 'zotero' not in tokens:
                    journal.reject_unsent(operation_id, 'zotero')
                label = 'zotero write outcome unknown' if 'zotero' in tokens else 'zotero write not dispatched'
                result.error = f'{label}: {exc}' + (f'; {rollback}' if rollback else '')
                result.receipt = _receipt(journal, operation_id)
                return result
            # Persist acknowledgements only after positive adapter return. An
            # ensuing journal failure is not proof of failed destination writes.
            journal.acknowledge(operation_id, 'zotero', tokens['zotero'], 'confirmed')
        if local_written:
            journal.acknowledge(operation_id, 'local', tokens['local'], 'confirmed')
        result.applied = True
        result.obsidian_written = local_written
        result.zotero_written = write_zotero
        result.receipt = _receipt(journal, operation_id)
        return result
    except Exception as exc:
        # Preserve the structured batch and original uncertain identity even if
        # the journal itself cannot persist a later receipt.
        dispatched = bool(tokens)
        result.error = ('apply outcome requires reconciliation' if dispatched else 'apply not dispatched') + f': {exc}'
        if operation_id is not None and result.receipt is None:
            try:
                journal.recover(operation_id)
                result.receipt = _receipt(journal, operation_id)
            except (JournalError, OSError):
                result.receipt = {'version': 2, 'operation_id': operation_id, 'status': 'receipt_unavailable',
                                  # Unreadable history cannot prove an earlier invocation was unsent.
                                  'dispatch_may_have_started': True,
                                  'current_attempt_dispatched': dispatched}
                result.error = f'apply outcome requires reconciliation; prior receipt unavailable: {exc}'
        if result.receipt is not None and blocking_ids:
            result.receipt['blocking_operation_ids'] = blocking_ids
        return result
