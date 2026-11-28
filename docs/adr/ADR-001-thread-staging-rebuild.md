# ADR-001｜Thread 全量重建的 staging 语义与人工决策重放

状态：已接受（2026-11-28）
关联：审计工作项 THR-001、THR-002（已实现稳定来源身份）

## 背景

`recompute_all_threads()` 先 `thread_repo.delete_all()` **立即提交**清空全部
Thread，再分批重放聚类。两个已证实的问题：

1. **非原子**：清空与重放是多次独立提交。重放中途崩溃/异常会留下部分新、
   部分空的聚合投影——旧投影已被删除，无法回退，API 期间读到不一致状态。
2. **人工决策失效**：`thread_overrides`（merge/split/reject_merge）与
   `thread_relations` 以一次性 Thread UUID 为键，重建生成新 ID 后人工纠错
   全部失效；算法可能重新犯用户已纠正过的错误。

## 决策

### 1. staging = 单事务（不引入 staging 表）

SQLite WAL 下，一个显式事务就是一个天然 staging 投影：

- 重建在**单个事务**内完成：清空 → 重放（复用采集管线算法）→ 孤儿补聚 →
  完整性校验 → 提交。
- 校验项（失败即整体回滚，旧投影继续可用）：
  - 每个 discussion 条目恰好归属一个 Thread（镜像与成员一致）；
  - `thread_items` 无孤儿引用（thread/item 都存在）；
  - `threads.item_count` 与实际成员数一致。
- 中断/校验失败 → 回滚 → 活动投影保持重建前的完整状态，可安全重试。

不建 staging 表的理由：单用户 SQLite 无并发读投影需求（WAL 快照隔离已
保证重建期间读到旧投影），staging 表会把"两份投影 + 原子切换 + 清理"
的复杂度引入 schema，而事务回滚以零迁移成本提供同样保证。

### 2. 人工决策以成员条目 ID 为稳定身份存储（迁移 031）

新表 `thread_manual_decisions`：

| 列 | 语义 |
|---|---|
| decision_type | `merge` / `split` / `reject_merge` |
| item_ids | JSON 数组，决策锚定的成员条目 ID（跨重建稳定） |
| payload_json | 附加信息（如 split 的保留侧锚点） |
| replayed_at | 已被某次重建重放的时间（NULL = 待重放） |

- merge：记录合并时两侧全部成员 ID。重放后若分散在多个 Thread，
  合并回锚点最多的那个 Thread（真实 thread_merger，保留审计链）。
- split：记录保留侧锚点 + 被移出条目 ID。重放后若算法再次把它们聚进
  同一 Thread，重新执行拆分。
- reject_merge（解除关联）：记录两侧锚点条目 ID。重放后若两侧分属不同
  Thread，按当前 Thread ID 重新登记 `reject_merge` override，
  阻止自动合并/关联在同一投影存续期内再犯。
- 重放发生在 staging 事务**提交之后**（决策合并器自己管理事务，避免
  嵌套连接死锁）；崩溃时 `replayed_at` 仍为 NULL，下次重建自动重试——
  决策永不静默丢失。
- 手动聚合（force_join）不进入重放：它是对既有投影的即时修正，
  不携带可重放的成员集合语义。

### 3. 不做的事

- 不改 `thread_overrides`/`thread_relations` 的现有语义（历史审计保留，
  Thread 键随投影存续期有效）。
- 不做投影版本号/回滚窗口（单事务回滚已覆盖中断场景；版本化留待
  多算法并存需求出现时再评估）。

## 后果

- 重建期间的长事务会阻塞其他写入（WAL 单写者）。个人规模（数千条目）
  重放在秒~分钟级，与现有 misfire 预算兼容；如未来规模增长，再评估
  分段 staging 表方案。
- 决策重放后 Thread ID 再次变化（merge 保留 target、split 生成新 ID），
  前端 Thread 引用按既有行为自然失效——与现状一致，不是新增破坏。
