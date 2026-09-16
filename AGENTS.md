# AI 编程代理严格执行规范

你现在进入【严格工程实施模式】。

本次开发必须以项目根目录中的：

```
DevHunter_全面综合审查与优化实施方案.md
```

作为本次工作的**最高优先级项目实施规范（Single Source of Truth）**。

除非用户明确提出新的指令覆盖该文档中的对应要求，否则：

> **不得自行改变、弱化、跳过、替换或重新解释文档中已经明确的目标、优先级、架构方向、实施顺序和验收标准。**

------

## 一、第一原则：先理解，后修改

开始任何代码修改之前，必须依次执行：

1. 完整读取：
   + `DevHunter_全面综合审查与优化实施方案.md`
   + 当前项目 README
   + 当前 Git 状态
   + 与本次任务相关的全部源码
   + 相关测试文件
   + 数据库 migration
   + API schema
   + 前端相关页面和组件
2. 建立当前项目实际状态与 Markdown 文档目标之间的差异。
3. 输出内部实施计划，至少包含：
   + 当前实现
   + 文档要求
   + 当前缺口
   + 修改文件
   + 修改顺序
   + 依赖关系
   + 风险
   + 验证方式
4. 在真正修改代码之前，确认自己理解：
   + P0 / P1 / P2 的优先级
   + 数据流变化
   + 数据模型变化
   + API 变化
   + 前端交互变化
   + 迁移兼容要求
   + 测试要求

禁止：

+ 尚未阅读完整 Markdown 就开始改代码；
+ 根据文件名猜测实现；
+ 只阅读一个文件便开始重构；
+ 用自己“认为更好”的方案替换文档方案。

------

# 二、严格遵循优先级

文档中的优先级具有明确执行意义：

### P0

必须优先完成。

不能因为：

+ 工作量较大；
+ 当前代码比较复杂；
+ AI 更喜欢另一种架构；
+ 可以“以后再做”；

而自动降低为 P1/P2。

### P1

只有在相关 P0 已完成、验证通过后才能开始。

### P2

不得在当前阶段擅自提前实施。

------

# 三、禁止 Scope Creep

除非用户明确授权，否则：

不要额外实施与当前任务没有直接关系的：

+ 新功能；
+ UI 大改；
+ 数据库结构重写；
+ 第三方服务替换；
+ 技术栈迁移；
+ 完全不同的推荐算法；
+ 完全不同的爬虫架构；
+ 与当前目标无关的代码清理。

如果发现：

> 为完成当前任务必须修改额外文件

可以修改。

如果发现：

> 某个额外重构“以后可能更好”

不要自动实施。

只记录：

```text
Future Improvement
```

不要偷偷扩大任务范围。

------

# 四、不要假设当前代码与你看到的文档完全一致

Markdown 是目标规范。

仓库代码是真实现状。

必须先做：

```text
Target
vs
Current
vs
Gap
```

例如：

```text
Target:
Thread V2 = lexical + entity + semantic + temporal + source

Current:
Jaccard title similarity

Gap:
缺少 entity / semantic / temporal / source independence
```

然后才能实施。

禁止：

> 看到文档中的目标代码结构，就假设项目已经存在对应文件。

必须先确认真实文件。

------

# 五、所有重大修改必须保持现有功能兼容

除非文档明确要求破坏性迁移，否则必须遵守：

```text
现有功能不能无故消失
现有 API 尽可能兼容
现有任务不能失效
现有 preset 不能因为新架构全部损坏
历史数据不能无故丢失
```

数据库迁移必须考虑：

```text
旧数据
旧任务
旧模板
旧推荐行为
旧 Thread
```

不得通过：

```sql
DROP TABLE
```

等方式粗暴重建数据结构，除非明确证明安全且有完整迁移方案。

------

# 六、每次实施必须采用“小步、可验证”模式

禁止一次性进行巨大重构：

```text
修改 30 个文件
→ 最后再测试
```

正确方式：

```text
1. 修改一组相关文件
2. 类型检查
3. 单元测试
4. 集成测试
5. 检查 diff
6. 确认功能没有回归
7. 再进入下一阶段
```

每完成一个逻辑阶段，都必须验证。

------

# 七、推荐固定实施循环

每一个开发任务都必须执行：

```text
READ
 ↓
UNDERSTAND
 ↓
PLAN
 ↓
IMPLEMENT
 ↓
TEST
 ↓
REVIEW
 ↓
FIX
 ↓
VERIFY
```

具体要求：

## READ

读取相关代码和文档。

## UNDERSTAND

解释当前实现与目标之间的差距。

## PLAN

列出本轮实际修改文件。

## IMPLEMENT

只实施当前任务。

## TEST

运行最相关测试。

## REVIEW

检查：

+ 是否遵循 Markdown；
+ 是否破坏现有功能；
+ 是否引入重复逻辑；
+ 是否存在隐式副作用；
+ 是否存在数据库兼容问题；
+ 是否存在竞态问题；
+ 是否存在性能回退。

## FIX

发现问题后必须继续修复。

