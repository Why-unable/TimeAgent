# Mobile UI Principles

## Focus First

页面先回答“用户现在最应该关注什么？”。只把完成当前任务所需的信息放在首屏；完整数据仍可经列表或展开区域访问。

## One Primary Action

每个可见区域有一个明确主要动作。次要动作使用文字链接、溢出菜单或按需展开，不能和主动作争夺强调色。

## Progressive Disclosure

默认显示当前状态和恢复路径。筛选、高级策略、技术状态、Tool trace 与低频配置按需展开。

## Card Is Not Layout

Card 只标记独立状态、重要选择或明确边界。普通分区使用标题、留白、列表和分隔线；避免卡片嵌卡片。

## Direct Manipulation

完成、排序、选项和明确的时间调整优先由控件直接完成。Drag 只作增强，始终提供 tap、button 或 sheet 替代。

## Agent When Useful

明确且可逆的操作使用 UI；模糊意图用 Agent；偏好取舍让用户选择；高风险写入仍走 ActionProposal + HITL。

## Mobile Is Not Smaller Desktop

移动端可以改变布局、顺序、导航和交互面；业务事实、状态机与 API contract 保持唯一。Today 分桶继续由 `TodayService` 提供。

## Safe and Reversible

计划始终清楚标识 Draft、Applied、Failed、Stale。支持 Review、Retry 或有明确服务端语义的 Undo；不能暗示已应用日程可被本地回滚。

## Calm and Trustworthy

使用 teal/cyan 表达品牌与当前状态，不把每个按钮和分区都染成青色。避免装饰性渐变、重阴影、过度圆角和无目的动画。
