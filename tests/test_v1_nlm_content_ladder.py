"""F8 first-principles fix: content-priority source ladder.

NotebookLM needs content, not a URL. Ladder: local PDF -> Unpaywall OA
PDF (both already worked) -> **abstract as a copied-text source** ->
raw URL last. This file pins the new rung (abstract-text) + the
client/upload plumbing for `action="text"`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_hub.notebooklm.bundle import _extract_abstract


def _sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _StubCfg:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.logs = root / "logs"
        self.research_hub_dir = root / ".research_hub"


def _note(path: Path, *, doi: str, url: str = "", abstract: str = "",
          title: str = "Paper", cluster: str = "alpha") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = ["---", f'title: "{title}"', f'doi: "{doi}"', f'url: "{url}"',
          f'topic_cluster: "{cluster}"', "---", "", f"# {title}", ""]
    if abstract is not None:
        fm += ["## Abstract", "", abstract, "", "## Notes", "x"]
    path.write_text("\n".join(fm), encoding="utf-8")


# ---- _extract_abstract ----

def test_extract_abstract_pulls_section(tmp_path):
    p = tmp_path / "n.md"
    _note(p, doi="10.1/x", title="Perovskite Study",
          abstract="We report a 25% efficiency perovskite cell with a "
                   "novel passivation layer improving stability markedly.")
    out = _extract_abstract(p, {"title": "Perovskite Study", "doi": "10.1/x"})
    assert "Perovskite Study" in out          # title header
    assert "DOI: 10.1/x" in out
    assert "passivation layer" in out          # the abstract body


def test_extract_abstract_skips_placeholder(tmp_path):
    p = tmp_path / "n.md"
    _note(p, doi="10.1/x", abstract="[TODO: fill abstract]")
    assert _extract_abstract(p, {}) == ""


def test_extract_abstract_absent_section(tmp_path):
    p = tmp_path / "n.md"
    p.write_text("---\ntitle: x\n---\n# x\nno abstract heading here",
                 encoding="utf-8")
    assert _extract_abstract(p, {}) == ""


# ---- bundle ladder: abstract-text rung ----

def _bundle(tmp_path, *, url, abstract, probe_quality):
    from research_hub.clusters import Cluster
    from research_hub.notebooklm.bundle import bundle_cluster
    from research_hub.notebooklm.url_quality import UrlQuality

    cfg = _StubCfg(tmp_path)
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    (cfg.root / "pdfs").mkdir()
    _note(cfg.raw / "alpha" / "p.md", doi="10.1016/j.est.1", url=url,
          abstract=abstract)
    cluster = Cluster(slug="alpha", name="Alpha", obsidian_subfolder="alpha")
    pr = UrlQuality(probe_quality, "r", "s")
    with patch("research_hub.notebooklm.url_quality._probe_url", return_value=pr):
        return bundle_cluster(cluster, cfg)


def test_paywall_url_with_abstract_becomes_text(tmp_path):
    rep = _bundle(tmp_path,
                  url="https://doi.org/10.1016/j.est.1",
                  abstract="A long real abstract about solid-state battery "
                           "electrolyte interface stability and dendrites.",
                  probe_quality="likely_error_page")
    e = rep.entries[0]
    assert e.action == "text"
    assert "electrolyte interface" in e.text
    assert rep.text_count == 1


def test_good_url_still_preferred_over_abstract(tmp_path):
    rep = _bundle(tmp_path,
                  url="https://doi.org/10.1016/j.est.1",
                  abstract="A long real abstract that should NOT be used "
                           "because the URL probed OK (full content).",
                  probe_quality="ok")
    e = rep.entries[0]
    assert e.action == "url"          # good url beats abstract (full text)


def test_paywall_url_no_abstract_falls_to_url(tmp_path):
    rep = _bundle(tmp_path,
                  url="https://doi.org/10.1016/j.est.1",
                  abstract="[TODO]",                 # no usable abstract
                  probe_quality="likely_error_page")
    e = rep.entries[0]
    assert e.action == "url"          # unchanged conservative fallback


# ---- client / upload plumbing for action="text" ----

def test_client_upload_text_calls_add_text():
    from research_hub.notebooklm.client import NotebookLMClient

    c = NotebookLMClient.__new__(NotebookLMClient)
    added = {}

    class _Sources:
        async def add_text(self, nb, *, title, content):
            added.update(notebook=nb, title=title, content=content)
            return SimpleNamespace(title=title)

    c._client = SimpleNamespace(sources=_Sources())
    c._run = _sync
    c._active_notebook_id = "nb-1"

    res = c.upload_text("ABSTRACT TEXT", title="My Paper")
    assert added == {"notebook": "nb-1", "title": "My Paper",
                     "content": "ABSTRACT TEXT"}
    assert res.success is True
    assert res.source_kind == "text"
