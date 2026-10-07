import socket

import pytest

from personal_predictive_ai.runtime.offline_guard import (
    OfflineNetworkError,
    OfflineNetworkGuard,
)


def test_guard_allows_ipv4_loopback_and_denies_public_ip_before_connect() -> None:
    original_connect = socket.socket.connect
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    with OfflineNetworkGuard():
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.settimeout(1.0)
            client.connect((host, port))
        finally:
            client.close()

        blocked = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OfflineNetworkError):
                blocked.connect(("8.8.8.8", 53))
        finally:
            blocked.close()

    server.close()
    assert socket.socket.connect is original_connect


def test_guard_denies_hostnames_without_dns_and_is_reversible() -> None:
    original_connect_ex = socket.socket.connect_ex

    guard = OfflineNetworkGuard()
    guard.install()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OfflineNetworkError):
                sock.connect_ex(("example.com", 443))
        finally:
            sock.close()
    finally:
        guard.remove()

    assert socket.socket.connect_ex is original_connect_ex


def test_loopback_hostname_is_allowed_by_policy_without_dns() -> None:
    guard = OfflineNetworkGuard()
    assert guard.is_allowed_target("localhost") is True
    assert guard.is_allowed_target("127.0.0.1") is True
    assert guard.is_allowed_target("::1") is True
    assert guard.is_allowed_target("192.0.2.1") is False


def test_guard_blocks_explicit_dns_resolution_and_restores_resolver() -> None:
    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyname = socket.gethostbyname

    with OfflineNetworkGuard():
        with pytest.raises(OfflineNetworkError):
            socket.getaddrinfo("example.com", 443)
        with pytest.raises(OfflineNetworkError):
            socket.gethostbyname("example.com")
        assert socket.getaddrinfo("localhost", 80)

    assert socket.getaddrinfo is original_getaddrinfo
    assert socket.gethostbyname is original_gethostbyname


def test_guard_blocks_udp_sendto_non_loopback_but_allows_loopback() -> None:
    original_sendto = socket.socket.sendto
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(1.0)
    host, port = receiver.getsockname()

    with OfflineNetworkGuard():
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            assert sender.sendto(b"local", (host, port)) == 5
            payload, _ = receiver.recvfrom(32)
            assert payload == b"local"
            with pytest.raises(OfflineNetworkError):
                sender.sendto(b"blocked", ("8.8.8.8", 53))
        finally:
            sender.close()

    receiver.close()
    assert socket.socket.sendto is original_sendto
