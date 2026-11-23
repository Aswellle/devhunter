"""
tests/test_recommendation/test_recommended_topics.py
「根据阅读历史推荐的主题」回归。

历史缺陷：task 类型亲缘的 affinity_value 是任务 UUID，旧实现直接对它
分词——推荐主题是一堆 8 位十六进制编号（64da59ff、44c0…），用户看不懂，
添加后也匹配不到任何标题。现在候选必须可读、带来源说明、且真实参与
「兴趣匹配」打分。
"""
import re
import uuid
from datetime import datetime, timezone

import pytest

from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.user_prefs_repo import (
    user_affinity_repo,
    user_topics_repo,
)
from app.services.recommendation_service import recommendation_service

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEX_RE = re.compile(r"^[0-9a-f]{6,}$", re.I)


@pytest.fixture()
def read_history():
    """一个高亲缘来源 + 该来源下标题高频复现的条目"""
    task_id = task_repo.insert({
        "name": f"来源-{uuid.uuid4().hex[:4]}",
        "source_url": "https://example.com/",
        "template_id": None,
        "selector_list": "div.item",
        "selector_title": "a",
        "selector_link": "a",
        "selector_summary": None,
        "selector_next_page": None,
        "keywords": [],
        "cron_expression": "0 9 * * *",
    })["id"]

    token = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    titles = [
        f"派早报：今日要闻 {token} 第一期",
        f"派早报：今日要闻 {token} 第二期",
        f"本周看什么：值得一看的作品 {token}",
    ]
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": t,
            "url": f"https://example.com/topics/{token}/{i}",
            "url_hash": f"topic-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i, t in enumerate(titles)
    ])

    # 亲缘累积：多次交互把 task/keyword 亲缘推到高分
    for _ in range(6):
        user_affinity_repo.update_affinity("task", task_id, score_delta=0.3)
        user_affinity_repo.update_affinity("keyword", f"rust{token[:4]}", score_delta=0.3)
    yield task_id
    # 清理本用例写入的偏好，避免影响共享测试库的其它推荐用例
    from app.core.database import get_db
    with get_db() as conn:
        conn.execute("DELETE FROM user_topic_affinity WHERE affinity_value = ?", (task_id,))
        conn.execute("DELETE FROM user_topic_affinity WHERE affinity_value LIKE ?", (f"rust{token[:4]}",))


class TestRecommendedTopicsReadable:
    def test_no_uuid_or_hex_topics(self, read_history):
        """回归：推荐主题里绝不能出现任务 UUID / 十六进制编号。"""
        topics = recommendation_service.get_recommended_topics(limit=15)
        assert topics, "有阅读历史时应产出候选"
        for t in topics:
            assert not UUID_RE.match(t["topic"]), f"UUID 不能作为主题: {t['topic']}"
            assert not HEX_RE.match(t["topic"]), f"编号片段不能作为主题: {t['topic']}"
            assert len(t["topic"]) >= 2

    def test_every_topic_has_reason(self, read_history):
        topics = recommendation_service.get_recommended_topics(limit=15)
        for t in topics:
            assert t.get("reason"), f"每条候选都要说明来源: {t['topic']}"

    def test_recurring_title_phrase_is_proposed(self, read_history):
        """标题中复现 ≥2 次的短语应成为候选（中文标题的轻量「分词」）。"""
        topics = recommendation_service.get_recommended_topics(limit=20)
        names = {t["topic"] for t in topics}
        assert "派早报" in names, f"高频标题短语应被推荐，实际候选：{names}"

    def test_added_topics_are_not_recommended_again(self, read_history):
        topics = recommendation_service.get_recommended_topics(limit=20)
        assert topics
        first = topics[0]["topic"]
        user_topics_repo.upsert(topic=first, category="custom", weight=1.0)
        try:
            again = {t["topic"] for t in recommendation_service.get_recommended_topics(limit=20)}
            assert first not in again, "已添加的主题不应再次出现在推荐里"
        finally:
            user_topics_repo.delete_by_topic(first)

    def test_candidates_actually_match_titles(self, read_history):
        """添加后的真实效果：候选词必须能命中站点标题（兴趣匹配分 > 0）。"""
        topics = recommendation_service.get_recommended_topics(limit=20)
        phrase = next(t for t in topics if t["topic"] == "派早报")
        score = recommendation_service._calc_topic_score(
            "派早报：今日要闻 第一期", {phrase["topic"]: 1.0},
        )
        assert score > 0, "候选主题必须能匹配到标题，否则添加无意义"
