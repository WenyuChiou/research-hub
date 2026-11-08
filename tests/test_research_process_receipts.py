"""Synthetic boundary checks, not evidence of live research or semantic truth."""
from copy import deepcopy
from pathlib import Path

from research_hub.direction_review import validate_direction_review
from research_hub.evidence_harness import validate_evidence_packet
from scripts.verify_source_grounded_research import build_fixture
from tests.test_direction_review import record  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def test_native_stage_one_has_receipt_and_capability_boundaries():
    text = ' '.join((ROOT / 'skills/research-hub/references/research-protocol.md').read_text(encoding='utf-8').split())
    for marker in ('## Stage 1: native capability inventory', 'declared-only',
                   'invocation-observed', 'artifact-bound', 'source-assessed',
                   'executed here', 'structurally checked', 'available but untested',
                   'unavailable here', 'deep-research', 'needed fields', 'reuse conditions',
                   'CLI route is unavailable in this executor',
                   'route remains untested, not absent'):
        assert marker in text, marker


def test_candidate_comparison_requires_revision_not_empty_unknown():
    text = (ROOT / 'skills/gap-to-topic/references/dossier-template.md').read_text(encoding='utf-8')
    for marker in ('Candidate revision after closest/contrary comparison',
                   'Original proposition', 'Observed overlap', 'Revised proposition',
                   'Remaining discriminating test', 'materials / needed fields / reuse conditions'):
        assert marker in text, marker


def test_nonexistent_locator_is_not_certified_by_direction_check(record):
    dossier, review, root = record
    review['evidence'][0]['locator'] = 'Nonexistent section 999; deliberately unverified'
    result = validate_direction_review(dossier, review, root)
    # A byte-bound supplied locator is not a semantically verified location.
    assert result['binding_status'] == 'current'
    assert result['semantic_assessment'] == 'not-performed'
    assert result['execution_authorized'] is False
    assert 'ready' not in result


def test_unknown_material_field_and_reuse_checks_remain_unknown(record):
    dossier, review, root = record
    template = next(r for r in review['checks'] if r['kind'] == 'data')
    for name in ('materials', 'needed-fields', 'reuse-conditions'):
        row = deepcopy(template)
        row.update(check_id='synthetic-' + name, statement=name, status='unknown',
                   evidence_refs=[], reason='Not observed in supplied materials',
                   next_check='Inspect the explicitly selected dictionary or permission record')
        review['checks'].append(row)
    result = validate_direction_review(dossier, review, root)
    unresolved = [r for r in result['prerequisites'] if r['check_id'].startswith('synthetic-')]
    assert len(unresolved) == 3
    assert all(r['status'] == 'unknown' for r in unresolved)
    assert result['execution_authorized'] is False
    assert result['human_selection'] == 'outside-checker'


def test_near_work_revision_invalidates_previous_candidate_review(record):
    dossier, review, root = record
    dossier['gaps'][0]['statement'] = 'Revised synthetic scope after overlapping prior work'
    result = validate_direction_review(dossier, review, root)
    assert result['binding_status'] == 'not-current'
    assert result['candidate_bindings'][0]['status'] == 'stale-candidate'
    assert result['execution_authorized'] is False


def test_claimed_locator_does_not_replace_exact_source_quote(tmp_path, monkeypatch):
    packet, audit = build_fixture(tmp_path, 'full-text', monkeypatch)
    audit['assessments'][0]['quote'] = 'Invented result absent from the captured source.'
    # Packet-only success is deliberately insufficient for source-level claims.
    assert validate_evidence_packet(packet) == []
    findings = validate_evidence_packet(packet, source_audit=audit, artifact_root=tmp_path)
    assert findings
    assert any('quote' in row['message'].lower() for row in findings), findings


def test_native_stage_one_is_routed_from_primary_skill_and_packaged():
    paths = [
        'research-hub/SKILL.md',
        'research-hub/references/research-protocol.md',
        'research-hub/references/source-claim-audit.md',
        'gap-to-topic/SKILL.md',
        'gap-to-topic/references/dossier-template.md',
    ]
    for relative in paths:
        assert (ROOT / 'skills' / relative).read_bytes() == (
            ROOT / 'src/research_hub/skills_data' / relative).read_bytes()
    skill = (ROOT / 'skills/research-hub/SKILL.md').read_text(encoding='utf-8')
    preflight = skill.split('## Agent preflight protocol', 1)[1]
    assert preflight.index('Inventory the actual host-native') < preflight.index('research-hub describe --json')
    assert 'does not prove the product' in skill
    assert 'Hub storage, vault/library actions and NotebookLM automation need the CLI:' not in skill


def test_missing_search_receipt_and_revision_do_not_reset_valid_work():
    protocol = ' '.join((ROOT / 'skills/research-hub/references/research-protocol.md').read_text(encoding='utf-8').split())
    template = ' '.join((ROOT / 'skills/gap-to-topic/references/dossier-template.md').read_text(encoding='utf-8').split())
    assert 'reconstructed bibliography is not a historical invocation receipt' in protocol
    assert 'Do not make the user repeat a search merely to repair a missing receipt' in protocol
    assert 'Preserve the original brief and unchanged decisions' in template
    assert 'hash change alone is not a blanket reauthorization requirement' in template
