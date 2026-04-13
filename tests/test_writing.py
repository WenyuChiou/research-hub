from __future__ import annotations

from pathlib import Path

from research_hub.writing import (
    Quote,
    build_inline_citation,
    build_markdown_citation,
    format_paper_meta_from_frontmatter,
    load_all_quotes,
    save_quote,
)


class StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"


def _cfg(tmp_path: Path) -> StubConfig:
    cfg = StubConfig(tmp_path / "vault")
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    cfg.clusters_file.write_text("- slug: agents\n  name: Agents\n", encoding="utf-8")
    return cfg


def _note(cfg: StubConfig, slug: str = "paper-one", *, authors: str = "Doe, Jane; Roe, Alex") -> Path:
    note_dir = cfg.raw / "agents"
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(
        f"""---
title: "Paper One"
authors: "{authors}"
year: "2025"
doi: "10.1000/one"
topic_cluster: "agents"
status: "cited"
---
Body
""",
        encoding="utf-8",
    )
    return path


def test_build_inline_citation_apa_one_author():
    assert build_inline_citation({"authors": "Doe, Jane", "year": "2025"}) == "(Doe, 2025)"


def test_build_inline_citation_apa_two_authors():
    assert build_inline_citation({"authors": "Doe, Jane; Roe, Alex", "year": "2025"}) == "(Doe & Roe, 2025)"


def test_build_inline_citation_apa_three_or_more():
    assert build_inline_citation({"authors": "Doe, Jane; Roe, Alex; Poe, Sam", "year": "2025"}) == "(Doe et al., 2025)"


def test_build_inline_citation_chicago():
    assert build_inline_citation({"authors": "Doe, Jane; Roe, Alex", "year": "2025"}, style="chicago") == "(Doe and Roe 2025)"


def test_build_inline_citation_latex_derives_bibkey_from_slug():
    assert build_inline_citation({"authors": "Doe, Jane", "year": "2025", "slug": "paper-one"}, style="latex") == "\\citep{paper-one}"


def test_build_markdown_citation_uses_doi_link():
    assert build_markdown_citation({"authors": "Doe, Jane; Roe, Alex; Poe, Sam", "year": "2025", "doi": "10.1000/one"}) == "[Doe et al. (2025)](https://doi.org/10.1000/one)"


def test_save_quote_creates_file_with_frontmatter(tmp_path):
    cfg = _cfg(tmp_path)
    path = save_quote(cfg, Quote(slug="paper-one", doi="", title="", authors="", year="", page="12", text="hello"))
    text = path.read_text(encoding="utf-8")
    assert 'page: "12"' in text
    assert "> hello" in text


def test_save_quote_appends_to_existing_file(tmp_path):
    cfg = _cfg(tmp_path)
    save_quote(cfg, Quote(slug="paper-one", doi="", title="", authors="", year="", page="12", text="one"))
    path = save_quote(cfg, Quote(slug="paper-one", doi="", title="", authors="", year="", page="13", text="two"))
    text = path.read_text(encoding="utf-8")
    assert text.count("---") >= 4
    assert "> one" in text
    assert "> two" in text


def test_load_all_quotes_parses_multi_block_files(tmp_path):
    cfg = _cfg(tmp_path)
    _note(cfg)
    path = cfg.research_hub_dir / "quotes" / "paper-one.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """---
captured_at: 2026-04-12T12:00:00Z
page: "12"
context_note: "Section A"
---
> First quote

---
captured_at: 2026-04-12T13:00:00Z
page: "13"
context_note: ""
---
> Second quote
""",
        encoding="utf-8",
    )
    quotes = load_all_quotes(cfg)
    assert len(quotes) == 2
    assert quotes[0].page == "13"
    assert quotes[1].text == "First quote"


def test_load_all_quotes_returns_empty_when_no_quotes_dir(tmp_path):
    cfg = _cfg(tmp_path)
    assert load_all_quotes(cfg) == []


def test_format_paper_meta_from_frontmatter_reads_authors(tmp_path):
    cfg = _cfg(tmp_path)
    path = _note(cfg)
    meta = format_paper_meta_from_frontmatter(path)
    assert meta["authors"] == "Doe, Jane; Roe, Alex"
    assert meta["title"] == "Paper One"


def test_quote_slug_is_preserved(tmp_path):
    cfg = _cfg(tmp_path)
    _note(cfg, slug="paper-one")
    save_quote(cfg, Quote(slug="paper-one", doi="", title="", authors="", year="", page="12", text="hello"))
    quote = load_all_quotes(cfg)[0]
    assert quote.slug == "paper-one"
