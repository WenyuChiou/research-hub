from __future__ import annotations

import re

from research_hub.dashboard.types import ClusterCard, PaperRow


def _escape_bibtex(value: str) -> str:
    return re.sub(r"([{}])", r"\\\1", value or "")


def build_bibtex_for_paper(paper: PaperRow, zot=None) -> str:
    """Return a BibTeX entry for one paper.

    Tries the Zotero API first when a client + zotero_key are present.
    On any failure (missing api key, no get_formatted method, network
    error, …) falls through to a minimal BibTeX built from the
    Obsidian frontmatter, so the [Cite] button always has SOMETHING
    to copy.
    """
    if zot is not None and paper.zotero_key:
        try:
            result = zot.get_formatted(paper.zotero_key, "bibtex")
            if result:
                return result
        except Exception:
            pass  # fall through to frontmatter fallback
    try:
        fields = [
            f"@article{{{paper.slug},",
            f"  title  = {{{_escape_bibtex(paper.title)}}},",
            f"  author = {{{_escape_bibtex(paper.authors)}}},",
            f"  year   = {{{_escape_bibtex(paper.year)}}},",
            f"  doi    = {{{_escape_bibtex(paper.doi)}}}",
            "}",
        ]
        return "\n".join(fields)
    except Exception:
        return ""


def build_bibtex_for_cluster(cluster: ClusterCard) -> str:
    """Concatenate every paper's BibTeX with a blank line separator."""
    return "\n\n".join(paper.bibtex for paper in cluster.papers if paper.bibtex)
