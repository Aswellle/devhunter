"""
连接层 IP pinning（SSRFPinnedNetworkBackend / SSRFPinnedTransport）测试。

验证 DNS rebinding TOCTOU 的关闭契约：TCP 连接只拨号到同一次调用内
通过黑名单校验的地址，DNS 解析失败/全部命中黑名单时 fail-closed。
"""
import socket

import httpcore
import httpx
import pytest

from app.core.ssrf import (
    SSRFPinnedNetworkBackend,
    SSRFPinnedTransport,
    _safe_dial_targets,
)

PUBLIC_V4 = "93.184.216.34"
PUBLIC_V4_B = "93.184.216.35"


class _RecordingDial(httpcore.NetworkBackend):
    """记录 connect_tcp 实际拨号目标；可配置部分地址连接被拒。"""

    def __init__(self, buffer: list[bytes] | None = None, refused: set[str] | None = None):
        self.dialed: list[tuple[str, int, float | None]] = []
        self.refused = refused or set()
        self._buffer = buffer or []

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.dialed.append((host, port, timeout))
        if host in self.refused:
            raise httpcore.ConnectError(f"connection refused by {host}")
        return httpcore.MockStream(list(self._buffer))

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise AssertionError("Unix domain socket 不应被拨号")


def _addrinfo(records):
    """(family, ip) 列表 → getaddrinfo 形状。"""
    return [
        (family, socket.SOCK_STREAM, 6, "", (ip, 0, 0, 0) if family == socket.AF_INET6 else (ip, 0))
        for family, ip in records
    ]


# ── _safe_dial_targets ────────────────────────────────────────────────────────

def test_ip_literal_dialed_without_dns(monkeypatch):
    """IP 字面量直接校验后拨号，不做 DNS 解析。"""

    def _no_dns(*a, **k):
        raise AssertionError("IP 字面量不应触发 DNS 解析")

    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)
    targets, err = _safe_dial_targets(PUBLIC_V4, 80)
    assert err is None
    assert targets == [PUBLIC_V4]


def test_ip_literal_private_blocked(monkeypatch):
    def _no_dns(*a, **k):
        raise AssertionError("IP 字面量不应触发 DNS 解析")

    monkeypatch.setattr(socket, "getaddrinfo", _no_dns)
    targets, err = _safe_dial_targets("127.0.0.1", 80)
    assert targets == []
    assert "SSRF blocked" in err


def test_mixed_records_private_never_dialed(monkeypatch):
    """解析结果混入私有地址时整体拒绝（与预检层语义一致）。"""
    records = [(socket.AF_INET, "10.0.0.5"), (socket.AF_INET, PUBLIC_V4)]
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, **k: _addrinfo(records))
    targets, err = _safe_dial_targets("rebind.example.com", 80)
    assert targets == []
    assert "SSRF blocked" in err
    assert "10.0.0.5" in err


def test_public_records_dialed_in_resolution_order(monkeypatch):
    records = [(socket.AF_INET, PUBLIC_V4), (socket.AF_INET6, "2606:2800:220:1:248:1893:25c8:1946")]
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, **k: _addrinfo(records))
    targets, err = _safe_dial_targets("example.com", 80)
    assert err is None
    assert targets[0] == PUBLIC_V4


def test_dns_failure_fail_closed(monkeypatch):
    def _raise_gaierror(*a, **k):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _raise_gaierror)
    targets, err = _safe_dial_targets("down.example.com", 80)
    assert targets == []
    assert "fail-closed" in err


def test_mapped_ipv6_record_blocked(monkeypatch):
    """::ffff:10.0.0.1 形式的内网地址在连接层同样被拦截。"""
    records = [(socket.AF_INET6, "::ffff:10.0.0.1")]
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, **k: _addrinfo(records))
    targets, err = _safe_dial_targets("mapped.example.com", 80)
    assert targets == []
    assert "SSRF blocked" in err


# ── SSRFPinnedNetworkBackend ──────────────────────────────────────────────────

