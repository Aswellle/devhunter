# DevHunter 全面综合审查与优化实施方案

> 审查对象：`Aswellle/devhunter`  
> 审查基准：GitHub `main` 当前公开仓库状态  
> 核心目标：将 DevHunter 从“多来源抓取 + 基础聚合 + 基础推荐 + 手工 Selector 配置”升级为真正稳定、可理解、可扩展的“开发者信息发现系统”。  
> 优先关注：跨平台事件聚合、个性化推荐、预设采集模板有效性、自定义模板创建流程、学习成本与可维护性。

---

## 1. 结论先行

当前 DevHunter 已经具备一个不错的产品骨架：

- FastAPI + React/Vite/TypeScript；
- HTML / JSON GET / JSON POST / RSS 多种采集模式；
- APScheduler 定时执行；
- SQLite WAL + FTS5；
- SSE 执行过程监控；
- 预设数据源模板；
- Thread 跨平台事件归组；
- 用户主题 + 浏览/点击/停留/收藏行为推荐。

README 对产品能力的定义也已经明确指向“多平台信息集中发现 + 事件归组 + 越用越懂用户”的方向。

但当前实现更接近 **MVP / Rule-based Aggregator**，尚未达到“稳定、可信、低学习成本、可持续学习”的成熟产品阶段。

### 核心判断

| 能力 | 当前状态 | 评价 |
|---|---|---|
| 多来源采集 | 已实现 | ✅ 基础能力完整 |
| 预设数据源 | 已实现 | ✅ 数量足够，但可维护性/健康检查不足 |
| 自定义数据源 | 已实现 | ⚠️ 对普通用户仍偏开发者化 |
| 跨平台 Thread | 已实现 | ⚠️ 算法过于依赖标题词集合 |
| 个性化推荐 | 已实现 | ⚠️ 更像加权排序，不是真正持续学习系统 |
| 用户行为学习 | 已实现 | ⚠️ 信号较粗，权重更新过于简单 |
| 推荐解释 | 基本缺失 | ❌ 用户不知道为什么推荐 |
| 推荐去重/多样性 | 不充分 | ❌ 容易被同主题/同来源占满 |
| 模板验证 | 基础语法验证 | ⚠️ 没有完整“试抓取 + 字段预览 + 健康评分” |
| 模板向导 | 偏配置表单 | ❌ 新手学习成本高 |
| 模板版本/健康状态 | 不成熟 | ❌ 来源变更后容易静默失效 |
| 跨语言/跨平台事件识别 | 很弱 | ❌ 中英文标题、同义改写、实体变形容易漏聚 |
| 可扩展推荐架构 | 较弱 | ⚠️ 需要拆分候选生成/特征/排序/重排 |
| 生产可靠性 | 基础可用 | ⚠️ 单机 SQLite/线程模型适合小规模自托管，但需补偿与可观测性 |

---

# 2. 当前仓库结构与运行模型

README 描述的结构为：

```text
devhunter/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── scheduler/
│   │   ├── crawler/
│   │   ├── schemas/
│   │   ├── core/
│   │   └── utils/
│   ├── migrations/
│   ├── templates/
│   └── run.py
├── frontend/
└── docker-compose.yml
```

当前数据流大体为：

```text
Scheduler
   ↓
Task Execute
   ↓
Crawler
   ↓
Extract / Filter / Dedup
   ↓
Save Item
   ↓
Thread Aggregation
   ↓
Recommendation / Search
   ↓
React UI
```

这个分层方向正确，但目前 **采集、聚合、推荐之间的“领域事件流”还不够清晰**。

建议后续演进为：

```text
Source
  ↓
Fetch
  ↓
Normalize
  ↓
Validate
  ↓
Canonicalize
  ↓
Deduplicate
  ↓
Enrich
  ↓
Cluster(Thread)
  ↓
Feature Index
  ↓
Candidate Generation
  ↓
Ranking
  ↓
Diversification
  ↓
UI Delivery
  ↓
Feedback
  ↺
```

核心原则：

> 不要让“抓到一条 Item”直接等价于“已经是一条可推荐的信息”。

---

# 3. P0：跨平台事件聚合能力审查

## 3.1 当前实现

`ThreadService.compute_threads_for_items()` 当前逻辑：

1. 获取最近 24 小时、尚未分配 Thread 的候选 Item；
2. 最多使用 500 条候选；
3. 对新 Item 的标题进行相似匹配；
4. Jaccard 相似度达到阈值后加入已有 Thread；
5. 否则创建新 Thread。

对应实现位于：

- `backend/app/services/thread_service.py`
- `backend/app/utils/similarity.py`
- `backend/app/repositories/thread_repo.py`

当前默认阈值为 `0.35`，tokenizer 主要依赖空格分词 + stop words；标题经过 Unicode、大小写、标点归一化后使用集合 Jaccard。

---

## 3.2 主要问题

### P0-1：标题词集合不能可靠表达“是否同一个事件”

当前：

```text
"OpenAI launches GPT-5"
"GPT-5 officially released by OpenAI"
"OpenAI 发布 GPT-5"
```

对于英语文本可能部分有效，但：

```text
"OpenAI releases GPT-5"
"GPT-5 lands today"
"GPT-5正式发布"
```

以及不同语言、不同标题风格下，非常容易低估相似度。

反过来：

```text
"React 19 performance"
"React 19 performance benchmark"
```

可能被错误聚合。

---

## 3.3 P0 改造：事件实体 + 多阶段聚类

不要直接用：

