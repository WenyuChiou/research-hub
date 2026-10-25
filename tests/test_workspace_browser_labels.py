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


def test_browser_uncertain_error_copy_uses_task_scoped_exact_ui_labels():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / 'scripts/workspace_browser_smoke.py').read_text(encoding='utf-8'))
    messages = (root / 'web/src/i18n.ts').read_text(encoding='utf-8')
    for key in ('errorHelp', 'errorUncertainHelp'):
        label = re.search(key + r': "([^"\n]+)"', messages)
        assert label is not None
        matches = [node for node in ast.walk(tree)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == 'get_by_text' and node.args
                   and isinstance(node.args[0], ast.Constant) and node.args[0].value == label.group(1)]
        assert len(matches) == 1
        call = matches[0]
        assert any(kw.arg == 'exact' and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in call.keywords)
        assert isinstance(call.func.value, ast.Call)
        assert isinstance(call.func.value.func, ast.Name) and call.func.value.func.id == 'task_card'
