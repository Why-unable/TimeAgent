# TimeAgent Mobile UI

TimeAgent Mobile UI 是 React + Vite + Capacitor Android WebView 的长期设计事实源。目标是让手机用户快速看懂当前行动，用少量直接操作完成执行、调整和收尾，同时保留现有 API、Agent、Planning、HITL 与 Memory 业务边界。

## 当前状态

Mobile UX V1 前两阶段已完成：Mobile Shell / Navigation、Today、Assistant、Plan Hub、手机月历、日历日程抽屉与 Tasks 页面已有独立评审、浏览器截图复核和回归验收。Planning 的交互主流程仍复用现有 `/planning` 和 HITL；Reminders、Approvals、Memory 与其他 Me 深层页面的完整移动端整理留在 Iteration 3。Day Closing 的业务流程没有在本轮改变。

生产审计基线：`main` / `origin/main` / 本机生产 Django 与 frontend 均为 `6b794ab`（2026-10-04）。生产 readiness 返回 HTTP 200，数据库和 Redis 均为 ready。

## 支持的尺寸

- 手机窄宽：320–359 CSS px；
- 目标手机截图和浏览器验收：360、375、393、412、430 CSS px；
- 横屏、平板与桌面继续使用响应式桌面布局，移动样式不得改变业务含义。

## 设计入口

- [Principles](principles.md)
- [Information architecture](information-architecture.md)
- [Design tokens](design-tokens.md)
- [Interaction patterns](interaction-patterns.md)
- [Accessibility](accessibility.md)
- [Android WebView](android-webview.md)
- [Acceptance checklist](acceptance-checklist.md)
- [Component inventory](component-inventory.md)
- [Screen blueprints](blueprints/)
- [Changelog](changelog.md)
- [Mobile UX V1 report](mobile-ux-v1-report.md)
- [Browser screenshot evidence](evidence/)

## 组件规范

组件的目的、使用边界、状态、触控尺寸和无障碍要求记录在 [component inventory](component-inventory.md)。本轮优先沿用现有 Router、Drawer、TodayService、Completion Harvest 和 Chat streaming 组件；只有真实交互缺口才增加新组件。

## Android WebView 特殊要求

每个固定/粘性区域都要处理 safe area。键盘布局以 `visualViewport` 的实际尺寸为准；焦点元素、Composer 和提交动作不得被遮挡。Android Back 应遵守当前 WebView/Router 历史，并优先关闭打开的 sheet/drawer。完整约束与真机未执行时的报告格式见 [Android WebView](android-webview.md)。

## 设计变更流程

核心页面必须先完成 Audit → Blueprint → 独立 Critic → Implementation → Browser screenshot → Repair。**修改重要手机端页面前，应先更新对应 Blueprint 或 Design Decision。**明显 UI 改动还要同步 component inventory 与 changelog；改变全局规则时更新 principles、tokens 或 ADR。报告必须区分自动化浏览器证据与 Android 真机证据。