```text
Jaccard(title_a, title_b)
```

升级成：

```text
Candidate Retrieval
        ↓
Lexical Similarity
        +
Entity Similarity
        +
Temporal Similarity
        +
Source Independence
        +
Semantic Similarity
        ↓
Pair Score
        ↓
Thread Assignment
        ↓
Cluster Merge / Split
```

推荐评分：

```text
thread_score =
    0.30 * lexical_score
  + 0.25 * entity_score
  + 0.20 * semantic_score
  + 0.15 * temporal_score
  + 0.10 * source_score
```

其中：

### lexical_score

继续复用现有 Jaccard，但仅作为一层信号。

### entity_score

从 title + summary 抽取：

- 公司
- 产品
- 项目
- 人物
- GitHub repo
- 编程语言
- AI 模型
- 版本号
- 日期
- 数字指标

例如：

```json
{
  "entities": [
    "OpenAI",
    "GPT-5"
  ],
  "version": "5",
  "event_keywords": [
    "release",
    "launch"
  ]
}
```

### temporal_score

同一事件通常具有时间窗口：

```text
0~6h     → 1.0
6~24h    → 0.8
24~72h   → 0.5
>72h     → 0.1
```

但不能硬编码成只有 24 小时。

应该改成：

```text
event_window = source_type + event_class dependent
```

例如：

- Breaking news：6~48h；
- Product launch：2~7d；
- Open-source release：3~14d；
- Long-running topic：7~30d。

### source_score

同一来源重复抓取不是“跨平台共识”。

应区分：

```text
same-source duplicates
cross-source corroboration
```

只有不同 source group 的内容才能明显增强 Thread confidence。

---

# 4. P0：Thread 数据模型重构

当前 `threads` / `thread_items` 已能表达聚合结果，但信息不足以支持高质量事件中心。

建议增加：

```sql
ALTER TABLE threads ADD COLUMN canonical_title TEXT;
ALTER TABLE threads ADD COLUMN summary TEXT;
ALTER TABLE threads ADD COLUMN event_type TEXT;
ALTER TABLE threads ADD COLUMN confidence REAL DEFAULT 0;
ALTER TABLE threads ADD COLUMN source_count INTEGER DEFAULT 0;
ALTER TABLE threads ADD COLUMN entity_keys TEXT;
ALTER TABLE threads ADD COLUMN canonical_key TEXT;
ALTER TABLE threads ADD COLUMN status TEXT DEFAULT 'active';
ALTER TABLE threads ADD COLUMN last_clustered_at TEXT;
```

新增：

```sql
CREATE TABLE thread_entities (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    UNIQUE(thread_id, entity_type, entity_key)
);
```

新增：

```sql
CREATE TABLE thread_merge_log (
    id TEXT PRIMARY KEY,
    source_thread_id TEXT NOT NULL,
    target_thread_id TEXT NOT NULL,
    reason TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);
```

这样才能支持：

- 自动合并；
- 人工纠错；
- 错误聚合回滚；
- Thread 重新聚类；
- 未来模型升级。

---

# 5. P0：Thread 必须允许“纠错”

成熟的事件聚合不能只有：

```text
自动匹配
```

必须支持：

```text
合并 Thread
拆分 Thread
将 Item 移出 Thread
将 Item 加入 Thread
标记误聚合
```

API 建议：

```http
POST   /api/threads/{id}/merge
POST   /api/threads/{id}/split
POST   /api/threads/{id}/items/{item_id}/move
POST   /api/threads/{id}/feedback
```

用户操作后的反馈应成为聚类规则训练数据：

```text
false_merge
false_split
correct_merge
correct_assignment
```

这部分未来可以直接用于离线评估或训练 embedding / reranker。

---

# 6. P1：Thread 展示也需要产品升级

当前 Thread 应从“多个 item 的列表”升级为“事件卡片”。

建议结构：

```text
┌─────────────────────────────────────────────┐
│ GPT-5 正式发布                               │
│                                             │
│ 4 个来源 · 2026-09-15 14:20                 │
│                                             │
│ OpenAI        官方发布                       │
│ Hacker News   社区讨论                      │
│ V2EX          中文开发者讨论                 │
│ GitHub        项目相关变化                   │
│                                             │
│ [查看事件脉络] [打开全部来源]                │
└─────────────────────────────────────────────┘
```

关键 UX：

- 默认展示 1 个主标题；
- 显示来源数量；
- 显示最新更新时间；
- 显示“首次出现”；
- 提供时间线；
- 相同事件下不重复刷屏；
- 在列表里优先显示 Thread，而不是每个 Item 都占一个位置。

---

# 7. P0：推荐系统当前实现审查

当前 `RecommendationService` 使用：

```text
0.4 topic
0.3 affinity
0.2 recency
0.1 engagement
```

并从最近最多 500 条 Item 中逐条计算。

推荐分数基本为：

```text
score =
    topic_match_weight * topic_score
  + affinity_weight * affinity_score
  + recency_weight * recency_score
  + engagement_weight * engagement_score
```

这套实现作为第一版完全合理，但不能称为真正的“越用越懂你”。

---

# 8. P0：推荐候选集存在明显上限

当前：

```python
items, total = item_repo.query(page=1, per_page=500)
```

意味着：

> 即使数据库里存在几万条新内容，推荐系统仍只从一个固定的前 500 条窗口里选。

这会导致：

- 数据源多以后出现候选偏差；
- 某个 source 数据量很大时挤压其他 source；
- 高价值旧信息无法被召回；
- Thread 级事件无法作为候选；
- 推荐结果高度依赖数据库默认排序。

