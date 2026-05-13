from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import notebooklm

from research_hub.clusters import Cluster, ClusterRegistry


class _FakeNotebookAPI:
    def __init__(self, owner):
        self._owner = owner

    async def list(self):
        return list(self._owner.notebook_items)

    async def create(self, title: str):
        notebook = SimpleNamespace(
            id="nb-created",
            title=title,
            url="https://notebooklm.google.com/notebook/nb-created",
        )
        self._owner.notebook_items.append(notebook)
        return notebook


class _FakeSourcesAPI:
    def __init__(self, owner):
        self._owner = owner

    async def add_file(self, notebook_id: str, path: str):
        self._owner.uploads.append(("file", notebook_id, path))
        return SimpleNamespace(title=Path(path).name)

    async def add_url(self, notebook_id: str, url: str):
        self._owner.uploads.append(("url", notebook_id, url))
        return SimpleNamespace(title=url)


class _FakeArtifactsAPI:
    async def generate_report(self, notebook_id: str, **kwargs):
        return SimpleNamespace(task_id="report-1", status="completed", url="")

    async def wait_for_completion(self, notebook_id: str, task_id: str, **kwargs):
        return SimpleNamespace(task_id=task_id, status="completed", url="")

    async def download_report(self, notebook_id: str, output_path: str, artifact_id: str | None = None):
        Path(output_path).write_text("Briefing body", encoding="utf-8")
        return output_path


class _FakeChatAPI:
    async def ask(self, notebook_id: str, question: str, source_ids=None):
        return SimpleNamespace(
            answer=f"Answer for {question}",
            references=[
                SimpleNamespace(
                    source_id="src-1",
                    citation_number=1,
                    cited_text="quoted passage",
                    start_char=10,
                    end_char=24,
                )
            ],
        )


class _FakeUpstreamClient:
    instances: list["_FakeUpstreamClient"] = []

    def __init__(self):
        self.notebook_items = []
        self.uploads = []
        self.notebooks = _FakeNotebookAPI(self)
        self.sources = _FakeSourcesAPI(self)
        self.artifacts = _FakeArtifactsAPI()
        self.chat = _FakeChatAPI()
        _FakeUpstreamClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeUpstreamClientWithState(_FakeUpstreamClient):
    pass


def _mock_from_storage(monkeypatch):
    _FakeUpstreamClient.instances.clear()

    async def _from_storage(**kwargs):
        return _FakeUpstreamClientWithState()

    monkeypatch.setattr(notebooklm.NotebookLMClient, "from_storage", staticmethod(_from_storage))


def _cfg(tmp_path: Path) -> SimpleNamespace:
    hub = tmp_path / ".research_hub"
    hub.mkdir()
    return SimpleNamespace(research_hub_dir=hub, clusters_file=hub / "clusters.yaml")


def _write_bundle(cfg: SimpleNamespace, cluster_slug: str, entries: list[dict]) -> None:
    bundle_dir = cfg.research_hub_dir / "bundles" / f"{cluster_slug}-20260512T000000Z"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")


def test_upload_cluster_uses_notebooklm_py_from_storage(monkeypatch, tmp_path):
    _mock_from_storage(monkeypatch)
    from research_hub.notebooklm.upload import upload_cluster

    cfg = _cfg(tmp_path)
    cluster = Cluster(slug="alpha", name="Alpha")
    registry = ClusterRegistry(cfg.clusters_file)
    registry.clusters[cluster.slug] = cluster
    registry.save()
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF")
    _write_bundle(
        cfg,
        cluster.slug,
        [
            {"action": "pdf", "pdf_path": str(pdf_path)},
            {"action": "url", "url": "https://example.com/paper"},
        ],
    )
    monkeypatch.setattr("research_hub.notebooklm.upload.time.sleep", lambda _seconds: None)

    report = upload_cluster(cluster, cfg)

    assert report.success_count == 2
    assert report.notebook_id == "nb-created"
    assert _FakeUpstreamClient.instances[-1].uploads == [
        ("file", "nb-created", str(pdf_path)),
        ("url", "nb-created", "https://example.com/paper"),
    ]


def test_ask_returns_structured_references_v086(monkeypatch, tmp_path):
    _mock_from_storage(monkeypatch)
    from research_hub.notebooklm.ask import ask_cluster_notebook
    from research_hub.notebooklm.auth import default_state_file

    cfg = _cfg(tmp_path)
    default_state_file(cfg.research_hub_dir).parent.mkdir(parents=True)
    default_state_file(cfg.research_hub_dir).write_text("{}", encoding="utf-8")
    cluster = Cluster(
        slug="alpha",
        name="Alpha",
        notebooklm_notebook_url="https://notebooklm.google.com/notebook/nb-created",
        notebooklm_notebook_id="nb-created",
    )

    result = ask_cluster_notebook(cluster, cfg, question="What changed?")

    assert result.ok is True
    assert result.answer == "Answer for What changed?"
    assert len(result.references) == 1
    assert result.references[0].source_id == "src-1"
    assert result.references[0].citation_number == 1
    assert result.artifact_path is not None and result.artifact_path.exists()
