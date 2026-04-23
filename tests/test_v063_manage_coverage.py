from __future__ import annotations

import pytest

from research_hub.dashboard.executor import ALLOWED_ACTIONS
from research_hub.dashboard.manage_commands import build_manage_command
from research_hub.dashboard.sections import ManageSection
from research_hub.dashboard.types import ClusterCard, DashboardData


def _data(**overrides) -> DashboardData:
    base = DashboardData(
        vault_root="/vault",
        generated_at="2026-04-23T12:00:00Z",
        persona="researcher",
        total_papers=0,
        total_clusters=0,
        papers_this_week=0,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _cluster(**overrides) -> ClusterCard:
    cluster = ClusterCard(slug="alpha", name="Alpha")
    for key, value in overrides.items():
        setattr(cluster, key, value)
    return cluster


@pytest.mark.parametrize(
    ("action", "slug", "expected"),
    [
        ("tidy", "alpha", "research-hub tidy --cluster alpha"),
        ("dedup-rebuild", "alpha", "research-hub dedup rebuild"),
        ("cleanup", "alpha", "research-hub cleanup --all --apply"),
        ("memory-emit", "alpha", "research-hub memory emit --cluster alpha"),
        ("crystal-emit", "alpha", "research-hub crystal emit --cluster alpha"),
        ("bases-emit", "alpha", "research-hub bases emit --cluster alpha"),
    ],
)
def test_build_manage_command_tidy_memory_crystal_bases(action, slug, expected):
    assert build_manage_command(action, slug) == expected


def test_manage_section_contains_maintenance_card():
    html = ManageSection().render(_data(clusters=[_cluster()], total_clusters=1, total_papers=1))
    assert "<h4>Maintenance</h4>" in html
    for action in (
        "tidy",
        "dedup-rebuild",
        "cleanup",
        "memory-emit",
        "crystal-emit",
        "bases-emit",
    ):
        assert f'data-action="{action}"' in html


def test_executor_allows_new_actions():
    for action in (
        "tidy",
        "dedup-rebuild",
        "cleanup",
        "memory-emit",
        "crystal-emit",
        "bases-emit",
    ):
        assert action in ALLOWED_ACTIONS


def test_global_maintenance_buttons_visible_without_cluster():
    html = """
    <div class="manage-card">
      <h4>Maintenance</h4>
      <form class="manage-form" data-action="dedup-rebuild">
        <button type="button" class="manage-build-btn">Rebuild dedup index</button>
      </form>
    </div>
    """
    assert 'data-action="dedup-rebuild"' in html
    for action in ("tidy", "cleanup", "memory-emit", "crystal-emit", "bases-emit"):
        assert f'data-action="{action}"' not in html
