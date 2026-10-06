from __future__ import annotations

import ipaddress
import socket
import threading
from typing import Any, ClassVar


class OfflineNetworkError(ConnectionRefusedError):
    """Raised when offline runtime code attempts a non-loopback connection."""


class OfflineNetworkGuard:
    _lock: ClassVar[threading.RLock] = threading.RLock()
    _install_count: ClassVar[int] = 0
    _original_connect: ClassVar[Any] = None
    _original_connect_ex: ClassVar[Any] = None

    def __init__(self) -> None:
        self._installed = False

    @staticmethod
    def is_allowed_target(host: object) -> bool:
        if isinstance(host, bytes):
            try:
                host = host.decode("ascii")
            except UnicodeDecodeError:
                return False
        if not isinstance(host, str):
            return False
        normalized = host.strip().rstrip(".").casefold()
        if normalized == "localhost":
            return True
        try:
            return ipaddress.ip_address(normalized).is_loopback
        except ValueError:
            return False

    @classmethod
    def _address_allowed(cls, sock: socket.socket, address: object) -> bool:
        if sock.family not in {socket.AF_INET, socket.AF_INET6}:
            return True
        if not isinstance(address, tuple) or not address:
            return False
        return cls.is_allowed_target(address[0])

    @staticmethod
    def _guarded_connect(sock: socket.socket, address: object) -> Any:
        cls = OfflineNetworkGuard
        if not cls._address_allowed(sock, address):
            raise OfflineNetworkError(f"offline runtime blocked outbound target: {address!r}")
        return cls._original_connect(sock, address)

    @staticmethod
    def _guarded_connect_ex(sock: socket.socket, address: object) -> int:
        cls = OfflineNetworkGuard
        if not cls._address_allowed(sock, address):
            raise OfflineNetworkError(f"offline runtime blocked outbound target: {address!r}")
        return int(cls._original_connect_ex(sock, address))

    def install(self) -> None:
        with type(self)._lock:
            if self._installed:
                return
            cls = type(self)
            if cls._install_count == 0:
                cls._original_connect = socket.socket.connect
                cls._original_connect_ex = socket.socket.connect_ex
                socket.socket.connect = cls._guarded_connect  # type: ignore[method-assign]
                socket.socket.connect_ex = cls._guarded_connect_ex  # type: ignore[method-assign]
            cls._install_count += 1
            self._installed = True

    def remove(self) -> None:
        with type(self)._lock:
            if not self._installed:
                return
            cls = type(self)
            cls._install_count -= 1
            self._installed = False
            if cls._install_count == 0:
                socket.socket.connect = cls._original_connect  # type: ignore[method-assign]
                socket.socket.connect_ex = cls._original_connect_ex  # type: ignore[method-assign]
                cls._original_connect = None
                cls._original_connect_ex = None

    def __enter__(self) -> "OfflineNetworkGuard":
        self.install()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.remove()