### 改造

推荐必须变成两阶段：

```text
Candidate Generation
        ↓
500~5000 candidates
        ↓
Ranking
        ↓
100~300 candidates
        ↓
Diversification
        ↓
20~50 results
```

候选来源：

```text
A. Topic match
B. User affinity
C. Recently popular
D. Freshest
E. Thread updates
F. Previously engaged topics
G. Explicitly starred topics
H. Exploration candidates
```

最终：

```text
candidates = union(A...H)
```

再排序。

---

# 9. P0：推荐算法存在“兴趣回音室”问题

当前 affinity 只会增强已有偏好：

```text
view → +0.05
star → +0.10
```

这会逐渐导致：

```text
喜欢 React
↓
更多 React
↓
继续点击 React
↓
更高 React affinity
↓
几乎不再出现 Vue / Rust / 数据库 / 新领域
```

需要加入：

```text
exploration_score
```

建议：

```text
final_score =
    0.35 preference
  + 0.20 affinity
  + 0.15 recency
  + 0.10 engagement
  + 0.10 thread_importance
  + 0.10 exploration
```

并采用：

```text
80% exploitation
20% exploration
```

同时 exploration 比例应根据用户活跃度自适应。

---

# 10. P1：行为模型必须从“事件计数”升级

当前互动主要是：

```text
view
click
dwell
star
share
```

但实现中不同互动的使用并不完整，例如接口支持 `share`，推荐服务却没有给 share 单独建立显式正向权重。

建议定义统一行为权重：

```python
INTERACTION_WEIGHTS = {
    "impression": 0.0,
    "view": 0.02,
    "click": 0.05,
    "dwell_10s": 0.08,
    "dwell_30s": 0.12,
    "star": 0.35,
    "share": 0.45,
    "hide": -0.50,
    "dismiss": -0.25,
    "not_interested": -0.80,
}
```

注意：

> “没有点击”不能等价于“不喜欢”。

因此未来必须保存：

```text
impression
position
visible_duration
interaction
```

否则无法区分：

```text
用户根本没看到
vs
看到了但不感兴趣
```

---

# 11. P1：Affinity 衰减当前方式存在逻辑问题

当前实现使用：

```python
new_score = old_score * 0.9 + score_delta * (1 - 0.9)
```

这会让 score 的变化高度依赖“交互发生次数”，而不是自然时间。

建议改为：

```text
score(t) =
    score_at_last_update
    * exp(-lambda * elapsed_time)
    + event_weight
```

数据库增加：

```sql
last_decayed_at
```

这样：

- 连续一个小时不看 → 兴趣自然下降；
- 连续一个月不看 → 老兴趣自然退出；
- 不需要用户发生下一次行为才触发衰减。

---

# 12. P1：推荐维度要从 task/platform 扩充到内容特征

当前 affinity 主要偏：

```text
task
platform
keyword
```

这还不够。

建议建立统一用户兴趣画像：

```json
{
  "topics": {
    "AI": 0.93,
    "Rust": 0.74,
    "SaaS": 0.61
  },
  "entities": {
    "OpenAI": 0.91,
    "Anthropic": 0.65
  },
  "formats": {
    "tutorial": 0.72,
    "release": 0.84,
    "discussion": 0.43
  },
  "sources": {
    "GitHub": 0.88,
    "HackerNews": 0.72
  },
  "freshness_preference": 0.81
}
```

这样推荐可以真正回答：

> “用户喜欢什么？”

而不是：

> “用户在哪个任务上点击比较多？”

---

# 13. P0：推荐必须增加“可解释性”

现在 API 只有：

```text
recommendation_score
```

用户无法知道为什么这条内容排在前面。

推荐响应增加：

```json
{
  "recommendation_score": 0.87,
  "recommendation_reasons": [
    {
      "type": "topic",
      "label": "你关注 AI"
    },
    {
      "type": "affinity",
      "label": "你最近经常阅读 OpenAI"
    },
    {
      "type": "recency",
      "label": "刚刚发布"
    }
  ]
}
```

前端显示：

```text
为什么推荐
· 符合你的 AI 关注
· 你最近经常阅读 OpenAI
· 2 小时内的新内容
```

这会明显提升用户对推荐系统的信任。

---

# 14. P0：推荐需要 Thread-aware Ranking

当前主要推荐 Item。

最终应该优先推荐：

```text
Thread
```

因为如果：

```text
GitHub：GPT-5
HackerNews：GPT-5
V2EX：GPT-5
Reddit：GPT-5
```

推荐 4 条就是重复噪音。

正确行为：

```text
GPT-5 正式发布
4 个来源
↓
一个推荐卡片
```

推荐打分应支持：

```text
thread_score =
    max(item_scores)
  + source_diversity_bonus
  + source_count_bonus
  + freshness_bonus
```

并对同 Thread 中的 Item 设置 anti-dup penalty。

---

# 15. P1：推荐增加“负反馈”

必须加入：

```text
不感兴趣
少看这个来源
少看这个主题
已经知道了
屏蔽关键词
```

API：

```http
POST /api/user-prefs/feedback
```

数据：

```json
{
  "item_id": "...",
  "feedback": "not_interested",
  "reason": "topic"
}
```

对应 affinity：

```text
negative affinity
```

不能简单删除历史行为。

---

# 16. P0：预设模板当前有效性分析

当前 `templates/sources.json` 已包含多个真实来源：

