from __future__ import annotations

import pytest


def test_real_zotero_get_client_is_blocked_by_default():
    from research_hub.zotero.client import get_client

    with pytest.raises(RuntimeError, match="Tests must not touch the real Zotero account"):
        get_client()


def test_real_zotero_dual_client_is_blocked_by_default():
    from research_hub.zotero.client import ZoteroDualClient

    with pytest.raises(RuntimeError, match="Tests must not touch the real Zotero account"):
        ZoteroDualClient()
