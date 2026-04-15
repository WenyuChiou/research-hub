from __future__ import annotations

from pathlib import Path

from research_hub.paper import ensure_label_tags_in_body


def _note(path: Path, body: str = "Body text\n") -> Path:
    path.write_text(
        "---\n"
        'title: "Paper"\n'
        'topic_cluster: "agents"\n'
        "---\n"
        f"{body}",
        encoding="utf-8",
    )
    return path


def test_ensure_label_tags_creates_sentinel_block(tmp_path: Path):
    path = _note(tmp_path / "paper.md")

    changed = ensure_label_tags_in_body(path, ["seed", "core"])

    text = path.read_text(encoding="utf-8")
    assert changed is True
    assert "<!-- research-hub tags start -->" in text
    assert "#label/core #label/seed" in text
    assert "<!-- research-hub tags end -->" in text


def test_ensure_label_tags_idempotent(tmp_path: Path):
    path = _note(tmp_path / "paper.md")

    ensure_label_tags_in_body(path, ["seed", "core"])
    first = path.read_text(encoding="utf-8")
    changed = ensure_label_tags_in_body(path, ["seed", "core"])
    second = path.read_text(encoding="utf-8")

    assert changed is False
    assert first == second


def test_ensure_label_tags_updates_existing_block(tmp_path: Path):
    path = _note(
        tmp_path / "paper.md",
        body=(
            "Body text\n\n"
            "<!-- research-hub tags start -->\n"
            "#label/old\n"
            "<!-- research-hub tags end -->\n"
        ),
    )

    ensure_label_tags_in_body(path, ["benchmark"])

    text = path.read_text(encoding="utf-8")
    assert text.count("<!-- research-hub tags start -->") == 1
    assert "#label/benchmark" in text
    assert "#label/old" not in text


def test_ensure_label_tags_empty_labels(tmp_path: Path):
    path = _note(tmp_path / "paper.md")

    ensure_label_tags_in_body(path, [])

    text = path.read_text(encoding="utf-8")
    assert "<!-- research-hub tags start -->" in text
    assert "<!-- research-hub tags end -->" in text
    assert "#label/" not in text
