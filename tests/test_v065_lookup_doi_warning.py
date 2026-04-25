"""v0.65 Track A3: lookup-doi --batch warns about Zotero auto-sync trigger."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_lookup_doi_batch_warns_about_zotero_autosync(monkeypatch, capsys, tmp_path):
    """When `paper lookup-doi --batch` runs, the first line of output must
    be a Zotero-side-effect warning. The user reported this trigger
    repeatedly in v0.64 sessions before the warning landed.

    Verified at the dispatcher level (_paper_command) to avoid the
    main()-level require_config plumbing.
    """
    from research_hub import cli

    fake_result = {
        "cluster": "test-cluster",
        "results": [{"slug": "p1", "status": "updated"}],
        "log_path": str(tmp_path / "lookup_log.json"),
    }
    monkeypatch.setattr(
        "research_hub.doi_lookup.batch_lookup_missing_dois",
        lambda cfg, slug: fake_result,
    )
    monkeypatch.setattr("research_hub.cli.get_config", lambda: MagicMock())

    args = MagicMock()
    args.paper_command = "lookup-doi"
    args.batch = True
    args.cluster = "test-cluster"

    rc = cli._paper_command(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "Note:" in out, "must announce the side-effect warning"
    assert "zotero.org/settings/keys" in out
    assert "auto-sync" in out
    assert "updated: 1" in out  # original output preserved
