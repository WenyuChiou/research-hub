"""v0.42 tests — Obsidian callout + block-ID conventions.

Adopted from [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)
(MIT, by the Obsidian team).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from research_hub.markdown_conventions import (
    summary_section_to_callout,
    unwrap_callout,
    upgrade_paper_body,
    wrap_callout,
)


def test_wrap_callout_prefixes_every_line():
    body = "line one\nline two"
    out = wrap_callout("abstract", body)
    assert out.startswith("> [!abstract]\n")
    assert "> line one" in out
    assert "> line two" in out


def test_wrap_callout_with_block_id_appends_anchor():
    out = wrap_callout("info", "hi", block_id="findings")
    assert out.rstrip().endswith("^findings")


def test_unwrap_callout_is_inverse_of_wrap():
    original = "line one\nline two\n"
    wrapped = wrap_callout("abstract", original, block_id="tldr")
    unwrapped = unwrap_callout(wrapped)
    assert unwrapped.strip() == original.strip()


def test_unwrap_callout_on_plain_text_is_identity():
    plain = "just a normal paragraph\nno callout here"
    assert unwrap_callout(plain) == plain


def test_summary_section_to_callout_produces_all_four_sections():
    out = summary_section_to_callout(
        summary="Paper proposes X.",
        key_findings=["Finding one", "Finding two"],
        methodology="Method Y.",
        relevance="Matters because Z.",
    )
    assert "## Summary" in out
    assert "## Key Findings" in out
    assert "## Methodology" in out
    assert "## Relevance" in out
    assert "> [!abstract]" in out
    assert "> [!success]" in out
    assert "> [!info]" in out
    assert "> [!note]" in out
    assert "^summary" in out
    assert "^findings" in out


def test_upgrade_paper_body_converts_plain_sections():
    body = (
        "some preamble\n\n"
        "## Summary\n\n"
        "Paper gist.\n\n"
        "## Key Findings\n\n"
        "- A\n- B\n\n"
        "## Methodology\n\n"
        "Method.\n\n"
        "## Relevance\n\n"
        "Relevance.\n"
    )
    out = upgrade_paper_body(body)
    assert "> [!abstract]" in out
    assert "> [!success]" in out
    assert "> [!info]" in out
    assert "> [!note]" in out
    # Heading anchors remain clean so regex extractors still match.
    import re
    assert re.search(r"^##\s+Summary\s*$", out, re.MULTILINE)
    assert re.search(r"^##\s+Key Findings\s*$", out, re.MULTILINE)


def test_upgrade_paper_body_is_idempotent():
    body = (
        "## Summary\n\n"
        "Paper gist.\n\n"
        "## Relevance\n\n"
        "Matters because Z.\n"
    )
    once = upgrade_paper_body(body)
    twice = upgrade_paper_body(once)
    assert once == twice


def test_upgrade_paper_body_leaves_unknown_sections_untouched():
    body = (
        "## Summary\n\n"
        "gist\n\n"
        "## Notes & Annotations\n\n"
        "> a quote\n"
    )
    out = upgrade_paper_body(body)
    assert "> [!abstract]" in out
    assert "## Notes & Annotations" in out
    assert "> a quote" in out


def test_crystal_to_markdown_wraps_tldr_in_abstract_callout():
    from research_hub.crystal import Crystal

    c = Crystal(
        cluster_slug="test",
        question_slug="q1",
        question="What?",
        tldr="The answer is X.",
        gist="",
        full="",
    )
    text = c.to_markdown()
    assert "## TL;DR" in text
    assert "> [!abstract]" in text
    assert "^tldr" in text


def test_crystal_round_trip_preserves_tldr_text():
    from research_hub.crystal import Crystal

    c = Crystal(
        cluster_slug="test",
        question_slug="q1",
        question='Needs "quotes"',
        tldr="Short answer.",
        gist="More detail.",
        full="Full paragraph.",
    )
    rehydrated = Crystal.from_markdown(c.to_markdown())
    assert rehydrated.tldr == "Short answer."
    assert rehydrated.gist == "More detail."


def test_overview_template_emits_callouts():
    from research_hub.topic import OVERVIEW_TEMPLATE

    rendered = OVERVIEW_TEMPLATE.format(
        cluster_slug="demo",
        cluster_title="Demo cluster",
    )
    assert "> [!abstract]" in rendered
    assert "> [!question]" in rendered
    assert "> [!warning]" in rendered
    assert "^tldr" in rendered


def test_vault_polish_cli_converts_paper_notes(tmp_path, monkeypatch):
    """End-to-end: polish-markdown upgrades a legacy note when --apply is passed."""
    raw = tmp_path / "raw" / "test-cluster"
    raw.mkdir(parents=True)
    note = raw / "paper.md"
    note.write_text(
        "---\n"
        "title: \"X\"\n"
        "topic_cluster: \"test-cluster\"\n"
        "---\n\n"
        "# X\n\n"
        "## Summary\n\n"
        "gist\n\n"
        "## Relevance\n\n"
        "why\n",
        encoding="utf-8",
    )

    from research_hub import cli as cli_module

    fake_cfg = type("Cfg", (), {"raw": tmp_path / "raw"})()
    monkeypatch.setattr(cli_module, "get_config", lambda: fake_cfg)

    rc_dry = cli_module._vault_polish_markdown(cluster="test-cluster", dry_run=True)
    assert rc_dry == 0
    # Dry-run leaves content untouched.
    assert "> [!abstract]" not in note.read_text(encoding="utf-8")

    rc_apply = cli_module._vault_polish_markdown(cluster="test-cluster", dry_run=False)
    assert rc_apply == 0
    text = note.read_text(encoding="utf-8")
    assert "> [!abstract]" in text
    assert "> [!note]" in text

    # Second run should be a no-op (idempotent).
    rc_again = cli_module._vault_polish_markdown(cluster="test-cluster", dry_run=False)
    assert rc_again == 0
    assert note.read_text(encoding="utf-8") == text
