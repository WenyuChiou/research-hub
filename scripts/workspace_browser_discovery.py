"""Synthetic saved Stage1 fixture and browser read-only consumer; no research execution."""
from __future__ import annotations

import hashlib
import json


def prepare_discovery_fixture(workspace):
    from research_hub.workspace.discovery import save_profile
    project = 'native-discovery-browser'
    workspace.create_project(id=project, title='Synthetic native Stage1 results')
    receipt = workspace.root / 'stage1-browser-capture.txt'
    receipt.write_bytes(b'Synthetic captured return; not executed research.')
    profile = {
        'format': 'research-discovery-observations/1.0', 'run_id': 'synthetic-browser',
        'project_id': project, 'brief': 'Synthetic Stage1 evidence handoff',
        'capabilities': [{'name': 'synthetic native search', 'kind': 'search',
                          'availability': 'available', 'observation': 'Fixture only'}],
        'needs': [{'id': 'n1', 'text': 'Closest and contrary evidence',
                   'families': ['closest', 'contrary'], 'status': 'unresolved'}],
        'attempts': [{'id': 'a1', 'need_ids': ['n1'], 'kind': 'search',
                     'tool': 'synthetic native search', 'input': 'Synthetic query',
                     'status': 'observed', 'outcome': 'partial', 'result_count': 2,
                     'receipt': {'reference': 'synthetic-capture:1', 'material': {
                         'path': receipt.name, 'sha256': hashlib.sha256(receipt.read_bytes()).hexdigest()}}}],
        'sources': [{'id': ident, 'work_id': 'synthetic:' + ident,
                     'title': 'Same synthetic title', 'locator': 'https://example.org/' + ident,
                     'access': 'public', 'need_ids': ['n1'], 'relevance': 'Synthetic relevance; unassessed.',
                     'version': None, 'reading_level': 'abstract', 'reading_ref': 'synthetic-read:' + ident,
                     'material': None, 'attempt_ids': ['a1']} for ident in ('s1', 's2')],
        'completion': {'status': 'partial', 'reason': 'Synthetic unresolved evidence',
                       'residual_need_ids': ['n1']}}
    path = workspace.root / 'stage1-browser.json'
    path.write_text(json.dumps(profile), encoding='utf-8')
    saved = save_profile(workspace, project, path.name)
    return {'project_id': project, 'saved': saved, 'receipt': receipt}


def guard_read_only(route, writes):
    if route.request.method not in ('GET', 'HEAD', 'OPTIONS'):
        writes.append({'method': route.request.method})
        route.fulfill(status=403, content_type='application/json',
                      body=json.dumps({'ok': False, 'code': 'forbidden',
                                       'error': 'Synthetic read-only journey forbids mutation dispatch'}))
    else:
        route.continue_()



def open_fresh_discovery(page, base, view_path):
    # Hash-only goto reuses the preceding journey's App and capability fixture.
    page.goto('about:blank')
    with page.expect_response(base + '/api/v1/workspace') as refreshed:
        page.goto(base + view_path)
    workspace_reply = refreshed.value.json()
    assert 'text_intake' in workspace_reply['capabilities'], 'Must not inherit legacy capability fixture'


def check_discovery_journey(screen, service, fixture, checks, output):
    from playwright.sync_api import expect
    page = screen.page
    project = fixture['project_id']
    writes = []
    pattern = screen.base + '/api/v1/**'
    def observed(route):
        guard_read_only(route, writes)
    page.route(pattern, observed)
    try:
        page.set_viewport_size({'width': 1440, 'height': 1000})
        open_fresh_discovery(page, screen.base, fixture['saved']['view_path'])
        result = page.get_by_role('region', name='Saved Stage 1 result', exact=True)
        expect(result).to_be_visible()
        expect(result.get_by_role('heading', name='Same synthetic title', exact=True)).to_have_count(2)
        expect(result.get_by_text('s1', exact=True)).to_be_visible()
        expect(result.get_by_text('s2', exact=True)).to_be_visible()
        expect(result.get_by_text('Sources without original material bytes: s1, s2', exact=True)).to_be_visible()
        expect(result.get_by_text('Referenced bytes at last check: current', exact=True)).to_be_visible()
        entry = page.get_by_role('button', name='Integrations & setup', exact=True)
        entry.focus()
        page.keyboard.press('Enter')
        expect(page.get_by_role('dialog')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(entry).to_be_focused()
        expect(result).to_be_visible()
        page.screenshot(path=str(output / 'workspace-native-discovery.png'), full_page=True)
        fixture['receipt'].unlink()  # synthetic missing capture; no outside data
        result.get_by_role('button', name='Recheck saved evidence (read only)', exact=True).click()
        result = page.get_by_role('region', name='Saved Stage 1 result', exact=True)
        expect(result.get_by_text('Referenced bytes at last check: not-current', exact=True)).to_be_visible()
        attempts = result.locator('summary').filter(has_text='Recorded searches and reads (not live agent activity)')
        attempts.click()
        expect(attempts).to_be_focused()
        expect(result.get_by_text('Captured observation-byte binding: unknown', exact=True)).to_be_visible()
        expect(result.get_by_text('synthetic native search · observed · partial', exact=True)).to_be_visible()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        expect(attempts).to_be_focused()
        skip_link = page.get_by_role('link', name='Skip to main content', exact=True)
        expect(skip_link).not_to_be_focused()
        expect(skip_link).not_to_be_in_viewport()
        skip_geometry = skip_link.evaluate("""element => {
            const r = element.getBoundingClientRect();
            return {focused: element === document.activeElement, top:r.top, bottom:r.bottom};
        }""")
        # Frame the beginning deliberately; do not move focus or hide a focus indicator.
        page.evaluate('scrollTo(0, 0)')
        expect(attempts).to_be_focused()
        expect(skip_link).not_to_be_in_viewport()
        page.screenshot(path=str(output / 'workspace-native-discovery.390px.viewport.png'))
        page.screenshot(path=str(output / 'workspace-native-discovery.390px.png'), full_page=True)
        snapshot = service.workspace.snapshot(project)
        assert not snapshot['tasks'] and not snapshot['actions'] and not snapshot['records']
        assert len(snapshot['artifacts']) == 1
        assert not writes, writes
        checks.append({'check': 'Single saved Stage1 link, exact duplicate-title IDs, setup interruption, missing capture and zero mutations',
                       'status': 'PASS', 'synthetic_only': True, 'execution_verified': False,
                       'semantic_assessment': 'not_performed', 'native_host_acceptance': 'not_tested',
                       'screenshots': ['workspace-native-discovery.png', 'workspace-native-discovery.390px.png', 'workspace-native-discovery.390px.viewport.png'],
                       'fresh_document': True, 'skip_link_geometry': skip_geometry,
                       'viewport': {'width': 390, 'height': 844}, 'native_zoom': 'not_tested'})
    finally:
        page.unroute(pattern, observed)
