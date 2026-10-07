from __future__ import annotations

import json
import os
from pathlib import Path
from textwrap import dedent

import pytest


def _install_subprocess_network_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fence real CLI children, which do not inherit pytest's socket patches.

    Audit events are rejected before DNS/socket I/O. Keep an on-disk record so
    catching an exception in production cannot silently turn a leak green.
    This only affects Python children launched with this fixture's environment.
    """
    guard_dir = tmp_path / "_offline_cli_guard"
    guard_dir.mkdir()
    attempts_path = guard_dir / "attempts.log"
    attempts_path.write_text("", encoding="utf-8")
    source = dedent(
        f"""\
        import os
        import sys

        def _deny_network(event, args):
            socket_io = event.startswith("socket.") and event not in {{
                "socket.__new__", "socket.bind", "socket.gethostname",
                "socket.getservbyname", "socket.getservbyport",
            }}
            # No CLI in this fixture needs an external helper. Deny nested
            # processes too, rather than allowing them to bypass Python hooks.
            process_io = event in {{
                "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn",
            }}
            if socket_io or process_io:
                try:
                    with open({str(attempts_path)!r}, "a", encoding="utf-8") as stream:
                        stream.write(event + "\\n")
                except BaseException:
                    os._exit(98)
                raise RuntimeError("offline CLI fixture blocked " + event)

        try:
            sys.addaudithook(_deny_network)
            sys._research_hub_e2e_offline = True

            # Mirror the parent test's browser stub in the fresh interpreter.
            # Dashboard health must report unverified capabilities as INFO,
            # rather than launch a browser driver or inspect real processes.
            try:
                import patchright.sync_api as _patchright
            except ImportError:
                pass
            else:
                def _offline_browser_probe():
                    raise RuntimeError("Chrome not checked in offline E2E fixture")
                _patchright.sync_playwright = _offline_browser_probe

            import research_hub.doctor as _doctor
            _doctor.check_nlm_chrome_orphans = lambda: _doctor.CheckResult(
                "nlm_chrome_orphans", "INFO",
                "Processes not checked in offline E2E fixture",
            )
        except BaseException:
            # sitecustomize normally prints and swallows startup errors.
            # A broken guard must stop this child instead of failing open.
            os._exit(98)
        """
    )
    compile(source, "sitecustomize.py", "exec")
    (guard_dir / "sitecustomize.py").write_text(source, encoding="utf-8")
    src = Path(__file__).resolve().parents[1] / "src"
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(guard_dir), str(src))))
    return attempts_path


def _write_note(
    path: Path,
    *,
    title: str,
    year: str,
    doi: str,
    cluster: str,
    status: str = "unread",
    labels: str = "[seed]",
    subtopics: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f'title: "{title}"\n'
            'authors: "Doe, Jane; Roe, Alex"\n'
            f'year: "{year}"\n'
            f'doi: "{doi}"\n'
            f"topic_cluster: {cluster}\n"
            f"status: {status}\n"
            f"labels: {labels}\n"
            f"{subtopics}"
            "---\n\n"
            "## Summary\n"
            f"{title} summary.\n\n"
            "## Key Findings\n"
            f"- {title} finding\n\n"
            "## Methodology\n"
            "Synthetic fixture.\n\n"
            "## Relevance\n"
            "Sandbox coverage.\n"
        ),
        encoding="utf-8",
    )


def _set_sandbox_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    clusters_file = tmp_path / "clusters.yaml"
    for path in (raw, hub, research_hub_dir):
        path.mkdir(parents=True, exist_ok=True)
    (research_hub_dir / "dedup_index.json").write_text("{}", encoding="utf-8")
    (research_hub_dir / "manifest.jsonl").write_text("", encoding="utf-8")
    (research_hub_dir / "nlm_cache.json").write_text("{}", encoding="utf-8")

    config_path = tmp_path / "_e2e_sandbox_config.json"
    config_path.write_text(
        json.dumps(
            {
                "knowledge_base": {
                    "root": str(root),
                    "raw": str(raw),
                    "hub": str(hub),
                },
                "clusters_file": str(clusters_file),
                "no_zotero": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(root))
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(config_path))
    monkeypatch.setenv("RESEARCH_HUB_ALLOW_EXTERNAL_ROOT", "1")
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setenv("PYTHONPATH", "src")

    import research_hub.config as cfg_mod

    cfg_mod._config = None
    cfg_mod._config_path = None
    return cfg_mod.HubConfig()


@pytest.fixture
def sandbox_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = _set_sandbox_root(tmp_path, monkeypatch)
    network_attempts = _install_subprocess_network_guard(tmp_path, monkeypatch)

    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha systems", name="Alpha", slug="alpha")
    registry.create(query="beta systems", name="Beta", slug="beta")
    registry.save()

    alpha_dir = cfg.raw / "alpha"
    beta_dir = cfg.raw / "beta"
    _write_note(
        alpha_dir / "alpha-paper-1.md",
        title="Alpha Agents Benchmark",
        year="2024",
        doi="10.1000/alpha1",
        cluster="alpha",
        subtopics="subtopics: [benchmark]\n",
    )
    _write_note(
        alpha_dir / "alpha-paper-2.md",
        title="Alpha Planning Systems",
        year="2025",
        doi="10.1000/alpha2",
        cluster="alpha",
        status="reading",
        subtopics="subtopics: [planning]\n",
    )
    _write_note(
        alpha_dir / "alpha-paper-3.md",
        title="Shared Query Methods",
        year="2026",
        doi="10.1000/alpha3",
        cluster="alpha",
        labels="[core]",
        subtopics="subtopics: [benchmark, methods]\n",
    )
    _write_note(
        beta_dir / "beta-paper-1.md",
        title="Beta Agents Benchmark",
        year="2024",
        doi="10.1000/beta1",
        cluster="beta",
    )
    _write_note(
        beta_dir / "beta-paper-2.md",
        title="Shared Query Evaluation",
        year="2025",
        doi="10.1000/beta2",
        cluster="beta",
    )

    # clusters-analyze runs in a fresh CLI child. Seed explicit synthetic
    # references so it tests the real graph/report path without contacting S2.
    cache_dir = cfg.research_hub_dir / "citation_cache" / "alpha"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for slug, refs in {
        "alpha-paper-1": ["10.1000/synthetic-shared", "10.1000/synthetic-benchmark"],
        "alpha-paper-2": ["10.1000/synthetic-shared", "10.1000/synthetic-planning"],
        "alpha-paper-3": ["10.1000/synthetic-benchmark"],
    }.items():
        (cache_dir / f"{slug}.json").write_text(json.dumps(refs), encoding="utf-8")

    quotes_dir = cfg.research_hub_dir / "quotes"
    quotes_dir.mkdir(parents=True, exist_ok=True)
    (quotes_dir / "alpha-paper-1.md").write_text(
        (
            "---\n"
            "captured_at: 2026-04-20T12:00:00Z\n"
            'page: "12"\n'
            "cluster: alpha\n"
            'cluster_name: "Alpha"\n'
            'context_note: "Introduction"\n'
            "---\n"
            "> Alpha quote one.\n\n"
            "---\n"
            "captured_at: 2026-04-20T12:30:00Z\n"
            'page: "15"\n'
            "cluster: alpha\n"
            'cluster_name: "Alpha"\n'
            'context_note: "Methods"\n'
            "---\n"
            "> Alpha quote two.\n"
        ),
        encoding="utf-8",
    )

    papers_input_path = tmp_path / "papers_input.json"
    papers_input_path.write_text(
        json.dumps(
            [
                {
                    "title": "Dry Run Ingest Paper",
                    "doi": "10.1000/dryrun",
                    "authors": [{"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}],
                    "year": "2026",
                    "abstract": "abstract",
                    "journal": "Journal",
                    "summary": "summary",
                    "key_findings": ["finding"],
                    "methodology": "methodology",
                    "relevance": "relevance",
                    "slug": "dry-run-ingest-paper",
                    "sub_category": "alpha",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    scored_path = tmp_path / "scored.json"
    scored_path.write_text(
        json.dumps(
            [
                {
                    "slug": "alpha-paper-1",
                    "title": "Alpha Agents Benchmark",
                    "score": 0.92,
                    "reason": "high fit",
                    "summary": "summary",
                    "key_findings": ["finding"],
                    "methodology": "methodology",
                    "relevance": "relevance",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    yield cfg
    assert network_attempts.read_text(encoding="utf-8") == "", (
        "CLI child attempted network/helper I/O:\n"
        + network_attempts.read_text(encoding="utf-8")
    )
