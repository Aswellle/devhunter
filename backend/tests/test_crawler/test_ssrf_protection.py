"""
Tests for SSRF DNS-rebinding TOCTOU fix.
Verifies engine.py uses resolve_and_validate_url with IP pinning.
"""
import socket

import pytest
from unittest.mock import patch, MagicMock
from app.crawler import engine


class TestSSRFProtection:
    """Test SSRF protection with IP pinning."""

    def test_resolve_and_validate_url_returns_ip(self):
        """Test that resolve_and_validate_url returns validated IP for pinning."""
        safe, msg, ip = engine.resolve_and_validate_url('https://example.com')
        assert safe is True
        assert ip is not None
        assert isinstance(ip, str)

    def test_private_ip_blocked(self):
        """Test that private IPs are blocked."""
        safe, msg, ip = engine.resolve_and_validate_url('http://127.0.0.1:8080')
        assert safe is False
        assert ip is None

    def test_loopback_blocked(self):
        """Test that loopback is blocked."""
        safe, msg, ip = engine.resolve_and_validate_url('http://localhost:8000')
        assert safe is False

    def test_cloud_metadata_blocked(self):
        """Test that cloud metadata endpoints are blocked."""
        safe, msg, ip = engine.resolve_and_validate_url('http://169.254.169.254/latest/meta-data')
        assert safe is False
        assert ip is None

    def test_dns_failure_fails_closed(self, monkeypatch):
        """
        DNS 解析失败必须 fail closed。

        用「不存在的域名」验证不可靠：部分环境（企业 DNS / VPN / 代理）会把任意
        域名解析到合成网段，断言会随环境漂移。这里直接让 getaddrinfo 抛异常，
        确定性地覆盖 fail-closed 分支。
        """
        def _raise_gaierror(*args, **kwargs):
            raise socket.gaierror("Name or service not known")

        monkeypatch.setattr(socket, "getaddrinfo", _raise_gaierror)
        safe, msg, ip = engine.resolve_and_validate_url('http://nonexistent.domain.invalid')
        assert safe is False
        assert ip is None

    def test_fetch_and_parse_uses_pinning(self):
        """Test that fetch_and_parse uses resolve_and_validate_url."""
        with patch.object(engine, 'resolve_and_validate_url') as mock_resolve:
            mock_resolve.return_value = (False, 'blocked', None)
            result = engine.fetch_and_parse('https://example.com', {}, [])
            assert 'SSRF blocked' in result.error
            mock_resolve.assert_called_once()

    def test_file_protocol_blocked(self):
        """Test that file: protocol is blocked."""
        safe, msg, ip = engine.resolve_and_validate_url('file:///etc/passwd')
        assert safe is False

    def test_ftp_protocol_blocked(self):
        """Test that ftp: protocol is blocked."""
        safe, msg, ip = engine.resolve_and_validate_url('ftp://example.com')
        assert safe is False


# ── IPv4-mapped IPv6 归一化 ──────────────────────────────────

def _addrinfo_result(sockaddr):
    return [(socket.AF_INET6, socket.SOCK_STREAM, 6, '', sockaddr)]


def test_ipv4_mapped_ipv6_private_blocked(monkeypatch):
    """回归：::ffff:10.0.0.1 与 10.0.0.0/8 版本不同，直接 in 判断为 False；
    OS 连接时会映射回 IPv4 内网地址，必须归一化后比对。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port: _addrinfo_result(('::ffff:10.0.0.1', 0, 0, 0)),
    )
    safe, msg, ip = engine.resolve_and_validate_url('http://[::ffff:10.0.0.1]/')
    assert safe is False


def test_ipv4_mapped_ipv6_metadata_blocked(monkeypatch):
    """mapped 形式的云元数据地址同样必须被拦截。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port: _addrinfo_result(('::ffff:169.254.169.254', 0, 0, 0)),
    )
    safe, msg, ip = engine.resolve_and_validate_url('http://[::ffff:169.254.169.254]/')
    assert safe is False


def test_ipv4_mapped_ipv6_public_allowed(monkeypatch):
    """mapped 形式的公网 IPv4 不得误伤。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port: _addrinfo_result(('::ffff:93.184.216.34', 0, 0, 0)),
    )
    safe, msg, ip = engine.resolve_and_validate_url('http://[::ffff:93.184.216.34]/')
    assert safe is True


def test_plain_ipv6_loopback_still_blocked(monkeypatch):
    """原生 IPv6 环回地址照常拦截（归一化不改变既有行为）。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port: _addrinfo_result(('::1', 0, 0, 0)),
    )
    safe, msg, ip = engine.resolve_and_validate_url('http://[::1]/')
    assert safe is False


def test_ipv6_unspecified_blocked(monkeypatch):
    """回归：IPv6 未指定地址 :: 必须被拦截（Linux 上 connect(::) 目标为本机）。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port: _addrinfo_result(('::', 0, 0, 0)),
    )
    safe, msg, ip = engine.resolve_and_validate_url('http://[::]:8000/')
    assert safe is False


def test_nat64_mapped_blocked(monkeypatch):
    """回归：NAT64 64:ff9b::/96 编码的 IPv4 地址必须被拦截。"""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port: _addrinfo_result(('64:ff9b::7f00:1', 0, 0, 0)),
    )
    safe, msg, ip = engine.resolve_and_validate_url('http://[64:ff9b::7f00:1]/')
    assert safe is False
