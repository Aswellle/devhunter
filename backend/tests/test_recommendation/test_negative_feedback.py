"""
tests/test_recommendation/test_negative_feedback.py
负反馈必须真实影响推荐（回归）。

历史缺陷：`POST /api/user-prefs/feedback` 把 not_interested / hide_source
写入 user_negative_feedback 表，但 score_candidates 的打分循环从不读取，
前端也没有入口——用户"不感兴趣"保存后完全不起作用（接口 docstring 声称
"推荐引擎后续会依据"，实际从未实现）。
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.repositories.item_repo import item_repo
from app.repositories.task_repo import task_repo
from app.repositories.user_prefs_repo import (
    recommendation_config_repo,
    user_interaction_repo,
)
from app.services.recommendation_service import recommendation_service


@pytest.fixture(autouse=True)
def _balanced_config():
    """固定打分权重，避免共享测试库里其它用例写入的配置影响阈值。"""
    for key, value in {
        "topic_match_weight": 0.35,
        "affinity_weight": 0.30,
        "recency_weight": 0.20,
        "engagement_weight": 0.10,
        "exploration_weight": 0.05,
        "min_score_threshold": 0.1,
        "max_items": 20,
    }.items():
        recommendation_config_repo.set(key, value)
    yield


def _insert_task_items(count: int = 2) -> tuple[str, list[str]]:
    task_id = task_repo.insert({
        "name": f"负反馈测试任务 {uuid.uuid4().hex[:6]}",
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
    item_repo.bulk_insert([
        {
            "task_id": task_id,
            "title": f"neg feedback item {token} #{i}",
            "url": f"https://example.com/neg/{token}/{i}",
            "url_hash": f"neg-hash-{token}-{i}",
            "summary": "s",
            "fetched_at": now,
        }
        for i in range(count)
    ])
    items, _ = item_repo.query(task_id=task_id)
    return task_id, [it["id"] for it in items]


def _recommended_ids() -> set[str]:
    return {it["id"] for it in recommendation_service.score_candidates(exclude_read=False)}


class TestNegativeFeedbackAffectsRecommendations:
    def test_baseline_items_are_recommended(self):
        _, ids = _insert_task_items(2)
        recommended = _recommended_ids()
        assert set(ids) <= recommended, "前置条件：未被拒绝的条目应进入推荐"

    def test_not_interested_hides_only_that_item(self):
        _, ids = _insert_task_items(2)
        target, control = ids[0], ids[1]

        user_interaction_repo.record_negative_feedback("not_interested", target)
        try:
            recommended = _recommended_ids()
            assert target not in recommended, "not_interested 的条目必须被排除"
            assert control in recommended, "同源的其它条目不受影响"
        finally:
            _clear_feedback(target)

    def test_hide_source_hides_whole_source(self):
        task_id, ids = _insert_task_items(2)

        user_interaction_repo.record_negative_feedback("hide_source", ids[0])
        try:
            recommended = _recommended_ids()
            assert not (set(ids) & recommended), (
                "hide_source 应把该来源（同一任务）的全部条目排除"
            )
        finally:
            _clear_feedback(ids[0])

    def test_feedback_map_parsing(self):
        _, ids = _insert_task_items(1)
        user_interaction_repo.record_negative_feedback("not_interested", ids[0])
        try:
            dismissed, hidden_tasks, hidden_names = (
                recommendation_service._load_negative_feedback()
            )
            assert ids[0] in dismissed
        finally:
            _clear_feedback(ids[0])


def _clear_feedback(target_item_id: str) -> None:
    """清理本用例写入的反馈，避免影响共享测试库中的其它用例。"""
    from app.core.database import get_db

    with get_db() as conn:
        conn.execute(
            "DELETE FROM user_negative_feedback WHERE target_value = ?",
            (target_item_id,),
        )