## VERIFY

再次运行验证。

------

# 八、任何“智能算法”都必须先保证 Deterministic Fallback

对于：

+ Thread 聚合；
+ 推荐；
+ 模板自动发现；
+ Selector 修复；
+ LLM 生成配置；

必须遵守：

```text
AI / heuristic
      ↓
Deterministic Validator
      ↓
Accept / Reject
```

不能：

```text
LLM 说配置正确
→ 直接保存
```

必须：

```text
LLM 生成
→ Schema validation
→ Security validation
→ Test fetch
→ Semantic validation
→ Pass
→ 保存
```

------

# 九、Thread 聚合开发规则

Thread 不能退化成单一字符串相似度。

必须保持文档要求的多因素架构：

```text
Lexical
Entity
Semantic
Temporal
Source independence
```

如果暂时无法实现某一个因素：

不要假装已经实现。

必须明确标记：

```text
implemented
partial
not implemented
```

禁止把：

```text
keyword overlap
```

包装成：

```text
semantic understanding
```

------

# 十、推荐系统开发规则

推荐必须遵循：

```text
Candidate Generation
        ↓
Feature Extraction
        ↓
Ranking
        ↓
Diversification
        ↓
Explanation
```

禁止继续把全部推荐逻辑塞进一个巨大函数。

需要保持模块化：

```text
candidates
features
scoring
ranking
diversification
profile
feedback
explanations
```

任何推荐算法修改都必须说明：

```text
为什么调整
会影响什么
如何验证
```

禁止通过“感觉更合理”直接调权重而没有验证。

------

# 十一、推荐结果必须考虑：

至少检查：

+ 新鲜度；
+ 用户兴趣；
+ 用户行为；
+ Thread；
+ 来源多样性；
+ Topic 多样性；
+ 探索；
+ 负反馈；
+ 重复内容。

不能让推荐系统长期形成单一主题回音室。

------

# 十二、模板系统开发规则

Preset 与 Custom 不得维护两套核心执行逻辑。

目标：

```text
Preset
   ↓
SourceConfig
   ↓
SourceAdapter

Custom
   ↓
SourceConfig
   ↓
SourceAdapter
```

不能：

```text
Preset 一套逻辑
Custom 另一套逻辑
```

模板必须尽量支持：

```text
schema version
configuration version
health
validation
preview
test fetch
semantic validation
```

------

# 十三、自定义模板 UX 必须遵守渐进式复杂度

默认用户不应该被要求理解：

```text
CSS Selector
JSONPath
Cron
Headers
POST body
Pagination
```

默认流程：

```text
输入 URL
↓
自动发现
↓
预览
↓
确认
↓
保存
```

高级能力：

```text
Advanced
```

才显示。

如果实现时发现前端设计与这一目标冲突：

> 优先保证用户任务流，而不是保留开发者配置方式。

------

# 十四、禁止删除现有正确实现来“方便重构”

重构时优先：

```text
Extract
Adapt
Migrate
Deprecate
Remove
```

而不是：

```text
Delete everything
Rewrite everything
```

只有当旧实现明确阻碍新架构，并且已存在替代实现和完整测试时，才能删除。

------

# 十五、数据库迁移严格要求

任何 migration 都必须回答：

```text
为什么增加这个字段？
旧数据怎么办？
默认值是什么？
回滚怎么办？
现有查询怎么办？
索引是否需要？
SQLite WAL 下是否安全？
```

新增字段优先：

```text
nullable
or
safe default
```

不要破坏现有数据库启动。

------

# 十六、测试是开发过程的一部分，不是结束后的附属工作

任何新增能力必须至少增加：

```text
Unit Test
```

涉及 API：

```text
API Test
```

涉及数据库：

```text
Repository / Migration Test
```

涉及 Thread：

```text
Clustering Regression Test
```

涉及 Recommendation：

```text
Ranking Regression Test
```

涉及 Template：

```text
Template Smoke Test
```

涉及 UI：

```text
Component / Interaction Test
```

------

# 十七、必须建立 Regression Fixtures

对于 Thread、Recommendation、Template：

不要每次只依赖线上真实网站。

必须建立固定测试样本。

例如：

```text
fixtures/
├── threads/
├── recommendation/
└── templates/
```

这样代码升级后可以验证：

```text
旧正确结果仍然正确
```

------

# 十八、对性能保持敏感

任何循环都必须问：

```text
N 是多少？
是否可能变成 10k？
100k？
1M？
```

特别检查：

```text
数据库分页
N+1 query
全量排序
Thread matching
推荐候选
DOM parsing
同步阻塞
SSE
```

禁止默认使用：

```text
load all
iterate all
sort all
```

而没有规模分析。

------

# 十九、运行前必须检查 Git Diff

每个阶段结束执行：

```bash
git status
git diff --stat
git diff
```

检查：

```text
是否修改了意外文件？
是否生成临时文件？
是否修改 lockfile？
是否修改配置？
是否修改数据库文件？
是否删除了测试？
```

发现异常必须停止并修正。

------

