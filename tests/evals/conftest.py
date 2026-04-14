import json
from pathlib import Path

import pytest
import yaml

METRICS_FILE = Path(__file__).parent / "_metrics.json"


class MetricsCollector:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, object]] = {}

    def record(self, category: str, key: str, value) -> None:
        self.data.setdefault(category, {})[str(key)] = value

    def dump(self) -> None:
        existing: dict[str, object] = {}
        if METRICS_FILE.exists():
            existing = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
        existing.update(self.data)
        METRICS_FILE.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "network: Tests that hit real external APIs (OpenAlex, arXiv, etc)",
    )
    config.addinivalue_line(
        "markers",
        "evals: Evaluation tests measuring search accuracy and fit-check quality",
    )
    config.addinivalue_line(
        "markers",
        "slow: Tests that take >5 seconds to run",
    )


def pytest_runtest_setup(item) -> None:
    markexpr = item.config.option.markexpr or ""
    if "network" in item.keywords and "network" not in markexpr:
        pytest.skip("network tests require explicit opt-in via `-m network`")


@pytest.fixture(scope="session")
def metrics_collector():
    collector = MetricsCollector()
    yield collector
    collector.dump()


@pytest.fixture
def golden_fixture():
    path = Path(__file__).parent / "fixtures" / "golden_llm_agents_se.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture
def live_cluster_sidecars():
    hub = Path.home() / "knowledge-base" / "hub" / "llm-agents-software-engineering"
    accepted_path = hub / ".fit_check_accepted.json"
    rejected_path = hub / ".fit_check_rejected.json"
    if not accepted_path.exists():
        pytest.skip("live accepted sidecar not present; run discover_continue first")
    return {
        "accepted": json.loads(accepted_path.read_text(encoding="utf-8")),
        "rejected": (
            json.loads(rejected_path.read_text(encoding="utf-8"))
            if rejected_path.exists()
            else []
        ),
    }
