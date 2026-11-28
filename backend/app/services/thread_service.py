"""
app/services/thread_service.py
Thread 业务层：计算新 Items 的 Thread 归属

V2: 使用多因素评分（lexical + entity + semantic + temporal + source）
"""
import logging
import threading
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.repositories.thread_repo import thread_repo
from app.repositories.task_repo import task_repo
from app.utils.url import source_identity
from app.utils.similarity import DEFAULT_THRESHOLD, find_similar_titles, jaccard_similarity
from app.features.extractor import feature_extractor
from app.threads.clustering import thread_clusterer
from app.threads.merge import thread_merger
from app.threads.split import thread_splitter
from app.threads.stats import build_thread_stats

logger = logging.getLogger(__name__)

# Thread 重建批次大小：候选池随批次刷新，批次过大窗口内候选会过期
_RECOMPUTE_BATCH_SIZE = 200
# 默认候选活动窗口（可在 .env 用 THREAD_CLUSTER_WINDOW_HOURS 调整）
DEFAULT_WINDOW_HOURS = settings.thread_cluster_window_hours
# 单次增量合并的上限，避免异常数据把一次扫描拖成长事务
_MAX_CONSOLIDATE_MERGES = 200


class ThreadService:

    # 重建互斥锁：防止两次重建并发交错（SQLite 单写入者，交错会产生半重建状态）。
    # RLock 可重入——重建线程内部逐批调 compute_threads_for_items 时持有同一把锁。
    _recompute_lock = threading.RLock()

    # 后台重建状态（start_recompute 在独立线程中跑 recompute_all_threads）
    _recompute_state_lock = threading.Lock()
    _recompute_state: dict = {"running": False, "result": None, "error": None}

    # 最近一次增量合并（定时任务 / 手动"立即聚合"）的结果，供概览展示
    _consolidation_state_lock = threading.Lock()
    _last_consolidation: dict | None = None

    def compute_threads_for_items(
        self,
        new_items: list[dict],
        threshold: float = DEFAULT_THRESHOLD,
        window_hours: int = DEFAULT_WINDOW_HOURS,
        conn: Any = None,
    ) -> int:
        """
        为一批新采集的 Items 计算 Thread 归属。

        V2 流程：对每个新 Item，使用多因素评分在近期活跃 Thread 中找最佳匹配；
        匹配则加入，否则创建新 Thread。

        内容性质门控：条目型（content_kind=catalog）任务的条目是独立资源
        （开源项目、产品、视频），彼此无事件关联，聚类只会产生无意义的
        单条目 Thread —— 直接跳过，不建 Thread 也不入 Thread。

        候选 Thread 逐条目刷新：同批次中先前条目刚创建/加入的 Thread 也会
        出现在后续条目的候选里——同一条事件的多篇报道才能聚进同一个 Thread。
        整批写入包在单个事务里（候选查询走同一连接，可见未提交的本批写入），
        避免逐条目独立提交与调度器争 SQLite 单写者。

        重建进行中时跳过本批聚类（重建结束后新条目随下次采集归位）：
        重建的 delete_all/重放与采集写入交错会产生双重归属。

        返回实际参与聚类的 Item 数量。
        """
        if not new_items:
            return 0

        # 获取各 task_id -> (platform 名称, content_kind) 的映射。
        # 必须覆盖全部任务（含 paused/软删除）：映射缺失的任务条目会按
        # 默认 discussion 聚类——已暂停的条目型任务的历史条目会在重建
        # 重放中被错误聚成 Thread（见 task_repo.list_all_tasks）
        tasks = {t["id"]: t for t in task_repo.list_all_tasks()}
        item_id_to_platform = {
            item["id"]: tasks.get(item.get("task_id"), {}).get("name", "unknown")
            for item in new_items
        }
        # 稳定来源身份：来源 URL 主机名（任务改名不影响，同平台多任务
        # 同主机不构成跨平台共识）
        item_id_to_source_key = {
            item["id"]: source_identity(
                tasks.get(item.get("task_id"), {}).get("source_url", ""),
                tasks.get(item.get("task_id"), {}).get("name", "unknown"),
            )
            for item in new_items
        }
        clusterable = [
            item for item in new_items
            if tasks.get(item.get("task_id"), {}).get("content_kind", "discussion") == "discussion"
        ]
        skipped = len(new_items) - len(clusterable)
        if skipped:
            logger.info(
                "Thread compute: skipped %d catalog-kind items (no clustering for catalog sources)",
                skipped,
            )

        if not clusterable:
            return 0

        if not self._recompute_lock.acquire(blocking=False):
            # RLock 对持有线程可重入：走到这里说明是重建线程之外
            # 的采集批次——让位于整体重建，避免交错写。
            # 本批条目暂不聚类；重建结束时的兜底扫描（recompute_all_threads
            # 末尾按 list_thread_orphans 补聚）会把它们聚进来，
            # 不会成为永久孤儿
            logger.warning(
                "Thread compute: skipped %d items (recompute in progress); "
                "the running recompute's final sweep will cluster them",
                len(clusterable),
            )
            return 0
        try:
            if conn is not None:
                # staging 事务路径：在调用方连接中聚类，不自行提交
                return self._cluster_items(
                    clusterable, item_id_to_platform, item_id_to_source_key,
                    window_hours, threshold, conn,
                )
            from app.core.database import transaction

            with transaction() as conn:
                return self._cluster_items(
                    clusterable, item_id_to_platform, item_id_to_source_key,
                    window_hours, threshold, conn,
                )
        finally:
            self._recompute_lock.release()

    def _cluster_items(
        self,
        clusterable: list[dict],
        item_id_to_platform: dict[str, str],
        item_id_to_source_key: dict[str, str],
        window_hours: int,
        threshold: float,
        conn: Any,
    ) -> int:
        """聚类单批条目（在调用方事务/连接内执行，不自行提交）。"""
        matched_count = 0
        for item in clusterable:
            item_id = item["id"]
            title = item["title"]
            platform = item_id_to_platform.get(item_id, "unknown")

            # 每个条目都重新取候选（近期活跃 Thread），见 get_candidate_threads；
            # 事务内可读到此批次先前条目的写入，语义与逐条目提交一致
            candidate_threads = thread_repo.get_candidate_threads(
                hours=window_hours, conn=conn,
            )

            # source_id 用稳定身份（主机名）；task_name 保留展示名，
            # 供未回填 source_keys 的旧线程回退比较
            source_key = item_id_to_source_key.get(item_id, platform)
            scoring_item = {
                **item,
                "source_id": source_key,
                "source_name": source_key,
                "task_name": platform,
            }

            # 使用多因素聚类
            result = thread_clusterer.cluster(
                scoring_item, candidate_threads, threshold=threshold,
            )

            if result.action == "join" and result.thread_id:
                # 加入已有 Thread
                matched_count += 1
                thread_repo.add_item(
                    thread_id=result.thread_id,
                    item_id=item_id,
                    similarity=result.score.total_score if result.score else 0.5,
                    title=title,
                    platform=platform,
                    match_reason=result.match_reason,
                    conn=conn,
                    source_key=source_key,
                )
            else:
                # 创建新 Thread
                new_thread_id = thread_repo.create(title=title, item_id=item_id, platform=platform, algorithm_version="v2", similarity_threshold=threshold, match_reason="no_match", conn=conn, source_key=source_key)
                # 同一故事线 near-miss：与最佳候选显式关联（展示层分层，不改变归属）
                if result.related_thread_id:
                    thread_repo.record_relation(
                        new_thread_id,
                        result.related_thread_id,
                        similarity=result.score.total_score if result.score else 0.0,
                        source="auto",
                        conn=conn,
                    )
        logger.info(
            "Thread compute: %d items clustered, %d matched to existing threads, %d created new"
            " (catalog-skipped logged at batch entry)",
            len(clusterable), matched_count, len(clusterable) - matched_count,
        )
        return len(clusterable)

    def _replay_manual_decisions(self) -> int:
        """重放待处理的人工纠错决策（ADR-001，staging 提交后调用）。

        决策以成员条目 ID 为锚（跨重建稳定）：
        - merge：锚点分散在多个 Thread 时合并回锚点最多的那个；
        - split：保留侧锚点所在 Thread 若又包含被移出条目，重新拆分；
        - reject_merge：两侧分属不同 Thread 时按当前 ID 重新登记仲裁。
        单条决策失败只记日志（其余决策继续），决策永不静默丢失——
        失败/未处理的决策保持待重放状态，下次重建自动补试。"""
        from app.threads.split import thread_splitter

        pending = thread_repo.list_pending_manual_decisions()
        if not pending:
            return 0
        applied = 0
        for decision in pending:
            try:
                dtype = decision["decision_type"]
                anchors = decision.get("item_ids") or []
                payload = decision.get("payload") or {}
                if dtype == "merge":
                    applied += self._replay_merge_decision(anchors)
                elif dtype == "split":
                    applied += self._replay_split_decision(
                        anchors, payload.get("kept_anchor"), thread_splitter,
                    )
                elif dtype == "reject_merge":
                    applied += self._replay_reject_decision(anchors)
                thread_repo.mark_manual_decision_replayed(decision["id"])
            except Exception as e:
                logger.warning(
                    "Manual decision replay failed (%s %s…): %s",
                    decision.get("decision_type"),
                    str(decision.get("id"))[:8], e,
                )
        if pending:
            logger.info("Manual decision replay: %d/%d applied", applied, len(pending))
        return applied

    @staticmethod
    def _thread_of_item(item_id: str) -> str | None:
        from app.repositories.item_repo import item_repo
        return (item_repo.get(item_id) or {}).get("thread_id")

    def _replay_merge_decision(self, anchors: list[str]) -> int:
        """merge 决策：锚点分散时合并回锚点最多的 Thread。"""
        location: dict[str, list[str]] = {}
        for anchor in anchors:
            tid = self._thread_of_item(anchor)
            if tid:
                location.setdefault(tid, []).append(anchor)
        if len(location) <= 1:
            return 0  # 已聚合，决策自然满足
        ordered = sorted(location.items(), key=lambda kv: -len(kv[1]))
        target = ordered[0][0]
        for source, _anchors in ordered[1:]:
            thread_merger.merge(source, target, reason="manual_decision_replay")
        return 1

    def _replay_split_decision(
        self, moved_ids: list[str], kept_anchor: str | None, splitter: Any,
    ) -> int:
        """split 决策：被移出条目若又被聚回保留侧，重新拆分。"""
        if not kept_anchor:
            return 0
        kept_thread = self._thread_of_item(kept_anchor)
        if not kept_thread:
            return 0
        still_in = [
            mid for mid in moved_ids
            if self._thread_of_item(mid) == kept_thread
        ]
        if not still_in:
            return 0  # 已保持分离，决策自然满足
        splitter.split(kept_thread, still_in)
        return 1

    @staticmethod
    def _replay_reject_decision(anchors: list[str]) -> int:
        """reject_merge 决策：两侧分属不同 Thread 时按当前 ID 重新登记。"""
        if len(anchors) < 2:
            return 0
        side_a = thread_service._thread_of_item(anchors[0])
        side_b = thread_service._thread_of_item(anchors[1])
        if not side_a or not side_b or side_a == side_b:
            return 0
        if not thread_repo.is_pair_rejected(side_a, side_b):
            thread_repo.record_override(
                side_a, "reject_merge", target_thread_id=side_b,
                reason="manual decision replay",
            )
        return 1

    @staticmethod
    def _validate_rebuild(conn: Any) -> None:
        """重建完整性校验（staging 提交前的最后一关，ADR-001）。

        任一违反抛 RuntimeError → staging 事务整体回滚，旧投影继续可用：
        1. thread_items 无孤儿引用（thread/item 都存在）；
        2. items.thread_id 镜像与 thread_items 成员一致；
        3. threads.item_count 与实际成员数一致。"""
        orphans = conn.execute(
            """
            SELECT COUNT(*) FROM thread_items ti
            WHERE NOT EXISTS (SELECT 1 FROM threads t WHERE t.id = ti.thread_id)
               OR NOT EXISTS (SELECT 1 FROM items i WHERE i.id = ti.item_id)
            """
        ).fetchone()[0]
        if orphans:
            raise RuntimeError(f"rebuild validation failed: {orphans} orphan membership row(s)")

        mirror_mismatch = conn.execute(
            """
            SELECT COUNT(*) FROM items i
            WHERE i.thread_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM thread_items ti
                  WHERE ti.thread_id = i.thread_id AND ti.item_id = i.id
              )
            """
        ).fetchone()[0]
        if mirror_mismatch:
            raise RuntimeError(
                f"rebuild validation failed: {mirror_mismatch} dangling thread_id mirror(s)"
            )

        count_mismatch = conn.execute(
            """
            SELECT COUNT(*) FROM threads t
            WHERE t.item_count != (
                SELECT COUNT(*) FROM thread_items ti WHERE ti.thread_id = t.id
            )
            """
        ).fetchone()[0]
        if count_mismatch:
            raise RuntimeError(
                f"rebuild validation failed: {count_mismatch} thread(s) with stale item_count"
            )

    def merge_threads(
        self,
        source_thread_id: str,
        target_thread_id: str,
        reason: str = "",
    ) -> dict | None:
        """
        合并两个 Thread。

        Args:
            source_thread_id: 源 Thread ID（将被删除）
            target_thread_id: 目标 Thread ID
            reason: 合并原因

        Returns:
            合并后的 Thread dict
        """
        # 人工合并记录为成员条目 ID 集合（稳定身份，ADR-001）：
        # 重建生成新 Thread ID 后按集合重放，合并结果不再被算法无声拆散
        member_ids = sorted({
            m["id"]
            for m in thread_repo.get_thread_item_map(
                [source_thread_id, target_thread_id]
            ).values()
            for m in m
        })
        merged = thread_merger.merge(source_thread_id, target_thread_id, reason)
        if merged:
            thread_repo.record_manual_decision("merge", member_ids)
        return merged

    def split_thread(
        self,
        thread_id: str,
        item_ids: list[str],
        new_thread_title: str | None = None,
    ) -> dict | None:
        """
        拆分 Thread。

        Args:
            thread_id: 源 Thread ID
            item_ids: 要移出的 item ID 列表
            new_thread_title: 新 Thread 标题

        Returns:
            新 Thread dict
        """
        # 人工拆分记录为被移出条目 + 保留侧锚点（ADR-001）：重建后若
        # 算法再次聚回同一 Thread，按决策重新拆分
        existing_members = {
            m["id"]
            for m in thread_repo.get_thread_item_map([thread_id]).get(thread_id, [])
        }
        kept_anchor = next(
            (mid for mid in existing_members if mid not in set(item_ids)), None
        )
        split = thread_splitter.split(thread_id, item_ids, new_thread_title)
        if split and kept_anchor:
            thread_repo.record_manual_decision(
                "split", list(item_ids), {"kept_anchor": kept_anchor},
            )
        return split

    def list_threads(
        self,
        task_id: str | None = None,
        page: int = 1,
        per_page: int = 20,
        sort: str = "first_seen",
        min_items: int = 1,
    ) -> tuple[list[dict], int]:
        """列出 Threads（sort: first_seen | hotness；min_items 过滤单条 Thread）"""
        return thread_repo.list_all(
            task_id=task_id, page=page, per_page=per_page,
            sort=sort, min_items=min_items,
        )

    def get_thread(self, thread_id: str) -> dict | None:
        """获取 Thread 详情（包含 Items、聚合画像 stats 与同一故事线关联层）"""
        thread = thread_repo.get(thread_id)
        if not thread:
            return None
        items = thread_repo.get_items_in_thread(thread_id)
        return {
            **thread,
            "items": items,
            "stats": build_thread_stats(thread, items),
            "related_threads": thread_repo.get_related_threads(thread_id),
        }

    def unlink_related_thread(self, thread_id: str, related_thread_id: str) -> bool:
        """
        解除一条"同一故事线"关联（用户拆除误关联）。

        拆除动作记录为 reject_merge 仲裁：同一对 Thread 存续期内
        不会再被自动关联（record_relation 消费该记录）。
        Returns: 关联是否存在
        """
        deleted = thread_repo.delete_relation(thread_id, related_thread_id)
        if deleted:
            # 解除关联记录两侧成员锚点（ADR-001）：重建后按当前 Thread ID
            # 重新登记 reject_merge，自动关联不再重犯
            member_map = thread_repo.get_thread_item_map([thread_id, related_thread_id])
            anchor_a = next(
                (m["id"] for m in member_map.get(thread_id, [])), None)
            anchor_b = next(
                (m["id"] for m in member_map.get(related_thread_id, [])), None)
            if anchor_a and anchor_b:
                thread_repo.record_manual_decision(
                    "reject_merge", [anchor_a, anchor_b],
                )
            thread_repo.record_override(
                thread_id,
                "reject_merge",
                target_thread_id=related_thread_id,
                reason="unlink_relation",
            )
        return deleted

    def generate_thread_digest(self, thread_id: str, force: bool = False) -> dict:
        """
        手动生成/更新 Thread AI 综述（与采集后自动触发同一生成函数）。

        与 digest.generate_digest 的静默语义不同：这是用户显式动作，
        不可用/失败原因要作为业务错误明确返回。
        """
        from app.core.exceptions import (
            DigestGenerationFailedError,
            DigestTooFewItemsError,
            LLMNotConfiguredError,
            LLMUnavailableError,
            NotFoundError,
        )
        from app.threads.digest import DIGEST_MIN_ITEMS, generate_digest
        from app.llm.provider import llm_provider

        thread = thread_repo.get(thread_id)
        if not thread:
            raise NotFoundError("Thread 不存在")
        if thread.get("digest") and not force:
            return {"digest": thread["digest"], "digest_at": thread.get("digest_at")}
        if (thread.get("item_count") or 0) < DIGEST_MIN_ITEMS:
            raise DigestTooFewItemsError
        if not llm_provider.is_configured():
            raise LLMNotConfiguredError
        if not llm_provider.is_available():
            raise LLMUnavailableError

        text = generate_digest(thread_id, force=True)
        if not text:
            raise DigestGenerationFailedError

        updated = thread_repo.get(thread_id) or {}
        return {"digest": text, "digest_at": updated.get("digest_at")}

    def start_recompute(self, window_hours: int = DEFAULT_WINDOW_HOURS) -> None:
        """
        在后台线程中启动全量重建（API 立即返回 202）。

        已有重建进行中时抛 ConflictError。进度经 recompute_status() 查询；
        重建与采集管线的互斥由 recompute_all_threads / compute_threads_for_items
        的锁语义保证。
        """
        with self._recompute_state_lock:
            if self._recompute_state["running"]:
                raise ConflictError("Thread 重建已在进行中，请稍后再试")
            self._recompute_state.update(running=True, result=None, error=None)

        worker = threading.Thread(
            target=self._run_recompute_background,
            args=(window_hours,),
            name="thread-recompute",
            daemon=True,
        )
        worker.start()

    def _run_recompute_background(self, window_hours: int) -> None:
        try:
            result = self.recompute_all_threads(window_hours=window_hours)
            with self._recompute_state_lock:
                self._recompute_state.update(running=False, result=result, error=None)
        except Exception as e:  # noqa: BLE001 — 后台线程必须自己兜底并暴露给状态端点
            logger.exception("Thread recompute failed")
            with self._recompute_state_lock:
                self._recompute_state.update(running=False, result=None, error=str(e))

    def recompute_status(self) -> dict:
        """后台重建状态：{running, result, error}"""
        with self._recompute_state_lock:
            return dict(self._recompute_state)

    def recompute_all_threads(self, window_hours: int = DEFAULT_WINDOW_HOURS) -> dict:
        """
        重建全部 Thread：清空后按 created_at 时间正序重放所有条目的聚类。

        - 使用与采集管线完全相同的算法（compute_threads_for_items），仅候选
          活动窗口可调（window_hours，默认 24h 与采集路径一致）
        - 按批次重放，候选随批次刷新
        - thread_overrides 为人工纠错审计记录，保留不动（旧引用自然失效）
        - 人工合并/拆分/解除关联按成员条目 ID 记录（031 决策表），
          staging 提交后重放——人工纠错跨重建保留（ADR-001）

        进程内互斥：已有重建进行中时抛 ConflictError。
        个人规模的条目量（数千级）应在秒级到分钟级内完成；
        经 start_recompute 在后台线程运行，本方法也可直接同步调用（测试）。

        Returns:
            {"items": 处理条目数, "threads": 重建后 Thread 数,
             "duration_ms": 耗时, "window_hours": 窗口}
        """
        if not self._recompute_lock.acquire(blocking=False):
            raise ConflictError("Thread 重建已在进行中，请稍后再试")
        try:
            from app.repositories.item_repo import item_repo
            from app.core.database import transaction

            started = time.monotonic()
            items = item_repo.list_all_chronological()

            # staging 语义（ADR-001）：清空 + 重放 + 校验在同一个事务内，
            # 校验通过才提交切换活动投影；中断/校验失败整体回滚，
            # 旧投影保持完整可用（WAL 快照让重建期间读到旧投影）
            with transaction() as conn:
                thread_repo.delete_all(conn=conn)
                for i in range(0, len(items), _RECOMPUTE_BATCH_SIZE):
                    self.compute_threads_for_items(
                        items[i:i + _RECOMPUTE_BATCH_SIZE],
                        window_hours=window_hours,
                        conn=conn,
                    )

                # 兜底扫描：重建期间到达的采集批次让位于重建被跳过（见
                # compute_threads_for_items 的锁语义），且重放快照取自重建
                # 开始前——按"thread_id 仍为 NULL 的讨论型条目"补聚一轮，
                # 保证重建结束后讨论型条目没有永久孤儿。本线程持有锁，
                # compute 内部的重入获取直接通过
                orphans = item_repo.list_thread_orphans()
                if orphans:
                    logger.info(
                        "Thread recompute: sweeping %d orphan item(s) that arrived mid-recompute",
                        len(orphans),
                    )
                    self.compute_threads_for_items(orphans, window_hours=window_hours, conn=conn)

                # 完整性校验：任一违反都回滚到旧投影
                self._validate_rebuild(conn)

            duration_ms = int((time.monotonic() - started) * 1000)

            # 人工决策重放（ADR-001）：staging 提交后执行——决策合并器
            # 自管事务，不能在 staging 事务内嵌套连接；崩溃时决策仍是
            # 待重放状态，下次重建自动补放，人工纠错永不静默丢失
            decisions_replayed = self._replay_manual_decisions()
            result = {
                "items": len(items),
                "threads": thread_repo.count_all(),
                "orphans_swept": len(orphans),
                "duration_ms": duration_ms,
                "manual_decisions_replayed": decisions_replayed,
                "window_hours": window_hours,
            }
            logger.info(
                "Thread recompute done: %d items -> %d threads in %dms (window=%dh)",
                result["items"], result["threads"], result["duration_ms"], window_hours,
            )
            return result
        finally:
            self._recompute_lock.release()

    def consolidation_status(self) -> dict | None:
        """最近一次增量合并的结果（定时任务或手动触发）。"""
        with self._consolidation_state_lock:
            return dict(self._last_consolidation) if self._last_consolidation else None

    def consolidate_threads(
        self,
        window_hours: int = DEFAULT_WINDOW_HOURS,
        trigger: str = "manual",
    ) -> dict:
        """
        增量合并：不删除、不重放全部历史，只做两件真实收敛动作。

        1. 补聚孤儿：讨论型但 thread_id 为 NULL 的条目（重建期间让位、
           采集批次被锁跳过等）按与采集管线相同的算法归位；
        2. 合并单条 Thread：把"只有 1 条报道"的 Thread 与窗口内更早的
           单条 Thread 或多条 Thread 比较，达到阈值就并入后者。

        为什么需要第 2 步：采集管线只让**新条目**去找候选 Thread，两个
        在不同批次各自创建的单条 Thread 永远不会互相比较——即使它们
        讲的是同一件事。定时任务每小时跑一次本方法，热点会随报道增多
        自动收敛，而不是永久停在 1 条。

        与重建一样持有进程内聚类锁：合并与采集管线的 add_item 交错会
        产生半合并状态。被让位的采集批次在末尾的兜底扫描里补聚。

        Returns:
            {window_hours, orphans_clustered, merged_threads, orphans_swept,
             threads_before, threads_after, duration_ms}
        """
        if not self._recompute_lock.acquire(blocking=False):
            raise ConflictError("Thread 聚合正在运行，请稍后再试")
        try:
            from datetime import datetime, timezone

            from app.repositories.item_repo import item_repo

            started = time.monotonic()
            orphans = item_repo.list_thread_orphans()
            orphans_clustered = 0
            if orphans:
                orphans_clustered = self.compute_threads_for_items(
                    orphans, window_hours=window_hours,
                )

            threads = thread_repo.get_candidate_threads(
                hours=window_hours, limit=1000,
            )
            by_id = {t["id"]: dict(t) for t in threads}
            singles = [t for t in threads if (t.get("item_count") or 0) == 1]
            item_map = thread_repo.get_thread_item_map([t["id"] for t in singles])
            tasks_by_id = {t["id"]: t for t in task_repo.list_all_tasks()}
            before = thread_repo.count_live_threads()

            merged = 0
            for source in singles:
                if merged >= _MAX_CONSOLIDATE_MERGES:
                    logger.warning(
                        "Thread consolidate: merge cap (%d) reached, stopping",
                        _MAX_CONSOLIDATE_MERGES,
                    )
                    break
                if source["id"] not in by_id:
                    continue
                # 已在本次扫描中吸收过其他单条 Thread 的目标不再作为源
                # （否则会把刚合并出的多条 Thread 再次搬走，方向失控）
                if (by_id[source["id"]].get("item_count") or 0) != 1:
                    continue
                items = item_map.get(source["id"]) or []
                if not items:
                    continue

                item = dict(items[0])
                platform = item.get("task_name") or "unknown"
                # 稳定身份：成员条目按 task_id 反查任务 source_url
                source_key = source_identity(
                    tasks_by_id.get(item.get("task_id"), {}).get("source_url", ""),
                    platform,
                )
                item.update({
                    "source_id": source_key,
                    "source_name": source_key,
                    "task_name": platform,
                })
                targets = [
                    t for t in by_id.values()
                    if t["id"] != source["id"]
                    and self._eligible_merge_target(source, t)
                ]
                if not targets:
                    continue

                result = thread_clusterer.cluster(
                    item, targets, threshold=DEFAULT_THRESHOLD,
                )
                if result.action != "join" or not result.thread_id:
                    continue
                if thread_repo.is_pair_rejected(source["id"], result.thread_id):
                    continue

                target = by_id.get(result.thread_id)
                if not target:
                    continue
                merged_target = thread_merger.merge(
                    source["id"], target["id"], reason="auto_consolidate",
                )
                if not merged_target:
                    continue
                merged += 1
                by_id.pop(source["id"], None)
                target["item_count"] = (
                    (target.get("item_count") or 0)
                    + (source.get("item_count") or 0)
                )
                target["last_seen_at"] = max(
                    target.get("last_seen_at") or "",
                    source.get("last_seen_at") or "",
                )
                target["title"] = merged_target.get("title") or target.get("title")
                target["platforms"] = (
                    merged_target.get("platforms") or target.get("platforms")
                )
                target["source_keys"] = (
                    merged_target.get("source_keys") or target.get("source_keys")
                )

            # 合并期间到达的采集批次被锁让位，这里补聚，避免永久孤儿
            swept_items = item_repo.list_thread_orphans()
            orphans_swept = 0
            if swept_items:
                orphans_swept = self.compute_threads_for_items(
                    swept_items, window_hours=window_hours,
                )

            after = thread_repo.count_live_threads()
            result = {
                "window_hours": window_hours,
                "orphans_clustered": orphans_clustered,
                "merged_threads": merged,
                "orphans_swept": orphans_swept,
                "threads_before": before["total"],
                "threads_after": after["total"],
                "threads_multi": after["multi"],
                "threads_single": after["single"],
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
            now = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3] + "Z"
            with self._consolidation_state_lock:
                self._last_consolidation = {
                    "at": now,
                    "trigger": trigger,
                    "result": result,
                }
            logger.info(
                "Thread consolidate (%s): %d orphan(s) clustered, %d thread(s) merged, "
                "%d -> %d threads in %dms (window=%dh)",
                trigger, orphans_clustered, merged,
                before["total"], after["total"], result["duration_ms"], window_hours,
            )
            return result
        finally:
            self._recompute_lock.release()

    @staticmethod
    def _eligible_merge_target(source: dict, target: dict) -> bool:
        """
        单条 Thread 的合并方向：只能并入多条 Thread，或并入更早创建的单条
        Thread（同时间按 id 定序）。保证一次扫描内方向确定，不会来回搬。
        """
        if (target.get("item_count") or 0) >= 2:
            return True
        s_first = source.get("first_seen_at") or ""
        t_first = target.get("first_seen_at") or ""
        if t_first < s_first:
            return True
        return t_first == s_first and (target.get("id") or "") < (source.get("id") or "")

    def aggregate_items(
        self,
        item_ids: list[str],
        title: str | None = None,
        target_thread_id: str | None = None,
    ) -> dict:
        """
        手动聚合：把用户勾选的条目收进同一个 Thread。

        - target_thread_id 为空 → 新建 Thread（标题取最长条目标题或用户输入）
        - 提供 target_thread_id → 把这些条目并入既有 Thread
        - 条目原先所在的 Thread 会被重新统计；变空的 Thread 自动删除

        这是"自动聚类没认出来、但用户知道是同一事件"的兜底入口，
        与自动聚类共用 thread_items/items.thread_id 数据模型。
        """
        from app.core.database import transaction
        from app.core.exceptions import (
            BadRequestError,
            ItemNotFoundError,
            NotFoundError,
        )
        from app.repositories.item_repo import item_repo

        unique_ids = list(dict.fromkeys(item_ids))
        if len(unique_ids) < 2:
            raise BadRequestError("至少选择两条内容才能聚合为热点")

        items: list[dict] = []
        for item_id in unique_ids:
            item = item_repo.get(item_id)
            if not item:
                raise ItemNotFoundError(f"条目 {item_id} 不存在")
            items.append(item)

        target = None
        if target_thread_id:
            target = thread_repo.get(target_thread_id)
            if not target:
                raise NotFoundError("目标 Thread 不存在")

        tasks = {t["id"]: t for t in task_repo.list_all_tasks()}

        def _platform(item: dict) -> str:
            return tasks.get(item.get("task_id"), {}).get("name") or "unknown"

        def _source_key(item: dict) -> str:
            return source_identity(
                tasks.get(item.get("task_id"), {}).get("source_url", ""),
                _platform(item),
            )

        default_title = max((i["title"] for i in items), key=len)
        new_title = " ".join((title or "").split()) or default_title
        new_title = new_title[:300]

        with transaction() as conn:
            old_thread_ids = {
                it.get("thread_id") for it in items
                if it.get("thread_id")
            } - {target_thread_id}
            if old_thread_ids:
                item_placeholders = ",".join(["?"] * len(unique_ids))
                thread_placeholders = ",".join(["?"] * len(old_thread_ids))
                conn.execute(
                    f"DELETE FROM thread_items WHERE item_id IN ({item_placeholders}) "
                    f"AND thread_id IN ({thread_placeholders})",
                    [*unique_ids, *old_thread_ids],
                )

            if target:
                thread_id = target["id"]
                for item in items:
                    thread_repo.add_item(
                        thread_id=thread_id,
                        item_id=item["id"],
                        similarity=1.0,
                        title=item["title"],
                        platform=_platform(item),
                        match_reason="manual_aggregate",
                        conn=conn,
                        source_key=_source_key(item),
                    )
                rebuild = thread_id
            else:
                first = items[0]
                thread_id = thread_repo.create(
                    title=new_title,
                    item_id=first["id"],
                    platform=_platform(first),
                    source_key=_source_key(first),
                    algorithm_version="manual",
                    similarity_threshold=1.0,
                    match_reason="manual_aggregate",
                    conn=conn,
                )
                for item in items[1:]:
                    thread_repo.add_item(
                        thread_id=thread_id,
                        item_id=item["id"],
                        similarity=1.0,
                        title=item["title"],
                        platform=_platform(item),
                        match_reason="manual_aggregate",
                        conn=conn,
                    )
                rebuild = thread_id

            thread_repo.rebuild_thread_stats(rebuild, conn=conn)
            # rebuild_thread_stats 会把标题改成"最长成员标题"；手动聚合
            # 指定了标题时必须保留用户输入（否则用户命名的热点会被静默改名）
            if title:
                conn.execute(
                    "UPDATE threads SET title = ? WHERE id = ?",
                    (new_title, thread_id),
                )
            for old_thread_id in old_thread_ids - {thread_id}:
                thread_repo.rebuild_thread_stats(old_thread_id, conn=conn)

        thread_repo.record_override(
            thread_id, "force_join", reason="manual_aggregate",
        )
        logger.info(
            "Manual aggregation: %d item(s) -> thread %s", len(unique_ids), thread_id,
        )
        return self.get_thread(thread_id) or {}

    def aggregation_overview(self, window_hours: int = DEFAULT_WINDOW_HOURS) -> dict:
        """
        聚合概览：给前端一个"为什么现在没有多来源热点 / 还剩多少待补聚"
        的可解释面板，不依赖前端自行拼装多个接口。
        """
        counts = thread_repo.count_live_threads()
        sources, items_in_window = thread_repo.count_recent_discussion(window_hours)
        return {
            "window_hours": window_hours,
            "threads_total": counts["total"],
            "threads_multi": counts["multi"],
            "threads_single": counts["single"],
            "active_discussion_sources": sources,
            "discussion_items_in_window": items_in_window,
            "orphan_items": thread_repo.count_orphan_discussion_items(),
            "recompute": self.recompute_status(),
            "last_consolidation": self.consolidation_status(),
        }

# 全局单例
thread_service = ThreadService()
