from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest
import research_hub

from research_hub.dashboard.drift import _check_crystal_staleness


@dataclass
class CrystalStaleness:
    crystal_slug: str
    added_papers: list[str] = field(default_factory=list)
    removed_papers: list[str] = field(default_factory=list)
    delta_ratio: float = 0.0
    stale: bool = False


class _FakeCluster:
    def __init__(self, slug: str):
        self.slug = slug


@pytest.fixture(autouse=True)
def _restore_crystal_module():
    """REGRESSION (CI): _install_fake_crystal_module() permanently replaces
    sys.modules["research_hub.crystal"] with a stub that only has
    check_staleness. Without restore-on-teardown the stub leaks into every
    subsequent test; in CI alphabetical order test_v033_workflows.py runs
    after this file and fails at mock.patch("research_hub.crystal.list_crystals")
    because the stub module has no list_crystals attribute.
    """
    original_module = sys.modules.get("research_hub.crystal")
    original_attr = getattr(research_hub, "crystal", None)
    try:
        yield
    finally:
        if original_module is None:
            sys.modules.pop("research_hub.crystal", None)
        else:
            sys.modules["research_hub.crystal"] = original_module
        if original_attr is None:
            try:
                delattr(research_hub, "crystal")
            except AttributeError:
                pass
        else:
            setattr(research_hub, "crystal", original_attr)


def _install_fake_crystal_module(check_impl) -> None:
    module = types.ModuleType("research_hub.crystal")
    module.check_staleness = check_impl
    sys.modules["research_hub.crystal"] = module
    setattr(research_hub, "crystal", module)


def test_drift_flags_stale_crystal():
    cfg = MagicMock()
    cluster = _FakeCluster("test")

    _install_fake_crystal_module(
        lambda _cfg, _slug: {
            "what-is-this-field": CrystalStaleness(
                crystal_slug="what-is-this-field",
                added_papers=["new-a", "new-b"],
                removed_papers=[],
                delta_ratio=0.15,
                stale=True,
            )
        }
    )
    alerts = _check_crystal_staleness(cfg, cluster)

    assert len(alerts) == 1
    assert alerts[0].kind == "crystal_stale"
    assert "what-is-this-field" in alerts[0].description
    assert "research-hub crystal emit" in alerts[0].fix_command


def test_drift_skips_fresh_crystal():
    cfg = MagicMock()
    cluster = _FakeCluster("test")

    _install_fake_crystal_module(
        lambda _cfg, _slug: {
            "what-is-this-field": CrystalStaleness(
                crystal_slug="what-is-this-field",
                added_papers=[],
                removed_papers=[],
                delta_ratio=0.0,
                stale=False,
            )
        }
    )
    alerts = _check_crystal_staleness(cfg, cluster)

    assert alerts == []


def test_drift_handles_crystal_module_exception():
    cfg = MagicMock()
    cluster = _FakeCluster("test")

    def _boom(_cfg, _slug):
        raise Exception("boom")

    _install_fake_crystal_module(_boom)
    alerts = _check_crystal_staleness(cfg, cluster)

    assert alerts == []
