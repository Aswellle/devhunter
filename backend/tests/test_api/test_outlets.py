"""
tests/test_api/test_outlets.py
机器可读出口 API 测试：GET /api/llms.txt
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestLlmsTxt:
    """llms.txt 出口测试"""

    def test_public_no_auth_required(self):
        """公开访问：无需认证"""
        response = client.get("/api/llms.txt")
        assert response.status_code == 200

    def test_content_type_is_plain_text(self):
        """Content-Type 为 text/plain"""
        response = client.get("/api/llms.txt")
        assert response.headers["content-type"].startswith("text/plain")

    def test_follows_llms_txt_structure(self):
        """符合 llms.txt 规范：H1 标题开头 + blockquote 简介 + 分节链接"""
        body = client.get("/api/llms.txt").text
        assert body.startswith("# DevHunter")
        assert "> 自托管的内容聚合系统" in body
        assert "## " in body
        assert "](/api/" in body  # markdown 链接指向 /api/ 路径

    def test_documents_auth_model(self):
        """说明认证模型（单用户 JWT）"""
        body = client.get("/api/llms.txt").text
        assert "/api/auth/login" in body
        assert "devhunter_token" in body
