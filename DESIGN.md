# Design System — DevHunter

## Product Context
- **What this is:** DevHunter 是一个自托管的内容采集与聚合系统，自动抓取 Hacker News、V2EX、GitHub Trending、掘金等平台的高价值信息
- **Who it's for:** 开发者、独立创业者、需要追踪多平台技术动态的人
- **Space/industry:** 开发者工具 / 内容聚合 / 生产力
- **Project type:** Dashboard / Web App
- **Memorable thing:** 信息触手可及的高效感 — 打开就能看到一切，没有障碍

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian — 工业实用主义
- **Decoration level:** Minimal — 排版本身做所有工作，无装饰
- **Mood:** 专业、高效、信息密集但可扫描。像仪表盘一样摊开信息，开发者不需要被装饰打扰
- **Layout approach:** Grid-disciplined — 固定侧边栏 + 主内容区，列表视图紧凑

## Typography
- **Display/Hero:** General Sans — 干净、现代、有态度但不装腔作势
- **Body:** Geist — 专为 UI 设计，小尺寸清晰
- **UI/Labels:** Geist (same as body)
- **Data/Tables:** Geist Mono — tabular-nums 对齐，用于数字和代码
- **Code:** Geist Mono
- **Loading:** Google Fonts CDN (General Sans + Geist + Geist Mono)
- **Scale:**
  - xs: 11px (标签、时间戳)
  - sm: 13px (正文、按钮)
  - base: 14px (默认)
  - lg: 16px (标题)
  - xl: 20px (页面标题)
  - 2xl: 28px (统计数字)

## Color
- **Approach:** Restrained — 单一强调色 + 中性色，颜色只用于语义状态
- **Primary/Accent:** #2563EB — 只用于可交互元素和选中状态
- **Accent hover:** #1D4ED8
- **Accent subtle:** #EFF6FF — 选中项背景
- **Sidebar background:** #0F1117 — 近黑带微蓝，创造控制台质感
- **Sidebar text:** #D1D5DB (未激活) / #FFFFFF (激活)
- **Sidebar hover:** #1F2937 背景
- **Neutrals:**
  - bg-primary: #FAFAFA
  - bg-surface: #FFFFFF
  - bg-subtle: #F5F5F5
  - text-primary: #1A1A1A
  - text-secondary: #6B7280
  - text-muted: #9CA3AF
  - border: #E5E7EB
  - border-strong: #D1D5DB
- **Semantic:**
  - success: #16A34A (成功/运行中)
  - success-subtle: #F0FDF4
  - warning: #D97706 (警告)
  - warning-subtle: #FFFBEB
  - error: #DC2626 (错误)
  - error-subtle: #FEF2F2
- **Dark mode:** 深色侧边栏保持 #0F1117，内容区转为深色表面

## Spacing
- **Base unit:** 8px
- **Density:** Compact — 开发者习惯信息密集界面
- **Scale:**
  - 2xs: 2px
  - xs: 4px
  - sm: 8px
  - md: 16px
  - lg: 24px
  - xl: 32px
  - 2xl: 48px
  - 3xl: 64px

## Layout
- **Approach:** Grid-disciplined — 固定网格，可预测对齐
- **Sidebar width:** 220px (固定)
- **Max content width:** 1200px
- **Border radius:**
  - xs: 4px (标签)
  - sm: 6px (按钮、输入框)
  - md: 8px (卡片)
  - lg: 12px (模态框)

## Motion
- **Approach:** Minimal-functional — 只用于辅助理解的状态过渡
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out)
- **Duration:**
  - micro: 50-100ms (按钮状态)
  - short: 150-250ms (页面切换)
  - medium: 250-400ms (模态框)

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-09-17 | 初始设计系统创建 | 基于"信息触手可及的高效感"，工业实用主义方向 |
| 2026-09-17 | 侧边栏保持高对比度 | 用户要求保持当前项目的明暗对比度视觉感知 |
| 2026-09-17 | 单一强调色策略 | 颜色只用于语义状态，不做装饰 |
| 2026-09-17 | 等宽数字对齐 | 数据对比一目了然 |
