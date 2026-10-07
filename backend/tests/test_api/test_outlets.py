"""
tests/test_api/test_outlets.py
机器可读出口 API 测试：GET /api/llms.txt、GET /api/rss*、GET /api/rss/feeds
"""
import hashlib
import uuid
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from app.core.security import create_access_token, machine_token
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo

client = TestClient(app)


def _auth_headers():
    """生成认证 header"""
    token = create_access_token({"sub": "admin"})
    return {"Authorization": f"Bearer {token}"}


def _seed_task_and_items(n_items: int = 2) -> str:
    """插入一个任务与若干条目，返回 task_id"""
    task = task_repo.insert({
        "name": f"RSS 测试源 {uuid.uuid4().hex[:6]}",
        "source_url": "https://example.com/list",
        "selector_list": ".item",
        "selector_title": "h2",
        "selector_link": "a",
        "cron_expression": "*/30 * * * *",
    })
    items = [
        {
            "task_id": task["id"],
            "title": f"条目 {i}：A&B <特殊字符>",
            "url": f"https://example.com/item/{i}",
            "url_hash": hashlib.sha256(f"{task['id']}-{i}".encode()).hexdigest(),
            "summary": f"摘要 {i} 含 CDATA 终止符测试 ]]> 与 & 符号",
            "fetched_at": "2026-10-07T08:00:00Z",
        }
        for i in range(n_items)
    ]
    item_repo.bulk_insert(items)
    return task["id"]


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


class TestRssAuth:
    """RSS 认证模型测试"""

    def test_rss_requires_auth_or_token(self):
        """无令牌且无认证 → 401"""
        response = client.get("/api/rss")
        assert response.status_code == 401

    def test_rss_rejects_wrong_token(self):
        """错误令牌 → 401"""
        response = client.get("/api/rss?token=wrong-token-value")
        assert response.status_code == 401

    def test_rss_accepts_machine_token(self):
        """正确能力令牌 → 200 RSS XML"""
        response = client.get(f"/api/rss?token={machine_token()}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/rss+xml")

    def test_rss_accepts_bearer_auth(self):
        """标准 Bearer 认证也能访问（前端/Agent 复用）"""
        response = client.get("/api/rss", headers=_auth_headers())
        assert response.status_code == 200


class TestRssContent:
    """RSS 内容与格式测试"""

    def test_channel_and_items(self):
        """channel 元数据与 item 字段完整"""
        task_id = _seed_task_and_items(2)
        response = client.get(f"/api/rss/{task_id}?token={machine_token()}")
        assert response.status_code == 200

        root = ET.fromstring(response.text)
        channel = root.find("channel")
        assert channel is not None
        assert channel.findtext("title").startswith("DevHunter · ")
        assert channel.findtext("link")  # 站点根 URL

        items = channel.findall("item")
        assert len(items) == 2
        first = items[0]
        assert first.findtext("link").startswith("https://example.com/item/")
        assert first.findtext("guid").startswith("条目") or first.findtext("guid")
        assert first.findtext("pubDate").endswith("+0000")  # RFC 822
        assert first.findtext("category")  # task_name

    def test_xml_escaping(self):
        """标题/摘要中的 & < > 被正确转义（XML 可解析即证明）"""
        _seed_task_and_items(1)
        response = client.get(f"/api/rss?token={machine_token()}")
        # 若转义缺失，ElementTree 解析会抛异常
        root = ET.fromstring(response.text)
        texts = [i.findtext("title") for i in root.findall(".//item")]
        assert any("A&B <特殊字符>" in t for t in texts if t)

    def test_summary_cdata_terminator_escaped(self):
        """摘要含 ]]> 也不会破坏 XML"""
        _seed_task_and_items(1)
        response = client.get(f"/api/rss?token={machine_token()}")
        ET.fromstring(response.text)  # 不抛异常即通过

    def test_unknown_task_returns_404(self):
        """不存在的 task_id → 404"""
        response = client.get(f"/api/rss/{uuid.uuid4()}?token={machine_token()}")
        assert response.status_code == 404


class TestFeedsEndpoint:
    """订阅地址清单端点测试"""

    def test_requires_auth(self):
        """无认证 → 401（令牌不能泄漏给未认证方）"""
        response = client.get("/api/rss/feeds")
        assert response.status_code == 401

    def test_returns_token_and_urls(self):
        """认证后返回能力令牌与全部订阅地址"""
        task_id = _seed_task_and_items(1)
        response = client.get("/api/rss/feeds", headers=_auth_headers())
        assert response.status_code == 200
        data = response.json()

        assert data["token"] == machine_token()
        assert f"?token={machine_token()}" in data["all_url"]
        feed = next(f for f in data["feeds"] if f["task_id"] == task_id)
        assert f"/api/rss/{task_id}?token=" in feed["url"]
        assert feed["task_name"]
