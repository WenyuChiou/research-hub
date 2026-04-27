from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.search import SearchResult


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _results() -> list[SearchResult]:
    return [
        SearchResult(
            title="Paper One",
            doi="10.1/one",
            authors=["Jane Doe", "John Roe"],
            year=2024,
            venue="Journal One",
            abstract="Abstract one.",
            source="openalex",
        ),
        SearchResult(
            title="Paper Two",
            doi="10.1/two",
            authors=["Alice Smith"],
            year=2025,
            venue="Journal Two",
            abstract="Abstract two.",
            source="semantic-scholar",
        ),
        SearchResult(
            title="Paper Three",
            doi="10.1/three",
            authors=["Bob Ray"],
            year=2023,
            venue="Journal Three",
            abstract="Abstract three.",
            source="arxiv",
        ),
    ]


def _write_state_and_candidates(tmp_path: Path, cluster: str = "agents") -> SimpleNamespace:
    from research_hub.discover import CANDIDATES_FILENAME, DiscoverState, STATE_FILENAME, stash_dir

    cfg = _cfg(tmp_path)
    dest = stash_dir(cfg, cluster)
    dest.mkdir(parents=True, exist_ok=True)
    state = DiscoverState(cluster_slug=cluster, stage="scored_pending", query="llm agents", candidate_count=3)
    (dest / STATE_FILENAME).write_text(state.to_json(), encoding="utf-8")
    (dest / CANDIDATES_FILENAME).write_text(
        json.dumps(
            [
                {
                    "title": "Paper One",
                    "doi": "10.1/one",
                    "authors": ["Jane Doe", "John Roe"],
                    "year": 2024,
                    "venue": "Journal One",
                    "abstract": "Abstract one.",
                },
                {
                    "title": "Paper Two",
                    "doi": "10.1/two",
                    "authors": ["Alice Smith"],
                    "year": 2025,
                    "venue": "Journal Two",
                    "abstract": "Abstract two.",
                },
                {
                    "title": "Paper Three",
                    "doi": "10.1/three",
                    "authors": ["Bob Ray"],
                    "year": 2023,
                    "venue": "Journal Three",
                    "abstract": "Abstract three.",
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    return cfg


def test_discover_new_stashes_candidates_to_state_dir(tmp_path, monkeypatch):
    from research_hub.discover import CANDIDATES_FILENAME, discover_new, stash_dir

    cfg = _cfg(tmp_path)
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: _results())
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    discover_new(cfg, "agents", "llm agents")

    candidates_path = stash_dir(cfg, "agents") / CANDIDATES_FILENAME
    payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    assert len(payload) == 3


def test_discover_new_writes_state_json_with_stage_scored_pending(tmp_path, monkeypatch):
    from research_hub.discover import STATE_FILENAME, discover_new, stash_dir

    cfg = _cfg(tmp_path)
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: _results())
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    state, _ = discover_new(cfg, "agents", "llm agents")
    written = json.loads((stash_dir(cfg, "agents") / STATE_FILENAME).read_text(encoding="utf-8"))

    assert state.stage == "scored_pending"
    assert written["stage"] == "scored_pending"


def test_discover_new_returns_prompt_containing_all_candidate_titles(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: _results())
    monkeypatch.setattr(
        "research_hub.fit_check.emit_prompt",
        lambda cluster_slug, candidates, **kwargs: "\n".join(item["title"] for item in candidates),
    )

    _, prompt = discover_new(cfg, "agents", "llm agents")

    assert "Paper One" in prompt
    assert "Paper Two" in prompt
    assert "Paper Three" in prompt


def test_discover_new_rerun_overwrites_state_cleanly(tmp_path, monkeypatch):
    from research_hub.discover import STATE_FILENAME, discover_new, stash_dir

    cfg = _cfg(tmp_path)
    first = _results()[:2]
    second = _results()[:1]
    calls = {"count": 0}

    def fake_search(*args, **kwargs):
        calls["count"] += 1
        return first if calls["count"] == 1 else second

    monkeypatch.setattr("research_hub.search.search_papers", fake_search)
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    discover_new(cfg, "agents", "first query")
    state, _ = discover_new(cfg, "agents", "second query")
    written = json.loads((stash_dir(cfg, "agents") / STATE_FILENAME).read_text(encoding="utf-8"))

    assert state.candidate_count == 1
    assert written["query"] == "second query"
    assert written["candidate_count"] == 1


def test_discover_status_returns_none_when_never_run(tmp_path):
    from research_hub.discover import discover_status

    assert discover_status(_cfg(tmp_path), "agents") is None


def test_discover_continue_raises_when_new_not_run(tmp_path):
    from research_hub.discover import discover_continue

    try:
        discover_continue(_cfg(tmp_path), "agents", [])
    except FileNotFoundError as exc:
        assert "discover new" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_discover_continue_reads_stashed_candidates(tmp_path, monkeypatch):
    from research_hub.discover import discover_continue
    from research_hub.fit_check import FitCheckReport

    cfg = _write_state_and_candidates(tmp_path)
    captured = {}

    def fake_apply(cluster_slug, candidates, scores, threshold=3, cfg=None):
        captured["titles"] = [item["title"] for item in candidates]
        return FitCheckReport(cluster_slug=cluster_slug, threshold=threshold, candidates_in=len(candidates))

    monkeypatch.setattr("research_hub.fit_check.apply_scores", fake_apply)

    discover_continue(cfg, "agents", [])

    assert captured["titles"] == ["Paper One", "Paper Two", "Paper Three"]


def test_discover_continue_applies_explicit_threshold(tmp_path, monkeypatch):
    from research_hub.discover import discover_continue
    from research_hub.fit_check import FitCheckReport

    cfg = _write_state_and_candidates(tmp_path)
    captured = {}

    def fake_apply(cluster_slug, candidates, scores, threshold=3, cfg=None):
        captured["threshold"] = threshold
        return FitCheckReport(cluster_slug=cluster_slug, threshold=threshold, candidates_in=len(candidates))

    monkeypatch.setattr("research_hub.fit_check.apply_scores", fake_apply)

    discover_continue(cfg, "agents", [{"doi": "10.1/one", "score": 5}], threshold=4)

    assert captured["threshold"] == 4


def test_discover_continue_auto_threshold_overrides_default(tmp_path, monkeypatch):
    from research_hub.discover import discover_continue
    from research_hub.fit_check import FitCheckReport

    cfg = _write_state_and_candidates(tmp_path)
    captured = {}

    def fake_apply(cluster_slug, candidates, scores, threshold=3, cfg=None):
        captured["threshold"] = threshold
        return FitCheckReport(cluster_slug=cluster_slug, threshold=threshold, candidates_in=len(candidates))

    monkeypatch.setattr("research_hub.fit_check.apply_scores", fake_apply)

    discover_continue(
        cfg,
        "agents",
        {"scores": [{"score": 5}, {"score": 5}, {"score": 5}, {"score": 3}, {"score": 0}]},
        auto_threshold=True,
    )

    assert captured["threshold"] == 4


def test_discover_continue_explicit_threshold_wins_over_auto(tmp_path, monkeypatch):
    from research_hub.discover import discover_continue
    from research_hub.fit_check import FitCheckReport

    cfg = _write_state_and_candidates(tmp_path)
    captured = {}

    def fake_apply(cluster_slug, candidates, scores, threshold=3, cfg=None):
        captured["threshold"] = threshold
        return FitCheckReport(cluster_slug=cluster_slug, threshold=threshold, candidates_in=len(candidates))

    monkeypatch.setattr("research_hub.fit_check.apply_scores", fake_apply)

    discover_continue(
        cfg,
        "agents",
        {"scores": [{"score": 5}, {"score": 5}, {"score": 5}, {"score": 3}, {"score": 0}]},
        threshold=5,
        auto_threshold=True,
    )

    assert captured["threshold"] == 5


def test_discover_continue_writes_papers_input_flat_list(tmp_path):
    from research_hub.discover import discover_continue

    cfg = _write_state_and_candidates(tmp_path)
    state, out_path = discover_continue(
        cfg,
        "agents",
        {"scores": [{"doi": "10.1/one", "score": 5, "reason": "fit"}]},
        threshold=3,
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))

    assert state.accepted_count == 1
    assert isinstance(payload, list)


def test_discover_continue_papers_input_has_creator_dict_authors(tmp_path):
    from research_hub.discover import discover_continue

    cfg = _write_state_and_candidates(tmp_path)
    _, out_path = discover_continue(
        cfg,
        "agents",
        {"scores": [{"doi": "10.1/one", "score": 5, "reason": "fit"}]},
        threshold=3,
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))

    assert payload[0]["authors"][0] == {
        "creatorType": "author",
        "firstName": "Jane",
        "lastName": "Doe",
    }