- Hacker News
- V2EX
- GitHub Trending
- 掘金
- Indie Hackers
- Dev.to
- Reddit
- 少数派
- Bilibili 等

整体思路很好。

模板当前主要描述：

```json
{
  "id": "...",
  "name": "...",
  "source_url": "...",
  "selector_list": "...",
  "selector_title": "...",
  "selector_link": "...",
  "selector_summary": "...",
  "description": "...",
  "default_keywords": [],
  "recommended_cron": "..."
}
```

问题在于：

> 当前模板更像“抓取配置 JSON”，还不是“可验证的数据源定义”。

---

# 17. P0：模板必须增加 schema/version/health

建议模板升级：

```json
{
  "schema_version": 2,
  "id": "github_trending",
  "name": "GitHub Trending",
  "platform": "github",
  "category": "developer",
  "icon": "github",
  "mode": "html",

  "source": {
    "url": "https://github.com/trending",
    "method": "GET"
  },

  "fields": {
    "list": "article.Box-row",
    "title": "h2.h3 a",
    "link": "h2.h3 a",
    "summary": "p.col-9"
  },

  "schedule": {
    "recommended": "0 9 * * *",
    "min_interval_minutes": 60
  },

  "health": {
    "expected_min_items": 5,
    "required_fields": ["title", "link"]
  },

  "metadata": {
    "locale": "en-US",
    "timezone": "UTC",
    "tags": ["github", "trending", "developer"]
  }
}
```

模板不应只告诉 crawler “怎么抓”，还应该告诉系统：

> “什么结果才算抓成功”。

---

# 18. P0：预设模板必须支持自动健康检测

当前一个站点 HTML 发生结构变化后，可能变成：

```text
HTTP 200
但是提取 0 条
```

如果系统只看 HTTP 200，就会错误地认为任务正常。

必须区分：

```text
transport_success
parse_success
semantic_success
```

健康判断：

```text
HTTP 200
AND
extracted_count > 0
AND
required fields coverage > 90%
```

否则：

```text
template_health = degraded
```

---

# 19. P0：模板 Health Score

为每个数据源建立：

```text
health_score 0~100
```

建议：

```text
HTTP availability       30%
Parse success            30%
Required field coverage  20%
Item freshness           10%
Duplicate rate           10%
```

UI：

```text
GitHub Trending
● Healthy

最近抓取 8 分钟前
最近 24h 采集 145 条
解析成功率 99.2%
```

失败：

```text
GitHub Trending
● Degraded

页面结构发生变化
标题字段提取率 0%
[修复模板]
```

---

# 20. P0：预设模板不能只靠硬编码 PRESET_TEMPLATES

当前 `TaskBase.template_id` 使用：

```python
PRESET_TEMPLATES = {...}
```

并与 JSON 文件手工同步。

这存在：

```text
sources.json 增加模板
↓
忘记修改 PRESET_TEMPLATES
↓
API 拒绝模板
```

应该让：

```text
Template Registry
```

成为单一数据源。

例如：

```python
template_registry.exists(template_id)
```

不要再维护第二份 ID 列表。

---

# 21. P1：模板版本化

数据源会变化。

因此必须存：

```text
template_id
template_version
task_template_version
```

任务创建时：

```text
source template v3
```

之后模板 v4 更新，不应该自动破坏旧任务。

建议：

```text
Preset Template
   ↓
Create Task
   ↓
Snapshot config
```

因此用户任务保存的是：

```text
effective_config
```

而不是运行时重新读取模板。

这也是确保历史任务稳定的重要设计。

---

# 22. P0：当前自定义模板的最大问题不是功能，而是认知负担

当前用户需要理解：

```text
URL
CSS Selector
JSON path
POST body
Cron
关键词
下一页 selector
```

这是一种开发者配置方式。

对普通用户来说：

```text
“我想订阅这个网站”
```

不应该转换成：

```text
“我要先研究 CSS Selector”。
```

---

# 23. P0：把“自定义模板”改造成三步向导

目标：

> 用户不应该需要学习 CSS Selector 才能添加来源。

推荐流程：

```text
Step 1  输入来源
Step 2  系统自动发现
Step 3  确认并保存
```

## Step 1

只问：

```text
你想关注什么网站？

[ https://example.com ]

[开始分析]
```

系统自动：

- GET 页面；
- 识别 RSS；
- 识别 JSON；
- 查找链接；
- 查找文章列表；
- 检测 pagination；
- 分析 DOM 结构。

---

# 24. Step 2：自动发现结果预览

UI：

```text
发现这个网站可能是：

● 文章列表
● RSS Feed
● JSON API

共发现 28 个候选项目

┌─────────────────────────────────┐
│ 文章标题 A                      │
│ https://example.com/a           │
│                                 │
│ 文章标题 B                      │
│ https://example.com/b           │
└─────────────────────────────────┘
```

让用户选择：

```text
☑ 标题
☑ 链接
☑ 摘要
☐ 作者
☐ 发布时间
```

用户不用写 Selector。

---

# 25. Step 3：可选高级模式

默认：

```text
简单模式
```

高级：

```text
开发者模式
```

里面再展示：

```text
CSS Selector
JSON Path
Headers
POST body
Pagination
Rate Limit
Timeout
```

这样：

```text
新手 → 不学习
高级用户 → 有控制权
```

---

# 26. P0：增加“测试并预览”能力

创建/编辑模板后必须提供：

```text
[测试连接]
[测试解析]
[保存]
```

测试结果：

