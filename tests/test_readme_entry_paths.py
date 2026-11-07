"""README entry choice and static, accessible two-path visual contracts.

These checks do not establish host readiness, visual acceptance, or scientific
quality. Render both locale images at mobile width before accepting layout.
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
SVG = '{http://www.w3.org/2000/svg}'


@pytest.mark.parametrize('filename,heading,install,expected', [
    ('README.md', '## Choose your starting path', '## Install and get started', (
        'No Hub installation, Zotero, Obsidian, or NotebookLM is required',
        'First request:', 'Expect a source list in your host',
        'Codex MCP is not release-verified',
        'selected destination and authorization', 'Python 3.10+, Git, and a local browser',
    )),
    ('README.zh-TW.md', '## 選擇你的起點', '## 安裝與快速開始', (
        '不需要安裝 Hub，也不需要 Zotero、Obsidian 或 NotebookLM',
        '第一個請求：', '預期在主機中取得來源清單',
        'Codex MCP 尚未通過版本發布驗證',
        '選定目的地與授權', 'Python 3.10+、Git 及本機瀏覽器',
    )),
])
def test_entry_choice_precedes_install_with_host_first_task(filename, heading, install, expected):
    text = (ROOT / filename).read_text(encoding='utf-8')
    assert text.index(heading) < text.index(install) < text.index('git clone')
    entry = text.split(heading, 1)[1].split(install, 1)[0]
    for term in expected:
        assert term in entry
    for link in ('skills/research-hub/', 'docs/setup.md#installed-skill-files',
                 'docs/ai-host-support.md', '#workspace-preview',
                 'docs/contracts/native-discovery-view.md'):
        assert f']({link})' in entry
    assert entry.index('research-entry-paths.') < entry.index(expected[0]), 'Show the choice before setup detail'
    assert '```' not in entry, 'Native research must not acquire an install command prerequisite'


def _visual(locale):
    path = ROOT / f'docs/images/research-entry-paths.{locale}.svg'
    data = path.read_bytes()
    assert len(data) < 8192
    assert b'<!DOCTYPE' not in data and b'<!ENTITY' not in data
    return ET.fromstring(data)


@pytest.mark.parametrize('locale', ['en', 'zh-TW'])
def test_entry_svg_is_static_accessible_and_mobile_sized(locale):
    root = _visual(locale)
    assert root.tag == SVG + 'svg'
    assert root.get('role') == 'img' and root.get('lang') == locale
    assert root.get('viewBox') == '0 0 320 480'
    assert (root.get('width'), root.get('height')) == ('320', '480')
    by_id = {node.get('id'): node for node in root.iter() if node.get('id')}
    for id in root.get('aria-labelledby').split():
        assert by_id[id].tag in {SVG + 'title', SVG + 'desc'}
        assert len(by_id[id].text.strip()) >= 6
    assert len(by_id) == len([node for node in root.iter() if node.get('id')])
    for node in root.iter():
        assert node.tag in {SVG + name for name in ('svg', 'title', 'desc', 'rect', 'g', 'text')}
        for key, value in node.attrib.items():
            assert not key.lower().startswith('on')
            assert not key.lower().endswith('href')
            assert 'url(' not in value.lower() and '@import' not in value.lower()
        if node.tag == SVG + 'text':
            # Minimum effective font 14.4px in a 288px image within a 320px viewport.
            assert float(node.get('font-size')) * 288 / 320 >= 14.4
            assert node.text and node.text.strip()
    canvas = root.find(SVG + 'rect')
    assert canvas.get('fill') == '#ffffff', 'Opaque canvas isolates dark surroundings'
    readme = (ROOT / ('README.md' if locale == 'en' else 'README.zh-TW.md')).read_text(encoding='utf-8')
    alt = re.search(r'!\[([^\]]+)\]\(docs/images/research-entry-paths\.' + locale + r'\.svg\)', readme)
    assert alt and len(alt.group(1)) > 80
    assert ('review' if locale == 'en' else '檢視') in alt.group(1)


def test_bilingual_entry_visuals_have_identical_structure():
    def structure(locale):
        # All geometry, reading order, labels and color contracts match; prose
        # translation and line widths require the separate visual inspection.
        return [(node.tag, {k: v for k, v in node.attrib.items() if k != 'lang'})
                for node in _visual(locale).iter()]
    assert structure('en') == structure('zh-TW')


def _luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))


def _contrast(a, b):
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + .05) / (dark + .05)


def test_entry_svg_text_and_boundaries_have_readable_contrast():
    for locale in ('en', 'zh-TW'):
        root = _visual(locale)
        text_color = root.find(SVG + 'g').get('fill')
        for rect in root.iter(SVG + 'rect'):
            assert _contrast(text_color, rect.get('fill')) >= 4.5
            assert _contrast(rect.get('stroke'), rect.get('fill')) >= 3
        assert _contrast('#64748b', '#0d1117') >= 3
