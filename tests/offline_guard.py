"""Block every non-loopback network connection (test mode for offline verification).

Patches socket.create_connection, socket.socket.connect/connect_ex and getaddrinfo so that
only localhost / 127.0.0.0/8 / ::1 can be reached. Any other attempt raises
OfflineViolation and is recorded in ``attempts``.
"""

from __future__ import annotations

import ipaddress
import socket
from contextlib import contextmanager


class OfflineViolation(OSError):
    pass


LOOPBACK_NAMES = {"localhost", "localhost.localdomain", ""}


def _is_loopback(host) -> bool:
    if host is None:
        return True
    host = str(host).strip("[]").lower()
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


@contextmanager
def block_network():
    attempts: list[str] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create = socket.create_connection
    real_getaddrinfo = socket.getaddrinfo

    def check(address) -> None:
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(address, (str, bytes)) and not isinstance(address, tuple):
            return  # AF_UNIX path or similar: not a network connection
        if not _is_loopback(host):
            attempts.append(str(host))
            raise OfflineViolation(f"offline test mode: connection to {host!r} blocked")

    def guarded_connect(self, address):
        check(address)
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        check(address)
        return real_connect_ex(self, address)

    def guarded_create(address, *args, **kwargs):
        check(address)
        return real_create(address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        check((host, 0))
        return real_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create
    socket.getaddrinfo = guarded_getaddrinfo
    try:
        yield attempts
    finally:
        socket.socket.connect = real_connect
        socket.socket.connect_ex = real_connect_ex
        socket.create_connection = real_create
        socket.getaddrinfo = real_getaddrinfo