def test_discover_continue_papers_input_has_todo_placeholders(tmp_path):
    """v0.68.4: when the search backend returned a real abstract,
    summary is now seeded from it ("Abstract one.") and methodology
    becomes "[review abstract; refine after reading PDF]" — TODO marker
    only appears now when the abstract is genuinely empty. relevance is
    still TODO because the backend can't infer cluster fit."""
    from research_hub.discover import discover_continue

    cfg = _write_state_and_candidates(tmp_path)
    _, out_path = discover_continue(
        cfg,
        "agents",
        {"scores": [{"doi": "10.1/one", "score": 5, "reason": "fit"}]},
        threshold=3,
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))

    assert payload[0]["summary"] == "Abstract one."
    assert payload[0]["key_findings"]
    assert "review abstract" in payload[0]["methodology"]
    assert payload[0]["relevance"].startswith("[TODO")


def test_compute_auto_threshold_median_minus_one():
    from research_hub.fit_check import compute_auto_threshold

    assert compute_auto_threshold([5, 5, 5, 3, 0]) == 4


def test_compute_auto_threshold_clamps_lower_bound():
    from research_hub.fit_check import compute_auto_threshold

    assert compute_auto_threshold([0, 0, 0]) == 2


def test_compute_auto_threshold_empty_returns_3():
    from research_hub.fit_check import compute_auto_threshold

    assert compute_auto_threshold([]) == 3


