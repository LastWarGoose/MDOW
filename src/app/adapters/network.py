"""Network guard installed only in the dedicated downloader subprocess."""

import ipaddress
import socket
import sys

from app.models.task import AppError


def public_address(value):
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return public_address(str(ip.ipv4_mapped))
        if ip.sixtofour or ip.teredo:
            return False
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def install_guard():
    original = socket.getaddrinfo

    def resolve(host, port, *args, **kwargs):
        answers = original(host, port, *args, **kwargs)
        if not answers or any(not public_address(a[4][0]) for a in answers):
            raise AppError("Сетевой адрес заблокирован: разрешены только публичные адреса.")
        return answers

    def audit(event, args):
        if event == "socket.connect":
            address = args[1]
            # Connecting only to already resolved numeric addresses also prevents DNS rebinding.
            if not isinstance(address, tuple) or not public_address(str(address[0])):
                raise AppError("Соединение с непубличным сетевым адресом запрещено.")

    socket.getaddrinfo = resolve
    sys.addaudithook(audit)