```text
✓ URL 可访问
✓ 发现 22 个条目
✓ 标题字段有效
✓ 链接字段有效
✓ 摘要字段有效
✓ 去重键有效

预览 5 条：
...
```

保存按钮只有在：

```text
minimum semantic validation = pass
```

时才变成主要 CTA。

---

# 27. P0：自动修复 Selector

当任务失败时，不应该只展示：

```text
selector failed
```

可以执行：

```text
重新抓取页面
↓
分析 DOM
↓
寻找与旧 selector 相似结构
↓
生成候选 selector
↓
验证结果
↓
给出：
“发现可能的新标题字段”
```

例如：

```text
旧：
h2.h3 a

建议：
h2 a[href*="/repo/"]
```

按钮：

```text
[应用建议]
```

这样 DevHunter 会逐渐从“爬虫配置器”变成“数据源维护系统”。

---

# 28. P1：自定义模板应支持自然语言创建

进一步降低学习成本：

用户输入：

```text
帮我监控这个网站的最新开发工具文章：
https://example.com
每天早上 9 点更新
只要 AI、Rust、开发工具相关
```

系统生成：

```json
{
  "source_url": "...",
  "keywords": ["AI", "Rust", "开发工具"],
  "cron": "0 9 * * *"
}
```

然后进入：

```text
验证 → 预览 → 保存
```

注意：

> LLM 只负责生成配置建议，真正执行前必须经过 deterministic validator + test fetch。

---

# 29. P1：频率配置不要直接把 Cron 当主 UI

当前支持快捷频率，但产品层仍然应该优先展示：

```text
更新频率

○ 每 30 分钟
○ 每小时
○ 每 6 小时
○ 每天
○ 自定义
```

而不是：

```text
*/30 * * * *
```

Cron 放进：

```text
高级设置
```

---

# 30. P1：模板推荐频率应该结合来源性质

不要统一让用户决定。

模板应提供：

```text
breaking news → 15~30 min
trending      → 1~2 h
articles      → 3~6 h
weekly source → 12~24 h
```

同时需要 rate-limit 和 `Retry-After` 处理。

---

# 31. P0：抓取引擎可靠性改造

当前抓取引擎已经有：

- 重试；
- 指数退避；
- MAX_RESPONSE_BYTES；
- MAX_PAGES；
- SSRF 防护；
- HTML/JSON/RSS；
- 多种链接解析。

这是较好的基础。

但后续需要明确：

```text
transport layer
parser layer
semantic validator
normalizer
dedup
persistence
```

不要继续在一个 crawler engine 文件中累积更多逻辑。

建议拆：

```text
crawler/
├── client.py
├── modes/
│   ├── html.py
│   ├── json.py
│   ├── json_post.py
│   └── rss.py
├── extraction/
│   ├── selectors.py
│   └── autodiscovery.py
├── validation/
│   └── result_validator.py
├── normalization/
│   └── item_normalizer.py
└── engine.py
```

---

# 32. P0：新增统一 Source Adapter

最终推荐接口：

```python
class SourceAdapter(Protocol):
    async def discover(self, source_url: str) -> DiscoveryResult: ...
    async def fetch(self, config: SourceConfig) -> FetchResult: ...
    async def parse(self, response: FetchResponse) -> list[RawItem]: ...
    async def validate(self, items: list[RawItem]) -> ValidationResult: ...
```

Preset / custom 都走同一接口。

这样：

```text
Preset ≠ 特殊代码

Preset = 官方提供的 SourceConfig
Custom = 用户创建的 SourceConfig
```

这个变化非常重要。

---

# 33. P0：Item 统一规范化

目前 Item 主要是：

```text
title
url
summary
task_id
fetched_at
```

建议增加：

```text
canonical_url
source_id
source_name
published_at
author
language
content_type
tags
entities
fingerprint
content_hash
```

这样才能支持：

- 更好的跨平台聚类；
- 推荐；
- 多样性；
- 时间排序；
- 语言识别；
- 去重。

---

# 34. P0：去重需要 URL + 内容双重策略

当前 `url_hash UNIQUE` 很实用，但不足以解决：

```text
同一内容不同 URL 参数
同一文章镜像站
不同平台转载
```

建议：

```text
1. canonical_url
2. normalized_url_hash
3. content_fingerprint
4. semantic duplicate
```

顺序：

```text
exact URL duplicate
       ↓
canonical URL duplicate
       ↓
content fingerprint duplicate
       ↓
semantic duplicate
```

---

# 35. P1：推荐与 Thread 应共享 Feature Pipeline

不要：

```text
Thread 自己分词
Recommendation 自己分词
Search 自己分词
```

统一：

```text
ItemFeatureService
```

输出：

```python
ItemFeatures(
    title_tokens,
    entities,
    topics,
    language,
    source,
    source_group,
    published_at,
    content_type,
    fingerprint,
)
```

然后：

```text
Thread clustering → Feature
Recommendation    → Feature
Search             → Feature
Analytics          → Feature
```

避免四套逻辑逐渐分裂。

---

# 36. P0：建议建立推荐 V2 模块

文件结构：

```text
backend/app/recommendation/
├── candidates.py
├── features.py
├── scoring.py
├── ranking.py
├── diversification.py
├── explanations.py
├── feedback.py
├── profile.py
└── service.py
```

接口：

```python
class RecommendationEngine:
    def generate_candidates(self, user, context) -> list[Candidate]:
        ...

    def score(self, candidates, profile) -> list[ScoredCandidate]:
        ...

    def diversify(self, candidates) -> list[ScoredCandidate]:
        ...

    def explain(self, candidate, profile) -> list[Reason]:
        ...
```

