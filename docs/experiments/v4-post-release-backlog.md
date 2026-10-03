# V4 Post-Release UX Backlog

Feature freeze remains active. These are follow-ups, not authorization to add agents, tools, interaction types, or broad redesigns.

## Critic findings and disposition

| Priority | Finding and evidence | User consequence | Disposition |
| --- | --- | --- | --- |
| P1 fixed | Now/Next/Later stayed stale when a time boundary passed; `useTodaySummary` had no interval/focus refresh. | A task could remain in “接下来” after it started. | Fixed: schedule refresh from server-provided bucket boundaries and refresh on focus/reconnect. |
| P1 fixed | Today rendered legacy task lists as well as the execution surface. | Duplicate cards and competing completion controls. | Fixed: removed the legacy desktop/mobile task lists; the server summary remains authoritative. |
| P1 fixed | Day Closing selection/idempotency lived only in component memory. | Reload after an ambiguous response could create a duplicate plan or lose the user's chosen items. | Fixed: tab-scoped storage + authenticated draft fetch; real staging gate verifies retry/reload. |
| P1 fixed | Today task/event Chat links lacked selected entity context; Chat plan preview lacked Planning return link. | User had to re-explain which item/plan they meant. | Fixed: carry entity context and add plan-specific return deep link. |
| P1 fixed | Shared Drawer declared modal but had no keyboard focus handling. | Keyboard users could stay behind an open modal and lose focus on close. | Fixed: focus entry/trap, Escape, focus restoration, automated regression. |
| P1 fixed | Today execution columns left task titles with zero usable width at a 1280px desktop viewport because a nested panel applied a three-column layout too early. | Users could not read or identify the current task. | Fixed: defer three columns to `2xl`; verified in the real Chromium staging journey. |
| P1 fixed | Real backend Daily Loop browser journey was absent. | Component mocks could miss persistence, authentication, or cross-service behavior. | Staging-only browser gate passes 1/1; evidence is in the release validation record. |
| P2 fixed | Day Closing lacked explicit DST boundary coverage. | A midnight range could shift or use the wrong duration on a daylight-saving transition. | Fixed: Los Angeles local midnight regression for 2026-03-08; see release validation. |
| P2 | Timeline edit returns focus to a pointer-only drag handle. Evidence: `interactive-plan-timeline.tsx` focus target after edit. | Keyboard users must Tab away to continue. | Backlog: return to a working keyboard control or add a keyboard drag alternative; cover with actual screen reader. |
| P2 | Conflict candidate/reason is not announced after resolver opens. Evidence: `conflict-resolver.tsx` and timeline rejection flow. | Screen reader user may hear only a generic conflict. | Backlog: focus resolver or provide a concise live announcement. |
| P2 | Recurring approval occurrence changes without a live announcement. Evidence: `approval-card.tsx` occurrence navigation. | New date/conflict state can be missed. | Backlog: announce selected occurrence and conflict summary. |
| P2 | Some controls are 40px high. Evidence: Timeline defer, Today retry/next-feedback controls. | Harder to tap on phones. | Backlog: bring key controls to at least 44px after touch-device review. |
| P2 | Morning Brief Today error copy offers trying again but does not expose an inline retry action. | Recovery requires an indirect navigation/reload. | Backlog: add a local retry affordance if a real user hits this case. |
| P2 validation | No physical NVDA/VoiceOver/TalkBack or Android WebView session was available. | Automated semantics cannot confirm announcements, keyboard resizing, or drag-vs-scroll. | Validate with physical equipment before making an accessibility/mobile conformance claim. |

## Interaction selection hypothesis

Use Chat for one explicit change or explanation; use PriorityRanker for ordering several items; Timeline for direct time placement; ConflictResolver for a blocked time choice; Approval for high-risk writes; Harvest for completion feedback; Day Closing for explicit carry-over selection. This is an **untested hypothesis**, not a measured winner. Run the matched study in `v4-chat-vs-interaction-evaluation.md` before changing selection policy.

## Journey friction still to observe

- [ ] Planning → Chat → same Plan navigation with a real user; verify the plan ID remains obvious on both pages.
- [ ] Today → Chat for an active task and event; confirm the prefilled context is sufficient and not intrusive.
- [ ] Day Closing → Planning and browser Back; confirm the draft remains discoverable.
- [ ] Test the Day Closing `sessionStorage` recovery path in an Android WebView that permits session storage.
- [ ] Observe whether removal of the legacy Today lists makes deadline-only, unscheduled tasks harder to find; only restore a separate view if users need it, without duplicate completion actions.
