"""Bind the smoke's exact read action to its UI-owned label, without a browser."""
import ast
from pathlib import Path
import re


def test_browser_read_source_locator_matches_ui_contract():
    root = Path(__file__).resolve().parents[1]
    script = ast.parse((root / 'scripts/workspace_browser_smoke.py').read_text(encoding='utf-8'))
    names = []
    for node in ast.walk(script):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'get_by_role':
            values = {kw.arg: kw.value.value for kw in node.keywords if isinstance(kw.value, ast.Constant)}
            if str(values.get('name', '')).startswith('Read selected '):
                assert values.get('exact') is True
                names.append(values['name'])
    label = re.search(r'abstractReadText: "([^"]+)"', (root / 'web/src/i18n.ts').read_text(encoding='utf-8'))
    assert label is not None
    assert names == [label.group(1)]
