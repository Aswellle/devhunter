"""
tests/test_api/test_user_prefs_api.py
用户偏好 API 回归测试：阅读亲缘度 / 推荐配置 / 负反馈。

这三个端点此前只存在于前端 api 层（ProfilePage 的"阅读偏好"区块与推荐设置
保存都调用它们），后端从未注册过 —— 前端拿到的一直是 404。
"""
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.user_prefs_repo import (
    recommendation_config_repo,
    user_affinity_repo,
    user_interaction_repo,
)

client = TestClient(app)

AFFINITY_FIELDS = {
    "id", "affinity_type", "affinity_value", "affinity_score",
    "interaction_count", "last_interacted_at", "updated_at",
}


def _auth_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _task_id() -> str:
    return task_repo.insert({
        "name": "prefs 测试任务",
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


def _insert_item(task_id: str) -> str:
    token = uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item_repo.bulk_insert([{
        "task_id": task_id,
        "title": f"prefs item {token}",
        "url": f"https://example.com/prefs/{token}",
        "url_hash": f"prefs-hash-{token}",
        "summary": "s",
        "fetched_at": now,
    }])
    items, _ = item_repo.query(task_id=task_id)
    return items[0]["id"]


class TestAffinitiesAPI:
    """GET /api/user-prefs/affinities"""

    def test_returns_recorded_affinities(self):
        user_affinity_repo.update_affinity("platform", "Hacker News", 0.8)

        response = client.get("/api/user-prefs/affinities", headers=_auth_headers())

        assert response.status_code == 200
        rows = response.json()
        assert any(r["affinity_type"] == "platform" and r["affinity_value"] == "Hacker News"
                   for r in rows)
        assert AFFINITY_FIELDS <= set(rows[0]), "画像页渲染依赖这些字段"
        assert rows[0]["affinity_score"] > 0

    def test_requires_auth(self):
        assert client.get("/api/user-prefs/affinities").status_code == 401


class TestRecommendationConfigAPI:
    """POST /api/user-prefs/recommendations/config"""

    def test_mode_only_applies_server_preset(self):
        response = client.post("/api/user-prefs/recommendations/config",
                               json={"preference_mode": "fresh_first"},
                               headers=_auth_headers())

        assert response.status_code == 200
        weights = response.json()["weights"]
        assert weights["recency"] == 0.5
        # 模式必须真正落到 recommendation_config（推荐引擎读的就是这几个 key）
        assert recommendation_config_repo.get("recency_weight", 0.0) == 0.5
        assert recommendation_config_repo.get("topic_match_weight", 0.0) == weights["topic_match"]

    def test_explicit_weights_override_preset(self):
        response = client.post("/api/user-prefs/recommendations/config",
                               json={"preference_mode": "balanced",
                                     "weights": {"recency": 0.05}},
                               headers=_auth_headers())

        assert response.status_code == 200
        assert response.json()["weights"]["recency"] == 0.05
        assert recommendation_config_repo.get("recency_weight", 0.0) == 0.05

    def test_missing_mode_and_weights_is_rejected(self):
        response = client.post("/api/user-prefs/recommendations/config",
                               json={}, headers=_auth_headers())
        assert response.status_code == 400

    def test_unknown_mode_is_rejected(self):
        response = client.post("/api/user-prefs/recommendations/config",
                               json={"preference_mode": "not_a_mode"},
                               headers=_auth_headers())
        assert response.status_code == 422

    def test_out_of_range_weight_is_rejected(self):
        response = client.post("/api/user-prefs/recommendations/config",
                               json={"weights": {"recency": 3}},
                               headers=_auth_headers())
        assert response.status_code == 422


class TestFeedbackAPI:
    """POST /api/user-prefs/feedback"""

    def test_records_feedback_for_existing_item(self):
        item_id = _insert_item(_task_id())

        response = client.post("/api/user-prefs/feedback",
                               json={"item_id": item_id,
                                     "feedback_type": "not_interested",
                                     "reason": "重复内容"},
                               headers=_auth_headers())

        assert response.status_code == 201
        assert response.json()["target_value"] == item_id
        recorded = user_interaction_repo.get_negative_feedback_map()
        assert item_id in recorded.get("not_interested", set())

    def test_unknown_item_is_rejected(self):
        response = client.post("/api/user-prefs/feedback",
                               json={"item_id": "no-such-item",
                                     "feedback_type": "not_interested"},
                               headers=_auth_headers())
        assert response.status_code == 404

    def test_unknown_feedback_type_is_rejected(self):
        item_id = _insert_item(_task_id())
        response = client.post("/api/user-prefs/feedback",
                               json={"item_id": item_id, "feedback_type": "whatever"},
                               headers=_auth_headers())
        assert response.status_code == 422

    def test_requires_auth(self):
        assert client.post("/api/user-prefs/feedback",
                           json={"item_id": "x", "feedback_type": "not_interested"}).status_code == 401


class TestInteractionVocabulary:
    """
    POST /api/user-prefs/interactions 的类型词表必须与 DB CHECK 兼容。

    018 重建 user_interactions 时把 CHECK 收窄成 R1 词表（impression/open/
    click_source/...），但 API schema、前端与参与度统计用的都是 view/click，
    于是最高频的浏览与点击直接撞约束（IntegrityError → 500），阅读亲缘度
    永远累积不起来 —— "我的画像"因此恒为空。
    """

    def test_api_vocabulary_is_accepted(self):
        item_id = _insert_item(_task_id())
        for interaction_type in ("view", "click", "dwell", "star", "share"):
            response = client.post(
                "/api/user-prefs/interactions",
                json={"item_id": item_id, "interaction_type": interaction_type},
                headers=_auth_headers(),
            )
            assert response.status_code == 200, f"{interaction_type} 被 DB CHECK 拒绝"

    def test_interaction_accumulates_affinity(self):
        item_id = _insert_item(_task_id())

        client.post("/api/user-prefs/interactions",
                    json={"item_id": item_id, "interaction_type": "view"},
                    headers=_auth_headers())

        rows = client.get("/api/user-prefs/affinities", headers=_auth_headers()).json()
        assert any(r["affinity_type"] == "task" and r["affinity_score"] > 0 for r in rows)

    def test_engagement_counters_capture_view_and_click(self):
        item_id = _insert_item(_task_id())
        for interaction_type in ("view", "click"):
            client.post("/api/user-prefs/interactions",
                        json={"item_id": item_id, "interaction_type": interaction_type},
                        headers=_auth_headers())

        stats = user_interaction_repo.get_user_engagement_stats(item_id)
        assert stats["view_count"] == 1
        assert stats["click_count"] == 1
