# Assistant Blueprint — Time Steward

Status: V1 Iteration 1 implemented; browser review recorded in `../mobile-ux-v1-report.md`.

## User goal

Start or resume a useful conversation quickly, understand whether the Agent is working, and safely review any proposed high-risk change.

Implementation: `frontend/src/pages/chat-page.tsx`, `frontend/src/components/chat/chat-empty-state.tsx`, `frontend/src/components/chat/`.

## Information hierarchy

1. Compact header: history/back action, “Time Steward”, contextual conversation title and overflow/new-chat action;
2. conversation messages and structured plan/approval artifacts;
3. run status, tool progress, error/reconnect and cancellation;
4. bottom composer with visible send/stop action;
5. on a new chat only, one short prompt and a horizontally scrolling row of suggestion chips.

## Wireframe

```text
┌──────────────────────────┐
│ ☰  Time Steward       ⋯  │
├──────────────────────────┤
│                          │
│ 今天想先处理哪件事？      │
│ [看今天安排] [整理任务] → │
│                          │
│      conversation        │
│                          │
├──────────────────────────┤
│ 输入时间管理请求…    [↑] │
└──────────────────────────┘
│ 今天   助理   计划   我的 │
└──────────────────────────┘
```

## States

- Empty: compact greeting + optional suggestion chips; composer is the primary action.
- Existing: messages occupy the viewport; avoid repeating intro/context blocks.
- Agent running: concise progress, tool detail collapsed by default, visible stop action.
- Interaction/Approval: render existing typed artifact and HITL state; approval remains explicit and high-risk.
- Error/reconnect: preserve draft text, explain whether send/run started, offer retry/resume when supported.
- Loading history: non-blocking progress in the message area.
- Offline/stale: retain conversation readably; do not claim an unsent message was delivered.

## Keyboard and touch

Composer is anchored above the visual viewport and safe area. Keep the final relevant message visible when keyboard opens, scroll to new streamed messages only when the user was already near the end, and preserve the visible send button. Touch Return inserts a newline; IME composition is not submitted prematurely.

History opens as a focused drawer/screen with close, focus management and Android Back. This blueprint does not change streaming, Agent execution, tools, approval routing or business rules.

Iteration 1 implementation: use the existing `Drawer`; trap and restore focus, make the background inert while open, close on Escape and Capacitor Android Back, and close when the selected conversation changes. Streaming now follows new entries only while the reader remains near the end; otherwise a “回到最新消息” action appears during the run.

## Accessibility and dimensions

Header actions are named and >=44 px, send/stop >=48 px. Message live announcements are restrained. Test empty, existing, running, tool, approval, error/reconnect and keyboard at 360/375/393/412/430 px plus desktop regression. Physical IME and TalkBack remain device-only.
