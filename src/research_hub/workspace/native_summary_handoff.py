"""Pure draft composition against an explicit snapshot, not a save or live gate.

This candidate helper does not read a workspace, infer source ownership, refresh
revisions, run a model or assess claim support. Existing import rechecks live
source/evidence and compare-and-save revisions before persisting the envelope.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from .core import encoded
from .native_summary import FIELDS, MARKERS, MAX_ENVELOPE, SECTIONS, fail, validate

CONTEXT_FIELDS = (FIELDS - {'sections'}) | {
    'selected_text', 'coordinate_frame', *MARKERS,
}


def compose(context, sections):
    """Copy frozen context fields and resolve only exact unambiguous quotes.

    ``context`` is the inner object returned by native-summary-context, not its
    transport wrapper. ``sections`` keeps the existing seven-section shape.
    Each evidence object must identify an explicitly selected artifact and may
    omit both offsets; a unique literal match then supplies file/codepoint
    offsets. Existing explicit offsets are verified and never corrected.
    """
    if (not isinstance(context, dict) or set(context) != CONTEXT_FIELDS
            or context.get('coordinate_frame') != 'file/python-unicode-codepoints'
            or any(context.get(key) != value for key, value in MARKERS.items())):
        fail('Select an unchanged native-summary context snapshot')
    # Bound caller objects and ensure ordinary finite, encodable JSON before
    # copying. Context includes selected text in addition to envelope metadata.
    try:
        context_size = len(encoded(context).encode('utf-8'))
        sections_size = len(encoded(sections).encode('utf-8'))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        fail('Use bounded JSON context and summary sections')
    if context_size > 2 * MAX_ENVELOPE:
        fail('Context snapshot exceeds the handoff limit', 'context_limit')
    if sections_size > MAX_ENVELOPE:
        fail('Summary sections exceed the handoff limit', 'context_limit')
    try:
        c, authored = deepcopy(context), deepcopy(sections)
    except RecursionError:
        fail('Use bounded JSON context and summary sections')
    selected_text = c['selected_text']
    if (not isinstance(selected_text, dict) or not isinstance(c['selections'], list)
            or not 1 <= len(c['selections']) <= 8):
        fail('Invalid selected-text snapshot')
    if not isinstance(authored, dict) or set(authored) != set(SECTIONS):
        fail('Provide all seven authored summary sections')
    selections = {}
    for selection in c['selections']:
        if (not isinstance(selection, dict)
                or set(selection) != {'artifact_id', 'sha256', 'text_sha256', 'start', 'end'}):
            fail('Invalid selected-text snapshot')
        aid = selection['artifact_id']
        if not isinstance(aid, str) or aid in selections:
            fail('Select each artifact exactly once')
        start, end = selection['start'], selection['end']
        text = selected_text.get(aid)
        if (type(start) is not int or type(end) is not int
                or not 0 <= start < end or not isinstance(text, str)
                or len(text) != end - start or '\x00' in text):
            fail('Selected text does not match the declared Unicode range')
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != selection['text_sha256']:
            fail('Selected text does not match its snapshot hash')
        selections[aid] = selection
    if set(selected_text) != set(selections):
        fail('Selected text must contain only the declared artifacts')
    if sum(len(text.encode('utf-8')) for text in selected_text.values()) > MAX_ENVELOPE:
        fail('Selected text exceeds the context limit', 'context_limit')

    for items in authored.values():
        if not isinstance(items, list):
            fail('Invalid authored section')
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('evidence'), list):
                fail('Invalid authored evidence')
            for evidence in item['evidence']:
                if not isinstance(evidence, dict) or set(evidence) not in (
                    {'artifact_id', 'quote'}, {'artifact_id', 'quote', 'start', 'end'},
                ):
                    fail('Evidence requires an artifact and quote, with both offsets or neither')
                aid, quote = evidence['artifact_id'], evidence['quote']
                if not isinstance(aid, str) or aid not in selections:
                    fail('Evidence must name an explicitly selected artifact')
                if not isinstance(quote, str) or not quote or not quote.strip():
                    fail('Evidence requires an exact nonempty quote')
                selection, text = selections[aid], selected_text[aid]
                if 'start' not in evidence:
                    index = text.find(quote)
                    if index < 0:
                        fail('Evidence quote is absent from selected text')
                    if text.find(quote, index + 1) >= 0:
                        fail('Evidence quote is ambiguous; supply explicit Unicode offsets')
                    evidence['start'] = selection['start'] + index
                    evidence['end'] = evidence['start'] + len(quote)
                start, end = evidence['start'], evidence['end']
                if (type(start) is not int or type(end) is not int
                        or not selection['start'] <= start < end <= selection['end']
                        or text[start-selection['start']:end-selection['start']] != quote):
                    fail('Evidence quote does not match selected Python Unicode range')

    envelope = {key: c[key] for key in FIELDS if key != 'sections'}
    envelope['sections'] = authored
    validate(envelope)
    # Reserve the same saved-marker overhead as the importer, conservatively
    # using a microsecond UTC timestamp. Never manufacture a saved envelope.
    validate({**envelope, **MARKERS, 'saved_at': '2000-01-01T00:00:00.000000Z'}, saved=True)
    return envelope


def preview(root, project_id, *, source_record_id, context_path, sections_path):
    """Read two explicitly selected files, without opening or writing a ledger.

    This checks a snapshot, NOT current ownership/freshness. Only the existing
    explicit import operation may recheck live state and persist the result.
    Do not resolve the root before the pinned reader checks its ancestors.
    """
    from .native_summary import _pairs, read_path

    selected = SimpleNamespace(root=Path(root).expanduser().absolute())

    def read_json(path, limit):
        raw = read_path(selected, path, limit)
        try:
            return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                              parse_constant=lambda _: fail())
        except (ValueError, UnicodeError, RecursionError):
            fail('Selected handoff input must be strict bounded UTF-8 JSON')

    context = read_json(context_path, 2 * MAX_ENVELOPE)
    if isinstance(context, dict) and set(context) == {'ok', 'context'} and context['ok'] is True:
        context = context['context']
    sections = read_json(sections_path, MAX_ENVELOPE)
    envelope = compose(context, sections)
    if envelope['project_id'] != project_id or envelope['source_record_id'] != source_record_id:
        fail('Context belongs to a different selected project or source')
    return {'ok': True, 'mode': 'preview', 'binding': 'snapshot_only',
            'envelope': envelope, **MARKERS}
