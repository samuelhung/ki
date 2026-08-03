"""Fail-closed public DNS fallback for Douyin media hosts behind Fake-IP DNS."""

from __future__ import annotations

import ipaddress
from collections.abc import Callable

import requests  # type: ignore

from .remote_transport import _resolve_host

DOH_ENDPOINT = "https://dns.google/resolve"
DOH_TIMEOUT = (5, 10)
_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")
_QUERY_TYPES = (("A", 1), ("AAAA", 28))


def _query_doh(host: str, *, doh_get: Callable = requests.get) -> list[str]:
    addresses: set[str] = set()
    try:
        for query_name, answer_type in _QUERY_TYPES:
            response = doh_get(
                DOH_ENDPOINT,
                params={"name": host, "type": query_name},
                headers={"Accept": "application/dns-json"},
                timeout=DOH_TIMEOUT,
                allow_redirects=False,
            )
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("unexpected DoH status")
            payload = response.json()
            if (
                not isinstance(payload, dict)
                or type(payload.get("Status")) is not int
                or payload["Status"] != 0
            ):
                raise ValueError("unsuccessful DoH response")
            for answer in payload.get("Answer") or []:
                if (
                    not isinstance(answer, dict)
                    or type(answer.get("type")) is not int
                    or answer["type"] != answer_type
                    or not isinstance(answer.get("data"), str)
                ):
                    continue
                address = ipaddress.ip_address(answer["data"])
                if address.is_global:
                    addresses.add(str(address))
    except (requests.RequestException, TypeError, ValueError) as exc:
        raise ValueError("抖音媒体公网 DNS 解析失败") from exc
    if not addresses:
        raise ValueError("抖音媒体公网 DNS 未返回可用地址")
    return sorted(
        addresses,
        key=lambda value: (
            ipaddress.ip_address(value).version,
            int(ipaddress.ip_address(value)),
        ),
    )


def resolve_douyin_host(
    host: str,
    port: int,
    *,
    system_resolver: Callable[[str, int], list[str]] = _resolve_host,
    doh_get: Callable = requests.get,
) -> list[str]:
    """Resolve normally, replacing only an all-Fake-IP answer with public DoH."""
    addresses = system_resolver(host, port)
    try:
        parsed = [ipaddress.ip_address(value) for value in addresses]
    except ValueError:
        return addresses
    if any(address.is_global for address in parsed):
        return addresses
    if parsed and all(
        address.version == 4 and address in _FAKE_IP_NETWORK for address in parsed
    ):
        return _query_doh(host, doh_get=doh_get)
    return addresses