# 二十、最终验收必须逐项对照 Markdown

完成后不能只说：

```text
Done.
```

必须输出：

```text
# Implementation Verification

## P0

- [x] Template Registry
- [x] Config Snapshot
- [x] Source Health
- [x] Semantic Validation
- [x] Thread V2
- [x] Recommendation Candidate Generation
- [x] Recommendation Explanation
- [x] Negative Feedback
- [x] Custom Source Wizard
- [x] Durable Execution Events

## P1

...

## P2

...
```

对于没有完成的项目：

```text
- [ ] Item
  Reason: ...
  Remaining files: ...
  Blocking issue: ...
```

不得伪造完成。

------

# 二十一、发现文档要求与现有代码/技术约束冲突时

不要擅自选择一个方案。

必须：

1. 明确指出冲突；
2. 说明具体文件；
3. 说明当前技术约束；
4. 给出最小改动方案；
5. 优先保持产品目标和数据兼容；
6. 只有确实无法执行时才暂停该部分。

但不要因为存在局部冲突就停止全部工作。

可以继续实施不受影响的部分。

------

# 二十二、任何不确定实现禁止“猜”

遇到：

```text
未知 API
未知数据库结构
未知第三方库行为
未知文件
未知运行方式
```

必须检查真实代码 / package / docs / tests。

禁止：

```text
我猜这里应该是...
```

------

# 二十三、最终代码质量要求

最终代码必须做到：

```text
可维护
可测试
可回滚
可观察
可扩展
```

避免：

```text
巨大 Service
隐式全局状态
重复逻辑
魔法数字
无意义抽象
临时 patch
TODO 驱动架构
```

------

# 二十四、提交粒度要求

建议按能力拆分：

```text
commit 1:
source/template foundation

commit 2:
health + semantic validation

commit 3:
thread v2

commit 4:
recommendation v2

commit 5:
custom source wizard

commit 6:
observability + regression tests
```

不要把完全无关内容塞进一个 commit。

------

# 二十五、现在开始执行

你的第一步不是修改代码。

第一步必须：

```text
1. 读取 DevHunter_全面综合审查与优化实施方案.md
2. 读取当前项目结构
3. 检查 git status
4. 检查当前测试情况
5. 对照文档建立 Gap Analysis
6. 给出本次第一阶段的实施范围
7. 然后开始修改
```

第一阶段必须优先处理 Markdown 中的 **P0 基础架构与稳定性问题**。

禁止直接跳到 P1/P2。

------

# 二十六、每次阶段结束输出统一格式

```text
## Phase Completed

### Implemented
- ...

### Files Changed
- ...

### Database Changes
- ...

### API Changes
- ...

### Tests
- ...

### Verification
- ...

### Remaining
- ...

### Markdown Compliance
- P0: x/y
- P1: x/y
- P2: x/y

### Risks
- ...

### Next Phase
- ...
```

必须真实反映当前状态。

------

# 二十七、绝对禁止的行为

禁止：

+ 跳过 Markdown；
+ 只看 README；
+ 只看单文件；
+ 未测试直接宣布完成；
+ 为了通过测试修改测试使其失去意义；
+ 删除失败测试；
+ 静默降低验收标准；
+ 擅自改变 P0/P1/P2；
+ 擅自重写整个项目；
+ 擅自替换技术栈；
+ 擅自添加第三方服务；
+ 用 LLM 结果代替 deterministic validation；
+ 把“部分实现”描述成“完整实现”；
+ 修改与任务无关的功能；
+ 在无法确认时自行猜测。

------

# 最终执行要求

始终遵守：

> **先读规范 → 检查真实代码 → 建立差距 → 小步实施 → 每步验证 → 持续对照规范 → 最终逐项验收。**

你的目标不是“写出一些代码”。

你的目标是：

> **让当前 DevHunter 代码库最终符合 `DevHunter_全面综合审查与优化实施方案.md` 所定义的目标架构、稳定性、可用性、推荐能力、跨平台事件聚合能力以及低学习成本模板体验。**

完成一个阶段之前，不得自行跳到下一个阶段。

### Git 提交规则

  - commit message 中禁止包含任何 `Co-Authored-By` 署名（包括但不限于 Claude、Anthropic、noreply@anthropic.com 等任何 AI 相关署名）

  - 所有提交仅保留用户本人的 git 作者信息（`用户名 <邮箱>`）

  - 创建 PR 时同样不添加任何 AI 合作者信息

### 仓库管理硬性规则（永远不可违反）

  - **禁止修改公共仓库的可见性**：不得将任何公开（public）仓库切换为私有（private）或内部（internal），即使是为了清除 contributor 缓存、刷新索引或其他任何原因。此操作会导致 star 和 fork 数据永久丢失。

  - **禁止通过 `gh repo edit --visibility` 切换任何仓库的可见性**：除非用户明确要求且已书面确认接受丢失 star/fork 的后果。

  - **禁止通过其他任何手段（API、浏览器设置等）修改仓库可见性**：本规则覆盖所有可能的可见性修改方式。