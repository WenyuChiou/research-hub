"""Concrete multi-locale-mirror-sync checks for the two workspace locales.

Image text still requires recorded visual review; structural parity is not an
OCR, translation-quality or scientific-acceptance claim.
"""
import json
import hashlib
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]


def without_code(text):
    return re.sub(r"```.*?```", "", text, flags=re.S)


def anchors(text):
    names = set(re.findall(r'<a\s+id="([^"]+)"', text))
    counts = {}
    for heading in re.findall(r"^#{1,6}\s+(.+)$", without_code(text), re.M):
        slug = re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-")
        number = counts.get(slug, 0)
        names.add(slug + (f"-{number}" if number else ""))
        counts[slug] = number + 1
    return names


@pytest.mark.parametrize("files", [("README.md", "README.zh-TW.md"), ("docs/workspace-guide.md", "docs/workspace-guide.zh-TW.md")])
def test_multi_locale_mirror_sync(files):
    texts = [(ROOT / filename).read_text(encoding="utf-8") for filename in files]
    assert len(re.findall(r"^## ", texts[0], re.M)) == len(re.findall(r"^## ", texts[1], re.M))
    table_shape = lambda text: [len(re.split(r"(?<!\\)\|", line)) for line in without_code(text).splitlines() if line.startswith("|")]
    assert table_shape(texts[0]) == table_shape(texts[1])
    # These documents contain no Mermaid blocks; diagrams use one shared map.
    assert all("```mermaid" not in text for text in texts)
    for filename, text in zip(files, texts):
        for term in ("Word", "LaTeX", "Markdown", "Codex", "MCP", "NotebookLM", "SHA256" if "guide" in filename else "PyPI"):
            assert term in text
        assert not re.search(r"pushed today|updated today|今天已更新|今天 pushed|very recently", text)
        for destination in re.findall(r"\]\(([^)]+)\)", without_code(text)):
            target = urlsplit(destination)
            if target.scheme or target.netloc:
                continue
            path = (ROOT / filename).parent / unquote(target.path) if target.path else ROOT / filename
            assert path.exists(), (filename, destination)
            if target.fragment and path.suffix == ".md":
                assert unquote(target.fragment) in anchors(path.read_text(encoding="utf-8")), (filename, destination)
    assert "繁體中文" in texts[1] or "人類" in texts[1]
    assert not re.search(r"软件|网络|数据", texts[1])


def test_bilingual_visual_semantics_share_node_and_edge_identity():
    mapping = json.loads((ROOT / "docs/workspace-visuals.json").read_text(encoding="utf-8"))
    for name in ("lifecycle", "writing", "technical"):
        diagram = mapping[name]
        ids = [node["id"] for node in diagram["nodes"]]
        assert len(ids) == len(set(ids))
        for node in diagram["nodes"]:
            assert node["en"].strip() and node["zh-TW"].strip()
            assert not re.search(r"软件|网络|数据", node["zh-TW"])
        for key in ("edges", "feedback", "optional_edges", "separate_edges"):
            for edge in diagram.get(key, []):
                assert len(edge) == 2 and set(edge) <= set(ids)
        for locale in ("en", "zh-TW"):
            assert (ROOT / f"docs/images/workspace-{name}.{locale}.png").is_file()


def test_workspace_docs_describe_current_isolation_and_human_bounds():
    text = (ROOT / "docs/workspace-architecture.md").read_text(encoding="utf-8")
    for term in ("Vertical AI Research Reference Harness", "MCP", "SQLite", "manuscript_state.json", "workflow_state.yml", "proposal", "legacy"):
        assert term.lower() in text.lower()


def test_reviewed_visual_assets_have_exact_provenance():
    provenance = json.loads((ROOT / "docs/workspace-visual-provenance.json").read_text(encoding="utf-8"))
    for filename, record in provenance["assets"].items():
        assert hashlib.sha256((ROOT / "docs/images" / filename).read_bytes()).hexdigest() == record["sha256"]
