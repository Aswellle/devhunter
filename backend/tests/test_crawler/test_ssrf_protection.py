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
