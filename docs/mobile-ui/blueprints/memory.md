# Time Memory Blueprint — Iteration 3

Status: Iteration 3 implemented after source audit and independent review.

## Mobile job and hierarchy

The page governs a privacy-sensitive feature. The first screen should answer: what can TimeAgent remember, what can it use, and is there anything awaiting a decision? All memory/proposal times use the account/profile IANA timezone, regardless of the device timezone.

```text
时间行为记忆
画像只提供建议背景，不会直接修改日程。

记忆权限
启用长期时间记忆       [toggle]
允许生成画像           [toggle]
允许注入聊天上下文     [toggle]

待确认偏好 · 1
“偏好内容” · 为什么需要确认
[记住] [忽略]

行为画像与样本          [查看]
常用地点 / 稳定规律     [展开]
清除画像                [单独的危险区]
```

Permissions and pending user decisions come first. Long analysis windows, model-derived behavior statistics and past proposals are progressively disclosed. The page must render the actual proposal value/reason, not machine keys only. Use safe human labels and an explicit fallback for unknown values.

## Privacy and interaction boundaries

- Preference switches call the existing preference hook. Memory proposal accept/ignore calls existing decision hooks. Forget/clear uses existing hooks and user confirmation.
- Memory remains advisory context and must never replace PostgreSQL facts or silently write new memory from this screen.
- A destructive clear action explains that it clears derived profiles/exclusion records but leaves tasks, calendar events and reminders intact. Use a shared confirmation Drawer, not `window.confirm`.
- Dates use the account IANA timezone consistently with the rest of the app.

## States and acceptance

- Loading and query errors have focused status/retry controls; errors do not look like empty profiles.
- No pending preferences and no profile data have distinct text empty states.
- Buttons are at least 44 px, preferably 48 px; each memory permission control has a visible keyboard focus ring and supports Space.
- Verify decision content, confidence/reason labels, unknown-key fallback, account-timezone formatting when the device timezone differs, privacy switches, proposal accept/ignore, undo, forgetting a place/pattern, cancel/confirm clear, and retry after query failure.
- Mobile screenshots at 360/393/430 px; 320 px must not overflow. VoiceOver/TalkBack, native Back and system bars require a device and are `NOT EXECUTED` until then.
