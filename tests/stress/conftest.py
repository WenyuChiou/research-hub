from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    del config
    for item in items:
        if "tests/stress/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.stress)
