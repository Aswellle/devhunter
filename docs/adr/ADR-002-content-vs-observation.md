# ADR-002｜内容实体与来源观测的边界（canonical Item vs Observation）

状态：已接受（2026-11-28）
关联：审计工作项 DATA-002、THR-002（已完成 provider 身份）、ADR-001

## 背景

`items` 表同时承载"内容主体"与"单一来源记录"。`crawler/dedup.py` 的
content_hash（title+summary 指纹）去重是**全局**的：三个站点转载同一篇
新闻时，只有第一条入库，后两条被静默丢弃——Thread 失去跨来源证据，
"同一事件被 N 个独立来源确认"的产品语义无法成立。

## 决策

### 1. 观测模型：当前 `items` 行即来源观测（observation）

不引入 `item_sources` 观测表的完整 canonical-item 模型。理由：

- 单用户 SQLite 规模下，"同一内容 × N 来源"的重复行成本可控（千行级）；
- Thread 聚合以条目为输入，跨来源证据需要的就是多条目；
- 完整 canonical 模型（items 拆内容表 + item_sources 观测表 + 双写迁移）
  触及 FTS、Thread、推荐、收藏、RSS 全部读路径，收益不成比例；
  留待多用户/大规模需求出现时再评估（届时本 ADR 的身份列可直接复用）。

### 2. 内容指纹去重按来源身份限定（migration 032）

- `items.source_key TEXT`（来源 URL 主机名，`utils/url.source_identity`，
  与 THR-002 的 `threads.source_keys` 同一身份体系）+ 索引；
- content_hash 匹配条件从"全局存在"收紧为"**同 source_key 已存在**"：
  - 同一来源重复同步同内容 → 继续被拦（不增加来源计数，既有
    url_hash/external_id 层也兜底）；
  - 跨来源同内容 → 保留为独立观测行，进入 Thread 跨来源证据；
  - 历史行 source_key 为 NULL（回填前）→ 不参与内容指纹匹配（保守：
    宁可多保留一行观测，不可丢证据）；
- 批内去重集合逻辑不变（同批同任务 → 同 source_key）。

### 3. 回填与删除策略

- 回填：启动时（`main.py` lifespan，init_database 之后）执行幂等的
  `item_repo.backfill_item_source_keys()`——按 task_id 分组取任务
  source_url 计算身份，只更新 `source_key IS NULL` 的行；测试/升级路径
  可显式调用。空库与升级库两条路径均有测试。
- 删除：`source_key` 是派生属性（可由任务 source_url 重建），删除任务
  时条目随之清理（既有 cleanup 语义），无新增删除分支；观测行之间
  无外键依赖，任何一行删除不影响其他来源的观测。

### 4. 不做的事

- 不拆 canonical content 表、不建 item_sources 表（理由见 §1）；
- 不改 url_hash 全局唯一与 external_id 按任务唯一的语义（URL 相同即
  同一页面观测，跨来源 URL 天然不同）；
- 不回填改写 `content_hash` 本身（指纹算法不变，只改匹配范围）。