def test_discover_status_reports_candidate_and_accepted_counts(tmp_path):
    from research_hub.discover import discover_continue, discover_status

    cfg = _write_state_and_candidates(tmp_path)
    discover_continue(
        cfg,
        "agents",
        {"scores": [{"doi": "10.1/one", "score": 5, "reason": "fit"}]},
        threshold=3,
    )

    state = discover_status(cfg, "agents")
    assert state is not None
    assert state.candidate_count == 3
    assert state.accepted_count == 1


def test_discover_clean_removes_stash_dir(tmp_path):
    from research_hub.discover import discover_clean, stash_dir

    cfg = _cfg(tmp_path)
    dest = stash_dir(cfg, "agents")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "state.json").write_text("{}", encoding="utf-8")

    assert discover_clean(cfg, "agents") is True
    assert not dest.exists()


def test_cli_discover_new_continue_produces_papers_input_flat_list(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: _results()[:1])

    assert cli.main(["discover", "new", "--cluster", "agents", "--query", "llm", "--prompt-out", str(tmp_path / "prompt.md")]) == 0

    scored_path = tmp_path / "scored.json"
    scored_path.write_text(
        json.dumps({"scores": [{"doi": "10.1/one", "score": 5, "reason": "fit"}]}),
        encoding="utf-8",
    )

    assert cli.main(["discover", "continue", "--cluster", "agents", "--scored", str(scored_path)]) == 0

    output = capsys.readouterr().out.strip().splitlines()[-1]
    papers_path = Path(output.split(": ", 1)[1])
    payload = json.loads(papers_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)