---

# 37. P1：加入推荐评估系统

没有离线评估，就无法判断算法升级到底变好了还是变差了。

每天统计：

```text
CTR
open rate
star rate
dwell > 10s
dwell > 30s
hide rate
duplicate rate
source diversity
topic diversity
```

同时保留：

```text
impression_log
```

结构：

```sql
CREATE TABLE recommendation_impressions (
    id TEXT PRIMARY KEY,
    item_id TEXT,
    thread_id TEXT,
    position INTEGER,
    model_version TEXT,
    score REAL,
    shown_at TEXT
);
```

这样未来可以做：

```text
model v1 → CTR 8.2%
model v2 → CTR 11.4%
```

而不是凭感觉调权重。

---

# 38. P0：SSE / EventBus 的可靠性

当前 EventBus 使用有界 Queue，满了直接：

```python
pass
```

也就是：

> 客户端消费慢时事件会被静默丢弃。

对于 UI 实时进度展示可以接受，但不能拿它作为真正审计日志。

必须区分：

```text
Durable execution state
+
Ephemeral live stream
```

即：

```text
SQLite execution_events
         ↓
EventBus
         ↓
SSE
```

SSE 断开后：

```text
last_event_id
↓
补齐缺失事件
↓
继续实时流
```

---

# 39. P1：任务执行状态机

推荐：

```text
queued
running
fetching
parsing
normalizing
deduplicating
persisting
clustering
completed
partial_failed
failed
cancelled
```

而不是依赖多个 boolean/counter 隐式表示状态。

---

# 40. P0：任务失败必须“自解释”

每个执行保存：

```json
{
  "status": "partial_failed",
  "stage": "parsing",
  "http_status": 200,
  "items_found": 0,
  "selector_failure": true,
  "health_score": 21,
  "suggested_fix": "selector_changed"
}
```

UI：

```text
GitHub Trending
⚠ 页面结构可能发生变化

连接正常
但标题提取失败

[查看详情]
[自动修复]
```

而不是：

```text
执行失败
```

---

# 41. P0：自定义模板保存模型

推荐新增：

```sql
CREATE TABLE source_templates (
    id TEXT PRIMARY KEY,
    owner_type TEXT NOT NULL,
    owner_id TEXT,
    kind TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    health_score REAL DEFAULT 0,
    last_validated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

字段：

```text
kind = preset | custom | imported
status = draft | healthy | degraded | broken
```

---

# 42. P0：任务与模板解耦

建议：

```text
SourceTemplate
      ↓ snapshot
Task
```

Task 不应永久依赖 template 的实时内容。

否则：

```text
管理员更新 preset
↓
用户任务突然改变
```

会产生极难排查的问题。

---

# 43. P1：前端信息架构优化

建议主导航：

```text
首页
发现
事件
来源
收藏
设置
```

### 首页

重点：

```text
For You
今日重要事件
新来源
```

### 发现

```text
全部内容
筛选
搜索
```

### 事件

```text
Cross-platform Threads
```

### 来源

```text
Preset
Custom
Health
```

### 设置

只放：

```text
兴趣
推荐
账户
系统
```

不要把“来源配置”塞进普通设置。

---

# 44. P0：自定义模板创建页面 UI

建议：

```text
新增来源

① 来源
  [ 粘贴网站地址                    ]

② 发现
  ✓ 检测到 RSS
  ✓ 找到文章列表
  ✓ 找到标题
  ✓ 找到链接

③ 预览
  [条目 1]
  [条目 2]
  [条目 3]

④ 过滤
  [ AI ] [ Rust ] [ SaaS ]

⑤ 更新
  每小时 ▼

                [取消] [创建来源]
```

高级配置折叠：

```text
高级设置 ▸
```

---

# 45. P1：模板页提供“模板市场”式体验

即使不做真正云端市场，也可以本地展示：

```text
推荐来源

AI
├─ Hacker News
├─ GitHub Trending
├─ Reddit WebDev

创业
├─ Indie Hackers

中文开发者
├─ V2EX
├─ 掘金
├─ 少数派
```

每个模板：

```text
Logo
名称
分类
描述
健康状态
更新频率
[一键启用]
```

这样比“创建任务 → 下拉框 → 选 template_id”更产品化。

---

# 46. P1：模板有效性要持续验证

推荐后台 job：

```text
每 6~24 小时
   ↓
测试 preset
   ↓
检查 HTTP
   ↓
检查解析
   ↓
检查字段
   ↓
更新 health
```

在 CI 中做 smoke test：

```text
for preset in presets:
    fetch
    parse
    assert title coverage > threshold
    assert link coverage > threshold
```

这样 GitHub HTML/API 变化能尽早发现。

---

# 47. P0：推荐配置 UI 不应让用户调四个 weight

当前虽然后端支持：

```text
topic_weight
affinity_weight
recency_weight
engagement_weight
```

但产品层不应该要求普通用户理解这些参数。

改成：

```text
推荐偏好

○ 更关注我的兴趣
○ 平衡
○ 更关注最新内容
○ 更多探索新领域
```

内部映射：

```text
interest_first
balanced
fresh_first
exploration_first
```

高级模式再允许权重。

---

# 48. P1：加入“我的兴趣画像”

页面：

```text
你的兴趣

AI                         ██████████ 92
Rust                       ████████   76
SaaS                       ██████     61

你常看：
GitHub
Hacker News

