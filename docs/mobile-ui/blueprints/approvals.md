# Approvals Blueprint — Iteration 3

Status: Iteration 3 implemented; preserve existing ActionProposal + HITL lifecycle and approval decisions.

## Mobile review hierarchy

- Default filter is `等待审批`; a compact `筛选` button opens the shared Drawer for all/awaiting/executed/rejected/expired/failed states. Show the active filter in visible text and `aria-pressed` state.
- Keep each proposal as a distinct review surface because it represents an independent high-risk decision. The first view shows action, status, essential target/time, conflict count, and explicit approve/edit/reject actions.
- Long batch previews show the first three items and a disclosure with the exact remaining count; expansion reveals every item. Never hide the fact that additional changes exist.
- Keep “在你确认前，这项操作不会执行” visible for awaiting proposals. Apply remains behind current HITL; do not add direct frontend Apply.
- Edit details remain secondary until the user chooses “调整后批准”; preserve current form validation, conflict checks, version checks and decision status announcements.

## Version and states

- If proposal version/update timestamp changes while the edit form is open, mark the local editor stale, disable save/approve, show the refreshed proposal and require the user to close/reopen editing. Never combine an old local payload with a newly refreshed version token; an E2E test must assert no decision request occurs while stale and that reopening uses the refreshed payload/version.
- Loading, empty, expired, stale, processing, failed, forbidden and list/API error have text states; list errors expose retry.
- Decision result keeps focus on the updated proposal/status; repeated actions announce the item sequence and final state.

## Acceptance

- Filter Drawer has Escape/Android Back, focus restoration and safe-area behavior; actions remain at least 44 px (48 px preferred).
- E2E: 21-item plan expands all items and shows count; conflict and stale states remain reviewable; edit version changes block stale submission; list failure retry works; approve/edit/reject continue through the existing proposal API only.
- Test narrow screens at 320, 360 and 393 px for no page overflow and decision controls reachable without excessive repeated scrolling.
- Physical TalkBack, IME, Android Back and system bars remain `NOT EXECUTED` without an Android device.
