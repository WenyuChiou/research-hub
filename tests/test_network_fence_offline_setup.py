"""No sockets/server: verify setup preserves pytest-socket0.8.1 offline guards."""
from pathlib import Path
import runpy
import socket
from types import SimpleNamespace

import pytest
import pytest_socket


def fence():
    module = runpy.run_path(str(Path(__file__).with_name('conftest.py')))
    request = SimpleNamespace(node=SimpleNamespace(get_closest_marker=lambda name: None))
    return module['_network_fence'].__wrapped__(request)


def test_fence_setup_performs_no_dns_and_keeps_disabled_guards(monkeypatch):
    pytest_socket.disable_socket(allow_unix_socket=True)
    guarded_socket = socket.socket
    guarded_dns = socket.getaddrinfo
    generator = fence()
    try:
        next(generator)  # Before repair this tries blocked localhost resolution.
        assert socket.socket is guarded_socket
        assert socket.getaddrinfo is guarded_dns
        with pytest.raises(pytest_socket.SocketBlockedError):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for hostname in ('localhost', 'example.invalid'):
            with pytest.raises(pytest_socket.SocketBlockedError):
                socket.getaddrinfo(hostname, 80)
    finally:
        generator.close()


def test_fence_exact_loopback_mapping_rejects_external_without_io(monkeypatch):
    calls = []
    monkeypatch.setattr(pytest_socket, '_true_connect', lambda instance, address: calls.append(address))
    def no_dns(*args, **kwargs):
        raise AssertionError('Fence setup must not resolve DNS')
    monkeypatch.setattr(socket, 'getaddrinfo', no_dns)
    generator = fence()
    class FakeSocket:
        family = socket.AF_INET
        closed = False
        def close(self):
            self.closed = True
    try:
        next(generator)
        for host in ('localhost', '127.0.0.1', '::1'):
            socket.socket.connect(FakeSocket(), (host, 80))
        assert calls == [(host, 80) for host in ('localhost', '127.0.0.1', '::1')]
        for host in ('192.0.2.1', 'example.invalid', '127.0.0.2', 'localhost.example.invalid'):
            fake = FakeSocket()
            with pytest.raises(pytest_socket.SocketConnectBlockedError):
                socket.socket.connect(fake, (host, 80))
            assert fake.closed
        assert len(calls) == 3
    finally:
        generator.close()