你最近开始关注：
Agent
MCP
Local AI

[管理兴趣]
```

这可以把“个性化”从黑箱变成用户可控的系统。

---

# 49. P0：数据流 V2

最终推荐的数据流：

```text
             ┌──────────────────┐
             │ Source Templates │
             └────────┬─────────┘
                      ↓
              Source Registry
                      ↓
             ┌────────────────┐
             │ Fetch Scheduler│
             └───────┬────────┘
                     ↓
               Fetch Response
                     ↓
               Parser/Adapter
                     ↓
              Item Normalizer
                     ↓
              Semantic Validate
                     ↓
        ┌────────────┼────────────┐
        ↓            ↓            ↓
     Dedup        Feature       Metrics
        ↓         Extraction
        └────────────┬────────────┘
                     ↓
               Thread Engine
                     ↓
               Item/Thread DB
                     ↓
        ┌────────────┴────────────┐
        ↓                         ↓
      Search                Recommendation
        ↓                         ↓
        └────────────┬────────────┘
                     ↓
                    UI
                     ↓
              User Feedback
                     ↓
              User Profile
                     ↺
```

---

# 50. 数据库 V2 建议

核心实体：

```text
sources
source_templates
source_template_versions
tasks
task_executions
items
threads
thread_items
thread_entities
item_features
user_topics
user_affinity
user_interactions
user_feedback
recommendation_impressions
recommendation_models
```

职责：

```text
source_templates → 如何抓
tasks            → 什么时候抓
items            → 抓到了什么
threads          → 哪些内容属于同一事件
features         → 内容是什么
affinity         → 用户喜欢什么
impressions      → 推荐展示了什么
feedback         → 用户明确喜欢/不喜欢什么
```

---

# 51. 实施顺序

## Phase 0：稳定性基线

### P0

- [ ] Template Registry 单一来源；
- [ ] Task 保存 effective config snapshot；
- [ ] Source health；
- [ ] semantic validation；
- [ ] execution state machine；
- [ ] durable execution event；
- [ ] Thread / recommendation 单元测试；
- [ ] preset smoke tests。

---

## Phase 1：Thread V2

### P0

- [ ] Item feature extraction；
- [ ] entity extraction；
- [ ] temporal score；
- [ ] lexical + entity + semantic hybrid；
- [ ] Thread confidence；
- [ ] merge/split；
- [ ] Thread-aware listing；
- [ ] same-source duplicate suppression。

---

## Phase 2：Recommendation V2

### P0

- [ ] candidate generation；
- [ ] Thread-aware candidate；
- [ ] negative feedback；
- [ ] exploration；
- [ ] time-decay profile；
- [ ] recommendation explanations；
- [ ] diversification。

### P1

- [ ] impression logging；
- [ ] recommendation analytics；
- [ ] model version；
- [ ] offline evaluation；
- [ ] A/B test infrastructure。

---

## Phase 3：Template UX V2

### P0

- [ ] 3-step template wizard；
- [ ] URL autodiscovery；
- [ ] preview extraction；
- [ ] test-before-save；
- [ ] simple mode；
- [ ] advanced mode。

### P1

- [ ] auto-fix selector；
- [ ] natural-language template creation；
- [ ] template health dashboard；
- [ ] template versioning；
- [ ] template categories。

---

# 52. 建议的文件级改造

## Backend

新增：

```text
backend/app/sources/
├── registry.py
├── models.py
├── discovery.py
├── health.py
└── validator.py

backend/app/features/
├── extractor.py
├── entities.py
├── language.py
└── fingerprint.py

backend/app/threads/
├── clustering.py
├── scoring.py
├── merge.py
├── split.py
└── service.py

backend/app/recommendation/
├── candidates.py
├── features.py
├── scoring.py
├── ranking.py
├── diversification.py
├── explanations.py
├── profile.py
└── service.py
```

调整：

```text
backend/app/crawler/engine.py
backend/app/services/thread_service.py
backend/app/services/recommendation_service.py
backend/app/repositories/thread_repo.py
backend/app/repositories/user_prefs_repo.py
backend/app/schemas/task.py
backend/app/api/tasks.py
backend/app/api/user_prefs.py
```

---

# 53. API V2 建议

## Sources

```http
GET    /api/sources
POST   /api/sources/discover
POST   /api/sources/validate
POST   /api/sources/test
POST   /api/sources
PATCH  /api/sources/{id}
DELETE /api/sources/{id}
GET    /api/sources/{id}/health
```

## Threads

```http
GET    /api/threads
GET    /api/threads/{id}
POST   /api/threads/{id}/merge
POST   /api/threads/{id}/split
POST   /api/threads/{id}/feedback
```

## Recommendation

```http
GET    /api/recommendations
GET    /api/recommendations/explanations
POST   /api/recommendations/impression
POST   /api/recommendations/feedback
GET    /api/user/profile
```

---

# 54. 推荐核心伪代码

```python
def recommend(user, context, limit=20):
    candidates = candidate_generator.generate(
        user=user,
        context=context,
        pools=[
            "topic",
            "affinity",
            "fresh",
            "thread_updates",
            "exploration",
        ],
    )

    features = feature_service.build(candidates)

    scored = ranking_service.rank(
        candidates=candidates,
        features=features,
        profile=user.profile,
    )

    diverse = diversification_service.apply(
        scored,
        max_per_thread=1,
        max_per_source=4,
        max_per_topic=6,
    )

    final = diverse[:limit]

    return [
        recommendation_explainer.attach(item, user.profile)
        for item in final
    ]
