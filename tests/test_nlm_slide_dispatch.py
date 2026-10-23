"""Offline contracts for the public slide-deck generation entry points."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from research_hub.notebooklm import upload
from research_hub.notebooklm.client import NotebookLMError


@pytest.fixture
def generation_context(tmp_path, monkeypatch):
    cfg = SimpleNamespace(
        research_hub_dir=tmp_path / ".research_hub",
        clusters_file=tmp_path / "clusters.json",
    )
    cfg.research_hub_dir.mkdir()
    cluster = SimpleNamespace(
        slug="demo", name="Demo", notebooklm_notebook="Demo notebook",
        notebooklm_notebook_id="nb-demo", notebooklm_notebook_url="https://example.invalid/notebook/nb-demo",
    )
    initial_cache = {"demo": {"uploaded_doi_count": 3, "artifacts": {"brief": {"path": "saved.txt"}}},
                     "other": {"notebook_id": "nb-other"}}
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache_path.write_text(json.dumps(initial_cache), encoding="utf-8")
    client = SimpleNamespace(
        set_active_notebook=Mock(), close=Mock(),
        trigger_briefing=Mock(return_value="brief-result"),
        trigger_audio_overview=Mock(return_value="audio-result"),
        trigger_mind_map=Mock(return_value="mind_map-result"),
        trigger_video_overview=Mock(return_value="video-result"),
        trigger_slide_deck=Mock(return_value="slide_deck-result"),
    )
    make_client = Mock(return_value=client)
    monkeypatch.setattr(upload, "_make_client", make_client)
    return SimpleNamespace(cfg=cfg, cluster=cluster, client=client, make_client=make_client,
                           cache_path=cache_path, initial_cache=initial_cache)


@pytest.mark.parametrize("keyword", ["kind", "artifact_type"])
@pytest.mark.parametrize("kind", ["slide_deck", "slide-deck"])
def test_generate_slide_deck_dispatches_and_preserves_cache(generation_context, keyword, kind):
    ctx = generation_context
    result = upload.generate_artifact(ctx.cluster, ctx.cfg, headless=True, **{keyword: kind})

    assert result == "slide_deck-result"
    ctx.client.trigger_slide_deck.assert_called_once_with("nb-demo")
    ctx.client.trigger_briefing.assert_not_called()
    ctx.client.set_active_notebook.assert_called_once_with("nb-demo")
    ctx.client.close.assert_called_once_with()
    ctx.make_client.assert_called_once_with(
        ctx.cfg.research_hub_dir / "nlm_sessions" / "state.json", headless=True, keepalive_sec=600,
    )
    cache = json.loads(ctx.cache_path.read_text(encoding="utf-8"))
    assert cache["other"] == ctx.initial_cache["other"]
    assert cache["demo"]["artifacts"] == ctx.initial_cache["demo"]["artifacts"]
    assert cache["demo"]["uploaded_doi_count"] == 3
    assert cache["demo"]["slide_deck_url"] == result
    assert cache["demo"]["notebook_id"] == "nb-demo"
    assert cache["demo"]["notebook_url"] == ctx.cluster.notebooklm_notebook_url
    assert cache["demo"]["notebook_name"] == "Demo notebook"
    assert cache["demo"]["last_synced"]
    events = [json.loads(line) for path in ctx.cfg.research_hub_dir.glob("nlm-debug-*.jsonl")
              for line in path.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["kind"] == "generate_ok"
    assert events[-1]["kind_name"] == "slide_deck"
    assert events[-1]["artifact_ref"] == result


@pytest.mark.parametrize("kind,method,cache_key", [
    ("brief", "trigger_briefing", "briefing_url"),
    ("audio", "trigger_audio_overview", "audio_url"),
    ("mind_map", "trigger_mind_map", "mind_map_url"),
    ("mind-map", "trigger_mind_map", "mind_map_url"),
    ("video", "trigger_video_overview", "video_url"),
])
def test_existing_generation_kinds_are_unchanged(generation_context, kind, method, cache_key):
    ctx = generation_context
    result = upload.generate_artifact(ctx.cluster, ctx.cfg, kind=kind)
    getattr(ctx.client, method).assert_called_once_with("nb-demo")
    ctx.client.trigger_slide_deck.assert_not_called()
    cache = json.loads(ctx.cache_path.read_text(encoding="utf-8"))
    assert cache["demo"][cache_key] == result
    assert "slide_deck_url" not in cache["demo"]


def test_slide_deck_supports_legacy_no_argument_trigger(generation_context):
    ctx = generation_context
    calls = []

    def trigger():
        calls.append(ctx.client._active_notebook_id)
        return "legacy-slide"

    del ctx.client.set_active_notebook
    ctx.client.trigger_slide_deck = trigger
    assert upload.generate_artifact(ctx.cluster, ctx.cfg, kind="slide_deck") == "legacy-slide"
    assert calls == ["nb-demo"]
    ctx.client.close.assert_called_once_with()


@pytest.mark.parametrize("failure", [NotebookLMError("slide generation failed"), ""])
def test_failed_slide_deck_closes_client_without_persisting_success(generation_context, failure):
    ctx = generation_context
    before = ctx.cache_path.read_bytes()
    if isinstance(failure, Exception):
        ctx.client.trigger_slide_deck.side_effect = failure
    else:
        ctx.client.trigger_slide_deck.return_value = failure
    with pytest.raises(NotebookLMError):
        upload.generate_artifact(ctx.cluster, ctx.cfg, kind="slide_deck")
    assert ctx.cache_path.read_bytes() == before
    ctx.client.close.assert_called_once_with()
    assert "generate_ok" not in "".join(path.read_text(encoding="utf-8")
                                        for path in ctx.cfg.research_hub_dir.glob("nlm-debug-*.jsonl"))


def test_artifact_type_precedence_is_preserved(generation_context):
    ctx = generation_context
    assert upload.generate_artifact(ctx.cluster, ctx.cfg, artifact_type="brief", kind="slide_deck") == "brief-result"
    ctx.client.trigger_slide_deck.assert_not_called()


@pytest.mark.parametrize("requested,kinds", [
    ("slide-deck", ["slide_deck"]),
    ("all", ["brief", "audio", "mind_map", "video", "slide_deck"]),
])
def test_cli_generate_reaches_real_dispatch(generation_context, monkeypatch, capsys, requested, kinds):
    from research_hub import cli

    ctx = generation_context
    monkeypatch.setattr(cli, "get_config", lambda: ctx.cfg)
    monkeypatch.setattr(cli, "_preflight_nlm_session", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "ClusterRegistry", lambda path: SimpleNamespace(get=lambda slug: ctx.cluster))
    rc = cli.main(["notebooklm", "generate", "--cluster", "demo", "--type", requested, "--headless"])

    assert rc == 0
    assert capsys.readouterr().out.splitlines() == [f"{kind}: {kind}-result" for kind in kinds]
    assert ctx.client.close.call_count == len(kinds)
    assert ctx.make_client.call_count == len(kinds)
    ctx.client.trigger_slide_deck.assert_called_once_with("nb-demo")
    assert json.loads(ctx.cache_path.read_text(encoding="utf-8"))["demo"]["slide_deck_url"] == "slide_deck-result"
