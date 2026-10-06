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