```

---

# 55. Thread 核心伪代码

```python
def assign_thread(item, candidates):
    feature = feature_service.extract(item)

    best = None

    for thread in candidates:
        score = (
            0.30 * lexical(feature, thread)
            + 0.25 * entity(feature, thread)
            + 0.20 * semantic(feature, thread)
            + 0.15 * temporal(feature, thread)
            + 0.10 * source_independence(feature, thread)
        )

        if best is None or score > best.score:
            best = Match(thread=thread, score=score)

    if best and best.score >= THREAD_ASSIGN_THRESHOLD:
        return attach(item, best.thread, best.score)

    return create_thread(item)
```

同时必须支持：

```text
HIGH confidence
MEDIUM confidence
LOW confidence
```

不要所有匹配都二元化成：

```text
属于 / 不属于
```

---

# 56. 验收标准

## Cross-platform Thread

必须通过：

```text
同一事件、多种标题 → 聚合成功率 >= 90%
明显不同事件 → 错误聚合率 <= 3%
同源重复 → 不重复创建 Thread
跨语言标题 → 可以在有足够实体信息时聚合
Thread 可以手动 merge / split
```

重点不在具体数字绝对值，而在建立可回归的 benchmark dataset。

---

## Recommendation

至少建立：

```text
1000 impressions
100 positive interactions
100 negative interactions
50 Thread clusters
```

然后比较：

```text
baseline
vs
V2
```

指标：

```text
CTR
star_rate
dwell_30s
negative_feedback_rate
duplicate_rate
source_diversity
topic_diversity
```

---

## Templates

每个 preset：

```text
HTTP success
parse success
required field coverage
minimum item count
dedup validity
```

全部自动测试。

---

## Custom Source UX

新用户必须可以：

```text
输入 URL
→ 预览
→ 确认
→ 保存
```

不需要：

```text
阅读 CSS Selector 文档
```

高级用户仍然可以：

```text
打开 Advanced
→ 手动调整 selector
```

---

# 57. Definition of Done

这一轮改造完成后，DevHunter 应该达到以下产品状态：

### 用户视角

```text
我把自己关心的网站交给 DevHunter。
DevHunter 自动负责：

抓取
↓
过滤
↓
去重
↓
识别是不是同一个事件
↓
合并不同平台报道
↓
理解我最近喜欢什么
↓
推荐真正值得看的内容
```

用户不应该感知：

```text
selector
Jaccard
Cron
retry
thread clustering
affinity decay
```

这些都应该成为内部实现细节。

### 产品目标

最终体验应从：

> “我配置了一个爬虫聚合器”

转变为：

> “我有一个会主动替我筛选开发者信息的个人信息雷达。”

---

# 58. 最终优先级

```text
P0-1  Template Registry + config snapshot
P0-2  Source semantic validation + health
P0-3  Thread V2 hybrid clustering
P0-4  Thread-aware recommendation
P0-5  Recommendation candidate generation
P0-6  Recommendation explanation
P0-7  Negative feedback
P0-8  3-step custom source wizard
P0-9  Test-before-save
P0-10 Durable execution events

P1-1  Entity extraction
P1-2  Exploration / diversification
P1-3  User interest profile
P1-4  Template versioning
P1-5  Selector auto-repair
P1-6  Impression analytics
P1-7  Recommendation evaluation
P1-8  Natural-language source creation

P2-1  Embedding-based semantic clustering
P2-2  Learning-to-rank
P2-3  Personalized model selection
P2-4  Cross-user anonymous trend intelligence
P2-5  Template marketplace / sharing
```

---

# 59. 关键工程原则

1. **Preset 与 Custom 使用同一 SourceConfig / Adapter，不维护两套逻辑。**
2. **Task 永远保存有效配置快照，不直接依赖未来模板版本。**
3. **Thread 不是标题相似度，而是实体 + 时间 + 语义 + 来源的事件聚类。**
4. **Recommendation 不是简单加权排序，而是 Candidate → Ranking → Diversification → Explanation。**
5. **所有推荐都必须可解释、可反馈、可回归评估。**
6. **“HTTP 200”不等于抓取成功，必须有 semantic validation。**
7. **SSE 是实时展示通道，不是唯一事件存储。**
8. **普通用户不应该学习 CSS Selector / Cron；高级配置应该渐进式暴露。**
9. **模型和智能能力只能给出建议，最终抓取配置必须由 deterministic validator 验证。**
10. **所有关键行为都需要可观测：来源健康、聚类置信度、推荐分数、推荐原因、用户反馈。**

---

## 60. 参考的当前实现位置

- Repository / README：`https://github.com/Aswellle/devhunter`
- Thread service：`backend/app/services/thread_service.py`
- Similarity：`backend/app/utils/similarity.py`
- Thread repository：`backend/app/repositories/thread_repo.py`
- Recommendation：`backend/app/services/recommendation_service.py`
- User preference repository：`backend/app/repositories/user_prefs_repo.py`
- Source templates：`backend/templates/sources.json`
- Template loader：`backend/app/crawler/templates.py`
- Task schema：`backend/app/schemas/task.py`
- Task API：`backend/app/api/tasks.py`
- Item API：`backend/app/api/items.py`
- Crawler engine：`backend/app/crawler/engine.py`
- Event bus：`backend/app/core/event_bus.py`

> 本文以当前公开仓库代码为基准，重点是“可以直接落地执行的产品/架构/代码改造方向”，而不是泛化的推荐系统理论说明。
