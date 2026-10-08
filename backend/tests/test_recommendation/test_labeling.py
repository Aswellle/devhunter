"""
tests/test_recommendation/test_labeling.py
推荐质量打标（金标）API 回归测试。

采样必须与线上推荐同一条打分路径（score_candidates），这样标注里快照的
sampled_score 才与真实推荐位次可比；测试中用 monkeypatch 固定候选池，
避免共享测试库里其他条目的得分波动。
"""
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.repositories.item_repo import item_repo
from app.repositories.relevance_repo import relevance_label_repo
from app.repositories.task_repo import task_repo
from app.services.recommendation_service import recommendation_service

client = TestClient(app)


def _auth_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _insert_items(count: int) -> list[str]:
    task_id = task_repo.insert({
        "name": f"打标测试任务 {uuid.uuid4().hex[:6]}",
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
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    token = uuid.uuid4().hex[:8]
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": f"label item {token} #{i}",
            "url": f"https://example.com/label/{token}/{i}",
            "url_hash": f"label-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i in range(count)
    ])
    items, _ = item_repo.query(task_id=task_id)
    return [it["id"] for it in items]


def _pool(item_ids: list[str], scores: list[float]) -> list[dict]:
    """把真实存在的 item id 组装成 score_candidates 的返回形状"""
    return [
        {
            "id": item_id,
            "task_id": "t1",
            "task_name": "打标测试任务",
            "title": f"title {item_id[:6]}",
            "url": f"https://example.com/{item_id}",
            "summary": "s",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "recommendation_score": score,
        }
        for item_id, score in zip(item_ids, scores)
    ]


class TestSampleAPI:
    """GET /api/user-prefs/recommendations/labels/sample"""

    def test_returns_unlabeled_with_score_snapshot(self, monkeypatch):
        ids = _insert_items(2)
        monkeypatch.setattr(
            recommendation_service, "score_candidates",
            lambda exclude_read=True: _pool(ids, [0.9, 0.4]),
        )

        response = client.get(
            "/api/user-prefs/recommendations/labels/sample",
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        rows = response.json()
        returned = {r["id"]: r for r in rows}
        assert ids[0] in returned and ids[1] in returned
        assert returned[ids[0]]["recommendation_score"] == 0.9
        assert {"id", "title", "task_name", "url", "fetched_at"} <= set(rows[0])

    def test_sample_excludes_already_labeled(self, monkeypatch):
        ids = _insert_items(2)
        relevance_label_repo.upsert(ids[0], label=True, sampled_score=0.9)
        monkeypatch.setattr(
            recommendation_service, "score_candidates",
            lambda exclude_read=True: _pool(ids, [0.9, 0.4]),
        )

        rows = client.get(
            "/api/user-prefs/recommendations/labels/sample",
            headers=_auth_headers(),
        ).json()

        assert ids[0] not in {r["id"] for r in rows}
        assert ids[1] in {r["id"] for r in rows}

    def test_empty_pool_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(
            recommendation_service, "score_candidates", lambda exclude_read=True: [],
        )
        assert client.get(
            "/api/user-prefs/recommendations/labels/sample",
            headers=_auth_headers(),
        ).json() == []

    def test_requires_auth(self):
        assert client.get("/api/user-prefs/recommendations/labels/sample").status_code == 401


class TestSubmitLabelAPI:
    """POST /api/user-prefs/recommendations/labels"""

    def test_submit_then_relabel_updates_in_place(self):
        (item_id,) = _insert_items(1)

        first = client.post(
            "/api/user-prefs/recommendations/labels",
            json={"item_id": item_id, "label": True, "sampled_score": 0.7},
            headers=_auth_headers(),
        )
        assert first.status_code == 201
        assert first.json()["label"] is True

        # 改判：同一 item 仍只有一条记录，且值为新判断
        second = client.post(
            "/api/user-prefs/recommendations/labels",
            json={"item_id": item_id, "label": False, "sampled_score": 0.7},
            headers=_auth_headers(),
        )
        assert second.status_code == 201
        stored = relevance_label_repo.upsert(item_id, label=False, sampled_score=0.7)
        assert stored["label"] is False

    def test_unknown_item_is_rejected(self):
        response = client.post(
            "/api/user-prefs/recommendations/labels",
            json={"item_id": "no-such-item", "label": True},
            headers=_auth_headers(),
        )
        assert response.status_code == 404

    def test_out_of_range_score_is_rejected(self):
        response = client.post(
            "/api/user-prefs/recommendations/labels",
            json={"item_id": "x", "label": True, "sampled_score": 1.5},
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    def test_requires_auth(self):
        assert client.post(
            "/api/user-prefs/recommendations/labels",
            json={"item_id": "x", "label": True},
        ).status_code == 401


class TestLabelSummaryAPI:
    """GET /api/user-prefs/recommendations/labels/summary"""

    def test_win_rate_math_over_snapshot_scores(self, monkeypatch):
        monkeypatch.setattr(relevance_label_repo, "summary",
                            lambda: {"total": 3, "positive": 2, "negative": 1})
        monkeypatch.setattr(relevance_label_repo, "list_scores",
                            lambda: [(0.9, 1), (0.6, 1), (0.3, 0)])

        data = client.get(
            "/api/user-prefs/recommendations/labels/summary",
            headers=_auth_headers(),
        ).json()

        # 2 正例均高于 1 负例 → 贴合度 1.0
        assert data == {"total": 3, "positive": 2, "negative": 1, "win_rate": 1.0}

    def test_win_rate_null_when_one_side_missing(self, monkeypatch):
        monkeypatch.setattr(relevance_label_repo, "summary",
                            lambda: {"total": 2, "positive": 2, "negative": 0})
        monkeypatch.setattr(relevance_label_repo, "list_scores",
                            lambda: [(0.9, 1), (0.6, 1)])

        data = client.get(
            "/api/user-prefs/recommendations/labels/summary",
            headers=_auth_headers(),
        ).json()

        assert data["win_rate"] is None, "只有正例时不应显示 0% 的误导性贴合度"

    def test_requires_auth(self):
        assert client.get("/api/user-prefs/recommendations/labels/summary").status_code == 401
