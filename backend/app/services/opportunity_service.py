"""
app/services/opportunity_service.py
机会板业务逻辑（PROD-005）：创建时校验原始证据存在，状态/优先级/笔记/
标签/提醒变更全部写入审计事件，查询时带回来原始证据。
"""
import logging
from typing import Any

from app.core.exceptions import BadRequestError, NotFoundError
from app.repositories.opportunity_repo import opportunity_repo

logger = logging.getLogger(__name__)


class OpportunityService:
    def _origin_evidence(self, origin_type: str, origin_id: str) -> dict[str, Any]:
        """读取原始证据（Item 或 Thread）；不存在则视为无效来源。"""
        if origin_type == "item":
            from app.repositories.item_repo import item_repo
            item = item_repo.get(origin_id)
            if not item:
                raise BadRequestError(f"条目 {origin_id} 不存在，无法加入机会板")
            return {
                "type": "item",
                "id": item["id"],
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "summary": (item.get("summary") or "")[:300],
                "published_at": item.get("published_at"),
                "fetched_at": item.get("fetched_at"),
            }
        if origin_type == "thread":
            from app.repositories.thread_repo import thread_repo
            thread = thread_repo.get(origin_id)
            if not thread:
                raise BadRequestError(f"Thread {origin_id} 不存在，无法加入机会板")
            return {
                "type": "thread",
                "id": thread["id"],
                "title": thread.get("title") or "",
                "url": f"/?thread={thread['id']}",
                "item_count": thread.get("item_count"),
                "platforms": thread.get("platforms") or [],
                "last_seen_at": thread.get("last_seen_at"),
            }
        raise BadRequestError("origin_type 必须是 item 或 thread")

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        origin_type = data.get("origin_type")
        origin_id = data.get("origin_id")
        if not origin_type or not origin_id:
            raise BadRequestError("必须提供 origin_type 与 origin_id")
        evidence = self._origin_evidence(origin_type, origin_id)
        payload = {
            **data,
            "title": data.get("title") or evidence.get("title") or "",
            "origin_type": origin_type,
            "origin_id": origin_id,
        }
        created = opportunity_repo.create(payload)
        created["evidence"] = evidence
        return created

    def get(self, opp_id: str) -> dict[str, Any]:
        opp = opportunity_repo.get(opp_id)
        if not opp:
            raise NotFoundError(f"Opportunity {opp_id} not found")
        opp["evidence"] = self._origin_evidence(opp["origin_type"], opp["origin_id"])
        opp["events"] = opportunity_repo.get_events(opp_id)
        return opp

    def list(
        self,
        status: str | None = None,
        origin_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        rows = opportunity_repo.list(status=status, origin_type=origin_type, limit=limit)
        for row in rows:
            try:
                row["evidence"] = self._origin_evidence(row["origin_type"], row["origin_id"])
            except BadRequestError:
                # 原始证据已随 TTL/删除消失：保留机会记录但标注证据缺失
                row["evidence"] = None
                row["evidence_missing"] = True
        return rows

    def update(self, opp_id: str, data: dict[str, Any]) -> dict[str, Any]:
        current = opportunity_repo.get(opp_id)
        if not current:
            raise NotFoundError(f"Opportunity {opp_id} not found")

        # 状态/优先级变更各写一条审计事件（from → to）
        if data.get("status") and data["status"] != current["status"]:
            opportunity_repo.update(
                opp_id, {}, event_type="status_change",
                from_value=current["status"], to_value=data["status"],
            )
        if data.get("priority") and data["priority"] != current["priority"]:
            opportunity_repo.update(
                opp_id, {}, event_type="priority_change",
                from_value=current["priority"], to_value=data["priority"],
            )
        if data.get("notes") is not None and data["notes"] != current["notes"]:
            opportunity_repo.update(
                opp_id, {}, event_type="note", note=data["notes"][:500],
            )
        if data.get("tags") is not None:
            opportunity_repo.update(opp_id, {}, event_type="tags",
                                    to_value=",".join(data["tags"]))
        if "remind_at" in data:
            opportunity_repo.update(
                opp_id, {}, event_type="remind",
                to_value=data.get("remind_at") or "cleared",
            )

        updated = opportunity_repo.update(opp_id, data)
        return self.get(updated["id"]) if updated else self.get(opp_id)

    def delete(self, opp_id: str) -> None:
        if not opportunity_repo.delete(opp_id):
            raise NotFoundError(f"Opportunity {opp_id} not found")


opportunity_service = OpportunityService()