def test_backend_dials_validated_ip_not_hostname(monkeypatch):
    """TCP 拨号目标是校验通过的 IP，而非主机名（pinning 契约核心）。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda h, p, **k: _addrinfo([(socket.AF_INET, PUBLIC_V4), (socket.AF_INET, PUBLIC_V4_B)]),
    )
    dial = _RecordingDial()
    backend = SSRFPinnedNetworkBackend(dial=dial)
    stream = backend.connect_tcp("example.com", 80, timeout=7.5)
    assert isinstance(stream, httpcore.MockStream)
    # 拨的是解析出的首个公网 IP，不是主机名
    assert dial.dialed == [(PUBLIC_V4, 80, 7.5)]


def test_backend_blocked_raises_connect_error_without_dialing(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda h, p, **k: _addrinfo([(socket.AF_INET, "192.168.1.1")]),
    )
    dial = _RecordingDial()
    backend = SSRFPinnedNetworkBackend(dial=dial)
    with pytest.raises(httpcore.ConnectError, match="SSRF blocked"):
        backend.connect_tcp("internal.example.com", 80)
    assert dial.dialed == []


def test_backend_dns_failure_raises_connect_error(monkeypatch):
    def _raise_gaierror(*a, **k):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _raise_gaierror)
    backend = SSRFPinnedNetworkBackend(dial=_RecordingDial())
    with pytest.raises(httpcore.ConnectError, match="fail-closed"):
        backend.connect_tcp("down.example.com", 80)


def test_backend_falls_back_to_next_validated_address(monkeypatch):
    """首个 IP 连接被拒（非安全问题）时，尝试下一个校验通过的地址。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda h, p, **k: _addrinfo([(socket.AF_INET, PUBLIC_V4), (socket.AF_INET, PUBLIC_V4_B)]),
    )
    dial = _RecordingDial(refused={PUBLIC_V4})
    backend = SSRFPinnedNetworkBackend(dial=dial)
    backend.connect_tcp("example.com", 80)
    assert [h for h, _, _ in dial.dialed] == [PUBLIC_V4, PUBLIC_V4_B]


def test_backend_reraises_timeout_type_after_all_targets_fail(monkeypatch):
    """全部地址失败时保留原始异常类型，引擎的超时分类不受影响。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda h, p, **k: _addrinfo([(socket.AF_INET, PUBLIC_V4)]),
    )

    class _TimeoutDial(httpcore.NetworkBackend):
        def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            raise httpcore.ConnectTimeout("timed out")

    backend = SSRFPinnedNetworkBackend(dial=_TimeoutDial())
    with pytest.raises(httpcore.ConnectTimeout):
        backend.connect_tcp("slow.example.com", 80)


# ── SSRFPinnedTransport 接线与全栈 ───────────────────────────────────────────

def test_transport_wires_pinning_backend_into_pool():
    transport = SSRFPinnedTransport()
    backend = transport._pool._network_backend
    assert isinstance(backend, SSRFPinnedNetworkBackend)


def test_full_stack_client_dials_pinned_ip(monkeypatch):
    """httpx.Client 全栈：DNS 返回主机名，真实请求拨到校验过的 IP。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda h, p, **k: _addrinfo([(socket.AF_INET, PUBLIC_V4)]),
    )
    dial = _RecordingDial(buffer=[b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"])
    client = httpx.Client(
        transport=SSRFPinnedTransport(dial_backend=dial),
        follow_redirects=False,
        timeout=httpx.Timeout(connect=9.0, read=9.0, write=9.0, pool=5.0),
    )
    try:
        resp = client.get("http://example.com/")
        assert resp.status_code == 200
        # 请求 URL 保持原始主机名（TLS SNI/Host 头不受影响），连接层拨的是 IP，
        # 且 connect timeout 原样透传
        assert str(resp.request.url) == "http://example.com/"
        assert dial.dialed == [(PUBLIC_V4, 80, 9.0)]
    finally:
        client.close()


def test_full_stack_client_blocks_private_resolution(monkeypatch):
    """全栈：解析出私有地址时请求失败，httpx 侧映射为 ConnectError。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda h, p, **k: _addrinfo([(socket.AF_INET, "127.0.0.1")]),
    )
    dial = _RecordingDial()
    client = httpx.Client(transport=SSRFPinnedTransport(dial_backend=dial))
    try:
        with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
            client.get("http://internal.example.com/")
        assert dial.dialed == []
    finally:
        client.close()
