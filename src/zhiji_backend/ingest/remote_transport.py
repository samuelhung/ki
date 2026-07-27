"""Pinned HTTP transport for untrusted remote media URLs."""

from __future__ import annotations

import ipaddress
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests  # type: ignore
from requests.cookies import get_cookie_header
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util import Timeout

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class _RemoteTarget:
    scheme: str
    hostname: str
    port: int
    host_header: str
    request_target: str
    public_ips: tuple[str, ...]


class _PinnedResponse:
    def __init__(self, response, pool) -> None:
        self._response = response
        self._pool = pool
        self.status_code = response.status
        self.headers = response.headers
        self._closed = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        try:
            yield from self._response.stream(chunk_size, decode_content=False)
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._response.close()
        finally:
            self._pool.close()


class _PinnedConnection:
    def __init__(self, pool) -> None:
        self._pool = pool
        self._response_cls = _PinnedResponse

    def get(self, target: str, *, headers: dict, timeout):
        if isinstance(timeout, tuple):
            timeout = Timeout(connect=timeout[0], read=timeout[1])
        try:
            response = self._pool.urlopen(
                "GET",
                target,
                headers=headers,
                timeout=timeout,
                redirect=False,
                retries=False,
                preload_content=False,
                decode_content=False,
            )
        except BaseException:
            self._pool.close()
            raise
        return self._response_cls(response, self._pool)


def create_pinned_connection(
    scheme: str,
    ip: str,
    port: int,
    hostname: str,
    *,
    http_pool_cls=HTTPConnectionPool,
    https_pool_cls=HTTPSConnectionPool,
    connection_cls=_PinnedConnection,
    response_cls=_PinnedResponse,
):
    if scheme == "https":
        pool = https_pool_cls(
            ip,
            port=port,
            assert_hostname=hostname,
            server_hostname=hostname,
            cert_reqs=ssl.CERT_REQUIRED,
            maxsize=1,
            block=True,
        )
    else:
        pool = http_pool_cls(ip, port=port, maxsize=1, block=True)
    connection = connection_cls(pool)
    connection._response_cls = response_cls
    return connection


def is_trusted_365yg_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        return False
    host = (parsed.hostname or "").rstrip(".").lower()
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.username is None
        and parsed.password is None
        and (host == "365yg.com" or host.endswith(".365yg.com"))
    )


def _resolve_host(host: str, port: int) -> list[str]:
    addresses = {
        sockaddr[0]
        for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    }
    return sorted(addresses)


def _validate_remote_url(
    url: str,
    *,
    resolver: Callable[[str, int], list[str]],
) -> _RemoteTarget:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("远程视频端口无效") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("不支持的远程视频协议")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("远程视频地址不得包含凭据")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise ValueError("远程视频地址缺少主机名")
    scheme = parsed.scheme.lower()
    effective_port = port or (443 if scheme == "https" else 80)
    resolved = resolver(host, effective_port)
    if not resolved:
        raise ValueError("远程视频主机无法解析")
    try:
        addresses = [ipaddress.ip_address(value) for value in resolved]
    except ValueError as exc:
        raise ValueError("远程视频主机解析结果无效") from exc
    public_ips = tuple(
        sorted({str(address) for address in addresses if address.is_global})
    )
    if not public_ips:
        raise ValueError("远程视频地址必须解析到公网 IP")
    host_header = f"[{host}]" if ":" in host else host
    if port is not None:
        host_header = f"{host_header}:{port}"
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    return _RemoteTarget(
        scheme=scheme,
        hostname=host,
        port=effective_port,
        host_header=host_header,
        request_target=request_target,
        public_ips=public_ips,
    )


def _session_cookie_header(
    session: requests.Session | None,
    url: str,
    *,
    requests_module=requests,
) -> str | None:
    if session is None:
        return None
    prepared = requests_module.Request("GET", url).prepare()
    return get_cookie_header(session.cookies, prepared)


def _safe_get(
    session: requests.Session | None,
    url: str,
    *,
    headers: dict,
    timeout,
    resolver: Callable[[str, int], list[str]],
    max_redirects: int,
    connection_factory,
    requests_module=requests,
    validate_remote_url_fn=None,
    cookie_header_fn=None,
    redirect_statuses=None,
):
    validate_url = validate_remote_url_fn or _validate_remote_url
    followed_statuses = (
        _REDIRECT_STATUSES if redirect_statuses is None else redirect_statuses
    )
    current = url
    visited: set[str] = set()
    redirects = 0
    while True:
        if current in visited:
            raise ValueError("远程视频重定向循环")
        visited.add(current)
        target = validate_url(current, resolver=resolver)
        request_headers = {**headers, "Host": target.host_header}
        cookie_header = (
            cookie_header_fn(session, current)
            if cookie_header_fn is not None
            else _session_cookie_header(
                session,
                current,
                requests_module=requests_module,
            )
        )
        if cookie_header:
            request_headers["Cookie"] = cookie_header
        connection = connection_factory(
            target.scheme,
            target.public_ips[0],
            target.port,
            target.hostname,
        )
        response = connection.get(
            target.request_target,
            headers=request_headers,
            timeout=timeout,
        )
        if response.status_code not in followed_statuses:
            return response
        if redirects >= max_redirects:
            response.close()
            raise ValueError("远程视频重定向次数超过限制")
        location = (
            response.headers.get("Location")
            if hasattr(response.headers, "get")
            else None
        )
        if not location:
            response.close()
            raise ValueError("远程视频重定向缺少 Location")
        close = getattr(response, "close", None)
        if callable(close):
            close()
        current = urljoin(current, location)
        redirects += 1