def test_cli_discover_status_after_continue_shows_done(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.search.search_papers", lambda *args, **kwargs: _results()[:1])

    assert cli.main(["discover", "new", "--cluster", "agents", "--query", "llm", "--prompt-out", str(tmp_path / "prompt.md")]) == 0

    scored_path = tmp_path / "scored.json"
    scored_path.write_text(
        json.dumps({"scores": [{"doi": "10.1/one", "score": 5, "reason": "fit"}]}),
        encoding="utf-8",
    )
    assert cli.main(["discover", "continue", "--cluster", "agents", "--scored", str(scored_path)]) == 0
    assert cli.main(["discover", "status", "--cluster", "agents"]) == 0

    stdout = capsys.readouterr().out
    assert "stage:   done" in stdout


def test_discover_new_forwards_new_search_filters(tmp_path, monkeypatch):
    from research_hub.discover import discover_new

    cfg = _cfg(tmp_path)
    captured = {}

    def fake_search(*args, **kwargs):
        captured["exclude_types"] = kwargs["exclude_types"]
        captured["exclude_terms"] = kwargs["exclude_terms"]
        captured["min_confidence"] = kwargs["min_confidence"]
        captured["rank_by"] = kwargs["rank_by"]
        return _results()

    monkeypatch.setattr("research_hub.search.search_papers", fake_search)
    monkeypatch.setattr("research_hub.fit_check.emit_prompt", lambda *args, **kwargs: "prompt")

    discover_new(
        cfg,
        "agents",
        "llm agents",
        exclude_types=("report",),
        exclude_terms=("ipcc",),
        min_confidence=0.75,
        rank_by="year",
    )

    assert captured == {
        "exclude_types": ("report",),
        "exclude_terms": ("ipcc",),
        "min_confidence": 0.75,
        "rank_by": "year",
    }


def test_cli_discover_new_forwards_new_flags(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    captured = {}
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    def fake_discover_new(cfg, cluster_slug, query, **kwargs):
        captured.update(kwargs)
        from research_hub.discover import DiscoverState

        return DiscoverState(cluster_slug=cluster_slug, stage="scored_pending", query=query), "prompt"

    monkeypatch.setattr("research_hub.discover.discover_new", fake_discover_new)

    assert cli.main(
        [
            "discover",
            "new",
            "--cluster",
            "agents",
            "--query",
            "llm",
            "--exclude-type",
            "report,book-chapter",
            "--exclude",
            "ipcc lancet",
            "--min-confidence",
            "0.75",
            "--rank-by",
            "citation",
            "--prompt-out",
            str(tmp_path / "prompt.md"),
        ]
    ) == 0

    assert captured["exclude_types"] == ("report", "book-chapter")
    assert captured["exclude_terms"] == ("ipcc", "lancet")
    assert captured["min_confidence"] == 0.75
    assert captured["rank_by"] == "citation"


def test_discover_new_field_flag_forwards_to_search(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    captured = {}
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    def fake_discover_new(cfg, cluster_slug, query, **kwargs):
        captured.update(kwargs)
        from research_hub.discover import DiscoverState

        return DiscoverState(cluster_slug=cluster_slug, stage="scored_pending", query=query), "prompt"

    monkeypatch.setattr("research_hub.discover.discover_new", fake_discover_new)

    assert cli.main(
        [
            "discover",
            "new",
            "--cluster",
            "agents",
            "--query",
            "llm",
            "--field",
            "bio",
            "--prompt-out",
            str(tmp_path / "prompt.md"),
        ]
    ) == 0

    assert captured["field"] == "bio"


def test_discover_new_region_flag_forwards_to_search(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    captured = {}
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    def fake_discover_new(cfg, cluster_slug, query, **kwargs):
        captured.update(kwargs)
        from research_hub.discover import DiscoverState

        return DiscoverState(cluster_slug=cluster_slug, stage="scored_pending", query=query), "prompt"

    monkeypatch.setattr("research_hub.discover.discover_new", fake_discover_new)

    assert cli.main(
        [
            "discover",
            "new",
            "--cluster",
            "agents",
            "--query",
            "llm",
            "--region",
            "cjk",
            "--prompt-out",
            str(tmp_path / "prompt.md"),
        ]
    ) == 0

    assert captured["region"] == "cjk"
