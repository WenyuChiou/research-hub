from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Watcher:
    def __init__(self, cfg, broadcaster) -> None:
        self.cfg = cfg
        self.broadcaster = broadcaster

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


def test_serve_dashboard_returns_gracefully_when_port_in_use(monkeypatch):
    from research_hub.dashboard import http_server

    monkeypatch.setattr(http_server, "VaultWatcher", _Watcher)
    monkeypatch.setattr(http_server, "EventBroadcaster", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(http_server, "JobQueue", lambda: SimpleNamespace())
    monkeypatch.setattr(
        http_server,
        "ThreadingHTTPServer",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("address already in use")),
    )

    assert http_server.serve_dashboard(SimpleNamespace(), open_browser=False) is None


def test_serve_dashboard_propagates_other_oserror(monkeypatch):
    from research_hub.dashboard import http_server

    monkeypatch.setattr(http_server, "VaultWatcher", _Watcher)
    monkeypatch.setattr(http_server, "EventBroadcaster", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(http_server, "JobQueue", lambda: SimpleNamespace())
    monkeypatch.setattr(
        http_server,
        "ThreadingHTTPServer",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("permission denied")),
    )

    with pytest.raises(OSError, match="permission denied"):
        http_server.serve_dashboard(SimpleNamespace(), open_browser=False)
